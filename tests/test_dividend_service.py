"""DividendService 비즈니스 로직 테스트 모듈.

배당 스캔, 필터링, 정렬, Slack 포맷 변환 등
DividendService의 핵심 로직을 검증한다.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

from src.schemas.stock import DividendScanResult, DividendStock
from src.services.dividend_service import (
    DEFAULT_SCAN_DAYS,
    MAX_STOCKS,
    MIN_DIVIDEND_YIELD_PCT,
    MIN_MARKET_CAP_USD,
    DividendService,
)


def _make_raw_stock(
    ticker: str = "JNJ",
    yield_pct: float = 5.0,
    market_cap: int = 500_000_000_000,
    ex_date: str = "2026-02-20",
) -> dict[str, Any]:
    """테스트용 원시 배당 데이터 dict를 생성한다.

    Args:
        ticker: 종목 심볼.
        yield_pct: 배당수익률 (%).
        market_cap: 시가총액 (USD).
        ex_date: 배당락일 (ISO 형식).

    Returns:
        dict: yahoo_finance.get_upcoming_dividends()의 반환 형태.
    """
    return {
        "ticker": ticker,
        "company_name": f"{ticker} Corp",
        "ex_dividend_date": ex_date,
        "dividend_yield": yield_pct,
        "dividend_amount": 2.0,
        "market_cap": market_cap,
        "yahoo_finance_url": f"https://finance.yahoo.com/quote/{ticker}",
    }


def _make_stock(
    ticker: str = "JNJ",
    yield_pct: float = 5.0,
    market_cap: int = 500_000_000_000,
) -> DividendStock:
    """테스트용 DividendStock 인스턴스를 생성한다.

    Args:
        ticker: 종목 심볼.
        yield_pct: 배당수익률 (%).
        market_cap: 시가총액 (USD).

    Returns:
        DividendStock: 테스트용 인스턴스.
    """
    return DividendStock(
        ticker=ticker,
        company_name=f"{ticker} Corp",
        ex_dividend_date=date(2026, 2, 20),
        dividend_yield=yield_pct,
        dividend_amount=2.0,
        market_cap=market_cap,
        yahoo_finance_url=f"https://finance.yahoo.com/quote/{ticker}",
    )


class TestScanDividends:
    """DividendService.scan_dividends() 테스트."""

    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_returns_scan_result(
        self, mock_get: MagicMock
    ) -> None:
        """스캔 결과를 DividendScanResult로 반환한다."""
        mock_get.return_value = [
            _make_raw_stock("JNJ", yield_pct=5.0),
        ]

        service = DividendService()
        result = service.scan_dividends()

        assert isinstance(result, DividendScanResult)
        assert result.scan_range_days == DEFAULT_SCAN_DAYS

    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_filters_by_yield(
        self, mock_get: MagicMock
    ) -> None:
        """배당수익률 기준 이하 종목은 필터링된다."""
        mock_get.return_value = [
            _make_raw_stock("HIGH", yield_pct=5.0),
            _make_raw_stock("LOW", yield_pct=1.0),
        ]

        service = DividendService()
        result = service.scan_dividends()

        tickers = [s.ticker for s in result.stocks]
        assert "HIGH" in tickers
        assert "LOW" not in tickers

    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_filters_by_market_cap(
        self, mock_get: MagicMock
    ) -> None:
        """시가총액 기준 이하 종목은 필터링된다."""
        mock_get.return_value = [
            _make_raw_stock("BIG", market_cap=50_000_000_000),
            _make_raw_stock("SMALL", market_cap=100_000),
        ]

        service = DividendService()
        result = service.scan_dividends()

        tickers = [s.ticker for s in result.stocks]
        assert "BIG" in tickers
        assert "SMALL" not in tickers

    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_sorts_by_yield_descending(
        self, mock_get: MagicMock
    ) -> None:
        """배당수익률 내림차순으로 정렬한다."""
        mock_get.return_value = [
            _make_raw_stock("A", yield_pct=4.0),
            _make_raw_stock("B", yield_pct=8.0),
            _make_raw_stock("C", yield_pct=6.0),
        ]

        service = DividendService()
        result = service.scan_dividends()

        yields = [s.dividend_yield for s in result.stocks]
        assert yields == sorted(yields, reverse=True)

    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_limits_to_max_stocks(
        self, mock_get: MagicMock
    ) -> None:
        """최대 MAX_STOCKS개까지만 반환한다."""
        # MAX_STOCKS + 5개 종목 생성
        mock_get.return_value = [
            _make_raw_stock(f"T{i}", yield_pct=float(20 - i))
            for i in range(MAX_STOCKS + 5)
        ]

        service = DividendService()
        result = service.scan_dividends()

        assert len(result.stocks) <= MAX_STOCKS

    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_empty_result_on_no_data(
        self, mock_get: MagicMock
    ) -> None:
        """데이터가 없으면 빈 결과를 반환한다."""
        mock_get.return_value = []

        service = DividendService()
        result = service.scan_dividends()

        assert len(result.stocks) == 0

    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_handles_api_error(
        self, mock_get: MagicMock
    ) -> None:
        """API 오류 시 빈 결과를 반환한다 (예외 전파 안 함)."""
        mock_get.side_effect = ConnectionError("네트워크 오류")

        service = DividendService()
        result = service.scan_dividends()

        assert isinstance(result, DividendScanResult)
        assert len(result.stocks) == 0

    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_filters_applied_metadata(
        self, mock_get: MagicMock
    ) -> None:
        """적용된 필터 정보를 메타데이터에 포함한다."""
        mock_get.return_value = []

        service = DividendService()
        result = service.scan_dividends()

        assert result.filters_applied["min_yield_pct"] == MIN_DIVIDEND_YIELD_PCT
        assert result.filters_applied["min_market_cap_usd"] == MIN_MARKET_CAP_USD
        assert result.filters_applied["max_stocks"] == MAX_STOCKS

    def test_custom_scan_days(self) -> None:
        """사용자 지정 스캔 범위로 서비스를 생성한다."""
        service = DividendService(scan_days=7)
        assert service._scan_days == 7


class TestFormatForSlack:
    """DividendService.format_for_slack() 테스트."""

    def test_format_with_stocks(self) -> None:
        """종목이 있을 때 section 블록을 생성한다."""
        service = DividendService()
        result = DividendScanResult(
            stocks=[_make_stock("JNJ"), _make_stock("PFE", yield_pct=4.0)],
            scan_range_days=3,
            filters_applied={},
        )

        blocks = service.format_for_slack(result)

        assert len(blocks) == 1
        assert blocks[0].type == "section"
        assert blocks[0].text is not None
        assert "JNJ" in blocks[0].text.text
        assert "PFE" in blocks[0].text.text
        assert "2종목" in blocks[0].text.text

    def test_format_with_no_stocks(self) -> None:
        """종목이 없을 때 안내 블록을 생성한다."""
        service = DividendService()
        result = DividendScanResult(
            stocks=[],
            scan_range_days=3,
            filters_applied={},
        )

        blocks = service.format_for_slack(result)

        assert len(blocks) == 1
        assert blocks[0].type == "section"
        assert "없습니다" in blocks[0].text.text

    def test_format_includes_yield_info(self) -> None:
        """포맷에 배당수익률 정보가 포함된다."""
        service = DividendService()
        stock = _make_stock("VZ", yield_pct=5.78)
        result = DividendScanResult(
            stocks=[stock],
            scan_range_days=3,
            filters_applied={},
        )

        blocks = service.format_for_slack(result)

        assert "5.8%" in blocks[0].text.text

    def test_format_includes_moneybag_emoji(self) -> None:
        """포맷에 :moneybag: 이모지가 포함된다."""
        service = DividendService()
        result = DividendScanResult(
            stocks=[_make_stock()],
            scan_range_days=3,
            filters_applied={},
        )

        blocks = service.format_for_slack(result)

        assert ":moneybag:" in blocks[0].text.text


class TestParseRawData:
    """DividendService._parse_raw_data() 테스트."""

    def test_parse_valid_data(self) -> None:
        """유효한 원시 데이터를 DividendStock으로 변환한다."""
        service = DividendService()
        raw = [_make_raw_stock("JNJ")]

        stocks = service._parse_raw_data(raw)

        assert len(stocks) == 1
        assert isinstance(stocks[0], DividendStock)
        assert stocks[0].ticker == "JNJ"

    def test_skip_invalid_data(self) -> None:
        """유효하지 않은 데이터는 건너뛴다."""
        service = DividendService()
        raw = [
            _make_raw_stock("JNJ"),
            {"invalid": "data"},  # 필수 키 누락
        ]

        stocks = service._parse_raw_data(raw)

        assert len(stocks) == 1
        assert stocks[0].ticker == "JNJ"


class TestApplyFilters:
    """DividendService._apply_filters() 테스트."""

    def test_filter_by_min_yield(self) -> None:
        """최소 배당수익률 이하 종목을 필터링한다."""
        service = DividendService()
        stocks = [
            _make_stock("HIGH", yield_pct=5.0),
            _make_stock("LOW", yield_pct=1.0),
        ]

        filtered = service._apply_filters(stocks)

        assert len(filtered) == 1
        assert filtered[0].ticker == "HIGH"

    def test_filter_by_min_market_cap(self) -> None:
        """최소 시가총액 이하 종목을 필터링한다."""
        service = DividendService()
        stocks = [
            _make_stock("BIG", market_cap=50_000_000_000),
            _make_stock("SMALL", market_cap=100_000),
        ]

        filtered = service._apply_filters(stocks)

        assert len(filtered) == 1
        assert filtered[0].ticker == "BIG"

    def test_exact_threshold_included(self) -> None:
        """정확히 임계값인 종목은 포함된다."""
        service = DividendService()
        stocks = [
            _make_stock(
                "EXACT",
                yield_pct=MIN_DIVIDEND_YIELD_PCT,
                market_cap=MIN_MARKET_CAP_USD,
            ),
        ]

        filtered = service._apply_filters(stocks)

        assert len(filtered) == 1


class TestSortAndLimit:
    """DividendService._sort_and_limit() 테스트."""

    def test_sort_descending(self) -> None:
        """배당수익률 내림차순으로 정렬한다."""
        service = DividendService()
        stocks = [
            _make_stock("A", yield_pct=3.0),
            _make_stock("B", yield_pct=7.0),
            _make_stock("C", yield_pct=5.0),
        ]

        sorted_stocks = service._sort_and_limit(stocks)

        assert sorted_stocks[0].ticker == "B"
        assert sorted_stocks[1].ticker == "C"
        assert sorted_stocks[2].ticker == "A"

    def test_limit_count(self) -> None:
        """MAX_STOCKS개까지 제한한다."""
        service = DividendService()
        stocks = [_make_stock(f"T{i}", yield_pct=float(i)) for i in range(20)]

        sorted_stocks = service._sort_and_limit(stocks)

        assert len(sorted_stocks) == MAX_STOCKS
