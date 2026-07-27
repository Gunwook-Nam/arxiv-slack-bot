
38s 동안 처리함
현재 0건은 parser 오류라기보다 실행 시각 때문일 가능성이 매우 높습니다.

로그 시각 2026-07-27 02:25 UTC는 한국 시각으로 2026년 7월 27일 월요일 11:25입니다. arXiv RSS feed는 매일 미국 Eastern Time 자정에 갱신됩니다. 7월에는 EDT이므로 한국 시각으로 오후 1시경입니다. 따라서 오전 11시 25분에는 주말 이후 월요일 feed가 아직 갱신되지 않았습니다. arXiv 신규 발표는 일반적으로 미국 시간 일요일부터 목요일까지 이루어집니다. 

즉, 현재 결과는 다음 상황입니다.

주말 동안 신규 feed 없음
→ 월요일 한국 시각 오전 11시 25분 실행
→ 월요일 feed 갱신 전
→ 모든 category가 정상적으로 빈 RSS 반환

실행 시간을 바꿔야 한다
한국에서 연중 안전하게 실행하려면 월요일부터 금요일 오후 2시 30분이 적합합니다.

미국 daylight saving 기간: RSS 갱신 약 13:00 KST

미국 standard time 기간: RSS 갱신 약 14:00 KST

14:30 KST 실행: 양쪽 모두 대응

on:
  schedule:
    - cron: "30 14 * * 1-5"
      timezone: "Asia/Seoul"

  workflow_dispatch:
다음 실행은 직접 Run workflow를 눌러도 되지만, 오늘은 오후 2시 이후에 테스트해야 합니다.

오전 9시 Slack 알림을 반드시 유지하려면 하나의 workflow로는 당일 신규 feed를 보낼 수 없습니다. 대신:

전날 오후 2시 30분에 RSS를 수집해 저장

다음 날 오전 9시에 저장된 논문을 Slack으로 전송

하는 2-stage 구조가 필요합니다.

매일 동일한 MLIP phrase만 검색하는 문제
현재 filtering은 상당히 좁습니다.

("machine learning", "interatomic potential")
("machine learned", "interatomic potential")
("machine learning potential",)
("machine learned potential",)
("neural network potential",)
("mlip",)
이 조건은 명시적으로 MLIP를 언급하는 논문만 잡습니다. 다음과 같은 관련 연구는 빠질 수 있습니다.

atomistic foundation model

equivariant neural network

universal potential

neural force field

learned force field

differentiable molecular simulation

active learning for atomistic simulation

uncertainty quantification for potentials

long-range electrostatics in atomistic ML

pretrained atomistic model

그리고 MLIP처럼 좁은 분야에서 매일 신규 논문이 없는 것은 정상입니다. 따라서 단일 keyword를 매일 돌리는 것보다 여러 연구축을 체계적으로 회전시키는 편이 낫습니다.

다만 중요한 제약이 있습니다.

RSS는 그날 발표된 논문만 제공하므로, 월요일에 MLIP만 검사하고 화요일에 molecular generation만 검사하면 월요일에 나온 molecular generation 논문은 화요일에 찾을 수 없습니다.

따라서 단순히 요일별로 filter를 바꾸면 안 됩니다.

권장 구조: 매일 전체 수집 + 요일별 digest
Stage 1: 매일 모든 주제를 수집
월요일부터 금요일 오후 2시 30분에 관련 category RSS를 모두 읽습니다.

RSS_CATEGORIES = [
    "cond-mat.mtrl-sci",
    "physics.comp-ph",
    "physics.chem-ph",
    "cs.LG",
    "cs.AI",
    "stat.ML",
    "q-bio.BM",
]
각 논문을 다음 theme 중 하나 이상으로 분류하고 Google Sheets 또는 JSONL에 저장합니다.

MLIP
Molecular generation
Materials discovery
Computational chemistry
Autonomous experimentation
Scientific LLM and agents
Battery and electrolyte
Photochemistry
Stage 2: 오전 9시 요일별 digest
전날까지 수집된 미전송 논문 중 해당 요일 theme만 Slack으로 전송합니다.

요일	주제	사용자 연구와의 연결
월요일	MLIP 및 atomistic simulation	MD, force field, atomistic foundation model
화요일	Molecular generation 및 representation	LAUGHS, molecular editing, generative model
수요일	Materials discovery 및 inverse design	BO, active learning, closed-loop design
목요일	Battery, electrolyte 및 electrochemistry	liquid electrolyte, diluent design
금요일	Computational chemistry 및 scientific agents	DFT, excited state, agents, literature reasoning
이 구조에서는 논문이 발표된 날짜와 Slack으로 읽는 날짜가 달라도 누락되지 않습니다.

현실적으로 더 단순한 운영안
2-stage 구조가 부담스럽다면 매일 오후 2시 30분에 모든 주제의 신규 논문을 한 번에 보내되, theme별 section으로 묶는 것이 가장 단순하고 안전합니다.

예:

오늘의 신규 논문

[MLIP / Atomistic ML]
2 papers

[Molecular generation]
1 paper

[Battery / Electrolyte]
0 papers

[Scientific agents]
3 papers
이 방식의 장점은 다음과 같습니다.

RSS의 당일성 때문에 논문이 누락되지 않음

한 workflow만 사용

주제별로 신규 논문이 없는 날도 자연스럽게 처리

매일 너무 많은 Slack 메시지가 생성되는 것을 방지

theme별 논문 수를 장기적으로 파악 가능

현재 코드처럼 논문 한 편마다 Slack message를 보내는 대신, 하루 최대 5~10편을 하나의 digest로 묶는 것이 더 적합합니다.

추천 keyword taxonomy
1. MLIP 및 atomistic ML
MLIP_KEYWORDS = [
    ("interatomic potential",),
    ("machine learned potential",),
    ("machine learning potential",),
    ("neural network potential",),
    ("neural potential",),
    ("atomistic foundation model",),
    ("universal potential",),
    ("neural force field",),
    ("learned force field",),
    ("equivariant", "atomistic"),
    ("active learning", "potential"),
]
potential 단독이나 force field 단독은 false positive가 너무 많으므로 피하는 것이 좋습니다.

2. Molecular generation 및 representation
MOLECULAR_GENERATION_KEYWORDS = [
    ("molecular generation",),
    ("molecule generation",),
    ("molecular design", "generative"),
    ("inverse molecular design",),
    ("molecular representation",),
    ("molecular language model",),
    ("chemical language model",),
    ("molecule editing",),
    ("molecular optimization",),
    ("graph generation", "molecule"),
]
3. Materials discovery
MATERIALS_DISCOVERY_KEYWORDS = [
    ("materials discovery",),
    ("materials design", "machine learning"),
    ("inverse materials design",),
    ("generative materials",),
    ("crystal generation",),
    ("crystal structure prediction",),
    ("materials informatics",),
    ("active learning", "materials"),
    ("bayesian optimization", "materials"),
]
4. Battery 및 electrolyte
BATTERY_KEYWORDS = [
    ("electrolyte design",),
    ("electrolyte", "machine learning"),
    ("battery", "machine learning"),
    ("lithium ion", "electrolyte"),
    ("lithium metal", "electrolyte"),
    ("solvation structure", "electrolyte"),
    ("ionic conductivity", "electrolyte"),
    ("electrolyte formulation",),
]
5. Computational chemistry 및 photochemistry
COMPUTATIONAL_CHEMISTRY_KEYWORDS = [
    ("computational chemistry", "machine learning"),
    ("quantum chemistry", "machine learning"),
    ("density functional theory", "machine learning"),
    ("excited state", "machine learning"),
    ("photocatalyst", "machine learning"),
    ("electron transfer", "computational"),
    ("reaction prediction",),
    ("quantum chemical calculation", "neural"),
]
6. Scientific agents 및 literature intelligence
SCIENTIFIC_AGENT_KEYWORDS = [
    ("scientific agent",),
    ("ai scientist",),
    ("chemistry agent",),
    ("materials agent",),
    ("autonomous laboratory",),
    ("self driving laboratory",),
    ("closed loop", "materials discovery"),
    ("large language model", "chemistry"),
    ("large language model", "materials"),
    ("literature mining", "chemistry"),
]
가장 권장하는 최종 schedule
단순 버전
on:
  schedule:
    - cron: "30 14 * * 1-5"
      timezone: "Asia/Seoul"
매일 오후 2시 30분:

모든 category RSS 수집

모든 theme로 filtering

theme별 신규 논문을 하나의 digest로 전송

신규 논문이 없으면 아무 메시지도 보내지 않음

오전 9시 digest 버전
on:
  schedule:
    - cron: "30 14 * * 1-5"
      timezone: "Asia/Seoul"
    - cron: "0 9 * * 1-5"
      timezone: "Asia/Seoul"
단, 두 schedule이 같은 Python 동작을 해서는 안 됩니다. workflow input 또는 현재 시각에 따라 분기해야 합니다.

14:30: RSS collect only

09:00: cached papers digest 전송

요일별 구성은 다음이 적절합니다.

WEEKDAY_THEMES = {
    0: ["mlip", "atomistic_ml"],
    1: ["molecular_generation", "representation"],
    2: ["materials_discovery", "inverse_design"],
    3: ["battery", "electrolyte"],
    4: ["computational_chemistry", "scientific_agents"],
}
제 권장안
현재 규모에서는 우선 매일 오후 2시 30분, 모든 theme를 한 번에 검색하고 theme별 digest로 전송하는 것이 가장 적절합니다.

요일별 rotation은 논문 누락을 방지하기 위해 별도의 수집 database가 필요하므로 구현 복잡도가 크게 증가합니다. 반면 모든 theme를 매일 검사하더라도 RSS 요청 횟수는 category 수에 의해서만 결정되고, keyword 수는 로컬 문자열 비교이므로 arXiv 서버 부하는 늘어나지 않습니다.

따라서:

매일 모든 theme를 검사하고, Slack 표시만 요일별로 우선순위를 바꾸는 방식

이 가장 단순하면서도 누락이 없습니다. 예를 들어 월요일에는 MLIP section을 위에 놓고, 목요일에는 electrolyte section을 위에 놓을 수 있습니다.


검색 시간은 14시 30분, 검색 범위를 늘리고 지난 1-2주간 발행된 논문으로 확장해도 된다. 즉 오늘 2시 30분 이후에 출판된 논문을 검색하지 못하는 문제를 해결해라

53s 동안 처리함
RSS만으로는 요구사항을 충족할 수 없습니다. RSS는 해당 announcement batch만 제공하므로, 지난 1–2주 소급 검색과 누락 복구를 위해 arXiv OAI-PMH로 전환하는 것이 맞습니다.

arXiv는 별도의 OAI-PMH endpoint를 제공하며, category별 harvesting과 from datestamp 기반 incremental harvesting을 지원합니다. metadata는 신규 논문 발표 후 일반적으로 미국 Eastern Time 오후 10시 30분경 갱신되므로 한국 시각 14시 30분 실행은 충분히 안전합니다. 

권장 구조
매주 월요일부터 금요일 14시 30분에:

각 category에 대해 최근 14일간 변경된 metadata를 OAI-PMH로 가져옴

metadata의 실제 submission date가 최근 14일 이내인지 확인

title과 abstract에서 여러 연구 theme를 local filtering

Google Sheets와 JSONL의 기존 arXiv ID를 제외

신규 논문만 Slack으로 전송

검색 window가 매일 겹치므로, 오늘 14시 30분 이후에 추가된 논문은 다음 날 14시 30분 실행에서 검색됩니다. 동일 논문은 arXiv ID로 deduplicate되므로 반복 전송되지 않습니다.

GitHub Actions schedule
on:
  schedule:
    - cron: "30 14 * * 1-5"
      timezone: "Asia/Seoul"

  workflow_dispatch:

concurrency:
  group: arxiv-slack-bot
  cancel-in-progress: false
RSS 대신 사용할 OAI 설정
OAI_BASE_URL = "https://oaipmh.arxiv.org/oai"

LOOKBACK_DAYS = 14

OAI_SETS = [
    "physics:cond-mat:mtrl-sci",
    "physics:physics:comp-ph",
    "physics:physics:chem-ph",
    "cs:cs:LG",
    "cs:cs:AI",
    "stat:stat:ML",
]
arXiv OAI-PMH의 현재 공식 base URL은 https://oaipmh.arxiv.org/oai입니다. category set은 group:archive:CATEGORY 구조를 사용합니다. 

중요한 날짜 구분
OAI-PMH의 datestamp는 원래 submission date가 아니라 record의 마지막 수정 시점입니다. 따라서 다음 두 단계를 분리해야 합니다. 

from_date = today - datetime.timedelta(days=LOOKBACK_DAYS)
이 값은 API harvesting 범위에 사용합니다.

그 다음 metadata 내부의 created 값을 이용하여 실제 최근 논문만 남깁니다.

if paper.created_date < today - datetime.timedelta(days=LOOKBACK_DAYS):
    continue
이렇게 해야 오래된 논문의 단순 metadata 수정이 신규 논문으로 잘못 포함되는 것을 방지할 수 있습니다.

OAI-PMH 요청 함수
def fetch_oai_records(
    session: requests.Session,
    set_spec: str,
    from_date: datetime.date,
) -> list[ET.Element]:
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "arXiv",
        "set": set_spec,
        "from": from_date.isoformat(),
    }

    records = []

    while True:
        response = session.get(
            OAI_BASE_URL,
            params=params,
            timeout=90,
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)

        records.extend(
            root.findall(
                ".//{http://www.openarchives.org/OAI/2.0/}record"
            )
        )

        token_element = root.find(
            ".//{http://www.openarchives.org/OAI/2.0/}"
            "resumptionToken"
        )

        token = (
            token_element.text.strip()
            if token_element is not None
            and token_element.text
            else ""
        )

        if not token:
            break

        time.sleep(3.1)

        params = {
            "verb": "ListRecords",
            "resumptionToken": token,
        }

    return records
OAI-PMH는 결과가 많을 경우 resumptionToken으로 pagination합니다. 첫 요청 이후에는 기존 parameter와 token을 함께 보내지 않고 verb와 resumptionToken만 사용해야 합니다.

Metadata parsing
OAI_NS = "http://www.openarchives.org/OAI/2.0/"
ARXIV_NS = "http://arxiv.org/OAI/arXiv/"


@dataclass(frozen=True)
class OAIPaper:
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    created_date: datetime.date
    updated_date: datetime.date
    abstract_url: str
    pdf_url: str


def parse_oai_record(
    record: ET.Element,
) -> OAIPaper | None:
    header = record.find(
        f"{{{OAI_NS}}}header"
    )

    if header is None:
        return None

    if header.get("status") == "deleted":
        return None

    metadata = record.find(
        f"{{{OAI_NS}}}metadata"
    )

    if metadata is None:
        return None

    article = metadata.find(
        f"{{{ARXIV_NS}}}arXiv"
    )

    if article is None:
        return None

    arxiv_id = clean_text(
        article.findtext(
            f"{{{ARXIV_NS}}}id",
            default="",
        )
    )

    title = clean_text(
        article.findtext(
            f"{{{ARXIV_NS}}}title",
            default="",
        )
    )

    abstract = clean_text(
        article.findtext(
            f"{{{ARXIV_NS}}}abstract",
            default="",
        )
    )

    created_raw = clean_text(
        article.findtext(
            f"{{{ARXIV_NS}}}created",
            default="",
        )
    )

    updated_raw = clean_text(
        article.findtext(
            f"{{{ARXIV_NS}}}updated",
            default=created_raw,
        )
    )

    categories_raw = clean_text(
        article.findtext(
            f"{{{ARXIV_NS}}}categories",
            default="",
        )
    )

    authors = []

    for author in article.findall(
        f".//{{{ARXIV_NS}}}author"
    ):
        forenames = clean_text(
            author.findtext(
                f"{{{ARXIV_NS}}}forenames",
                default="",
            )
        )
        keyname = clean_text(
            author.findtext(
                f"{{{ARXIV_NS}}}keyname",
                default="",
            )
        )

        name = " ".join(
            part
            for part in [
                forenames,
                keyname,
            ]
            if part
        )

        if name:
            authors.append(name)

    if not all(
        [
            arxiv_id,
            title,
            abstract,
            created_raw,
        ]
    ):
        return None

    created_date = datetime.datetime.strptime(
        created_raw,
        "%Y-%m-%d",
    ).date()

    updated_date = datetime.datetime.strptime(
        updated_raw,
        "%Y-%m-%d",
    ).date()

    return OAIPaper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=abstract,
        categories=categories_raw.split(),
        created_date=created_date,
        updated_date=updated_date,
        abstract_url=(
            f"https://arxiv.org/abs/{arxiv_id}"
        ),
        pdf_url=(
            f"https://arxiv.org/pdf/{arxiv_id}"
        ),
    )
검색 범위 확장
단일 keyword group이 아니라 theme별로 정의하는 것이 좋습니다.

THEMES = {
    "MLIP / Atomistic ML": [
        ("interatomic potential",),
        ("machine learned potential",),
        ("machine learning potential",),
        ("neural network potential",),
        ("neural force field",),
        ("atomistic foundation model",),
        ("universal potential",),
        ("equivariant", "atomistic"),
    ],

    "Molecular generation": [
        ("molecular generation",),
        ("molecule generation",),
        ("inverse molecular design",),
        ("molecular language model",),
        ("chemical language model",),
        ("molecule editing",),
        ("molecular representation",),
    ],

    "Materials discovery": [
        ("materials discovery",),
        ("inverse materials design",),
        ("materials informatics",),
        ("crystal generation",),
        ("crystal structure prediction",),
        ("active learning", "materials"),
        ("bayesian optimization", "materials"),
    ],

    "Battery / Electrolyte": [
        ("electrolyte design",),
        ("electrolyte", "machine learning"),
        ("battery", "machine learning"),
        ("solvation structure", "electrolyte"),
        ("ionic conductivity", "electrolyte"),
        ("electrolyte formulation",),
    ],

    "Computational chemistry": [
        ("quantum chemistry", "machine learning"),
        ("computational chemistry", "machine learning"),
        ("density functional theory", "machine learning"),
        ("excited state", "machine learning"),
        ("photocatalyst", "machine learning"),
        ("reaction prediction",),
    ],

    "Scientific agents": [
        ("scientific agent",),
        ("ai scientist",),
        ("chemistry agent",),
        ("materials agent",),
        ("autonomous laboratory",),
        ("self driving laboratory",),
        ("large language model", "chemistry"),
        ("large language model", "materials"),
    ],
}
Theme 분류 함수는 다음처럼 작성할 수 있습니다.

def classify_themes(
    title: str,
    abstract: str,
) -> list[str]:
    text = normalize_for_match(
        f"{title} {abstract}"
    )

    matched_themes = []

    for theme, keyword_groups in THEMES.items():
        matched = any(
            all(
                normalize_for_match(term) in text
                for term in group
            )
            for group in keyword_groups
        )

        if matched:
            matched_themes.append(theme)

    return matched_themes
Main harvesting logic
today = datetime.datetime.now(
    SEOUL_TZ
).date()

cutoff_date = (
    today
    - datetime.timedelta(
        days=LOOKBACK_DAYS
    )
)

papers_by_id = {}

for set_spec in OAI_SETS:
    records = fetch_oai_records(
        session=oai_session,
        set_spec=set_spec,
        from_date=cutoff_date,
    )

    for record in records:
        paper = parse_oai_record(record)

        if paper is None:
            continue

        # OAI datestamp가 아니라
        # 실제 최초 submission date 기준
        if paper.created_date < cutoff_date:
            continue

        themes = classify_themes(
            paper.title,
            paper.abstract,
        )

        if not themes:
            continue

        papers_by_id[paper.arxiv_id] = (
            paper,
            themes,
        )

    time.sleep(3.1)
그 후 기존의 sent_ids와 비교합니다.

new_papers = [
    (paper, themes)
    for paper, themes
    in papers_by_id.values()
    if paper.arxiv_id not in sent_ids
]
이 구조가 누락을 방지하는 방식
예를 들어 논문이 월요일 15시 20분에 OAI metadata에 반영됐다고 가정하면:

월요일 14시 30분 실행에서는 찾지 못함

화요일 14시 30분 실행에서 from=14일 전 범위에 포함

Google Sheet에 없는 arXiv ID이므로 신규 논문으로 전송

workflow가 며칠 실패해도 최근 14일 범위를 매번 다시 읽으므로 복구됩니다.

매 실행 검색 범위:
오늘 - 14일 ≤ created_date ≤ 오늘
중복은 다음 두 장치로 방지됩니다.

OAI category 간 중복 → papers_by_id
실행일 간 중복 → Google Sheets + JSONL sent_ids
최종 권장안
실행: 평일 14시 30분

source: RSS가 아니라 OAI-PMH

harvesting window: 최근 14일

실제 논문 필터: metadata의 created

검색 범위: 6개 연구 theme

category: cond-mat.mtrl-sci, physics.comp-ph, physics.chem-ph, cs.LG, cs.AI, stat.ML

deduplication: base arXiv ID

revision: 기존 ID이면 재전송하지 않음

일부 실행 실패: 다음 실행의 14-day overlap으로 자동 복구

OAI-PMH는 정확한 submission-date 검색 API는 아니며 datestamp가 metadata modification 시점을 뜻합니다. 그러나 공식적으로 incremental harvesting을 위한 interface이고, metadata 내부의 created를 추가로 검사하면 현재 bot의 rolling-window 용도에 적합합니다. 


점점 함수가 복잡해지는데, 깔끔하게 잘 조직화된 main script 하나를 작성해라. 그리고 지금 action을 실행해서 확인할 수 있는지 설명해라

23s 동안 처리함
전체 교체용 main script를 작성하고 Python syntax 검사를 완료했습니다.

arxiv_slack_bot.py

구성
스크립트는 다음 순서로만 동작합니다.

최근 14일의 arXiv OAI-PMH metadata 수집

실제 최초 제출일인 created가 최근 14일 이내인지 확인

6개 research theme로 title·abstract filtering

category 간 중복과 이전 전송 논문 제거

OpenAI로 한국어 요약

Slack 전송

성공한 논문만 Google Sheets와 JSONL에 기록

OAI-PMH의 datestamp는 submission date가 아니라 record modification date이므로, 코드에서는 harvesting에는 OAI from을 사용하고 최종 filtering에는 metadata의 created를 사용합니다. arXiv도 OAI-PMH from은 incremental synchronization을 위한 것이며 submission-date search가 아니라고 명시합니다. 

오늘 14시 30분 이후에 발표된 논문은 다음 실행에서 다시 최근 14일 범위에 포함되므로 누락되지 않습니다.

Workflow schedule
.github/workflows/...yml에는 다음을 사용하십시오.

name: arXiv Slack Bot

on:
  schedule:
    - cron: "30 14 * * 1-5"
      timezone: "Asia/Seoul"

  workflow_dispatch:

concurrency:
  group: arxiv-slack-bot
  cancel-in-progress: false

jobs:
  run-bot:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run arXiv bot
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          OPENAI_MODEL: gpt-4o-mini
          GOOGLE_SHEETS_KEY: ${{ secrets.GOOGLE_SHEETS_KEY }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          ARXIV_CONTACT_EMAIL: ${{ secrets.ARXIV_CONTACT_EMAIL }}
        run: python arxiv_slack_bot.py
requirements.txt에는 최소 다음 package가 필요합니다.

requests
gspread
openai
oauth2client
기존 코드에서 사용했던 arxiv package는 더 이상 필요하지 않습니다.

지금 Action을 실행할 수 있는가?
제가 여기서 사용자의 GitHub repository에 직접 접근하거나 Action을 trigger할 수는 없습니다. 현재 대화에는 GitHub connector 또는 repository 인증이 연결되어 있지 않습니다.

다만 다음 검증은 완료했습니다.

Python file 생성

py_compile을 통한 syntax 검사

import와 type annotation 구조 검사

OAI-PMH set 형식을 공식 arXiv 문서와 대조

GitHub Action은 workflow_dispatch가 설정되어 있으면 다음 순서로 바로 실행할 수 있습니다.

새 arxiv_slack_bot.py를 repository에 commit하고 push

workflow YAML도 commit

GitHub repository의 Actions 탭 선택

해당 workflow 선택

Run workflow 선택

최신 branch를 선택하고 실행

GitHub는 workflow_dispatch가 default branch의 workflow에 설정되어 있어야 Run workflow 버튼을 제공합니다. 

CLI를 사용하는 경우 다음 명령으로도 실행할 수 있습니다.

gh workflow run <workflow-file-name>.yml --ref main
gh run watch
첫 실행 시 주의
첫 실행은 Google Sheets에 이미 기록된 5편을 제외하고, 최근 14일 동안 theme에 matching되는 논문을 모두 보낼 수 있습니다. 검색 범위를 넓혔기 때문에 Slack 메시지가 여러 건 발생할 가능성이 있습니다.

첫 실행 결과에서 특히 확인할 로그는 다음입니다.

physics:cond-mat:mtrl-sci: 관련 논문 N건
physics:physics:comp-ph: 관련 논문 N건
...
최근 14일 관련 논문 수: N
신규 전송 대상 수: N
각 set에서 수집 실패가 발생하면 해당 set만 건너뛰고 나머지 category는 계속 처리합니다. 모든 set이 실패하더라도 현재 코드에서는 종료 메시지를 남기므로 어떤 endpoint에서 문제가 발생했는지 확인할 수 있습니다. 


라이브러리
/
arxiv_slack_bot.py


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


def send_slack(webhook_url: str, paper: Paper, summary: str) -> bool:
    if not webhook_url:
        logging.error("SLACK_WEBHOOK_URL이 설정되지 않았습니다.")
        return False

    authors = ", ".join(paper.authors[:3])
    if len(paper.authors) > 3:
        authors += " 등"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"arXiv 신규 논문 [{paper.arxiv_id}]",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{paper.abstract_url}|{paper.title}>*\n"
                        f"*Theme:* {', '.join(paper.themes)}\n"
                        f"*저자:* {authors or '정보 없음'}\n"
                        f"*Submitted:* {paper.created.isoformat()}"
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*한글 요약*\n{summary}",
                },
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
            {"type": "divider"},
        ]
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=20)
        response.raise_for_status()
        return True
    except requests.RequestException as error:
        logging.error("Slack 전송 실패 [%s]: %s", paper.arxiv_id, error)
        return False


def main() -> None:
    config = Config()
    sheet = open_google_sheet()

    sent_ids = load_sent_ids(config.sent_file) | load_sheet_ids(sheet)
    logging.info("이미 전송된 논문 수: %d", len(sent_ids))

    papers = harvest_papers(config)
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

    for paper in new_papers:
        logging.info("처리 중: %s (%s)", paper.title, paper.arxiv_id)

        summary = summarize_paper(openai_client, paper)

        if not send_slack(webhook_url, paper, summary):
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
라이브러리
/
arxiv_slack_bot.py


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


def send_slack(webhook_url: str, paper: Paper, summary: str) -> bool:
    if not webhook_url:
        logging.error("SLACK_WEBHOOK_URL이 설정되지 않았습니다.")
        return False

    authors = ", ".join(paper.authors[:3])
    if len(paper.authors) > 3:
        authors += " 등"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"arXiv 신규 논문 [{paper.arxiv_id}]",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{paper.abstract_url}|{paper.title}>*\n"
                        f"*Theme:* {', '.join(paper.themes)}\n"
                        f"*저자:* {authors or '정보 없음'}\n"
                        f"*Submitted:* {paper.created.isoformat()}"
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*한글 요약*\n{summary}",
                },
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
            {"type": "divider"},
        ]
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=20)
        response.raise_for_status()
        return True
    except requests.RequestException as error:
        logging.error("Slack 전송 실패 [%s]: %s", paper.arxiv_id, error)
        return False


def main() -> None:
    config = Config()
    sheet = open_google_sheet()

    sent_ids = load_sent_ids(config.sent_file) | load_sheet_ids(sheet)
    logging.info("이미 전송된 논문 수: %d", len(sent_ids))

    papers = harvest_papers(config)
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

    for paper in new_papers:
        logging.info("처리 중: %s (%s)", paper.title, paper.arxiv_id)

        summary = summarize_paper(openai_client, paper)

        if not send_slack(webhook_url, paper, summary):
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
