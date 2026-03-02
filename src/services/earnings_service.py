"""미국 주식 실적발표 일정 비즈니스 로직 서비스 모듈.

실적발표 예정 종목 스캔, 날짜 범위 필터링, 정렬,
Slack Block Kit 포맷 변환 등 실적발표 관련 비즈니스 로직을 전담한다.
tools/yahoo_finance.py의 원시 데이터를 가공하여
의미 있는 결과로 변환한다.
"""

import logging
from datetime import date, timedelta
from typing import Any

from src.schemas.earnings import EarningsScanResult, EarningsStock
from src.schemas.slack import DigestBlock, TextObject
from src.tools.yahoo_finance import EARNINGS_TICKERS, get_upcoming_earnings

logger = logging.getLogger(__name__)

# 기본 스캔 범위 (일) — 항상 2주치 실적발표 일정을 보여준다
DEFAULT_SCAN_DAYS = 14

# Slack 메시지에 표시할 최대 종목 수
# 왜 15개인가: 실적 시즌에는 대형주가 다수 포함되므로
# 배당(10개)보다 여유 있게 설정하되 가독성을 유지한다.
MAX_STOCKS = 15

# Yahoo Finance URL 서식 (Slack mrkdwn 링크)
_YAHOO_URL_TEMPLATE = "<https://finance.yahoo.com/quote/{ticker}|{ticker}>"


class EarningsService:
    """미국 주식 실적발표 일정 스캔 및 포맷팅 서비스.

    yahoo_finance.py에서 수집한 원시 데이터를 필터링, 정렬하여
    투자자에게 유용한 실적발표 일정 정보를 제공한다.

    Attributes:
        _scan_days: 스캔 범위 (일).
    """

    def __init__(self, scan_days: int | None = None) -> None:
        """EarningsService를 초기화한다.

        Args:
            scan_days: 스캔 범위 (일). None이면 기본 14일.
        """
        self._scan_days = scan_days or DEFAULT_SCAN_DAYS

    def calculate_scan_range(self, today: date) -> tuple[date, date]:
        """고정 14일 스캔 범위를 계산한다.

        배당과 달리 요일별 동적 계산 없이 항상 고정 범위를 사용한다.

        Args:
            today: 기준 날짜.

        Returns:
            tuple[date, date]: (스캔 시작일, 스캔 종료일).
        """
        return (today, today + timedelta(days=self._scan_days))

    def scan_earnings(self) -> EarningsScanResult:
        """실적발표 예정 종목을 스캔하고 필터링한다.

        파이프라인:
        1. 원시 데이터 수집 (Yahoo Finance API)
        2. Pydantic 모델로 파싱
        3. 날짜 범위 필터링
        4. 날짜순 정렬
        5. 최대 MAX_STOCKS개 제한

        Returns:
            EarningsScanResult: 필터링된 종목 목록과 메타데이터.
        """
        today = date.today()
        start_date, end_date = self.calculate_scan_range(today)
        scan_range_days = (end_date - start_date).days

        logger.info(
            "실적발표 스캔 범위: %s ~ %s (%d일)",
            start_date, end_date, scan_range_days,
        )

        try:
            raw_data = get_upcoming_earnings(
                start_date=start_date, end_date=end_date,
            )
            stocks = self._parse_raw_data(raw_data)

            logger.info(
                "파싱 완료: %d개 종목 (전체 스캔 대상: %d개)",
                len(stocks), len(EARNINGS_TICKERS),
            )

            # 날짜 범위 필터링 (tools에서 이미 필터링하지만 안전장치)
            filtered = self._filter_by_date_range(
                stocks, start_date, end_date,
            )

            # 날짜순 정렬
            sorted_stocks = self._sort_by_date(filtered)

            # 최대 개수 제한
            sorted_stocks = sorted_stocks[:MAX_STOCKS]

            logger.info("최종 종목 수: %d", len(sorted_stocks))
        except (ConnectionError, ValueError, TypeError, OSError) as e:
            logger.error("실적발표 스캔 실패: %s", e)
            sorted_stocks = []

        return EarningsScanResult(
            stocks=sorted_stocks,
            scan_range_days=scan_range_days,
            scan_start_date=start_date,
            scan_end_date=end_date,
            total_scanned=len(EARNINGS_TICKERS),
        )

    def format_for_slack(
        self, result: EarningsScanResult
    ) -> list[DigestBlock]:
        """스캔 결과를 Slack Block Kit 형식으로 변환한다.

        각 종목에 발표 시점 이모지, EPS 추정치, 서프라이즈 이력을 포함한다.

        Args:
            result: EarningsService.scan_earnings()의 반환값.

        Returns:
            list[DigestBlock]: Slack 발송용 블록 목록.
                종목이 없으면 "해당 없음" 안내 블록을 반환한다.
        """
        if not result.stocks:
            return [self._build_empty_notice(result)]

        items = [self._format_stock_line(stock) for stock in result.stocks]
        bullet_list = "\n".join(f"  {item}" for item in items)

        title = f"미국 실적발표 일정 ({len(result.stocks)}종목)"
        markdown_text = f":calendar: *{title}*\n{bullet_list}"

        section = DigestBlock(
            type="section",
            text=TextObject(type="mrkdwn", text=markdown_text),
        )

        return [section]

    # --- Private methods ---

    def _parse_raw_data(
        self, raw_data: list[dict[str, Any]]
    ) -> list[EarningsStock]:
        """원시 dict 데이터를 EarningsStock 모델로 변환한다.

        Args:
            raw_data: yahoo_finance.get_upcoming_earnings()의 반환값.

        Returns:
            list[EarningsStock]: 변환된 종목 리스트.
                파싱 실패한 항목은 건너뛴다.
        """
        stocks: list[EarningsStock] = []
        for item in raw_data:
            try:
                stock = EarningsStock(
                    ticker=item["ticker"],
                    company_name=item["company_name"],
                    earnings_date=date.fromisoformat(item["earnings_date"]),
                    earnings_timing=item.get("earnings_timing"),
                    eps_estimate=item.get("eps_estimate"),
                    revenue_estimate=item.get("revenue_estimate"),
                    market_cap=item.get("market_cap", 0),
                    current_price=item.get("current_price", 0.0),
                    sector=item.get("sector"),
                    last_eps_actual=item.get("last_eps_actual"),
                    last_eps_estimate=item.get("last_eps_estimate"),
                    last_surprise_pct=item.get("last_surprise_pct"),
                    yahoo_finance_url=item["yahoo_finance_url"],
                )
                stocks.append(stock)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning("실적발표 종목 파싱 실패: %s", e)
        return stocks

    def _filter_by_date_range(
        self,
        stocks: list[EarningsStock],
        start: date,
        end: date,
    ) -> list[EarningsStock]:
        """날짜 범위로 필터링한다.

        Args:
            stocks: 필터링 전 종목 리스트.
            start: 시작일 (포함).
            end: 종료일 (포함).

        Returns:
            list[EarningsStock]: 범위 내 종목만 포함.
        """
        return [
            s for s in stocks
            if start <= s.earnings_date <= end
        ]

    def _sort_by_date(
        self, stocks: list[EarningsStock]
    ) -> list[EarningsStock]:
        """실적발표일 기준으로 오름차순 정렬한다.

        Args:
            stocks: 정렬 전 종목 리스트.

        Returns:
            list[EarningsStock]: 날짜순 정렬된 종목 리스트.
        """
        return sorted(stocks, key=lambda s: s.earnings_date)

    def _format_stock_line(self, stock: EarningsStock) -> str:
        """단일 종목을 Slack 메시지용 문자열로 포맷팅한다.

        발표 시점 이모지, 종목 링크, 날짜, EPS 추정치,
        직전 서프라이즈를 한 줄로 표시한다.

        Args:
            stock: 포맷팅할 실적발표 종목.

        Returns:
            Slack mrkdwn 형식의 종목 정보 문자열.
        """
        # 발표 시점 이모지
        timing_emoji = self._get_timing_emoji(stock.earnings_timing)

        url = _YAHOO_URL_TEMPLATE.format(ticker=stock.ticker)

        # 날짜 포맷: 3/5(수)
        date_str = self._format_date_with_weekday(stock.earnings_date)

        # 기본 라인: 이모지 종목 — 날짜 시점
        timing_str = stock.earnings_timing or "TAS"
        line = f"{timing_emoji} {url} — {date_str} {timing_str}"

        # EPS 추정치
        if stock.eps_estimate is not None:
            line += f" | EPS 추정 ${stock.eps_estimate:.2f}"

        # 직전 서프라이즈
        if stock.last_surprise_pct is not None:
            sign = "+" if stock.last_surprise_pct >= 0 else ""
            line += f" | 직전 서프라이즈 {sign}{stock.last_surprise_pct:.1f}%"
        else:
            line += " | 서프라이즈 N/A"

        return line

    def _get_timing_emoji(self, timing: str | None) -> str:
        """발표 시점에 맞는 이모지를 반환한다.

        Args:
            timing: 발표 시점 ("BMO", "AMC", "TAS", None).

        Returns:
            이모지 문자열.
        """
        emoji_map = {
            "BMO": ":sunrise:",       # 장전
            "AMC": ":city_sunset:",   # 장후
            "TAS": ":white_circle:",  # 미지정
        }
        return emoji_map.get(timing or "TAS", ":white_circle:")

    def _format_date_with_weekday(self, d: date) -> str:
        """날짜를 '3/5(수)' 형식으로 포맷팅한다.

        Args:
            d: 포맷팅할 날짜.

        Returns:
            포맷팅된 날짜 문자열.
        """
        weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
        weekday = weekday_names[d.weekday()]
        return f"{d.month}/{d.day}({weekday})"

    def _build_empty_notice(
        self, result: EarningsScanResult
    ) -> DigestBlock:
        """실적발표 예정 종목이 없을 때의 안내 블록을 생성한다.

        Args:
            result: 스캔 결과 (범위 정보 표시에 사용).

        Returns:
            section 타입의 DigestBlock.
        """
        start = result.scan_start_date or "N/A"
        end = result.scan_end_date or "N/A"
        return DigestBlock(
            type="section",
            text=TextObject(
                type="mrkdwn",
                text=(
                    ":calendar: *미국 실적발표 일정*\n"
                    f"  {start} ~ {end} 범위에 "
                    f"실적발표 예정 종목이 없습니다."
                ),
            ),
        )


if __name__ == "__main__":
    """EarningsService 파이프라인 전체를 테스트한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    service = EarningsService()

    # 기본 14일 범위 스캔
    result = service.scan_earnings()

    print(f"\n=== 스캔 결과 ({len(result.stocks)}개 종목) ===")
    print(f"스캔 범위: {result.scan_start_date} ~ {result.scan_end_date}")
    print(f"전체 스캔 대상: {result.total_scanned}개")

    for stock in result.stocks:
        timing = stock.earnings_timing or "TAS"
        eps_str = f"${stock.eps_estimate:.2f}" if stock.eps_estimate else "N/A"
        surprise_str = (
            f"{stock.last_surprise_pct:+.1f}%"
            if stock.last_surprise_pct is not None
            else "N/A"
        )
        print(
            f"  {stock.ticker:5s} | {stock.company_name:30s} | "
            f"{stock.earnings_date} {timing:3s} | "
            f"EPS 추정: {eps_str} | 서프라이즈: {surprise_str}"
        )

    # Slack 포맷 확인
    blocks = service.format_for_slack(result)
    for block in blocks:
        print(f"\nSlack 블록: {block.to_slack_dict()}")
