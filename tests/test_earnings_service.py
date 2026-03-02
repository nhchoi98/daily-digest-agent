"""EarningsService 비즈니스 로직 테스트 모듈.

실적발표 스캔, 날짜 범위 필터링, 정렬,
Slack 포맷 변환, 빈 결과 처리 등
EarningsService의 핵심 로직을 검증한다.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

from src.schemas.earnings import EarningsScanResult, EarningsStock
from src.services.earnings_service import (
    DEFAULT_SCAN_DAYS,
    MAX_STOCKS,
    EarningsService,
)


def _make_raw_earnings(
    ticker: str = "AAPL",
    earnings_date: str = "2026-03-10",
    earnings_timing: str | None = "AMC",
    eps_estimate: float | None = 1.42,
    revenue_estimate: float | None = 94_000_000_000,
    market_cap: int = 3_500_000_000_000,
    current_price: float = 225.0,
    sector: str | None = "Technology",
    last_eps_actual: float | None = 1.40,
    last_eps_estimate: float | None = 1.35,
    last_surprise_pct: float | None = 3.7,
) -> dict[str, Any]:
    """테스트용 원시 실적발표 데이터 dict를 생성한다.

    Args:
        ticker: 종목 심볼.
        earnings_date: 실적발표일 (ISO 형식).
        earnings_timing: 발표 시점.
        eps_estimate: EPS 추정치.
        revenue_estimate: 매출 추정치.
        market_cap: 시가총액.
        current_price: 현재가.
        sector: 섹터.
        last_eps_actual: 직전 실제 EPS.
        last_eps_estimate: 직전 추정 EPS.
        last_surprise_pct: 직전 서프라이즈 %.

    Returns:
        dict: yahoo_finance.get_upcoming_earnings()의 반환 형태.
    """
    return {
        "ticker": ticker,
        "company_name": f"{ticker} Corp",
        "earnings_date": earnings_date,
        "earnings_timing": earnings_timing,
        "eps_estimate": eps_estimate,
        "revenue_estimate": revenue_estimate,
        "market_cap": market_cap,
        "current_price": current_price,
        "sector": sector,
        "last_eps_actual": last_eps_actual,
        "last_eps_estimate": last_eps_estimate,
        "last_surprise_pct": last_surprise_pct,
        "yahoo_finance_url": f"https://finance.yahoo.com/quote/{ticker}",
    }


def _make_earnings_stock(
    ticker: str = "AAPL",
    earnings_date: date | None = None,
    earnings_timing: str | None = "AMC",
    eps_estimate: float | None = 1.42,
    last_surprise_pct: float | None = 3.7,
) -> EarningsStock:
    """테스트용 EarningsStock 인스턴스를 생성한다.

    Args:
        ticker: 종목 심볼.
        earnings_date: 실적발표일.
        earnings_timing: 발표 시점.
        eps_estimate: EPS 추정치.
        last_surprise_pct: 직전 서프라이즈 %.

    Returns:
        EarningsStock: 테스트용 인스턴스.
    """
    return EarningsStock(
        ticker=ticker,
        company_name=f"{ticker} Corp",
        earnings_date=earnings_date or date(2026, 3, 10),
        earnings_timing=earnings_timing,
        eps_estimate=eps_estimate,
        revenue_estimate=94_000_000_000,
        market_cap=3_500_000_000_000,
        current_price=225.0,
        sector="Technology",
        last_eps_actual=1.40,
        last_eps_estimate=1.35,
        last_surprise_pct=last_surprise_pct,
        yahoo_finance_url=f"https://finance.yahoo.com/quote/{ticker}",
    )


class TestCalculateScanRange:
    """EarningsService.calculate_scan_range() 테스트."""

    def test_default_14_day_range(self) -> None:
        """기본 14일 범위를 반환한다."""
        service = EarningsService()
        start, end = service.calculate_scan_range(date(2026, 3, 2))

        assert start == date(2026, 3, 2)
        assert end == date(2026, 3, 16)
        assert (end - start).days == 14

    def test_custom_scan_days(self) -> None:
        """scan_days 오버라이드 시 지정된 범위를 사용한다."""
        service = EarningsService(scan_days=7)
        start, end = service.calculate_scan_range(date(2026, 3, 2))

        assert (end - start).days == 7

    def test_weekend_same_range(self) -> None:
        """주말에도 동일한 고정 범위를 사용한다."""
        service = EarningsService()
        # 토요일
        start_sat, end_sat = service.calculate_scan_range(date(2026, 3, 7))
        # 월요일
        start_mon, end_mon = service.calculate_scan_range(date(2026, 3, 9))

        assert (end_sat - start_sat).days == 14
        assert (end_mon - start_mon).days == 14


class TestScanEarnings:
    """EarningsService.scan_earnings() 테스트."""

    @patch("src.services.earnings_service.get_upcoming_earnings")
    def test_returns_scan_result(
        self, mock_get: MagicMock
    ) -> None:
        """스캔 결과를 EarningsScanResult로 반환한다."""
        mock_get.return_value = [
            _make_raw_earnings("AAPL"),
        ]

        service = EarningsService()
        result = service.scan_earnings()

        assert isinstance(result, EarningsScanResult)
        assert result.scan_start_date is not None
        assert result.scan_end_date is not None

    @patch("src.services.earnings_service.get_upcoming_earnings")
    def test_scan_result_includes_date_range(
        self, mock_get: MagicMock
    ) -> None:
        """스캔 결과에 시작일/종료일이 포함된다."""
        mock_get.return_value = []

        service = EarningsService()
        result = service.scan_earnings()

        assert result.scan_start_date is not None
        assert result.scan_end_date is not None
        assert result.scan_range_days == DEFAULT_SCAN_DAYS

    @patch("src.services.earnings_service.get_upcoming_earnings")
    def test_scan_result_includes_total_scanned(
        self, mock_get: MagicMock
    ) -> None:
        """스캔 결과에 전체 스캔 대상 종목 수가 포함된다."""
        mock_get.return_value = []

        service = EarningsService()
        result = service.scan_earnings()

        assert result.total_scanned > 0

    @patch("src.services.earnings_service.get_upcoming_earnings")
    def test_empty_result_on_no_data(
        self, mock_get: MagicMock
    ) -> None:
        """데이터가 없으면 빈 결과를 반환한다."""
        mock_get.return_value = []

        service = EarningsService()
        result = service.scan_earnings()

        assert len(result.stocks) == 0

    @patch("src.services.earnings_service.get_upcoming_earnings")
    def test_handles_api_error(
        self, mock_get: MagicMock
    ) -> None:
        """API 오류 시 빈 결과를 반환한다 (예외 전파 안 함)."""
        mock_get.side_effect = ConnectionError("네트워크 오류")

        service = EarningsService()
        result = service.scan_earnings()

        assert isinstance(result, EarningsScanResult)
        assert len(result.stocks) == 0

    @patch("src.services.earnings_service.get_upcoming_earnings")
    def test_limits_to_max_stocks(
        self, mock_get: MagicMock
    ) -> None:
        """최대 MAX_STOCKS개까지만 반환한다."""
        mock_get.return_value = [
            _make_raw_earnings(
                f"T{i:02d}",
                earnings_date=f"2026-03-{(i % 14) + 2:02d}",
            )
            for i in range(MAX_STOCKS + 5)
        ]

        service = EarningsService()
        result = service.scan_earnings()

        assert len(result.stocks) <= MAX_STOCKS

    @patch("src.services.earnings_service.get_upcoming_earnings")
    def test_sorted_by_date(
        self, mock_get: MagicMock
    ) -> None:
        """결과가 날짜순으로 정렬된다."""
        mock_get.return_value = [
            _make_raw_earnings("LATE", earnings_date="2026-03-12"),
            _make_raw_earnings("EARLY", earnings_date="2026-03-05"),
            _make_raw_earnings("MID", earnings_date="2026-03-08"),
        ]

        service = EarningsService()
        result = service.scan_earnings()

        if len(result.stocks) >= 2:
            dates = [s.earnings_date for s in result.stocks]
            assert dates == sorted(dates)


class TestParseRawData:
    """EarningsService._parse_raw_data() 테스트."""

    def test_parse_valid_data(self) -> None:
        """유효한 원시 데이터를 EarningsStock으로 변환한다."""
        service = EarningsService()
        raw = [_make_raw_earnings("AAPL")]

        stocks = service._parse_raw_data(raw)

        assert len(stocks) == 1
        assert isinstance(stocks[0], EarningsStock)
        assert stocks[0].ticker == "AAPL"

    def test_skip_invalid_data(self) -> None:
        """유효하지 않은 데이터는 건너뛴다."""
        service = EarningsService()
        raw = [
            _make_raw_earnings("AAPL"),
            {"invalid": "data"},
        ]

        stocks = service._parse_raw_data(raw)

        assert len(stocks) == 1
        assert stocks[0].ticker == "AAPL"

    def test_parse_includes_eps_estimate(self) -> None:
        """파싱 결과에 eps_estimate가 포함된다."""
        service = EarningsService()
        raw = [_make_raw_earnings("AAPL", eps_estimate=1.42)]

        stocks = service._parse_raw_data(raw)

        assert stocks[0].eps_estimate == 1.42

    def test_parse_none_eps_estimate(self) -> None:
        """EPS 추정치가 없으면 None으로 설정된다."""
        service = EarningsService()
        raw = [_make_raw_earnings("AAPL", eps_estimate=None)]

        stocks = service._parse_raw_data(raw)

        assert stocks[0].eps_estimate is None

    def test_parse_includes_surprise(self) -> None:
        """파싱 결과에 서프라이즈 데이터가 포함된다."""
        service = EarningsService()
        raw = [_make_raw_earnings(
            "AAPL",
            last_eps_actual=1.40,
            last_eps_estimate=1.35,
            last_surprise_pct=3.7,
        )]

        stocks = service._parse_raw_data(raw)

        assert stocks[0].last_eps_actual == 1.40
        assert stocks[0].last_eps_estimate == 1.35
        assert stocks[0].last_surprise_pct == 3.7


class TestFilterByDateRange:
    """EarningsService._filter_by_date_range() 테스트."""

    def test_filter_within_range(self) -> None:
        """범위 내 종목만 반환한다."""
        service = EarningsService()
        stocks = [
            _make_earnings_stock("IN", earnings_date=date(2026, 3, 5)),
            _make_earnings_stock("OUT", earnings_date=date(2026, 4, 1)),
        ]

        filtered = service._filter_by_date_range(
            stocks, date(2026, 3, 2), date(2026, 3, 16),
        )

        assert len(filtered) == 1
        assert filtered[0].ticker == "IN"

    def test_boundary_dates_included(self) -> None:
        """시작일과 종료일 경계값도 포함된다."""
        service = EarningsService()
        stocks = [
            _make_earnings_stock("START", earnings_date=date(2026, 3, 2)),
            _make_earnings_stock("END", earnings_date=date(2026, 3, 16)),
        ]

        filtered = service._filter_by_date_range(
            stocks, date(2026, 3, 2), date(2026, 3, 16),
        )

        assert len(filtered) == 2


class TestSortByDate:
    """EarningsService._sort_by_date() 테스트."""

    def test_sorts_ascending(self) -> None:
        """날짜 오름차순으로 정렬한다."""
        service = EarningsService()
        stocks = [
            _make_earnings_stock("C", earnings_date=date(2026, 3, 12)),
            _make_earnings_stock("A", earnings_date=date(2026, 3, 5)),
            _make_earnings_stock("B", earnings_date=date(2026, 3, 8)),
        ]

        sorted_stocks = service._sort_by_date(stocks)

        assert [s.ticker for s in sorted_stocks] == ["A", "B", "C"]


class TestFormatForSlack:
    """EarningsService.format_for_slack() 테스트."""

    def test_format_with_stocks(self) -> None:
        """종목이 있을 때 section 블록을 생성한다."""
        service = EarningsService()
        result = EarningsScanResult(
            stocks=[
                _make_earnings_stock("AAPL"),
                _make_earnings_stock("MSFT"),
            ],
            scan_range_days=14,
            total_scanned=102,
        )

        blocks = service.format_for_slack(result)

        assert len(blocks) == 1
        assert blocks[0].type == "section"
        assert blocks[0].text is not None
        assert "AAPL" in blocks[0].text.text
        assert "MSFT" in blocks[0].text.text
        assert "2종목" in blocks[0].text.text

    def test_format_with_no_stocks(self) -> None:
        """종목이 없을 때 안내 블록을 생성한다."""
        service = EarningsService()
        result = EarningsScanResult(
            stocks=[],
            scan_range_days=14,
            scan_start_date=date(2026, 3, 2),
            scan_end_date=date(2026, 3, 16),
            total_scanned=102,
        )

        blocks = service.format_for_slack(result)

        assert len(blocks) == 1
        assert blocks[0].type == "section"
        assert "없습니다" in blocks[0].text.text

    def test_format_includes_calendar_emoji(self) -> None:
        """포맷에 :calendar: 이모지가 포함된다."""
        service = EarningsService()
        result = EarningsScanResult(
            stocks=[_make_earnings_stock()],
            scan_range_days=14,
            total_scanned=102,
        )

        blocks = service.format_for_slack(result)

        assert ":calendar:" in blocks[0].text.text

    def test_format_includes_eps_estimate(self) -> None:
        """포맷에 EPS 추정치가 포함된다."""
        service = EarningsService()
        result = EarningsScanResult(
            stocks=[_make_earnings_stock(eps_estimate=1.42)],
            scan_range_days=14,
            total_scanned=102,
        )

        blocks = service.format_for_slack(result)

        assert "EPS 추정 $1.42" in blocks[0].text.text

    def test_format_includes_surprise(self) -> None:
        """포맷에 서프라이즈 정보가 포함된다."""
        service = EarningsService()
        result = EarningsScanResult(
            stocks=[_make_earnings_stock(last_surprise_pct=4.2)],
            scan_range_days=14,
            total_scanned=102,
        )

        blocks = service.format_for_slack(result)

        assert "서프라이즈 +4.2%" in blocks[0].text.text

    def test_format_surprise_na(self) -> None:
        """서프라이즈 데이터가 없으면 N/A가 표시된다."""
        service = EarningsService()
        result = EarningsScanResult(
            stocks=[_make_earnings_stock(last_surprise_pct=None)],
            scan_range_days=14,
            total_scanned=102,
        )

        blocks = service.format_for_slack(result)

        assert "서프라이즈 N/A" in blocks[0].text.text

    def test_format_includes_timing_emoji(self) -> None:
        """BMO/AMC에 맞는 이모지가 포함된다."""
        service = EarningsService()

        # AMC
        result_amc = EarningsScanResult(
            stocks=[_make_earnings_stock(earnings_timing="AMC")],
            scan_range_days=14,
            total_scanned=102,
        )
        blocks_amc = service.format_for_slack(result_amc)
        assert ":city_sunset:" in blocks_amc[0].text.text

        # BMO
        result_bmo = EarningsScanResult(
            stocks=[_make_earnings_stock(earnings_timing="BMO")],
            scan_range_days=14,
            total_scanned=102,
        )
        blocks_bmo = service.format_for_slack(result_bmo)
        assert ":sunrise:" in blocks_bmo[0].text.text

    def test_empty_notice_shows_date_range(self) -> None:
        """빈 결과 안내에 스캔 날짜 범위가 표시된다."""
        service = EarningsService()
        result = EarningsScanResult(
            stocks=[],
            scan_range_days=14,
            scan_start_date=date(2026, 3, 2),
            scan_end_date=date(2026, 3, 16),
            total_scanned=102,
        )

        blocks = service.format_for_slack(result)

        assert "2026-03-02" in blocks[0].text.text
        assert "2026-03-16" in blocks[0].text.text


class TestFormatDateWithWeekday:
    """EarningsService._format_date_with_weekday() 테스트."""

    def test_format_monday(self) -> None:
        """월요일 날짜를 '3/2(월)' 형식으로 포맷팅한다."""
        service = EarningsService()
        result = service._format_date_with_weekday(date(2026, 3, 2))
        assert result == "3/2(월)"

    def test_format_wednesday(self) -> None:
        """수요일 날짜를 '3/4(수)' 형식으로 포맷팅한다."""
        service = EarningsService()
        result = service._format_date_with_weekday(date(2026, 3, 4))
        assert result == "3/4(수)"


class TestGetTimingEmoji:
    """EarningsService._get_timing_emoji() 테스트."""

    def test_bmo_emoji(self) -> None:
        """BMO는 :sunrise: 이모지."""
        service = EarningsService()
        assert service._get_timing_emoji("BMO") == ":sunrise:"

    def test_amc_emoji(self) -> None:
        """AMC는 :city_sunset: 이모지."""
        service = EarningsService()
        assert service._get_timing_emoji("AMC") == ":city_sunset:"

    def test_tas_emoji(self) -> None:
        """TAS는 :white_circle: 이모지."""
        service = EarningsService()
        assert service._get_timing_emoji("TAS") == ":white_circle:"

    def test_none_emoji(self) -> None:
        """None은 :white_circle: 이모지."""
        service = EarningsService()
        assert service._get_timing_emoji(None) == ":white_circle:"
