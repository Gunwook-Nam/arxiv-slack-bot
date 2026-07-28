import os
import re
import json
import time
import html
import logging
import datetime as dt
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import requests
import gspread
from openai import OpenAI
from oauth2client.service_account import ServiceAccountCredentials


THEME_COLORS = {
    "MLIP / Atomistic ML": "#2F80ED",
    "Molecular generation": "#9B51E0",
    "Materials discovery": "#27AE60",
    "Battery / Electrolyte": "#F2994A",
    "Computational chemistry": "#EB5757",
    "Scientific agents": "#56CCF2",
}

DEFAULT_THEME_COLOR = "#808080"


def get_theme_color(themes: tuple[str, ...]) -> str:
    if not themes:
        return DEFAULT_THEME_COLOR

    # use first theme color when it has mutliple themes
    return THEME_COLORS.get(
        themes[0],
        DEFAULT_THEME_COLOR,
    )
    
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


@dataclass(frozen=True)
class Config:
    oai_url: str = "https://oaipmh.arxiv.org/oai"
    lookback_days: int = 14
    request_interval: float = 3.1
    sent_file: str = "sent_papers.jsonl"
    timezone: str = "Asia/Seoul"

    oai_sets: tuple[str, ...] = (
        "physics:cond-mat:mtrl-sci",
        "physics:physics:comp-ph",
        "physics:physics:chem-ph",
        "cs:cs:LG",
        "cs:cs:AI",
        "stat:stat:ML",
    )

    themes: dict[str, tuple[tuple[str, ...], ...]] = None

    def __post_init__(self):
        if self.themes is None:
            object.__setattr__(
                self,
                "themes",
                {
                    "MLIP / Atomistic ML": (
                        ("interatomic potential",),
                        ("machine learned potential",),
                        ("machine learning potential",),
                        ("neural network potential",),
                        ("neural force field",),
                        ("atomistic foundation model",),
                        ("universal potential",),
                        ("equivariant", "atomistic"),
                    ),
                    "Molecular generation": (
                        ("molecular generation",),
                        ("molecule generation",),
                        ("inverse molecular design",),
                        ("molecular language model",),
                        ("chemical language model",),
                        ("molecule editing",),
                        ("molecular representation",),
                    ),
                    "Materials discovery": (
                        ("materials discovery",),
                        ("inverse materials design",),
                        ("materials informatics",),
                        ("crystal generation",),
                        ("crystal structure prediction",),
                        ("active learning", "materials"),
                        ("bayesian optimization", "materials"),
                    ),
                    "Battery / Electrolyte": (
                        ("electrolyte design",),
                        ("electrolyte", "machine learning"),
                        ("battery", "machine learning"),
                        ("solvation structure", "electrolyte"),
                        ("ionic conductivity", "electrolyte"),
                        ("electrolyte formulation",),
                    ),
                    "Computational chemistry": (
                        ("quantum chemistry", "machine learning"),
                        ("computational chemistry", "machine learning"),
                        ("density functional theory", "machine learning"),
                        ("excited state", "machine learning"),
                        ("photocatalyst", "machine learning"),
                        ("reaction prediction",),
                    ),
                    "Scientific agents": (
                        ("scientific agent",),
                        ("ai scientist",),
                        ("chemistry agent",),
                        ("materials agent",),
                        ("autonomous laboratory",),
                        ("self driving laboratory",),
                        ("large language model", "chemistry"),
                        ("large language model", "materials"),
                    ),
                },
            )


@dataclass(frozen=True)
class Paper:
    arxiv_id: str
    title: str
    authors: tuple[str, ...]
    abstract: str
    categories: tuple[str, ...]
    created: dt.date
    updated: dt.date
    themes: tuple[str, ...]

    @property
    def abstract_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"

    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.arxiv_id}"


OAI_NS = "http://www.openarchives.org/OAI/2.0/"
ARXIV_NS = "http://arxiv.org/OAI/arXiv/"
SEOUL_TZ = ZoneInfo("Asia/Seoul")
SHEET_HEADERS = ["날짜", "arXiv ID", "제목", "저자", "Theme", "한글 요약", "PDF 링크"]


def clean_text(text: str | None) -> str:
    return " ".join(html.unescape(text or "").split())


def normalize_text(text: str) -> str:
    text = html.unescape(text).lower()
    text = re.sub(r"[\u2010-\u2015\-_/]", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def classify_themes(title: str, abstract: str, config: Config) -> tuple[str, ...]:
    text = normalize_text(f"{title} {abstract}")
    matched = []

    for theme, groups in config.themes.items():
        if any(all(normalize_text(term) in text for term in group) for group in groups):
            matched.append(theme)

    return tuple(matched)

def sort_papers_by_theme(
    papers: list[Paper],
    config: Config,
) -> list[Paper]:
    theme_order = {
        theme: index
        for index, theme in enumerate(config.themes)
    }

    return sorted(
        papers,
        key=lambda paper: (
            theme_order.get(
                paper.themes[0],
                len(theme_order),
            ),
            -paper.created.toordinal(),
            paper.title.lower(),
        ),
    )
def request_oai(
    session: requests.Session,
    config: Config,
    params: dict[str, str],
) -> ET.Element:
    logging.info("OAI 요청: %s", params)

    response = session.get(
        config.oai_url,
        params=params,
        timeout=90,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)

    error = root.find(f"{{{OAI_NS}}}error")
    if error is not None:
        code = error.get("code", "unknown")
        message = clean_text(error.text)

        if code == "noRecordsMatch":
            return root

        raise RuntimeError(f"OAI-PMH error [{code}]: {message}")

    return root


def parse_record(record: ET.Element, config: Config) -> Paper | None:
    header = record.find(f"{{{OAI_NS}}}header")
    metadata = record.find(f"{{{OAI_NS}}}metadata")

    if header is None or metadata is None or header.get("status") == "deleted":
        return None

    article = metadata.find(f"{{{ARXIV_NS}}}arXiv")
    if article is None:
        return None

    arxiv_id = clean_text(article.findtext(f"{{{ARXIV_NS}}}id"))
    title = clean_text(article.findtext(f"{{{ARXIV_NS}}}title"))
    abstract = clean_text(article.findtext(f"{{{ARXIV_NS}}}abstract"))
    created_text = clean_text(article.findtext(f"{{{ARXIV_NS}}}created"))
    updated_text = clean_text(article.findtext(f"{{{ARXIV_NS}}}updated")) or created_text
    categories = tuple(clean_text(article.findtext(f"{{{ARXIV_NS}}}categories")).split())

    authors = []
    authors_element = article.find(f"{{{ARXIV_NS}}}authors")
    if authors_element is not None:
        for author in authors_element.findall(f"{{{ARXIV_NS}}}author"):
            forenames = clean_text(author.findtext(f"{{{ARXIV_NS}}}forenames"))
            keyname = clean_text(author.findtext(f"{{{ARXIV_NS}}}keyname"))
            name = " ".join(part for part in (forenames, keyname) if part)
            if name:
                authors.append(name)

    if not all((arxiv_id, title, abstract, created_text)):
        return None

    created = dt.date.fromisoformat(created_text)
    updated = dt.date.fromisoformat(updated_text)
    themes = classify_themes(title, abstract, config)

    if not themes:
        return None

    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=tuple(authors),
        abstract=abstract,
        categories=categories,
        created=created,
        updated=updated,
        themes=themes,
    )


def harvest_set(
    session: requests.Session,
    config: Config,
    set_spec: str,
    from_date: dt.date,
) -> list[Paper]:
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "arXiv",
        "set": set_spec,
        "from": from_date.isoformat(),
    }

    papers = []

    while True:
        root = request_oai(session, config, params)

        for record in root.findall(f".//{{{OAI_NS}}}record"):
            paper = parse_record(record, config)
            if paper is not None and paper.created >= from_date:
                papers.append(paper)

        token_element = root.find(f".//{{{OAI_NS}}}resumptionToken")
        token = clean_text(token_element.text) if token_element is not None else ""

        if not token:
            break

        time.sleep(config.request_interval)
        params = {
            "verb": "ListRecords",
            "resumptionToken": token,
        }

    return papers


def harvest_papers(config: Config) -> list[Paper]:
    today = dt.datetime.now(SEOUL_TZ).date()
    from_date = today - dt.timedelta(days=config.lookback_days)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "arxiv-slack-bot/3.0 "
                f"(contact: {os.getenv('ARXIV_CONTACT_EMAIL', 'not-provided')})"
            )
        }
    )

    papers_by_id: dict[str, Paper] = {}

    for index, set_spec in enumerate(config.oai_sets):
        if index > 0:
            time.sleep(config.request_interval)

        try:
            papers = harvest_set(session, config, set_spec, from_date)
            logging.info("%s: 관련 논문 %d건", set_spec, len(papers))
        except Exception as error:
            logging.error("%s 수집 실패: %s", set_spec, error)
            continue

        for paper in papers:
            previous = papers_by_id.get(paper.arxiv_id)
            if previous is None or paper.updated > previous.updated:
                papers_by_id[paper.arxiv_id] = paper

    return sorted(
        papers_by_id.values(),
        key=lambda paper: (paper.created, paper.updated, paper.arxiv_id),
        reverse=True,
    )


def load_sent_ids(file_path: str) -> set[str]:
    if not os.path.exists(file_path):
        return set()

    sent_ids = set()

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            try:
                record = json.loads(line)
                if record.get("arxiv_id"):
                    sent_ids.add(record["arxiv_id"])
            except json.JSONDecodeError:
                logging.warning("잘못된 JSONL 행을 건너뜁니다.")

    return sent_ids


def append_jsonl(record: dict, file_path: str) -> None:
    with open(file_path, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def open_google_sheet():
    sheet_key = os.getenv("GOOGLE_SHEETS_KEY")
    credentials_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not sheet_key or not credentials_raw:
        logging.warning("Google Sheets 설정이 없어 JSONL만 사용합니다.")
        return None

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    if credentials_raw.lstrip().startswith("{"):
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            json.loads(credentials_raw),
            scope,
        )
    else:
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            credentials_raw,
            scope,
        )

    sheet = gspread.authorize(credentials).open_by_key(sheet_key).sheet1

    if not sheet.row_values(1):
        sheet.append_row(SHEET_HEADERS, value_input_option="RAW")

    return sheet


def load_sheet_ids(sheet) -> set[str]:
    if sheet is None:
        return set()

    return {value.strip() for value in sheet.col_values(2)[1:] if value.strip()}


def append_sheet(sheet, record: dict) -> None:
    if sheet is None:
        return

    sheet.append_row(
        [
            record["sent_date"],
            record["arxiv_id"],
            record["title"],
            ", ".join(record["authors"]),
            ", ".join(record["themes"]),
            record["summary_ko"],
            record["pdf_url"],
        ],
        value_input_option="RAW",
    )


def summarize_paper(client: OpenAI | None, paper: Paper) -> str:
    if client is None:
        return "OpenAI 요약 기능이 설정되지 않았습니다."

    prompt = f"""
다음 논문의 제목과 초록을 한국어로 정확히 3개의 bullet point로 요약하세요.

제목:
{paper.title}

초록:
{paper.abstract}

규칙:
- 각 줄은 '• '로 시작합니다.
- 주요 technical term은 English로 유지합니다.
- 논문이 해결하는 문제, 방법, 핵심 결과를 각각 포함합니다.
- 제목이나 추가 설명은 출력하지 않습니다.
""".strip()

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": "You summarize scientific papers accurately and concisely.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as error:
        logging.error("OpenAI 요약 실패 [%s]: %s", paper.arxiv_id, error)
        return "요약 생성 중 오류가 발생했습니다."


def format_authors(authors: tuple[str, ...], limit: int = 3) -> str:
    if not authors:
        return "정보 없음"

    text = ", ".join(authors[:limit])

    if len(authors) > limit:
        text += " 등"

    return text

def build_slack_payload(paper: Paper, summary: str) -> dict:
    theme_text = ", ".join(paper.themes)
    primary_theme = paper.themes[0] if paper.themes else ""
    color = THEME_COLORS.get(primary_theme, DEFAULT_THEME_COLOR)
    authors = format_authors(paper.authors)

    metadata = "\n".join(
        [
            f"<{paper.abstract_url}|{paper.title}>",
            f"*저자:* {authors}",
            f"*Submitted:* {paper.created.isoformat()}",
        ]
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": theme_text},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": metadata}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*한글 요약*\n{summary}"},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "PDF"},
                    "url": paper.pdf_url,
                }
            ],
        },
    ]

    return {
        "attachments": [{"color": color, "blocks": blocks}],
        "unfurl_links": False,
        "unfurl_media": False,
    }


def send_slack(
    webhook_url: str,
    paper: Paper,
    summary: str,
) -> bool:
    if not webhook_url:
        logging.error("SLACK_WEBHOOK_URL이 설정되지 않았습니다.")
        return False

    try:
        response = requests.post(
            webhook_url,
            json=build_slack_payload(paper, summary),
            timeout=20,
        )
        response.raise_for_status()
        return True

    except requests.RequestException as error:
        logging.error(
            "Slack 전송 실패 [%s]: %s",
            paper.arxiv_id,
            error,
        )
        return False


def main() -> None:
    config = Config()
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    
    sheet = open_google_sheet()
    sent_ids = load_sent_ids(config.sent_file) | load_sheet_ids(sheet)

    logging.info("실행 모드: %s", "TEST" if test_mode else "NORMAL")
    logging.info("이미 전송된 논문 수: %d", len(sent_ids))

    papers = harvest_papers(config)
    papers = sort_papers_by_theme(papers, config)

    if test_mode:
        new_papers = papers[:1]
    else:
        new_papers = [paper for paper in papers if paper.arxiv_id not in sent_ids]
        
    logging.info("최근 %d일 관련 논문 수: %d", config.lookback_days, len(papers))
    logging.info("신규 전송 대상 수: %d", len(new_papers))

    if not new_papers:
        logging.info("전송할 신규 논문이 없습니다.")
        return

    openai_client = None
    if os.getenv("OPENAI_API_KEY"):
        openai_client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=60,
            max_retries=2,
        )

    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    sent_date = dt.datetime.now(SEOUL_TZ).date().isoformat()

    current_theme = None
    for paper in new_papers:
        primary_theme = (paper.themes[0] if paper.themes else "Unclassified")

        if primary_theme != current_theme:
            current_theme = primary_theme
            logging.info("===== Theme: %s =====", current_theme)
            
        logging.info("처리 중: %s (%s)", paper.title, paper.arxiv_id)

        summary = summarize_paper(openai_client, paper)

        if not send_slack(webhook_url, paper, summary):
            continue

        if test_mode:
            logging.info("TEST_MODE: 전송 기록을 저장하지 않는다 [%s]", paper.arxiv_id)
            continue
            
        record = {
            "sent_date": sent_date,
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": list(paper.authors),
            "themes": list(paper.themes),
            "summary_ko": summary,
            "abstract_url": paper.abstract_url,
            "pdf_url": paper.pdf_url,
            "categories": list(paper.categories),
            "created": paper.created.isoformat(),
            "updated": paper.updated.isoformat(),
        }

        try:
            append_sheet(sheet, record)
        except Exception as error:
            logging.error("Google Sheet 기록 실패 [%s]: %s", paper.arxiv_id, error)

        append_jsonl(record, config.sent_file)
        sent_ids.add(paper.arxiv_id)

    logging.info("실행 완료")


if __name__ == "__main__":
    main()
