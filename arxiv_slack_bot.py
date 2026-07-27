import os
import re
import json
import html
import time
import logging
import datetime
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests
import gspread
from openai import OpenAI
from oauth2client.service_account import ServiceAccountCredentials


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

SENT_PAPERS_FILE = "sent_papers.jsonl"
SEOUL_TZ = ZoneInfo("Asia/Seoul")

RSS_BASE_URL = "https://rss.arxiv.org/rss"

DEFAULT_RSS_CATEGORIES = (
    "cond-mat.mtrl-sci",
    "physics.comp-ph",
    "physics.chem-ph",
    "cs.LG",
)

# Tuple 내부의 표현이 모두 존재하면 관련 논문으로 판단한다.
# Hyphen과 punctuation은 normalize_for_match()에서 공백으로 바뀐다.
KEYWORD_GROUPS = (
    ("machine learning", "interatomic potential"),
    ("machine learned", "interatomic potential"),
    ("machine learning potential",),
    ("machine learned potential",),
    ("neural network potential",),
    ("mlip",),
)

RSS_MIN_INTERVAL_SECONDS = 3.1
RSS_RETRY_DELAYS = (10, 30)
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}

SHEET_HEADERS = [
    "날짜",
    "arXiv ID",
    "제목",
    "저자",
    "한글 요약",
    "PDF 링크",
]

ARXIV_NS = "http://arxiv.org/schemas/atom"
DC_NS = "http://purl.org/dc/elements/1.1/"


@dataclass(frozen=True)
class RSSPaper:
    arxiv_id: str
    versioned_id: str
    title: str
    authors: list[str]
    abstract: str
    entry_url: str
    pdf_url: str
    announce_type: str
    categories: list[str]
    published_at: datetime.datetime


class ArxivRSSClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.last_request_time = 0.0

        user_agent = "arxiv-slack-bot/2.0"
        contact_email = os.environ.get(
            "ARXIV_CONTACT_EMAIL",
            "",
        ).strip()

        if contact_email:
            user_agent += f" (contact: {contact_email})"

        self.session.headers.update(
            {"User-Agent": user_agent}
        )

    def _wait_for_rate_limit(self) -> None:
        elapsed = (
            time.monotonic()
            - self.last_request_time
        )
        remaining = (
            RSS_MIN_INTERVAL_SECONDS
            - elapsed
        )

        if remaining > 0:
            logging.info(
                "RSS 요청 간격 준수를 위해 %.1f초 대기",
                remaining,
            )
            time.sleep(remaining)

    def get(self, url: str) -> requests.Response:
        total_attempts = (
            len(RSS_RETRY_DELAYS) + 1
        )

        for attempt in range(total_attempts):
            self._wait_for_rate_limit()

            logging.info(
                "RSS 요청: %s (%d/%d)",
                url,
                attempt + 1,
                total_attempts,
            )

            self.last_request_time = (
                time.monotonic()
            )

            try:
                response = self.session.get(
                    url,
                    timeout=60,
                )

            except requests.RequestException as error:
                if attempt == total_attempts - 1:
                    raise

                delay = RSS_RETRY_DELAYS[attempt]

                logging.warning(
                    "RSS 연결 오류: %s. "
                    "%d초 후 재시도합니다.",
                    error,
                    delay,
                )
                time.sleep(delay)
                continue

            if (
                response.status_code
                not in RETRYABLE_HTTP_STATUS
            ):
                response.raise_for_status()
                return response

            if attempt == total_attempts - 1:
                response.raise_for_status()

            delay = RSS_RETRY_DELAYS[attempt]

            logging.warning(
                "RSS HTTP %d. "
                "%d초 후 재시도합니다.",
                response.status_code,
                delay,
            )
            time.sleep(delay)

        raise RuntimeError(
            "RSS 요청이 예기치 않게 종료되었습니다."
        )


# ---------------------------------------------------------------------
# Text 처리
# ---------------------------------------------------------------------


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )
    return " ".join(text.split())


def normalize_for_match(text: str) -> str:
    text = html.unescape(
        text or ""
    ).lower()

    text = re.sub(
        r"[\u2010-\u2015\-_/]",
        " ",
        text,
    )
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return " ".join(text.split())


def is_relevant_paper(
    title: str,
    abstract: str,
) -> bool:
    searchable_text = normalize_for_match(
        f"{title} {abstract}"
    )

    return any(
        all(
            term in searchable_text
            for term in group
        )
        for group in KEYWORD_GROUPS
    )


def base_arxiv_id(
    versioned_id: str,
) -> str:
    return re.sub(
        r"v\d+$",
        "",
        versioned_id.strip(),
    )


def parse_rss_description(
    description: str,
) -> tuple[str, str, str]:
    text = clean_text(description)

    match = re.search(
        r"arXiv:(?P<arxiv_id>\S+)\s+"
        r"Announce Type:\s*"
        r"(?P<announce_type>\S+)\s+"
        r"Abstract:\s*"
        r"(?P<abstract>.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        raise ValueError(
            "RSS description 형식을 "
            "해석할 수 없습니다."
        )

    return (
        match.group("arxiv_id"),
        match.group("announce_type"),
        match.group("abstract").strip(),
    )


def parse_pub_date(
    value: str,
) -> datetime.datetime:
    if not value:
        return datetime.datetime.min.replace(
            tzinfo=datetime.timezone.utc
        )

    try:
        parsed = parsedate_to_datetime(
            value
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=datetime.timezone.utc
            )

        return parsed

    except (TypeError, ValueError):
        return datetime.datetime.min.replace(
            tzinfo=datetime.timezone.utc
        )


# ---------------------------------------------------------------------
# arXiv RSS
# ---------------------------------------------------------------------


def parse_rss_feed(
    xml_content: bytes,
) -> list[RSSPaper]:
    root = ET.fromstring(xml_content)
    papers: list[RSSPaper] = []

    for item in root.findall(
        "./channel/item"
    ):
        title = clean_text(
            item.findtext(
                "title",
                default="",
            )
        )
        entry_url = clean_text(
            item.findtext(
                "link",
                default="",
            )
        )
        description = item.findtext(
            "description",
            default="",
        )
        creator = clean_text(
            item.findtext(
                f"{{{DC_NS}}}creator",
                default="",
            )
        )
        announce_element = clean_text(
            item.findtext(
                f"{{{ARXIV_NS}}}announce_type",
                default="",
            )
        )
        guid = clean_text(
            item.findtext(
                "guid",
                default="",
            )
        )

        categories = [
            clean_text(
                category.text or ""
            )
            for category in item.findall(
                "category"
            )
            if clean_text(
                category.text or ""
            )
        ]

        published_at = parse_pub_date(
            item.findtext(
                "pubDate",
                default="",
            )
        )

        try:
            (
                description_id,
                description_announce,
                abstract,
            ) = parse_rss_description(
                description
            )

        except ValueError as error:
            logging.warning(
                "RSS item parsing 실패: "
                "%s (%s)",
                title,
                error,
            )
            continue

        guid_id = ""

        if guid.startswith(
            "oai:arXiv.org:"
        ):
            guid_id = guid.removeprefix(
                "oai:arXiv.org:"
            )

        versioned_id = (
            guid_id
            or description_id
        )
        arxiv_id = base_arxiv_id(
            versioned_id
        )
        announce_type = (
            announce_element
            or description_announce
        )

        if (
            not arxiv_id
            or not title
            or not abstract
        ):
            logging.warning(
                "필수 metadata가 없는 "
                "RSS item을 건너뜁니다: %s",
                title,
            )
            continue

        authors = [
            author.strip()
            for author in creator.split(",")
            if author.strip()
        ]

        if not entry_url:
            entry_url = (
                "https://arxiv.org/abs/"
                f"{arxiv_id}"
            )

        papers.append(
            RSSPaper(
                arxiv_id=arxiv_id,
                versioned_id=versioned_id,
                title=title,
                authors=authors,
                abstract=abstract,
                entry_url=entry_url,
                pdf_url=(
                    "https://arxiv.org/pdf/"
                    f"{arxiv_id}"
                ),
                announce_type=announce_type,
                categories=categories,
                published_at=published_at,
            )
        )

    return papers


def get_rss_categories() -> list[str]:
    raw = os.environ.get(
        "ARXIV_RSS_CATEGORIES",
        "",
    ).strip()

    if not raw:
        return list(
            DEFAULT_RSS_CATEGORIES
        )

    categories = [
        category.strip()
        for category in raw.split(",")
    ]

    return [
        category
        for category in categories
        if category
    ]


def fetch_rss_papers(
    categories: list[str],
) -> tuple[list[RSSPaper], list[str]]:
    rss_client = ArxivRSSClient()

    papers_by_id: dict[
        str,
        RSSPaper,
    ] = {}

    failed_categories: list[str] = []

    for category in categories:
        url = (
            f"{RSS_BASE_URL}/"
            f"{category}"
        )

        try:
            response = rss_client.get(
                url
            )
            category_papers = (
                parse_rss_feed(
                    response.content
                )
            )

            logging.info(
                "%s RSS에서 %d건을 "
                "읽었습니다.",
                category,
                len(category_papers),
            )

        except (
            requests.RequestException,
            ET.ParseError,
        ) as error:
            logging.error(
                "%s RSS 처리 실패: %s",
                category,
                error,
            )
            failed_categories.append(
                category
            )
            continue

        for paper in category_papers:
            existing = papers_by_id.get(
                paper.arxiv_id
            )

            # 여러 category에 중복된 경우
            # 더 최신 announcement를 유지한다.
            if (
                existing is None
                or paper.published_at
                > existing.published_at
            ):
                papers_by_id[
                    paper.arxiv_id
                ] = paper

    papers = sorted(
        papers_by_id.values(),
        key=lambda paper: (
            paper.published_at
        ),
        reverse=True,
    )

    return papers, failed_categories


# ---------------------------------------------------------------------
# JSONL 전송 기록
# ---------------------------------------------------------------------


def load_sent_paper_ids(
    file_path: str = SENT_PAPERS_FILE,
) -> set[str]:
    sent_ids: set[str] = set()

    if not os.path.exists(file_path):
        return sent_ids

    try:
        with open(
            file_path,
            "r",
            encoding="utf-8",
        ) as file:
            for line in file:
                line = line.strip()

                if not line:
                    continue

                try:
                    data = json.loads(
                        line
                    )

                except json.JSONDecodeError:
                    logging.warning(
                        "잘못된 JSONL 행을 "
                        "건너뜁니다: %s",
                        line[:100],
                    )
                    continue

                arxiv_id = data.get(
                    "arxiv_id"
                )

                if arxiv_id:
                    sent_ids.add(
                        base_arxiv_id(
                            str(arxiv_id)
                        )
                    )

    except OSError as error:
        logging.error(
            "전송 기록 읽기 실패: %s",
            error,
        )

    return sent_ids


def append_sent_paper(
    paper_data: dict,
    file_path: str = SENT_PAPERS_FILE,
) -> bool:
    try:
        with open(
            file_path,
            "a",
            encoding="utf-8",
        ) as file:
            file.write(
                json.dumps(
                    paper_data,
                    ensure_ascii=False,
                )
                + "\n"
            )

        return True

    except OSError as error:
        logging.error(
            "전송 기록 저장 실패: %s",
            error,
        )
        return False


# ---------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------


def open_google_sheet():
    sheet_key = os.environ.get(
        "GOOGLE_SHEETS_KEY"
    )
    creds_raw = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_JSON"
    )

    if not sheet_key or not creds_raw:
        logging.warning(
            "Google Sheets 설정이 없습니다. "
            "JSONL만 중복 확인에 사용합니다."
        )
        return None

    try:
        scope = [
            (
                "https://spreadsheets."
                "google.com/feeds"
            ),
            (
                "https://www.googleapis.com/"
                "auth/drive"
            ),
        ]

        if creds_raw.lstrip().startswith(
            "{"
        ):
            credentials = (
                ServiceAccountCredentials
                .from_json_keyfile_dict(
                    json.loads(creds_raw),
                    scope,
                )
            )
        else:
            credentials = (
                ServiceAccountCredentials
                .from_json_keyfile_name(
                    creds_raw,
                    scope,
                )
            )

        client = gspread.authorize(
            credentials
        )
        sheet = (
            client
            .open_by_key(sheet_key)
            .sheet1
        )

        if not sheet.row_values(1):
            sheet.append_row(
                SHEET_HEADERS,
                value_input_option="RAW",
            )

        return sheet

    except Exception as error:
        logging.error(
            "Google Sheet 연결 실패: %s",
            error,
        )
        return None


def load_sent_paper_ids_from_sheet(
    sheet,
) -> set[str]:
    if sheet is None:
        return set()

    try:
        values = sheet.col_values(2)

        return {
            base_arxiv_id(
                value.strip()
            )
            for value in values[1:]
            if value.strip()
        }

    except Exception as error:
        logging.error(
            "Google Sheet 전송 기록 "
            "읽기 실패: %s",
            error,
        )
        return set()


def append_to_google_sheet(
    paper_record: dict,
    sheet,
) -> bool:
    if sheet is None:
        return False

    row = [
        paper_record.get(
            "sent_date",
            "",
        ),
        paper_record.get(
            "arxiv_id",
            "",
        ),
        paper_record.get(
            "title",
            "",
        ),
        ", ".join(
            paper_record.get(
                "authors",
                [],
            )
        ),
        paper_record.get(
            "summary_ko",
            "",
        ),
        paper_record.get(
            "pdf_url",
            "",
        ),
    ]

    try:
        sheet.append_row(
            row,
            value_input_option="RAW",
        )
        return True

    except Exception as error:
        logging.error(
            "Google Sheet 기록 실패: %s",
            error,
        )
        return False


# ---------------------------------------------------------------------
# OpenAI 요약
# ---------------------------------------------------------------------


def create_openai_client():
    api_key = os.environ.get(
        "OPENAI_API_KEY"
    )

    if not api_key:
        logging.warning(
            "OPENAI_API_KEY가 "
            "설정되지 않았습니다."
        )
        return None

    return OpenAI(
        api_key=api_key,
        timeout=60.0,
        max_retries=2,
    )


def summarize_abstract_ko(
    client,
    title: str,
    abstract: str,
) -> str:
    if client is None:
        return (
            "요약 기능 미설정 "
            "(OPENAI_API_KEY 필요)"
        )

    prompt = f"""
다음 학술 논문의 제목과 초록을 한국어로 요약하세요.

[논문 제목]
{title}

[초록]
{abstract}

[작성 규칙]
1. 주요 학술 및 전문 용어는 번역하지 말고 영문으로 유지합니다.
2. 정확히 3개의 핵심 포인트로 요약합니다.
3. 각 줄은 '• '로 시작합니다.
4. 서론, 인사말, 제목, 추가 설명은 출력하지 않습니다.
""".strip()

    try:
        response = (
            client.chat.completions.create(
                model=os.environ.get(
                    "OPENAI_MODEL",
                    "gpt-4o-mini",
                ),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You summarize academic "
                            "abstracts into concise "
                            "Korean bullet points while "
                            "preserving technical terms "
                            "in English."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.3,
            )
        )

        content = (
            response
            .choices[0]
            .message
            .content
        )

        if not content:
            return (
                "요약 결과가 "
                "비어 있습니다."
            )

        return content.strip()

    except Exception as error:
        logging.error(
            "OpenAI API 호출 실패: %s",
            error,
        )
        return "요약 생성 중 오류 발생"


# ---------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------


def escape_slack_text(
    text: str,
) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def post_to_slack(
    webhook_url: str,
    payload: dict,
) -> bool:
    if not webhook_url:
        logging.error(
            "SLACK_WEBHOOK_URL이 "
            "설정되지 않았습니다."
        )
        return False

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        return True

    except requests.RequestException as error:
        logging.error(
            "Slack 전송 실패: %s",
            error,
        )
        return False


def send_to_slack(
    webhook_url: str,
    paper: RSSPaper,
    summary_ko: str,
) -> bool:
    authors_str = ", ".join(
        paper.authors[:3]
    )

    if len(paper.authors) > 3:
        authors_str += " 등"

    if not authors_str:
        authors_str = "저자 정보 없음"

    safe_title = (
        escape_slack_text(
            paper.title
        )
        .replace("|", "¦")
    )
    safe_authors = escape_slack_text(
        authors_str
    )
    safe_summary = escape_slack_text(
        summary_ko
    )
    safe_categories = escape_slack_text(
        ", ".join(
            paper.categories
        )
    )
    safe_announce_type = (
        escape_slack_text(
            paper.announce_type
            or "unknown"
        )
    )

    metadata_lines = [
        f"*저자:* {safe_authors}"
    ]

    if safe_categories:
        metadata_lines.append(
            f"*Category:* {safe_categories}"
        )

    metadata_lines.append(
        "*Announce type:* "
        f"{safe_announce_type}"
    )

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": (
                        "arXiv 신규 논문 알림 "
                        f"[{paper.arxiv_id}]"
                    ),
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{paper.entry_url}|"
                        f"{safe_title}>*\n"
                        + "\n".join(
                            metadata_lines
                        )
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*한글 요약*\n"
                        f"{safe_summary}"
                    ),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "PDF 열기",
                            "emoji": True,
                        },
                        "url": paper.pdf_url,
                    }
                ],
            },
            {
                "type": "divider",
            },
        ]
    }

    return post_to_slack(
        webhook_url,
        payload,
    )


def send_status_to_slack(
    webhook_url: str,
    message: str,
) -> bool:
    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "⚠️ *arXiv RSS bot "
                        "상태 알림*\n"
                        f"{escape_slack_text(message)}"
                    ),
                },
            }
        ]
    }

    return post_to_slack(
        webhook_url,
        payload,
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


def main() -> None:
    webhook_url = os.environ.get(
        "SLACK_WEBHOOK_URL",
        "",
    )
    categories = get_rss_categories()

    if not categories:
        logging.error(
            "RSS category가 설정되지 않았습니다."
        )
        raise SystemExit(1)

    logging.info(
        "RSS categories: %s",
        ", ".join(categories),
    )
    logging.info(
        "keyword groups: %s",
        "; ".join(
            " + ".join(group)
            for group in KEYWORD_GROUPS
        ),
    )

    sheet = open_google_sheet()

    sent_ids = load_sent_paper_ids()
    sent_ids.update(
        load_sent_paper_ids_from_sheet(
            sheet
        )
    )

    logging.info(
        "이미 전송된 논문 수: %d",
        len(sent_ids),
    )

    papers, failed_categories = (
        fetch_rss_papers(categories)
    )

    if (
        len(failed_categories)
        == len(categories)
    ):
        message = (
            "모든 arXiv RSS category "
            "요청에 실패했습니다: "
            + ", ".join(
                failed_categories
            )
        )

        logging.error(message)

        send_status_to_slack(
            webhook_url,
            message,
        )

        raise SystemExit(1)

    if failed_categories:
        warning = (
            "일부 RSS category 요청에 "
            "실패했습니다: "
            + ", ".join(
                failed_categories
            )
        )

        logging.warning(warning)

        send_status_to_slack(
            webhook_url,
            warning,
        )

    relevant_papers = [
        paper
        for paper in papers
        if is_relevant_paper(
            paper.title,
            paper.abstract,
        )
    ]

    new_papers = [
        paper
        for paper in relevant_papers
        if paper.arxiv_id
        not in sent_ids
    ]

    max_papers_raw = os.environ.get(
        "MAX_PAPERS_PER_RUN",
        "0",
    ).strip()

    try:
        max_papers = int(
            max_papers_raw
        )

    except ValueError:
        logging.warning(
            "MAX_PAPERS_PER_RUN이 "
            "정수가 아닙니다. "
            "제한 없이 처리합니다."
        )
        max_papers = 0

    if max_papers > 0:
        new_papers = new_papers[
            :max_papers
        ]

    logging.info(
        "RSS 전체 고유 논문 수: %d",
        len(papers),
    )
    logging.info(
        "keyword 일치 논문 수: %d",
        len(relevant_papers),
    )
    logging.info(
        "신규 전송 대상 수: %d",
        len(new_papers),
    )

    if not new_papers:
        logging.info(
            "전송할 신규 논문이 없습니다."
        )
        return

    openai_client = (
        create_openai_client()
    )

    today_str = (
        datetime.datetime.now(
            SEOUL_TZ
        )
        .date()
        .isoformat()
    )

    sent_count = 0

    for paper in new_papers:
        logging.info(
            "신규 논문 처리 중: "
            "%s (%s)",
            paper.title,
            paper.arxiv_id,
        )

        summary_ko = (
            summarize_abstract_ko(
                openai_client,
                paper.title,
                paper.abstract,
            )
        )

        record = {
            "arxiv_id": (
                paper.arxiv_id
            ),
            "versioned_id": (
                paper.versioned_id
            ),
            "title": paper.title,
            "authors": paper.authors,
            "summary_ko": summary_ko,
            "abstract_url": (
                paper.entry_url
            ),
            "pdf_url": paper.pdf_url,
            "announce_type": (
                paper.announce_type
            ),
            "categories": (
                paper.categories
            ),
            "published_at": (
                paper
                .published_at
                .isoformat()
            ),
            "sent_date": today_str,
        }

        slack_sent = send_to_slack(
            webhook_url,
            paper,
            summary_ko,
        )

        if not slack_sent:
            logging.error(
                "Slack 전송 실패로 "
                "완료 기록을 남기지 "
                "않습니다: %s",
                paper.arxiv_id,
            )
            continue

        sheet_saved = (
            append_to_google_sheet(
                record,
                sheet,
            )
        )
        jsonl_saved = (
            append_sent_paper(
                record
            )
        )

        if (
            sheet is not None
            and not sheet_saved
        ):
            logging.warning(
                "Slack 전송은 성공했지만 "
                "Google Sheet 기록에 "
                "실패했습니다: %s",
                paper.arxiv_id,
            )

        if not jsonl_saved:
            logging.warning(
                "Slack 전송은 성공했지만 "
                "JSONL 기록에 "
                "실패했습니다: %s",
                paper.arxiv_id,
            )

        sent_ids.add(
            paper.arxiv_id
        )
        sent_count += 1

    logging.info(
        "신규 논문 %d건 전송을 "
        "완료했습니다.",
        sent_count,
    )


if __name__ == "__main__":
    main()
