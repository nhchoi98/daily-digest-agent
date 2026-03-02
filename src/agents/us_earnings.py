"""crewAI 미국 실적발표 일정 스캐너 Agent 정의 모듈.

실적발표 예정 종목을 스캔하여 EPS 추정치, 서프라이즈 이력 등
실적 관련 정보를 수집하는 crewAI Agent를 정의한다.
EarningsService를 crewAI Tool로 래핑하여 사용한다.
"""

import logging

from crewai import Agent
from crewai.tools import BaseTool
from pydantic import Field

from src.services.earnings_service import EarningsService

logger = logging.getLogger(__name__)


class ScanEarningsTool(BaseTool):
    """실적발표 예정 종목을 스캔하는 crewAI Tool.

    EarningsService.scan_earnings()를 래핑하여
    crewAI Agent가 실적발표 데이터를 수집할 수 있게 한다.

    Attributes:
        name: 도구 이름.
        description: 도구 설명.
        scan_days: 실적발표 스캔 범위 (일).
    """

    name: str = Field(
        default="scan_us_earnings",
        description="crewAI에서 이 도구를 식별하는 고유 이름",
    )
    description: str = Field(
        default=(
            "미국 주요 종목의 실적발표 일정을 스캔한다. "
            "S&P 100 구성종목 중 향후 2주 내 실적발표 예정인 "
            "종목의 EPS 추정치와 서프라이즈 이력을 반환한다."
        ),
        description="Agent가 이 도구의 사용 시점을 판단하기 위한 설명",
    )
    scan_days: int = Field(
        default=14,
        description="실적발표 스캔 범위 (일)",
    )

    def _run(self, query: str = "") -> str:
        """실적발표 예정 종목을 스캔하여 결과를 문자열로 반환한다.

        crewAI Agent는 도구 실행 결과를 문자열로 받으므로
        스캔 결과를 읽기 쉬운 형태로 포맷팅하여 반환한다.

        모든 예외를 내부에서 catch하여 실패 메시지를 반환하므로
        호출자에게 예외가 전파되지 않는다.

        Args:
            query: crewAI Agent가 전달하는 쿼리 문자열 (사용하지 않음).

        Returns:
            스캔 결과 문자열.
        """
        try:
            service = EarningsService(scan_days=self.scan_days)
            result = service.scan_earnings()

            if not result.stocks:
                return f"향후 {self.scan_days}일 이내 실적발표 예정 종목 없음"

            lines = [
                f"실적발표 예정 종목 ({len(result.stocks)}개):"
            ]
            for stock in result.stocks:
                timing = stock.earnings_timing or "TAS"
                eps_str = (
                    f"EPS 추정 ${stock.eps_estimate:.2f}"
                    if stock.eps_estimate is not None
                    else "EPS N/A"
                )
                lines.append(
                    f"  - {stock.ticker} ({stock.company_name}): "
                    f"{stock.earnings_date} {timing} | {eps_str}"
                )
            return "\n".join(lines)
        except (ConnectionError, ValueError, TypeError, OSError) as e:
            logger.error("실적발표 스캔 도구 실행 실패: %s", e)
            return f"스캔 실패: {e}"


def create_us_earnings_agent() -> Agent:
    """미국 실적발표 일정 스캐너 Agent를 생성한다.

    실적발표 예정 종목을 스캔하여 EPS 추정치와 서프라이즈 이력을
    수집하는 crewAI Agent를 구성하여 반환한다.

    Returns:
        Agent: 구성 완료된 crewAI Agent 인스턴스.

    Raises:
        ValueError: crewAI에 LLM 설정이 누락된 경우.
    """
    tool = ScanEarningsTool()

    return Agent(
        role="US Earnings Calendar Scanner",
        goal=(
            "미국 주요 종목의 실적발표 일정과 EPS 추정치를 수집하여 "
            "투자자가 실적 시즌을 대비할 수 있도록 정보를 제공한다."
        ),
        backstory=(
            "당신은 미국 주식 시장의 실적발표 전문가입니다. "
            "매일 실적발표가 예정된 주요 종목을 스캔하여 "
            "팀원들이 실적 시즌의 주요 이벤트를 놓치지 않도록 돕습니다."
        ),
        tools=[tool],
        verbose=True,
        allow_delegation=False,
    )


if __name__ == "__main__":
    """US Earnings Agent 생성 및 정보를 출력한다."""
    logging.basicConfig(level=logging.INFO)

    agent = create_us_earnings_agent()

    print(f"Role: {agent.role}")
    print(f"Goal: {agent.goal}")
    print(f"Tools: {[t.name for t in agent.tools]}")
