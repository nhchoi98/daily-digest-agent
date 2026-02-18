"""Yahoo Finance 배당 데이터 수집 모듈 테스트.

yfinance API를 mock하여 배당락일 수집, 범위 필터링,
에러 처리 등을 검증한다.
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from src.tools.yahoo_finance import (
    DIVIDEND_TICKERS,
    _fetch_ticker_dividend_info,
    get_upcoming_dividends,
)


def _make_yfinance_info(
    ticker: str = "JNJ",
    ex_div_days_from_today: int = 1,
    dividend_yield: float = 3.5,
    market_cap: int = 400_000_000_000,
) -> dict[str, Any]:
    """테스트용 yfinance info dict를 생성한다.

    Args:
        ticker: 종목 심볼.
        ex_div_days_from_today: 오늘로부터 며칠 후 배당락일인지.
        dividend_yield: 배당수익률 (%, yfinance가 반환하는 그대로).
        market_cap: 시가총액 (USD).

    Returns:
        dict: yfinance Ticker.info 형태의 dict.
    """
    from datetime import timezone

    ex_date = date.today() + timedelta(days=ex_div_days_from_today)
    # yfinance는 exDividendDate를 Unix timestamp(초)로 반환
    from datetime import datetime

    timestamp = int(
        datetime(
            ex_date.year, ex_date.month, ex_date.day,
            tzinfo=timezone.utc,
        ).timestamp()
    )

    return {
        "shortName": f"{ticker} Corp",
        "exDividendDate": timestamp,
        "dividendYield": dividend_yield,
        "dividendRate": 2.0,
        "marketCap": market_cap,
        "currentPrice": 150.0,
        "lastDividendValue": 0.50,
    }


class TestGetUpcomingDividends:
    """get_upcoming_dividends() 테스트."""

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_stocks_in_range(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """스캔 범위 내 배당락일 종목을 반환한다."""
        mock_info = _make_yfinance_info(
            ticker="JNJ", ex_div_days_from_today=1,
        )
        mock_ticker_cls.return_value.info = mock_info

        today = date.today()
        end_date = today + timedelta(days=3)
        results = get_upcoming_dividends(
            start_date=today, end_date=end_date,
        )

        # DIVIDEND_TICKERS의 모든 종목이 같은 mock을 반환하므로
        # 모든 종목이 결과에 포함된다
        assert len(results) == len(DIVIDEND_TICKERS)
        assert results[0]["ticker"] == DIVIDEND_TICKERS[0]

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_excludes_stocks_outside_range(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """스캔 범위 밖의 배당락일 종목은 제외한다."""
        # 30일 후 배당락일 → 3일 범위에 포함되지 않음
        mock_info = _make_yfinance_info(ex_div_days_from_today=30)
        mock_ticker_cls.return_value.info = mock_info

        today = date.today()
        end_date = today + timedelta(days=3)
        results = get_upcoming_dividends(
            start_date=today, end_date=end_date,
        )

        assert len(results) == 0

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_default_dates_when_none(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """start_date/end_date 미지정 시 기본값을 사용한다."""
        mock_info = _make_yfinance_info(ex_div_days_from_today=1)
        mock_ticker_cls.return_value.info = mock_info

        results = get_upcoming_dividends()

        assert len(results) == len(DIVIDEND_TICKERS)

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_skips_stock_without_ex_dividend_date(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """exDividendDate가 없는 종목은 건너뛴다."""
        mock_ticker_cls.return_value.info = {
            "shortName": "No Dividend Corp",
            "exDividendDate": None,
        }

        results = get_upcoming_dividends()

        assert len(results) == 0

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_handles_api_error_gracefully(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """yfinance API 오류 시 해당 종목을 건너뛴다."""
        mock_info = MagicMock()
        mock_info.get.side_effect = OSError("네트워크 오류")
        mock_ticker_cls.return_value.info = mock_info

        results = get_upcoming_dividends()

        assert isinstance(results, list)
        assert len(results) == 0

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_dividend_yield_not_multiplied(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """yfinance의 dividendYield를 그대로 반환한다 (x100 하지 않음)."""
        mock_info = _make_yfinance_info(
            dividend_yield=5.78, ex_div_days_from_today=1,
        )
        mock_ticker_cls.return_value.info = mock_info

        results = get_upcoming_dividends()

        # yfinance가 5.78을 반환하면 그대로 5.78이어야 함
        assert results[0]["dividend_yield"] == 5.78

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_none_dividend_yield_defaults_to_zero(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """dividendYield가 None이면 0.0으로 기본값을 설정한다."""
        mock_info = _make_yfinance_info(ex_div_days_from_today=1)
        mock_info["dividendYield"] = None
        mock_ticker_cls.return_value.info = mock_info

        results = get_upcoming_dividends()

        assert results[0]["dividend_yield"] == 0.0


class TestFetchTickerDividendInfo:
    """_fetch_ticker_dividend_info() 내부 함수 테스트."""

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_valid_dict(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """유효한 배당 정보 dict를 반환한다."""
        today = date.today()
        end_date = today + timedelta(days=3)
        mock_info = _make_yfinance_info(ex_div_days_from_today=1)
        mock_ticker_cls.return_value.info = mock_info

        result = _fetch_ticker_dividend_info("JNJ", today, end_date)

        assert result is not None
        assert result["ticker"] == "JNJ"
        assert "ex_dividend_date" in result
        assert "dividend_yield" in result
        assert "current_price" in result
        assert "last_dividend_value" in result
        assert "yahoo_finance_url" in result
        assert "JNJ" in result["yahoo_finance_url"]

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_none_for_out_of_range(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """범위 밖의 배당락일이면 None을 반환한다."""
        today = date.today()
        end_date = today + timedelta(days=3)
        mock_info = _make_yfinance_info(ex_div_days_from_today=10)
        mock_ticker_cls.return_value.info = mock_info

        result = _fetch_ticker_dividend_info("JNJ", today, end_date)

        assert result is None

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_none_on_exception(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """예외 발생 시 None을 반환한다."""
        mock_ticker_cls.side_effect = OSError("네트워크 오류")

        today = date.today()
        end_date = today + timedelta(days=3)
        result = _fetch_ticker_dividend_info("JNJ", today, end_date)

        assert result is None


class TestDividendTickers:
    """DIVIDEND_TICKERS 상수 테스트."""

    def test_tickers_list_not_empty(self) -> None:
        """티커 목록이 비어있지 않다."""
        assert len(DIVIDEND_TICKERS) > 0

    def test_tickers_are_uppercase_strings(self) -> None:
        """모든 티커가 대문자 문자열이다."""
        for ticker in DIVIDEND_TICKERS:
            assert isinstance(ticker, str)
            assert ticker == ticker.upper()

    def test_no_duplicate_tickers(self) -> None:
        """중복 티커가 없다."""
        assert len(DIVIDEND_TICKERS) == len(set(DIVIDEND_TICKERS))
