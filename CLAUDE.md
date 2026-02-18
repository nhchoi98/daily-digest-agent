[200~cat > CLAUDE.md << 'CLAUDEMD'
# Daily Digest Agent

## 프로젝트 개요
매일 아침 국내/미국 주식 정보 + 프로그래밍 트렌드를 수집하여 Slack으로 발송하는 자동화 시스템.
crewAI 프레임워크로 에이전트를 구성하고, GitHub Actions로 스케줄 실행한다.

## 기술 스택
- Python 3.11, FastAPI, crewAI
- GitHub Actions (스케줄러)
- Slack Webhook (알림)

## 디렉토리 구조
- app/ : FastAPI 서버 (routers/health.py, routers/digest.py)
- src/agents/ : crewAI 에이전트 정의
- src/tools/ : 외부 API 래퍼 (Yahoo Finance, DART, FRED, Slack 등)
- src/crews/ : crewAI Crew 조합 및 실행
- src/config/ : agents.yaml, tasks.yaml
- tests/ : 테스트 코드

## 코딩 컨벤션
- 타입 힌트 필수
- 각 모듈은 `if __name__ == "__main__":` 으로 독립 실행 가능
- 환경변수는 python-dotenv로 .env에서 로드
- 에러 처리: try/except + logging 필수, 한 모듈 실패가 전체를 중단시키지 않음
- docstring 필수 (Google 스타일)
- sudo 사용 금지

## 현재 개발 단계
Phase 1: Step 1(슬랙) → Step 2(미국배당) → Step 3(미국실적)
Phase 2: Step 3.5(미니Crew+슬랙E2E) → Step 7(GitHub Actions)
Phase 3: Step 4(국내실적) → Step 5(금리) → Step 6(개발트렌드)

## 환경변수
- SLACK_WEBHOOK_URL : Slack Incoming Webhook URL
- ANTHROPIC_API_KEY : crewAI LLM 호출용
- DART_API_KEY : 국내주식 DART API (Phase 3)
- FRED_API_KEY : 미국 금리 FRED API (Phase 3)

