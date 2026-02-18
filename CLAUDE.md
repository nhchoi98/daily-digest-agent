# Daily Digest Agent

## 프로젝트 개요
매일 아침 국내/미국 주식 정보 + 프로그래밍 트렌드를 수집하여 Slack으로 발송하는 자동화 시스템.
crewAI 프레임워크로 에이전트를 구성하고, GitHub Actions로 스케줄 실행한다.
Slack Bolt SDK (Socket Mode)로 슬래시 커맨드, 인터랙티브 버튼도 지원한다.

## 기술 스택
- Python 3.12, FastAPI, crewAI, slack-bolt
- GitHub Actions (스케줄러)
- Slack Webhook + Bolt SDK (Socket Mode)

## 아키텍처 원칙
- 비즈니스 로직은 반드시 src/services/ 에 분리
- src/tools/ 는 순수 외부 API 호출만 담당
- src/tools/slack_bolt_app.py 는 라우팅(핸들러 등록)만 담당
- 모든 입출력은 src/schemas/ 의 Pydantic 모델로 타입 체크 (dict 직접 전달 금지)
- 환경변수도 Pydantic BaseModel(또는 BaseSettings)로 로드 및 검증

## 디렉토리 구조
- app/ : FastAPI 서버 (routers/health.py, routers/digest.py)
- src/agents/ : crewAI 에이전트 정의
- src/services/ : 비즈니스 로직 (slack_service.py 등)
- src/schemas/ : Pydantic 모델 (입출력 타입 정의)
- src/tools/ : 외부 API 래퍼 (Yahoo Finance, DART, FRED, Slack 등)
- src/crews/ : crewAI Crew 조합 및 실행
- src/config/ : agents.yaml, tasks.yaml
- tests/ : pytest 테스트

## 코딩 컨벤션
- 타입 힌트 필수
- 각 모듈은 if __name__ == "__main__": 으로 독립 실행 가능
- 환경변수는 python-dotenv로 .env에서 로드
- 에러: try/except + logging, 한 모듈 실패가 전체를 중단시키지 않음
- docstring 필수 (Google 스타일, Args/Returns/Raises 포함)
- 모든 .py 파일 상단에 모듈 설명 docstring
- 복잡한 로직에 "왜(why)" 설명하는 인라인 주석
- Pydantic Field(description="...") 모든 스키마 필드에 필수
- import 순서: stdlib → third-party → local
- 한 함수 30줄 이내
- bare except 금지 (구체적 Exception 사용)
- 하드코딩 금지, 상수 분리
- sudo 사용 금지

## 현재 개발 단계
Step 2: 미국주식 배당락일 모듈 + Slack E2E 연동

## 환경변수
- SLACK_WEBHOOK_URL, SLACK_BOT_TOKEN, SLACK_APP_TOKEN
- SLACK_CHANNEL (#daily-digest)
- ANTHROPIC_API_KEY
