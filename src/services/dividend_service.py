"""미국 주식 배당락일 비즈니스 로직 서비스 모듈.

배당 종목 스캔, 필터링, 정렬, Slack 포맷 변환 등
배당 관련 비즈니스 로직을 전담한다.
tools/yahoo_finance.py의 원시 데이터를 가공하여
의미 있는 결과로 변환한다.
"""

import logging
from datetime import date
from typing import Any

from src.schemas.slack import DigestBlock, TextObject
from src.schemas.stock import DividendScanResult, DividendStock
from src.tools.yahoo_finance import get_upcoming_dividends

logger = logging.getLogger(__name__)

# 필터링 기준 상수
# 왜 3%인가: 미국 S&P 500 평균 배당수익률(~1.5%)의 약 2배로,
# 고배당주에 관심 있는 투자자에게 의미 있는 수준이다.
MIN_DIVIDEND_YIELD_PCT = 3.0

# 왜 $1B인가: 시가총액 $1B 이상은 미드캡 이상의 안정적인 기업으로,
# 배당 지속 가능성이 높다.
MIN_MARKET_CAP_USD = 1_000_000_000

# 왜 10개인가: Slack 메시지의 가독성을 위해
# 과도한 종목 수를 제한한다.
MAX_STOCKS = 10

# 기본 스캔 범위 (일)
DEFAULT_SCAN_DAYS = 3

# Yahoo Finance URL 서식
_YAHOO_URL_TEMPLATE = "<https://finance.yahoo.com/quote/{ticker}|{ticker}>"


class DividendService:
    """미국 주식 배당락일 스캔 및 포맷팅 서비스.

    yahoo_finance.py에서 수집한 원시 데이터를 필터링, 정렬하여
    투자자에게 유용한 배당락일 정보를 제공한다.

    Attributes:
        _scan_days: 배당락일 스캔 범위 (일).
    """

    def __init__(self, scan_days: int = DEFAULT_SCAN_DAYS) -> None:
        """DividendService를 초기화한다.

        Args:
            scan_days: 오늘로부터 며칠 이내의 배당락일을 스캔할지.
        """
        self._scan_days = scan_days

    def scan_dividends(self) -> DividendScanResult:
        """배당락일 임박 종목을 스캔하고 필터링한다.

        yahoo_finance.py에서 원시 데이터를 수집한 후:
        1. DividendStock Pydantic 모델로 변환
        2. 배당수익률 >= MIN_DIVIDEND_YIELD_PCT 필터
        3. 시가총액 >= MIN_MARKET_CAP_USD 필터
        4. 수익률 내림차순 정렬
        5. 최대 MAX_STOCKS개 제한

        내부에서 예외를 catch하여 빈 결과를 반환하므로
        호출자에게 예외가 전파되지 않는다.

        Returns:
            DividendScanResult: 필터링된 종목 목록과 메타데이터.
        """
        filters = {
            "min_yield_pct": MIN_DIVIDEND_YIELD_PCT,
            "min_market_cap_usd": MIN_MARKET_CAP_USD,
            "max_stocks": MAX_STOCKS,
        }

        try:
            raw_data = get_upcoming_dividends(days_ahead=self._scan_days)
            stocks = self._parse_raw_data(raw_data)
            filtered = self._apply_filters(stocks)
            sorted_stocks = self._sort_and_limit(filtered)
        except (ConnectionError, ValueError, TypeError, OSError) as e:
            logger.error("배당 스캔 실패: %s", e)
            sorted_stocks = []

        return DividendScanResult(
            stocks=sorted_stocks,
            scan_range_days=self._scan_days,
            filters_applied=filters,
        )

    def format_for_slack(
        self, result: DividendScanResult
    ) -> list[DigestBlock]:
        """스캔 결과를 Slack Block Kit 형식으로 변환한다.

        Args:
            result: DividendService.scan_dividends()의 반환값.

        Returns:
            list[DigestBlock]: Slack 발송용 블록 목록.
                종목이 없으면 "해당 없음" 안내 블록을 반환한다.
        """
        if not result.stocks:
            return [self._build_empty_notice()]

        items = [self._format_stock_line(stock) for stock in result.stocks]
        # 제목과 불릿 리스트를 마크다운으로 조합
        bullet_list = "\n".join(f"  • {item}" for item in items)
        title = f"미국 배당락일 임박 ({len(result.stocks)}종목)"
        markdown_text = f":moneybag: *{title}*\n{bullet_list}"

        section = DigestBlock(
            type="section",
            text=TextObject(type="mrkdwn", text=markdown_text),
        )

        return [section]

    def _parse_raw_data(
        self, raw_data: list[dict[str, Any]]
    ) -> list[DividendStock]:
        """원시 dict 데이터를 DividendStock 모델로 변환한다.

        Args:
            raw_data: yahoo_finance.get_upcoming_dividends()의 반환값.

        Returns:
            list[DividendStock]: 변환된 종목 리스트.
                파싱 실패한 항목은 건너뛴다.
        """
        stocks: list[DividendStock] = []
        for item in raw_data:
            try:
                stock = DividendStock(
                    ticker=item["ticker"],
                    company_name=item["company_name"],
                    ex_dividend_date=date.fromisoformat(
                        item["ex_dividend_date"]
                    ),
                    dividend_yield=item.get("dividend_yield", 0.0),
                    dividend_amount=item.get("dividend_amount", 0.0),
                    market_cap=item.get("market_cap", 0),
                    yahoo_finance_url=item["yahoo_finance_url"],
                )
                stocks.append(stock)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning("종목 데이터 파싱 실패: %s", e)
        return stocks

    def _apply_filters(
        self, stocks: list[DividendStock]
    ) -> list[DividendStock]:
        """배당수익률과 시가총액 기준으로 필터링한다.

        필터 조건:
        - 배당수익률 >= 3% (S&P 500 평균의 약 2배, 고배당 기준)
        - 시가총액 >= $1B (미드캡 이상, 배당 지속 가능성 확보)

        Args:
            stocks: 필터링 전 종목 리스트.

        Returns:
            list[DividendStock]: 필터 조건을 충족하는 종목만 포함.
        """
        return [
            s for s in stocks
            # 3%: 고배당 기준 / $1B: 안정적 미드캡 이상 (상수 정의 참조)
            if s.dividend_yield >= MIN_DIVIDEND_YIELD_PCT
            and s.market_cap >= MIN_MARKET_CAP_USD
        ]

    def _sort_and_limit(
        self, stocks: list[DividendStock]
    ) -> list[DividendStock]:
        """수익률 내림차순 정렬 후 최대 개수를 제한한다.

        Args:
            stocks: 정렬 전 종목 리스트.

        Returns:
            list[DividendStock]: 정렬 및 제한된 종목 리스트
                (최대 MAX_STOCKS=10개).
        """
        sorted_stocks = sorted(
            stocks,
            key=lambda s: s.dividend_yield,
            reverse=True,
        )
        # 10개 제한: Slack 메시지 가독성을 위해 (상수 MAX_STOCKS 참조)
        return sorted_stocks[:MAX_STOCKS]

    def _format_stock_line(self, stock: DividendStock) -> str:
        """단일 종목을 Slack 메시지용 문자열로 포맷팅한다.

        Args:
            stock: 포맷팅할 배당 종목.

        Returns:
            Slack mrkdwn 형식의 종목 정보 문자열.
        """
        url = _YAHOO_URL_TEMPLATE.format(ticker=stock.ticker)
        return (
            f"{url} {stock.company_name} | "
            f"배당수익률 {stock.dividend_yield:.1f}% | "
            f"배당락일 {stock.ex_dividend_date}"
        )

    def _build_empty_notice(self) -> DigestBlock:
        """배당락일 임박 종목이 없을 때의 안내 블록을 생성한다.

        Returns:
            section 타입의 DigestBlock.
        """
        return DigestBlock(
            type="section",
            text=TextObject(
                type="mrkdwn",
                text=(
                    ":moneybag: *미국 배당락일 임박*\n"
                    f"  향후 {self._scan_days}일 이내 배당락일 "
                    f"임박 종목이 없습니다."
                ),
            ),
        )


if __name__ == "__main__":
    """DividendService의 scan_dividends와 format_for_slack을 테스트한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    # 기본 3일 범위로 스캔
    service = DividendService()
    result = service.scan_dividends()

    print(f"\n=== 스캔 결과 ({len(result.stocks)}개 종목) ===")
    print(f"스캔 범위: {result.scan_range_days}일")
    print(f"필터 조건: {result.filters_applied}")

    for stock in result.stocks:
        print(
            f"  {stock.ticker:5s} | {stock.company_name:30s} | "
            f"수익률 {stock.dividend_yield:.1f}% | "
            f"배당락일 {stock.ex_dividend_date}"
        )

    # 종목이 없으면 7일로 재시도
    if not result.stocks:
        print("\n--- 7일 범위로 재스캔 ---")
        service_7d = DividendService(scan_days=7)
        result_7d = service_7d.scan_dividends()
        for stock in result_7d.stocks:
            print(
                f"  {stock.ticker:5s} | {stock.company_name:30s} | "
                f"수익률 {stock.dividend_yield:.1f}% | "
                f"배당락일 {stock.ex_dividend_date}"
            )

    # Slack 포맷 확인
    blocks = service.format_for_slack(result)
    for block in blocks:
        print(f"\nSlack 블록: {block.to_slack_dict()}")
