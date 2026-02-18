# Daily Digest Agent

매일 아침 국내/미국 주식 정보와 프로그래밍 트렌드를 수집하여 Slack으로 발송하는 자동화 시스템입니다.
crewAI 프레임워크로 에이전트를 구성하고, GitHub Actions로 스케줄 실행하며,
Slack Bolt SDK (Socket Mode)를 통해 슬래시 커맨드와 인터랙티브 버튼도 지원합니다.

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| 웹 프레임워크 | FastAPI |
| AI 에이전트 | crewAI |
| Slack 연동 | slack-sdk (Webhook), slack-bolt (Socket Mode) |
| 주식 데이터 | yfinance (Yahoo Finance API) |
| 데이터 검증 | Pydantic v2, pydantic-settings |
| 스케줄러 | GitHub Actions |
| 환경변수 관리 | python-dotenv |

## 디렉토리 구조

```
daily-digest-agent/
├── app/                    # FastAPI 서버
│   ├── __init__.py
│   └── routers/            # API 라우터 (health, digest)
│       └── __init__.py
├── src/
│   ├── agents/             # crewAI 에이전트 정의
│   │   ├── publisher.py    #   - 다이제스트 발송 퍼블리셔 Agent
│   │   └── us_dividend.py  #   - 미국 고배당주 스캐너 Agent
│   ├── services/           # 비즈니스 로직
│   │   ├── slack_service.py#   - 다이제스트 실행 및 상태 관리
│   │   └── dividend_service.py# - 배당 스캔, 필터링, Slack 포맷 변환
│   ├── schemas/            # Pydantic 모델 (입출력 타입 정의)
│   │   ├── slack.py        #   - Block Kit, 실행 결과, 환경변수 스키마
│   │   └── stock.py        #   - 배당 종목 정보, 스캔 결과 스키마
│   ├── tools/              # 외부 API 래퍼 (순수 API 호출만 담당)
│   │   ├── slack_webhook.py#   - Incoming Webhook 메시지 발송
│   │   ├── slack_bolt_app.py#  - Bolt 슬래시 커맨드 및 인터랙티브 핸들러
│   │   └── yahoo_finance.py#   - Yahoo Finance 배당 데이터 수집
│   ├── crews/              # crewAI Crew 조합 및 실행
│   │   └── daily_crew.py   #   - 배당 스캔 → 슬랙 발송 파이프라인
│   ├── config/             # agents.yaml, tasks.yaml
│   └── __init__.py
├── tests/                  # pytest 테스트
├── .github/
│   └── workflows/          # GitHub Actions 워크플로우
├── .env.example            # 환경변수 템플릿
├── requirements.txt        # Python 의존성 목록
├── CLAUDE.md               # 프로젝트 규칙 및 코딩 컨벤션
└── README.md
```

## 설치 방법

### 1. 저장소 클론

```bash
git clone <repository-url>
cd daily-digest-agent
```

### 2. 가상환경 생성 및 활성화

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 항목을 설정합니다.

## 환경변수 설정

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `SLACK_WEBHOOK_URL` | O | Slack Incoming Webhook URL (`https://hooks.slack.com/services/...`) |
| `SLACK_BOT_TOKEN` | O | Slack Bot User OAuth Token (`xoxb-`로 시작) |
| `SLACK_APP_TOKEN` | O | Slack App-Level Token, Socket Mode용 (`xapp-`로 시작) |
| `SLACK_CHANNEL` | - | 메시지 발송 채널 (기본값: `#daily-digest`) |
| `ANTHROPIC_API_KEY` | O | Anthropic API Key (crewAI Agent 실행에 필요) |
| `DART_API_KEY` | - | DART 전자공시 API Key (향후 사용 예정) |
| `FRED_API_KEY` | - | FRED 미국 경제 데이터 API Key (향후 사용 예정) |
| `BOK_API_KEY` | - | 한국은행 Open API Key (향후 사용 예정) |

### Slack 앱 설정 방법

1. [Slack API](https://api.slack.com/apps)에서 새 앱을 생성합니다.
2. **Incoming Webhooks**를 활성화하고 채널에 연결하여 Webhook URL을 획득합니다.
3. **OAuth & Permissions**에서 Bot Token (`xoxb-`)을 획득합니다.
4. **Socket Mode**를 활성화하고 App-Level Token (`xapp-`)을 생성합니다.
5. **Slash Commands**에서 `/digest` 커맨드를 등록합니다.
6. **Interactivity & Shortcuts**를 활성화합니다.

## 실행 방법

### Webhook 테스트 (단일 메시지 발송)

Slack Incoming Webhook을 통해 테스트 메시지를 발송합니다.

```bash
python -m src.tools.slack_webhook
```

### Slack Service 테스트 (다이제스트 실행)

비즈니스 로직 레이어에서 다이제스트를 생성하고 발송합니다.

```bash
python -m src.services.slack_service
```

### Yahoo Finance 배당 데이터 수집 (원시 데이터)

yfinance를 사용하여 배당락일 임박 종목의 원시 데이터를 수집합니다.
비즈니스 로직(필터링, 정렬) 없이 순수 API 호출만 수행합니다.

```bash
python -m src.tools.yahoo_finance
```

### 배당 서비스 테스트 (필터링 + Slack 포맷)

배당 종목을 스캔하고 필터링(수익률 >= 3%, 시가총액 >= $1B)한 뒤
Slack Block Kit 포맷으로 변환합니다.

```bash
python -m src.services.dividend_service
```

### Daily Crew 파이프라인 (배당 스캔 -> 슬랙 발송)

배당락일 스캔부터 슬랙 발송까지 전체 파이프라인을 실행합니다.
crewAI Agent 정보도 함께 출력합니다 (LLM 미설정 시 Agent 생성 스킵).

```bash
python -m src.crews.daily_crew
```

### Bolt App 실행 (Socket Mode)

슬래시 커맨드 `/digest now`, `/digest status` 및 인터랙티브 버튼을 지원하는 Bolt App을 시작합니다.

```bash
python -m src.tools.slack_bolt_app
```

실행 후 Slack에서 다음 커맨드를 사용할 수 있습니다:

- `/digest now` - 다이제스트 즉시 실행 및 발송
- `/digest status` - 마지막 실행 상태 조회

### Publisher Agent 확인

crewAI Publisher Agent의 생성 및 구성을 확인합니다.

```bash
python -m src.agents.publisher
```

### US Dividend Agent 확인

crewAI 미국 고배당주 스캐너 Agent의 생성 및 구성을 확인합니다.

```bash
python -m src.agents.us_dividend
```

### 스키마 검증

Pydantic 모델의 생성 및 직렬화를 테스트합니다.

```bash
python -m src.schemas.slack
python -m src.schemas.stock
```

### 테스트 실행

```bash
pytest tests/
```

### 슬랙 E2E 테스트 (배당락일 다이제스트 발송)

환경변수 `.env` 설정 후, 배당락일 스캔부터 슬랙 발송까지의 전체 흐름을 확인합니다.

```bash
# 1. 원시 데이터 수집 확인 (Slack 미발송)
python -m src.tools.yahoo_finance

# 2. 필터링 + Slack 포맷 확인 (Slack 미발송)
python -m src.services.dividend_service

# 3. 실제 Slack 발송 (Webhook 필요)
python -m src.crews.daily_crew

# 4. Bolt App을 통한 슬래시 커맨드 테스트
python -m src.tools.slack_bolt_app
# Slack에서 /digest now 실행 → 배당 섹션이 포함된 다이제스트 확인
```

## 아키텍처 원칙

- **비즈니스 로직 분리**: 모든 비즈니스 로직은 `src/services/`에 위치합니다.
- **순수 API 호출**: `src/tools/`는 외부 API 호출만 담당합니다.
- **타입 안전성**: 모든 입출력은 `src/schemas/`의 Pydantic 모델로 타입 검증합니다 (dict 직접 전달 금지).
- **환경변수 검증**: 환경변수도 Pydantic BaseSettings로 로드하고 검증합니다.
- **핸들러 분리**: `slack_bolt_app.py`는 라우팅(핸들러 등록)만 담당하고, 로직은 `SlackService`에 위임합니다.

## 현재 개발 단계

**Step 1: 슬랙 알림 모듈 (Webhook + Bolt 기반)** - 완료

- [x] Pydantic 스키마 정의 (`src/schemas/slack.py`)
- [x] Slack Webhook 발송 모듈 (`src/tools/slack_webhook.py`)
- [x] Slack 비즈니스 로직 서비스 (`src/services/slack_service.py`)
- [x] Slack Bolt 핸들러 (`src/tools/slack_bolt_app.py`)
- [x] crewAI Publisher Agent (`src/agents/publisher.py`)

**Step 2: 미국 배당락일 스캔 모듈** - 진행 중

미국 주식 중 배당락일이 임박한 고배당 종목을 자동으로 스캔하여
Slack 다이제스트에 포함하는 기능입니다.

주요 기능:
- yfinance를 통한 배당락일, 배당수익률, 시가총액 등 원시 데이터 수집
- 배당수익률 >= 3%, 시가총액 >= $1B 기준 필터링
- 수익률 내림차순 정렬, 최대 10개 종목 제한
- Slack Block Kit 형식으로 포맷팅 및 발송
- crewAI Agent(ScanDividendsTool)로 래핑하여 Crew에서 활용 가능

- [x] 배당 종목 Pydantic 스키마 (`src/schemas/stock.py`)
- [x] Yahoo Finance 배당 데이터 수집 (`src/tools/yahoo_finance.py`)
- [x] 배당 비즈니스 로직 서비스 (`src/services/dividend_service.py`)
- [x] crewAI US Dividend Agent (`src/agents/us_dividend.py`)
- [x] SlackService 배당 섹션 통합 (`src/services/slack_service.py`)
- [x] Daily Crew 파이프라인 (`src/crews/daily_crew.py`)
