"""crewAI 금리 모니터링 Agent 정의 모듈.

미국/한국 금리 동향을 모니터링하여 투자 정보를 제공하는
crewAI Agent를 정의한다.
RateService를 crewAI Tool로 래핑하여 사용한다.
"""

import logging

from crewai import Agent
from crewai.tools import BaseTool
from pydantic import Field

from src.services.rate_service import RateService

logger = logging.getLogger(__name__)


class MonitorRatesTool(BaseTool):
    """미국/한국 금리를 모니터링하는 crewAI Tool.

    RateService.monitor_rates()를 래핑하여
    crewAI Agent가 금리 데이터를 수집할 수 있게 한다.

    Attributes:
        name: 도구 이름.
        description: 도구 설명.
    """

    name: str = Field(
        default="monitor_interest_rates",
        description="crewAI에서 이 도구를 식별하는 고유 이름",
    )
    description: str = Field(
        default=(
            "미국(FRED)과 한국(BOK) 주요 금리 지표를 조회한다. "
            "연방기금금리, 국채 수익률, 기준금리, 수익률 곡선 상태를 반환한다."
        ),
        description="Agent가 이 도구의 사용 시점을 판단하기 위한 설명",
    )

    def _run(self, query: str = "") -> str:
        """금리를 모니터링하여 결과를 문자열로 반환한다.

        모든 예외를 내부에서 catch하여 실패 메시지를 반환하므로
        호출자에게 예외가 전파되지 않는다.

        Args:
            query: crewAI Agent가 전달하는 쿼리 문자열 (사용하지 않음).

        Returns:
            모니터링 결과 문자열.
        """
        try:
            service = RateService()
            result = service.monitor_rates()

            lines: list[str] = ["금리 모니터링 결과:"]

            if result.us_rates:
                lines.append("\n[미국 금리]")
                for rate in result.us_rates:
                    change = (
                        f" (1W: {rate.change_1w:+.2f}pp)"
                        if rate.change_1w is not None
                        else ""
                    )
                    lines.append(
                        f"  - {rate.name}: {rate.value:.2f}%{change}"
                    )

            if result.yield_curve:
                curve = result.yield_curve
                lines.append(
                    f"\n[수익률 곡선] {curve.status} "
                    f"(스프레드: {curve.spread_10y_2y:+.2f}pp)"
                )

            if result.kr_rates:
                lines.append("\n[한국 금리]")
                for rate in result.kr_rates:
                    change = (
                        f" (1W: {rate.change_1w:+.2f}pp)"
                        if rate.change_1w is not None
                        else ""
                    )
                    lines.append(
                        f"  - {rate.name}: {rate.value:.2f}%{change}"
                    )

            if not result.us_rates and not result.kr_rates:
                return "금리 데이터를 가져올 수 없습니다."

            return "\n".join(lines)
        except (ConnectionError, ValueError, TypeError, OSError) as e:
            logger.error("금리 모니터링 도구 실행 실패: %s", e)
            return f"모니터링 실패: {e}"


def create_rate_monitor_agent() -> Agent:
    """금리 모니터링 Agent를 생성한다.

    미국/한국 금리 동향을 모니터링하여 투자 정보를 제공하는
    crewAI Agent를 구성하여 반환한다.

    Returns:
        Agent: 구성 완료된 crewAI Agent 인스턴스.

    Raises:
        ValueError: crewAI에 LLM 설정이 누락된 경우.
    """
    tool = MonitorRatesTool()

    return Agent(
        role="Interest Rate Monitor",
        goal=(
            "미국과 한국의 주요 금리 지표를 모니터링하여 "
            "금리 변동과 수익률 곡선 상태를 팀에 보고한다."
        ),
        backstory=(
            "당신은 채권 시장과 금리 동향 전문 애널리스트입니다. "
            "매일 미국 연방기금금리, 국채 수익률, 한국 기준금리를 "
            "추적하여 금리 변동이 투자에 미치는 영향을 분석합니다. "
            "수익률 곡선 역전 같은 경기침체 신호도 감지합니다."
        ),
        tools=[tool],
        verbose=True,
        allow_delegation=False,
    )


if __name__ == "__main__":
    """Rate Monitor Agent 생성 및 정보를 출력한다."""
    logging.basicConfig(level=logging.INFO)

    agent = create_rate_monitor_agent()

    print(f"Role: {agent.role}")
    print(f"Goal: {agent.goal}")
    print(f"Tools: {[t.name for t in agent.tools]}")
