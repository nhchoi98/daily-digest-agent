"""Yahoo Finance 실적발표 데이터 수집 모듈 테스트.

yfinance API를 mock하여 실적발표 일정 수집, 범위 필터링,
서프라이즈 계산, 에러 처리 등을 검증한다.
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd

from src.tools.yahoo_finance import (
    EARNINGS_TICKERS,
    _calculate_surprise_pct,
    _determine_earnings_timing,
    _fetch_last_earnings_surprise,
    _fetch_ticker_earnings_info,
    _parse_earnings_date,
    get_upcoming_earnings,
)


def _make_calendar_dict(
    earnings_days_from_today: int = 5,
    eps_estimate: float | None = 1.42,
    revenue_estimate: float | None = 94_000_000_000,
) -> dict[str, Any]:
    """테스트용 yfinance calendar dict를 생성한다.

    Args:
        earnings_days_from_today: 오늘로부터 며칠 후 실적발표인지.
        eps_estimate: EPS 추정치.
        revenue_estimate: 매출 추정치.

    Returns:
        dict: yfinance Ticker.calendar 형태의 dict.
    """
    earnings_date = date.today() + timedelta(days=earnings_days_from_today)
    # yfinance calendar는 Earnings Date를 리스트로 반환한다
    earnings_ts = pd.Timestamp(earnings_date)

    return {
        "Earnings Date": [earnings_ts, earnings_ts],
        "EPS Estimate": eps_estimate,
        "Revenue Estimate": revenue_estimate,
    }


def _make_info_dict(
    ticker: str = "AAPL",
    market_cap: int = 3_500_000_000_000,
    current_price: float = 225.0,
    sector: str = "Technology",
) -> dict[str, Any]:
    """테스트용 yfinance info dict를 생성한다.

    Args:
        ticker: 종목 심볼.
        market_cap: 시가총액.
        current_price: 현재가.
        sector: 섹터.

    Returns:
        dict: yfinance Ticker.info 형태의 dict.
    """
    return {
        "shortName": f"{ticker} Corp",
        "marketCap": market_cap,
        "currentPrice": current_price,
        "sector": sector,
    }


class TestGetUpcomingEarnings:
    """get_upcoming_earnings() 테스트."""

    @patch("src.tools.yahoo_finance._fetch_ticker_earnings_info")
    def test_returns_stocks_in_range(
        self, mock_fetch: MagicMock
    ) -> None:
        """스캔 범위 내 실적발표 종목을 반환한다."""
        mock_fetch.return_value = {
            "ticker": "AAPL",
            "company_name": "Apple Corp",
            "earnings_date": "2026-03-05",
            "earnings_timing": "AMC",
            "eps_estimate": 1.42,
            "revenue_estimate": None,
            "market_cap": 3_500_000_000_000,
            "current_price": 225.0,
            "sector": "Technology",
            "last_eps_actual": None,
            "last_eps_estimate": None,
            "last_surprise_pct": None,
            "yahoo_finance_url": "https://finance.yahoo.com/quote/AAPL",
        }

        today = date.today()
        end_date = today + timedelta(days=14)
        results = get_upcoming_earnings(
            start_date=today, end_date=end_date,
        )

        # 모든 종목이 같은 mock을 반환하므로 전체가 포함
        assert len(results) == len(EARNINGS_TICKERS)

    @patch("src.tools.yahoo_finance._fetch_ticker_earnings_info")
    def test_excludes_none_results(
        self, mock_fetch: MagicMock
    ) -> None:
        """None 반환 종목은 제외한다."""
        mock_fetch.return_value = None

        results = get_upcoming_earnings()

        assert len(results) == 0

    @patch("src.tools.yahoo_finance._fetch_ticker_earnings_info")
    def test_default_dates_when_none(
        self, mock_fetch: MagicMock
    ) -> None:
        """start_date/end_date 미지정 시 기본값을 사용한다."""
        mock_fetch.return_value = None

        results = get_upcoming_earnings()

        # 함수가 호출되어야 함 (빈 결과이지만 호출은 됨)
        assert mock_fetch.call_count == len(EARNINGS_TICKERS)


class TestFetchTickerEarningsInfo:
    """_fetch_ticker_earnings_info() 테스트."""

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_valid_dict(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """유효한 실적발표 정보 dict를 반환한다."""
        today = date.today()
        end_date = today + timedelta(days=14)
        cal = _make_calendar_dict(earnings_days_from_today=5)
        info = _make_info_dict()

        mock_ticker = MagicMock()
        mock_ticker.calendar = cal
        mock_ticker.info = info
        mock_ticker.get_earnings_dates.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        result = _fetch_ticker_earnings_info("AAPL", today, end_date)

        assert result is not None
        assert result["ticker"] == "AAPL"
        assert "earnings_date" in result
        assert "eps_estimate" in result
        assert "yahoo_finance_url" in result

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_none_for_out_of_range(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """범위 밖의 실적발표일이면 None을 반환한다."""
        today = date.today()
        end_date = today + timedelta(days=14)
        # 30일 후 → 14일 범위 밖
        cal = _make_calendar_dict(earnings_days_from_today=30)
        info = _make_info_dict()

        mock_ticker = MagicMock()
        mock_ticker.calendar = cal
        mock_ticker.info = info
        mock_ticker_cls.return_value = mock_ticker

        result = _fetch_ticker_earnings_info("AAPL", today, end_date)

        assert result is None

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_none_when_no_calendar(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """calendar가 None이면 None을 반환한다."""
        mock_ticker = MagicMock()
        mock_ticker.calendar = None
        mock_ticker_cls.return_value = mock_ticker

        today = date.today()
        end_date = today + timedelta(days=14)
        result = _fetch_ticker_earnings_info("AAPL", today, end_date)

        assert result is None

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_none_on_exception(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """예외 발생 시 None을 반환한다."""
        mock_ticker_cls.side_effect = OSError("네트워크 오류")

        today = date.today()
        end_date = today + timedelta(days=14)
        result = _fetch_ticker_earnings_info("AAPL", today, end_date)

        assert result is None

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_includes_eps_estimate(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """결과에 EPS 추정치가 포함된다."""
        today = date.today()
        end_date = today + timedelta(days=14)
        cal = _make_calendar_dict(
            earnings_days_from_today=5, eps_estimate=2.89,
        )
        info = _make_info_dict()

        mock_ticker = MagicMock()
        mock_ticker.calendar = cal
        mock_ticker.info = info
        mock_ticker.get_earnings_dates.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        result = _fetch_ticker_earnings_info("MSFT", today, end_date)

        assert result is not None
        assert result["eps_estimate"] == 2.89


class TestParseEarningsDate:
    """_parse_earnings_date() 테스트."""

    def test_parse_date_object(self) -> None:
        """date 객체를 그대로 반환한다."""
        d = date(2026, 3, 5)
        assert _parse_earnings_date(d) == d

    def test_parse_timestamp(self) -> None:
        """pandas Timestamp를 date로 변환한다."""
        ts = pd.Timestamp("2026-03-05")
        assert _parse_earnings_date(ts) == date(2026, 3, 5)

    def test_parse_iso_string(self) -> None:
        """ISO 형식 문자열을 date로 변환한다."""
        assert _parse_earnings_date("2026-03-05") == date(2026, 3, 5)

    def test_parse_none(self) -> None:
        """None 입력 시 None을 반환한다."""
        assert _parse_earnings_date(None) is None

    def test_parse_invalid_string(self) -> None:
        """잘못된 문자열 입력 시 None을 반환한다."""
        assert _parse_earnings_date("invalid") is None


class TestDetermineEarningsTiming:
    """_determine_earnings_timing() 테스트."""

    def test_non_list_returns_tas(self) -> None:
        """리스트가 아니면 TAS를 반환한다."""
        assert _determine_earnings_timing("2026-03-05") == "TAS"

    def test_single_element_list_returns_tas(self) -> None:
        """리스트가 1개면 TAS를 반환한다."""
        assert _determine_earnings_timing([pd.Timestamp("2026-03-05")]) == "TAS"

    def test_same_dates_returns_tas(self) -> None:
        """두 날짜가 같으면 TAS를 반환한다."""
        ts = pd.Timestamp("2026-03-05")
        assert _determine_earnings_timing([ts, ts]) == "TAS"


class TestFetchLastEarningsSurprise:
    """_fetch_last_earnings_surprise() 테스트."""

    def test_returns_surprise_data(self) -> None:
        """직전 분기 서프라이즈 데이터를 반환한다."""
        mock_ticker = MagicMock()
        past_date = pd.Timestamp(date.today() - timedelta(days=30))
        df = pd.DataFrame(
            {
                "Reported EPS": [1.40],
                "EPS Estimate": [1.35],
            },
            index=[past_date],
        )
        mock_ticker.get_earnings_dates.return_value = df

        result = _fetch_last_earnings_surprise(mock_ticker)

        assert result["last_eps_actual"] == 1.40
        assert result["last_eps_estimate"] == 1.35
        assert result["last_surprise_pct"] is not None

    def test_returns_empty_on_no_data(self) -> None:
        """데이터가 없으면 모든 값이 None인 dict를 반환한다."""
        mock_ticker = MagicMock()
        mock_ticker.get_earnings_dates.return_value = pd.DataFrame()

        result = _fetch_last_earnings_surprise(mock_ticker)

        assert result["last_eps_actual"] is None
        assert result["last_eps_estimate"] is None
        assert result["last_surprise_pct"] is None

    def test_skips_future_dates(self) -> None:
        """미래 날짜는 건너뛴다."""
        mock_ticker = MagicMock()
        future_date = pd.Timestamp(date.today() + timedelta(days=30))
        df = pd.DataFrame(
            {
                "Reported EPS": [1.40],
                "EPS Estimate": [1.35],
            },
            index=[future_date],
        )
        mock_ticker.get_earnings_dates.return_value = df

        result = _fetch_last_earnings_surprise(mock_ticker)

        assert result["last_eps_actual"] is None

    def test_handles_exception(self) -> None:
        """예외 발생 시 빈 결과를 반환한다."""
        mock_ticker = MagicMock()
        mock_ticker.get_earnings_dates.side_effect = OSError("오류")

        result = _fetch_last_earnings_surprise(mock_ticker)

        assert result["last_eps_actual"] is None


class TestCalculateSurprisePct:
    """_calculate_surprise_pct() 테스트."""

    def test_positive_surprise(self) -> None:
        """Beat: 실제 > 추정이면 양수."""
        result = _calculate_surprise_pct(1.40, 1.35)
        assert result is not None
        assert result > 0

    def test_negative_surprise(self) -> None:
        """Miss: 실제 < 추정이면 음수."""
        result = _calculate_surprise_pct(1.30, 1.35)
        assert result is not None
        assert result < 0

    def test_none_actual(self) -> None:
        """actual이 None이면 None을 반환한다."""
        assert _calculate_surprise_pct(None, 1.35) is None

    def test_none_estimate(self) -> None:
        """estimate가 None이면 None을 반환한다."""
        assert _calculate_surprise_pct(1.40, None) is None

    def test_zero_estimate(self) -> None:
        """estimate가 0이면 None을 반환한다 (0으로 나누기 방지)."""
        assert _calculate_surprise_pct(1.40, 0) is None

    def test_calculation_accuracy(self) -> None:
        """계산 정확도를 검증한다."""
        # (1.40 - 1.35) / |1.35| × 100 = 3.70%
        result = _calculate_surprise_pct(1.40, 1.35)
        assert result is not None
        assert abs(result - 3.70) < 0.1


class TestEarningsTickers:
    """EARNINGS_TICKERS 상수 테스트."""

    def test_tickers_list_not_empty(self) -> None:
        """티커 목록이 비어있지 않다."""
        assert len(EARNINGS_TICKERS) > 0

    def test_tickers_are_uppercase_strings(self) -> None:
        """모든 티커가 대문자 문자열이다 (BRK-B 같은 하이픈 허용)."""
        for ticker in EARNINGS_TICKERS:
            assert isinstance(ticker, str)
            assert ticker == ticker.upper()

    def test_no_duplicate_tickers(self) -> None:
        """중복 티커가 없다."""
        assert len(EARNINGS_TICKERS) == len(set(EARNINGS_TICKERS))

    def test_contains_major_stocks(self) -> None:
        """주요 대형주가 포함되어 있다."""
        major = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
        for ticker in major:
            assert ticker in EARNINGS_TICKERS
