"""Daily Digest Crew 조합 및 실행 모듈.

배당락일 스캔(DividendService) → Slack 발송(SlackService)까지
한 번에 실행하는 파이프라인을 제공한다.
crewAI Agent(us_dividend + publisher)를 조합하며,
직접 실행 모드도 지원한다.
"""

import logging
from typing import Any

from src.schemas.slack import SlackConfig
from src.services.slack_service import SlackService

logger = logging.getLogger(__name__)


def get_crew_agents(config: SlackConfig) -> dict[str, Any]:
    """Crew에 사용할 Agent들을 생성한다.

    crewAI Agent 생성에는 LLM 연동이 필요하므로,
    ANTHROPIC_API_KEY 등 LLM 설정이 없으면
    Agent 생성을 건너뛰고 빈 딕셔너리를 반환한다.

    Args:
        config: Slack 연동 설정값.

    Returns:
        dict[str, Any]: Agent 인스턴스를 담은 딕셔너리.
            키: "us_dividend", "publisher".
            LLM 설정이 없으면 빈 딕셔너리.
    """
    try:
        from src.agents.publisher import create_publisher_agent
        from src.agents.us_dividend import create_us_dividend_agent

        return {
            "us_dividend": create_us_dividend_agent(),
            "publisher": create_publisher_agent(config),
        }
    except (ImportError, ValueError) as e:
        # crewAI Agent 생성에 LLM 키가 필요하나 설정되지 않은 경우
        logger.warning("crewAI Agent 생성 스킵 (LLM 미설정): %s", e)
        return {}


def run_daily_digest(config: SlackConfig) -> None:
    """배당락일 스캔부터 슬랙 발송까지 전체 파이프라인을 실행한다.

    실행 흐름:
    1. SlackService 초기화 (DividendService 포함)
    2. 배당락일 임박 종목 스캔 (Yahoo Finance API)
    3. 필터링/정렬 후 Block Kit 메시지 구성
    4. Slack Webhook으로 발송

    서비스 레이어를 직접 호출하며, 모든 예외는
    SlackService 내부에서 처리되어 로그만 남긴다.

    Args:
        config: Slack 연동 설정값 (Webhook URL 포함).
    """
    logger.info("Daily Digest 파이프라인 시작")

    service = SlackService(config)
    result = service.run_digest()

    if result.success:
        logger.info(
            "Daily Digest 완료: %s (%.2f초)",
            result.message,
            result.duration_sec,
        )
    else:
        logger.error("Daily Digest 실패: %s", result.message)


if __name__ == "__main__":
    """배당락일 스캔 → 슬랙 발송 파이프라인을 실행한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    config = SlackConfig()  # type: ignore[call-arg]

    # Agent 정보 출력 (LLM 미설정 시 스킵)
    agents = get_crew_agents(config)
    if agents:
        for name, agent in agents.items():
            print(f"Agent [{name}]: {agent.role}")
            print(f"  Tools: {[t.name for t in agent.tools]}")
    else:
        print("crewAI Agent 스킵 (LLM 미설정)")

    print("\n=== 파이프라인 실행 ===")
    run_daily_digest(config)
