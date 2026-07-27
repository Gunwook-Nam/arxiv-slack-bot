import os
import re
import json
import time
import random
import logging
import datetime
from zoneinfo import ZoneInfo

import arxiv
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

# arXiv가 429/503을 반환할 때의 대기 시간
ARXIV_BACKOFF_SECONDS = (30, 60, 120, 240, 480)
RETRYABLE_ARXIV_STATUS = {429, 500, 502, 503, 504}

SHEET_HEADERS = [
    "날짜",
    "arXiv ID",
    "제목",
    "저자",
    "한글 요약",
    "PDF 링크",
]


# ---------------------------------------------------------------------
# 전송 기록
# ---------------------------------------------------------------------

def load_sent_paper_ids(
    file_path: str = SENT_PAPERS_FILE,
) -> set[str]:
    sent_ids: set[str] = set()

    if not os.path.exists(file_path):
        return sent_ids

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logging.warning(
                        "잘못된 JSONL 행을 건너뜁니다: %s",
                        line[:100],
                    )
                    continue

                arxiv_id = data.get("arxiv_id")

                if arxiv_id:
                    sent_ids.add(arxiv_id)

    except OSError as error:
        logging.error("전송 기록 읽기 실패: %s", error)

    return sent_ids


def append_sent_paper(
    paper_data: dict,
    file_path: str = SENT_PAPERS_FILE,
) -> bool:
    try:
        with open(file_path, "a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    paper_data,
                    ensure_ascii=False,
                )
                + "\n"
            )

        return True

    except OSError as error:
        logging.error("전송 기록 저장 실패: %s", error)
        return False


# ---------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------

def open_google_sheet():
    sheet_key = os.environ.get("GOOGLE_SHEETS_KEY")
    creds_raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not sheet_key or not creds_raw:
        logging.warning(
            "Google Sheets 설정이 없습니다. "
            "JSONL 파일만 중복 확인에 사용합니다."
        )
        return None

    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]

        if creds_raw.lstrip().startswith("{"):
            creds_dict = json.loads(creds_raw)

            credentials = (
                ServiceAccountCredentials.from_json_keyfile_dict(
                    creds_dict,
                    scope,
                )
            )
        else:
            credentials = (
                ServiceAccountCredentials.from_json_keyfile_name(
                    creds_raw,
                    scope,
                )
            )

        client = gspread.authorize(credentials)
        sheet = client.open_by_key(sheet_key).sheet1

        if not sheet.row_values(1):
            sheet.append_row(
                SHEET_HEADERS,
                value_input_option="RAW",
            )

        return sheet

    except Exception as error:
        logging.error("Google Sheet 연결 실패: %s", error)
        return None


def load_sent_paper_ids_from_sheet(sheet) -> set[str]:
    if sheet is None:
        return set()

    try:
        # 두 번째 열: arXiv ID
        values = sheet.col_values(2)

        # 첫 번째 행은 header이므로 제외
        return {
            value.strip()
            for value in values[1:]
            if value.strip()
        }

    except Exception as error:
        logging.error(
            "Google Sheet 전송 기록 읽기 실패: %s",
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
        paper_record.get("sent_date", ""),
        paper_record.get("arxiv_id", ""),
        paper_record.get("title", ""),
        ", ".join(paper_record.get("authors", [])),
        paper_record.get("summary_ko", ""),
        paper_record.get("pdf_url", ""),
    ]

    try:
        sheet.append_row(
            row,
            value_input_option="RAW",
        )
        return True

    except Exception as error:
        logging.error("Google Sheet 기록 실패: %s", error)
        return False


# ---------------------------------------------------------------------
# OpenAI 요약
# ---------------------------------------------------------------------

def create_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        logging.warning(
            "OPENAI_API_KEY가 설정되지 않았습니다."
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
        return "요약 기능 미설정 (API Key 필요)"

    prompt = f"""
다음 학술 논문의 제목과 초록을 한국어로 요약하세요.

[논문 제목]
{title}

[초록]
{abstract}

[작성 규칙]
1. 주요 학술 및 전문 용어는 영문으로 표기합니다.
2. 정확히 3개의 핵심 포인트로 요약합니다.
3. 각 줄은 '• '로 시작합니다.
4. 서론, 인사말, 제목, 추가 설명은 출력하지 않습니다.
""".strip()

    try:
        response = client.chat.completions.create(
            model=os.environ.get(
                "OPENAI_MODEL",
                "gpt-4o-mini",
            ),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You summarize academic abstracts "
                        "into concise Korean bullet points."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.3,
        )

        content = response.choices[0].message.content

        if not content:
            return "요약 결과가 비어 있습니다."

        return content.strip()

    except Exception as error:
        logging.error(
            "OpenAI API 호출 중 오류 발생: %s",
            error,
        )
        return "요약 생성 중 오류 발생"


# ---------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------

def escape_slack_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def post_to_slack(
    webhook_url: str,
    payload: dict,
) -> bool:
    if not webhook_url:
        logging.error(
            "SLACK_WEBHOOK_URL이 설정되지 않았습니다."
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
        logging.error("Slack 전송 실패: %s", error)
        return False


def send_to_slack(
    webhook_url: str,
    title: str,
    authors: list[str],
    summary_ko: str,
    link: str,
    arxiv_id: str,
) -> bool:
    authors_str = ", ".join(authors[:3])

    if len(authors) > 3:
        authors_str += " 등"

    safe_title = escape_slack_text(title).replace("|", "¦")
    safe_authors = escape_slack_text(authors_str)
    safe_summary = escape_slack_text(summary_ko)

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": (
                        f"arXiv 신규 논문 알림 "
                        f"[{arxiv_id}]"
                    ),
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{link}|{safe_title}>*\n"
                        f"*저자:* {safe_authors}"
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*한글 요약*\n"
                        f"{safe_summary}"
                    ),
                },
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
                        "⚠️ *arXiv bot 오류*\n"
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
# arXiv 검색
# ---------------------------------------------------------------------

def fetch_arxiv_results(
    search: arxiv.Search,
) -> list[arxiv.Result]:
    page_size = max(
        1,
        search.max_results or 100,
    )

    # arxiv.py의 짧은 내부 retry를 사용하지 않는다.
    client = arxiv.Client(
        page_size=page_size,
        delay_seconds=10.0,
        num_retries=0,
    )

    total_attempts = len(ARXIV_BACKOFF_SECONDS) + 1

    for attempt in range(total_attempts):
        try:
            return list(client.results(search))

        except arxiv.HTTPError as error:
            retryable = (
                error.status in RETRYABLE_ARXIV_STATUS
            )

            if (
                not retryable
                or attempt == total_attempts - 1
            ):
                raise

            wait_seconds = (
                ARXIV_BACKOFF_SECONDS[attempt]
                + random.uniform(0, 10)
            )

            logging.warning(
                "arXiv API HTTP %s. "
                "%.1f초 후 재시도합니다. (%d/%d)",
                error.status,
                wait_seconds,
                attempt + 1,
                total_attempts,
            )

            time.sleep(wait_seconds)

        except (
            arxiv.UnexpectedEmptyPageError,
            requests.RequestException,
        ) as error:
            if attempt == total_attempts - 1:
                raise

            wait_seconds = (
                ARXIV_BACKOFF_SECONDS[attempt]
                + random.uniform(0, 10)
            )

            logging.warning(
                "arXiv API 연결 오류: %s. "
                "%.1f초 후 재시도합니다. (%d/%d)",
                error,
                wait_seconds,
                attempt + 1,
                total_attempts,
            )

            time.sleep(wait_seconds)

    return []


def normalize_arxiv_id(
    result: arxiv.Result,
) -> str:
    short_id = result.get_short_id()

    # 2607.12345v2 -> 2607.12345
    # 문자열 중간의 v는 제거하지 않는다.
    return re.sub(
        r"v\d+$",
        "",
        short_id,
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    webhook_url = os.environ.get(
        "SLACK_WEBHOOK_URL",
        "",
    )

    # Google Sheet 연결은 실행당 한 번만 수행
    sheet = open_google_sheet()

    # local JSONL과 Google Sheet를 모두 중복 확인에 사용
    sent_ids = load_sent_paper_ids()
    sent_ids.update(
        load_sent_paper_ids_from_sheet(sheet)
    )

    query = os.environ.get(
        "ARXIV_QUERY",
        'all:"Machine learning interatomic potentials"',
    )

    try:
        max_results = int(
            os.environ.get(
                "ARXIV_MAX_RESULTS",
                "5",
            )
        )
    except ValueError:
        logging.warning(
            "ARXIV_MAX_RESULTS가 정수가 아닙니다. "
            "기본값 5를 사용합니다."
        )
        max_results = 5

    if max_results < 1:
        max_results = 1

    logging.info(
        "검색 키워드: %s",
        query,
    )
    logging.info(
        "이미 전송된 논문 수: %d",
        len(sent_ids),
    )

    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    try:
        results = fetch_arxiv_results(search)

    except Exception as error:
        logging.exception(
            "arXiv 검색이 모든 재시도 후 실패했습니다."
        )

        send_status_to_slack(
            webhook_url,
            f"arXiv API 검색 실패: {error}",
        )

        raise SystemExit(1)

    today_str = (
        datetime.datetime.now(SEOUL_TZ)
        .date()
        .isoformat()
    )

    openai_client = create_openai_client()
    new_paper_count = 0

    for result in results:
        arxiv_id = normalize_arxiv_id(result)

        if arxiv_id in sent_ids:
            logging.info(
                "이미 알림 전송된 논문: %s",
                arxiv_id,
            )
            continue

        title = " ".join(
            result.title.split()
        )

        authors = [
            author.name
            for author in result.authors
        ]

        paper_url = (
            result.pdf_url
            or result.entry_id
        )

        logging.info(
            "신규 논문 처리 중: %s (%s)",
            title,
            arxiv_id,
        )

        summary_ko = summarize_abstract_ko(
            openai_client,
            title,
            result.summary,
        )

        record = {
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "summary_ko": summary_ko,
            "pdf_url": paper_url,
            "sent_date": today_str,
        }

        slack_sent = send_to_slack(
            webhook_url,
            title,
            authors,
            summary_ko,
            paper_url,
            arxiv_id,
        )

        # Slack 전송 실패 시 전송 완료로 기록하지 않는다.
        if not slack_sent:
            logging.error(
                "Slack 전송 실패로 전송 완료 기록을 "
                "남기지 않습니다: %s",
                arxiv_id,
            )
            continue

        # Slack 전송 성공 이후에만 저장
        append_to_google_sheet(
            record,
            sheet,
        )
        append_sent_paper(record)

        sent_ids.add(arxiv_id)
        new_paper_count += 1

    logging.info(
        "신규 논문 %d건 처리를 완료했습니다.",
        new_paper_count,
    )


if __name__ == "__main__":
    main()
