import os
import json
import logging
import datetime
import arxiv
import requests
import gspread
from openai import OpenAI
from oauth2client.service_account import ServiceAccountCredentials

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SENT_PAPERS_FILE = "sent_papers.jsonl"

# 1. JSONL 읽기 (중복 체크용)
def load_sent_paper_ids(file_path: str = SENT_PAPERS_FILE) -> set:
    sent_ids = set()
    if not os.path.exists(file_path):
        return sent_ids

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    if "arxiv_id" in data:
                        sent_ids.add(data["arxiv_id"])
                except json.JSONDecodeError:
                    continue
    return sent_ids

# 2. JSONL 쓰기 (기록 추가)
def append_sent_paper(paper_data: dict, file_path: str = SENT_PAPERS_FILE):
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(paper_data, ensure_ascii=False) + "\n")

# 3. OpenAI를 이용한 초록 한글 요약
def summarize_abstract_ko(title: str, abstract: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logging.warning("OPENAI_API_KEY가 설정되지 않았습니다.")
        return "요약 기능 미설정 (API Key 필요)"

    client = OpenAI(api_key=api_key)

    prompt = f"""
다음은 학술 논문의 제목과 초록(Abstract)입니다. 
한국어로 쉽게 이해할 수 있도록 핵심 내용을 3개의 불렛포인트로 요약해 주세요.

[논문 제목]
{title}

[초록]
{abstract}

[작성 규칙]
1. 주요 학술/전문 용어는 가급적 영문 용어 그대로 표기해 주세요. (예: 머신러닝 인터아토믹 포텐셜 (X), MLIP (O))
2. 3개의 핵심 포인트로 요약해 주세요. (각 줄은 '• '로 시작)
3. 서론, 인사말, 추가 설명 없이 요약 불렛포인트만 깔끔하게 출력해 주세요.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 가성비와 성능이 우수한 모델 사용
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes academic abstracts into concise Korean bullet points."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"OpenAI API 호출 중 오류 발생: {e}")
        return "요약 생성 중 오류 발생"

# 4. Slack 메시지 전송
def send_to_slack(webhook_url: str, title: str, authors: list, summary_ko: str, link: str, arxiv_id: str):
    if not webhook_url:
        return

    authors_str = ", ".join(authors[:3]) + (" 등" if len(authors) > 3 else "")

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"arXiv 신규 논문 알림 [{arxiv_id}]",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{link}|{title}>*\n*저자:* {authors_str}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"* 한글 요약*\n{summary_ko}"
                }
            },
            {"type": "divider"}
        ]
    }
    requests.post(webhook_url, json=payload)

# 5. Google Sheets 기록
def append_to_google_sheet(paper_record: dict):
    sheet_key = os.environ.get("GOOGLE_SHEETS_KEY")
    creds_raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not sheet_key or not creds_raw:
        return

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        if creds_raw.startswith("{"):
            creds_dict = json.loads(creds_raw)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_raw, scope)

        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_key).sheet1

        if len(sheet.get_all_values()) == 0:
            sheet.append_row(["날짜", "arXiv ID", "제목", "저자", "한글 요약", "PDF 링크"])

        row = [
            paper_record.get("sent_date", ""),
            paper_record.get("arxiv_id", ""),
            paper_record.get("title", ""),
            ", ".join(paper_record.get("authors", [])),
            paper_record.get("summary_ko", ""),
            paper_record.get("pdf_url", "")
        ]
        sheet.append_row(row)
    except Exception as e:
        logging.error(f"Google Sheet 기록 실패: {e}")

# 6. 메인 실행 함수
def main():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    sent_ids = load_sent_paper_ids()

    query = os.environ.get("ARXIV_QUERY", 'all:"Machine learning interatomic potentials"')
    logging.info(f"검색 키워드: {query}")
    
    client = arxiv.Client()
 
    search = arxiv.Search(
        query=query,
        max_results=5,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    for result in client.results(search):
        arxiv_id = result.entry_id.split("/")[-1].split("v")[0]

        if arxiv_id in sent_ids:
            logging.info(f"이미 알림 전송된 논문: {arxiv_id}")
            continue

        title = result.title.replace("\n", " ")
        authors = [a.name for a in result.authors]
        pdf_url = result.pdf_url

        logging.info(f"신규 논문 처리 중: {title} ({arxiv_id})")

        # OpenAI 요약 실행
        summary_ko = summarize_abstract_ko(title, result.summary)

        record = {
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "summary_ko": summary_ko,
            "pdf_url": pdf_url,
            "sent_date": today_str
        }

        # 전송 및 저장
        send_to_slack(webhook_url, title, authors, summary_ko, pdf_url, arxiv_id)
        append_to_google_sheet(record)
        append_sent_paper(record)
        sent_ids.add(arxiv_id)

if __name__ == "__main__":
    main()
