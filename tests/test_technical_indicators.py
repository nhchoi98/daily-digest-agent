"""Yahoo Finance 기술적 지표 계산 모듈 테스트.

RSI, Stochastic, 변동성, 5일 수익률, 평균 거래량 계산을
알려진 값으로 교차 검증하고 에러 처리를 확인한다.
"""

import math
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.tools.yahoo_finance import (
    _calculate_avg_volume,
    _calculate_price_change,
    _calculate_rsi,
    _calculate_stochastic,
    _calculate_volatility,
    get_technical_indicators,
)


def _make_close_series(values: list[float]) -> pd.Series:
    """테스트용 종가 Series를 생성한다.

    Args:
        values: 종가 리스트.

    Returns:
        pd.Series: 종가 데이터.
    """
    return pd.Series(values, dtype=float)


def _make_volume_series(values: list[float]) -> pd.Series:
    """테스트용 거래량 Series를 생성한다.

    Args:
        values: 거래량 리스트.

    Returns:
        pd.Series: 거래량 데이터.
    """
    return pd.Series(values, dtype=float)


class TestCalculateRSI:
    """_calculate_rsi() 테스트."""

    def test_rsi_in_valid_range(self) -> None:
        """RSI 값이 0~100 범위 내에 있다."""
        # 점진적 상승 데이터 (RSI가 높아야 함)
        prices = [100 + i * 0.5 for i in range(30)]
        close = _make_close_series(prices)

        rsi = _calculate_rsi(close)

        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_rsi_high_for_uptrend(self) -> None:
        """연속 상승 시 RSI가 50 이상이다."""
        # 매일 1%씩 상승하는 30일 데이터
        prices = [100 * (1.01 ** i) for i in range(30)]
        close = _make_close_series(prices)

        rsi = _calculate_rsi(close)

        assert rsi is not None
        assert rsi > 50

    def test_rsi_low_for_downtrend(self) -> None:
        """연속 하락 시 RSI가 50 이하이다."""
        # 매일 1%씩 하락하는 30일 데이터
        prices = [100 * (0.99 ** i) for i in range(30)]
        close = _make_close_series(prices)

        rsi = _calculate_rsi(close)

        assert rsi is not None
        assert rsi < 50

    def test_rsi_none_for_insufficient_data(self) -> None:
        """데이터가 14일 미만이면 None을 반환한다."""
        close = _make_close_series([100.0] * 10)

        rsi = _calculate_rsi(close)

        assert rsi is None

    def test_rsi_known_value(self) -> None:
        """알려진 데이터로 RSI를 교차 검증한다.

        14일 중 10일 상승(+1), 4일 하락(-1)이면
        RSI ≈ 71.4 (= 100 - 100/(1 + 10/4)) 근처여야 한다.
        Wilder's smoothing 때문에 정확히 일치하지는 않지만 근사한다.
        """
        # 시드: 14일 동안 10일 상승, 4일 하락
        prices = [100.0]
        changes = [1] * 10 + [-1] * 4  # +10, -4
        for c in changes:
            prices.append(prices[-1] + c)
        # 충분한 데이터를 위해 추가 상승 데이터
        for _ in range(5):
            prices.append(prices[-1] + 0.5)

        close = _make_close_series(prices)
        rsi = _calculate_rsi(close)

        assert rsi is not None
        # Wilder smoothing 적용 후 정확한 값은 아니지만 60~85 범위에 있어야 함
        assert 55 <= rsi <= 90


class TestCalculateStochastic:
    """_calculate_stochastic() 테스트."""

    def _make_ohlc_df(
        self,
        high_vals: list[float],
        low_vals: list[float],
        close_vals: list[float],
    ) -> pd.DataFrame:
        """테스트용 OHLC DataFrame을 생성한다."""
        return pd.DataFrame({
            "High": high_vals,
            "Low": low_vals,
            "Close": close_vals,
        })

    def test_stochastic_in_valid_range(self) -> None:
        """%K, %D가 0~100 범위 내에 있다."""
        n = 30
        high = [100 + i * 0.5 + 1 for i in range(n)]
        low = [100 + i * 0.5 - 1 for i in range(n)]
        close = [100 + i * 0.5 for i in range(n)]
        hist = self._make_ohlc_df(high, low, close)

        k, d = _calculate_stochastic(hist)

        assert k is not None and d is not None
        assert 0 <= k <= 100
        assert 0 <= d <= 100

    def test_stochastic_high_at_top(self) -> None:
        """종가가 14일 최고가 근처이면 %K가 높다."""
        n = 25
        # 안정적으로 상승하는 데이터
        high = [100 + i * 2 + 1 for i in range(n)]
        low = [100 + i * 2 - 1 for i in range(n)]
        close = [100 + i * 2 for i in range(n)]
        hist = self._make_ohlc_df(high, low, close)

        k, d = _calculate_stochastic(hist)

        assert k is not None
        # 상승 추세에서 종가가 항상 최고가 근처이므로 %K가 높아야 함
        assert k > 70

    def test_stochastic_none_for_insufficient_data(self) -> None:
        """데이터가 부족하면 (None, None)을 반환한다."""
        hist = self._make_ohlc_df(
            [100] * 10, [99] * 10, [99.5] * 10,
        )

        k, d = _calculate_stochastic(hist)

        assert k is None
        assert d is None


class TestCalculateVolatility:
    """_calculate_volatility() 테스트."""

    def test_volatility_positive(self) -> None:
        """변동이 있는 데이터에서 변동성이 양수이다."""
        # 교차 변동 데이터
        prices = [100 + ((-1) ** i) * 2 for i in range(30)]
        close = _make_close_series(prices)

        vol = _calculate_volatility(close)

        assert vol is not None
        assert vol > 0

    def test_volatility_annualized_reasonable(self) -> None:
        """일반적 주가 데이터에서 연환산 변동성이 합리적 범위에 있다.

        S&P 500 평균 변동성이 ~15-20% 수준이므로,
        일반적 데이터에서 5~100% 범위여야 한다.
        """
        # 일간 1% 변동 (높은 편)
        prices = [100.0]
        for i in range(30):
            change = 0.01 * ((-1) ** i)
            prices.append(prices[-1] * (1 + change))
        close = _make_close_series(prices)

        vol = _calculate_volatility(close)

        assert vol is not None
        assert 5 <= vol <= 100

    def test_volatility_none_for_insufficient_data(self) -> None:
        """데이터가 20일 미만이면 None을 반환한다."""
        close = _make_close_series([100.0] * 15)

        vol = _calculate_volatility(close)

        assert vol is None


class TestCalculatePriceChange:
    """_calculate_price_change() 테스트."""

    def test_positive_change(self) -> None:
        """상승 시 양수 수익률을 반환한다."""
        # 5일 전 100, 현재 110 → +10%
        prices = [100, 102, 104, 106, 108, 110]
        close = _make_close_series(prices)

        change = _calculate_price_change(close)

        assert change is not None
        assert abs(change - 10.0) < 0.01

    def test_negative_change(self) -> None:
        """하락 시 음수 수익률을 반환한다."""
        prices = [100, 98, 96, 94, 92, 90]
        close = _make_close_series(prices)

        change = _calculate_price_change(close)

        assert change is not None
        assert abs(change - (-10.0)) < 0.01

    def test_none_for_insufficient_data(self) -> None:
        """데이터가 5일 미만이면 None을 반환한다."""
        close = _make_close_series([100, 101, 102])

        change = _calculate_price_change(close)

        assert change is None


class TestCalculateAvgVolume:
    """_calculate_avg_volume() 테스트."""

    def test_avg_volume_correct(self) -> None:
        """20일 평균 거래량이 정확하다."""
        volumes = [1_000_000] * 20
        vol = _make_volume_series(volumes)

        avg = _calculate_avg_volume(vol)

        assert avg is not None
        assert abs(avg - 1_000_000) < 1

    def test_none_for_insufficient_data(self) -> None:
        """데이터가 20일 미만이면 None을 반환한다."""
        vol = _make_volume_series([1000] * 10)

        avg = _calculate_avg_volume(vol)

        assert avg is None


class TestGetTechnicalIndicators:
    """get_technical_indicators() 통합 테스트."""

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_all_indicators(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """정상 데이터에서 모든 지표가 반환된다."""
        n = 60
        dates = pd.date_range(end="2026-02-18", periods=n)
        hist = pd.DataFrame({
            "Open": [100 + i * 0.3 for i in range(n)],
            "High": [101 + i * 0.3 for i in range(n)],
            "Low": [99 + i * 0.3 for i in range(n)],
            "Close": [100 + i * 0.3 for i in range(n)],
            "Volume": [5_000_000] * n,
        }, index=dates)
        mock_ticker_cls.return_value.history.return_value = hist

        result = get_technical_indicators("AAPL")

        assert result is not None
        assert "rsi_14" in result
        assert "stochastic_k" in result
        assert "stochastic_d" in result
        assert "volatility_20d" in result
        assert "price_change_5d" in result
        assert "avg_volume_20d" in result
        assert all(v is not None for v in result.values())

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_none_on_empty_data(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """빈 히스토리에서 None을 반환한다."""
        mock_ticker_cls.return_value.history.return_value = pd.DataFrame()

        result = get_technical_indicators("AAPL")

        assert result is None

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_none_on_api_error(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """API 오류 시 None을 반환한다."""
        mock_ticker_cls.side_effect = OSError("네트워크 오류")

        result = get_technical_indicators("AAPL")

        assert result is None

    @patch("src.tools.yahoo_finance.yf.Ticker")
    def test_returns_none_for_insufficient_data(
        self, mock_ticker_cls: MagicMock
    ) -> None:
        """데이터가 부족하면 None을 반환한다."""
        dates = pd.date_range(end="2026-02-18", periods=5)
        hist = pd.DataFrame({
            "Open": [100] * 5,
            "High": [101] * 5,
            "Low": [99] * 5,
            "Close": [100] * 5,
            "Volume": [1000] * 5,
        }, index=dates)
        mock_ticker_cls.return_value.history.return_value = hist

        result = get_technical_indicators("AAPL")

        assert result is None
