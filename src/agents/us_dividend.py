"""crewAI 미국 고배당주 스캐너 Agent 정의 모듈.

배당락일 임박 종목을 스캔하여 투자 정보를 수집하는
crewAI Agent를 정의한다.
DividendService를 crewAI Tool로 래핑하여 사용한다.
"""

import logging

from crewai import Agent
from crewai.tools import BaseTool
from pydantic import Field

from src.services.dividend_service import DividendService

logger = logging.getLogger(__name__)


class ScanDividendsTool(BaseTool):
    """배당락일 임박 종목을 스캔하는 crewAI Tool.

    DividendService.scan_dividends()를 래핑하여
    crewAI Agent가 배당 데이터를 수집할 수 있게 한다.

    Attributes:
        name: 도구 이름.
        description: 도구 설명.
        scan_days: 배당락일 스캔 범위 (일).
    """

    name: str = Field(
        default="scan_us_dividends",
        description="crewAI에서 이 도구를 식별하는 고유 이름",
    )
    description: str = Field(
        default=(
            "미국 주식 중 배당락일이 임박한 고배당 종목을 스캔한다. "
            "배당수익률 3% 이상, 시가총액 $1B 이상 종목만 반환한다."
        ),
        description="Agent가 이 도구의 사용 시점을 판단하기 위한 설명",
    )
    scan_days: int = Field(
        default=3,
        description="배당락일 스캔 범위 (일)",
    )

    def _run(self, query: str = "") -> str:
        """배당락일 임박 종목을 스캔하여 결과를 문자열로 반환한다.

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
            service = DividendService(scan_days=self.scan_days)
            result = service.scan_dividends()

            if not result.stocks:
                return f"향후 {self.scan_days}일 이내 배당락일 임박 종목 없음"

            lines = [
                f"배당락일 임박 종목 ({len(result.stocks)}개):"
            ]
            for stock in result.stocks:
                lines.append(
                    f"  - {stock.ticker} ({stock.company_name}): "
                    f"수익률 {stock.dividend_yield:.1f}%, "
                    f"배당락일 {stock.ex_dividend_date}"
                )
            return "\n".join(lines)
        except (ConnectionError, ValueError, TypeError, OSError) as e:
            logger.error("배당 스캔 도구 실행 실패: %s", e)
            return f"스캔 실패: {e}"


def create_us_dividend_agent() -> Agent:
    """미국 고배당주 스캐너 Agent를 생성한다.

    배당락일 임박 종목을 스캔하여 투자 정보를 수집하는
    crewAI Agent를 구성하여 반환한다.

    Returns:
        Agent: 구성 완료된 crewAI Agent 인스턴스.

    Raises:
        ValueError: crewAI에 LLM 설정이 누락된 경우.
    """
    tool = ScanDividendsTool()

    return Agent(
        role="US Dividend Stock Scanner",
        goal=(
            "미국 주식 중 배당락일이 임박한 고배당 종목을 찾아 "
            "투자자에게 유용한 정보를 제공한다."
        ),
        backstory=(
            "당신은 미국 주식 시장의 배당 전문가입니다. "
            "매일 배당락일이 다가오는 고배당 종목을 스캔하여 "
            "팀원들이 배당 투자 기회를 놓치지 않도록 돕습니다."
        ),
        tools=[tool],
        verbose=True,
        allow_delegation=False,
    )


if __name__ == "__main__":
    """US Dividend Agent 생성 및 정보를 출력한다."""
    logging.basicConfig(level=logging.INFO)

    agent = create_us_dividend_agent()

    print(f"Role: {agent.role}")
    print(f"Goal: {agent.goal}")
    print(f"Tools: {[t.name for t in agent.tools]}")
