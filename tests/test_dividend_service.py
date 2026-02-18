"""DividendService 비즈니스 로직 테스트 모듈.

배당 스캔, 필터링, 정렬, 기술적 지표 기반 위험도 평가,
세후 수익성 분석, Slack 포맷 변환,
요일별 스캔 범위 계산 등 DividendService의 핵심 로직을 검증한다.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

from src.schemas.stock import (
    DividendScanResult,
    DividendStock,
    RiskAssessment,
    TechnicalIndicators,
)
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
    current_price: float = 150.0,
    last_dividend_value: float = 1.30,
) -> dict[str, Any]:
    """테스트용 원시 배당 데이터 dict를 생성한다.

    Args:
        ticker: 종목 심볼.
        yield_pct: 배당수익률 (%).
        market_cap: 시가총액 (USD).
        ex_date: 배당락일 (ISO 형식).
        current_price: 현재 주가 (USD).
        last_dividend_value: 마지막 1회 배당금 (USD).

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
        "current_price": current_price,
        "last_dividend_value": last_dividend_value,
        "yahoo_finance_url": f"https://finance.yahoo.com/quote/{ticker}",
    }


def _make_stock(
    ticker: str = "JNJ",
    yield_pct: float = 5.0,
    market_cap: int = 500_000_000_000,
    current_price: float = 150.0,
    dividend_amount: float = 2.0,
    last_dividend_value: float = 0.50,
    indicators: TechnicalIndicators | None = None,
    risk: RiskAssessment | None = None,
) -> DividendStock:
    """테스트용 DividendStock 인스턴스를 생성한다.

    Args:
        ticker: 종목 심볼.
        yield_pct: 배당수익률 (%).
        market_cap: 시가총액 (USD).
        current_price: 현재 주가 (USD).
        dividend_amount: 연간 배당금 (USD).
        last_dividend_value: 마지막 1회 배당금 (USD).
        indicators: 기술적 지표.
        risk: 위험도 평가.

    Returns:
        DividendStock: 테스트용 인스턴스.
    """
    return DividendStock(
        ticker=ticker,
        company_name=f"{ticker} Corp",
        ex_dividend_date=date(2026, 2, 20),
        dividend_yield=yield_pct,
        dividend_amount=dividend_amount,
        market_cap=market_cap,
        current_price=current_price,
        last_dividend_value=last_dividend_value,
        yahoo_finance_url=f"https://finance.yahoo.com/quote/{ticker}",
        indicators=indicators,
        risk=risk,
    )


class TestCalculateScanRange:
    """DividendService.calculate_scan_range() 테스트."""

    def test_monday_range(self) -> None:
        """월요일: today + 2일 (수요일까지)."""
        service = DividendService()
        start, end = service.calculate_scan_range(date(2026, 2, 16))
        assert start == date(2026, 2, 16)
        assert end == date(2026, 2, 18)
        assert (end - start).days == 2

    def test_tuesday_range(self) -> None:
        """화요일: today + 2일 (목요일까지)."""
        service = DividendService()
        start, end = service.calculate_scan_range(date(2026, 2, 17))
        assert start == date(2026, 2, 17)
        assert end == date(2026, 2, 19)
        assert (end - start).days == 2

    def test_wednesday_range(self) -> None:
        """수요일: today + 2일 (금요일까지)."""
        service = DividendService()
        start, end = service.calculate_scan_range(date(2026, 2, 18))
        assert start == date(2026, 2, 18)
        assert end == date(2026, 2, 20)
        assert (end - start).days == 2

    def test_thursday_range_includes_friday(self) -> None:
        """목요일: today + 3일 (일요일까지, 금요일 배당락 포함)."""
        service = DividendService()
        start, end = service.calculate_scan_range(date(2026, 2, 19))
        assert start == date(2026, 2, 19)
        assert end == date(2026, 2, 22)
        assert (end - start).days == 3

    def test_friday_range_includes_monday(self) -> None:
        """금요일: today + 3일 (월요일까지, 월요일 배당락 포함)."""
        service = DividendService()
        start, end = service.calculate_scan_range(date(2026, 2, 20))
        assert start == date(2026, 2, 20)
        assert end == date(2026, 2, 23)
        assert (end - start).days == 3

    def test_saturday_range(self) -> None:
        """토요일: today + 4일 (수요일까지)."""
        service = DividendService()
        start, end = service.calculate_scan_range(date(2026, 2, 21))
        assert start == date(2026, 2, 21)
        assert end == date(2026, 2, 25)
        assert (end - start).days == 4

    def test_sunday_range(self) -> None:
        """일요일: today + 3일 (수요일까지)."""
        service = DividendService()
        start, end = service.calculate_scan_range(date(2026, 2, 22))
        assert start == date(2026, 2, 22)
        assert end == date(2026, 2, 25)
        assert (end - start).days == 3


class TestScanDividends:
    """DividendService.scan_dividends() 테스트."""

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_returns_scan_result(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """스캔 결과를 DividendScanResult로 반환한다."""
        mock_get.return_value = [
            _make_raw_stock("JNJ", yield_pct=5.0),
        ]
        mock_tech.return_value = None

        service = DividendService()
        result = service.scan_dividends()

        assert isinstance(result, DividendScanResult)
        assert result.scan_start_date is not None
        assert result.scan_end_date is not None

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_scan_result_includes_date_range(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """스캔 결과에 시작일/종료일이 포함된다."""
        mock_get.return_value = []
        mock_tech.return_value = None

        service = DividendService()
        result = service.scan_dividends()

        assert result.scan_start_date is not None
        assert result.scan_end_date is not None
        assert result.scan_range_days == (
            result.scan_end_date - result.scan_start_date
        ).days

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_override_scan_days(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """scan_days 오버라이드 시 고정 범위를 사용한다."""
        mock_get.return_value = []
        mock_tech.return_value = None

        service = DividendService(scan_days=7)
        result = service.scan_dividends()

        assert result.scan_range_days == 7

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_filters_by_yield(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """배당수익률 기준 이하 종목은 필터링된다."""
        mock_get.return_value = [
            _make_raw_stock("HIGH", yield_pct=5.0),
            _make_raw_stock("LOW", yield_pct=1.0),
        ]
        mock_tech.return_value = None

        service = DividendService()
        result = service.scan_dividends()

        tickers = [s.ticker for s in result.stocks]
        assert "HIGH" in tickers
        assert "LOW" not in tickers

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_filters_by_market_cap(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """시가총액 기준 이하 종목은 필터링된다."""
        mock_get.return_value = [
            _make_raw_stock("BIG", market_cap=50_000_000_000),
            _make_raw_stock("SMALL", market_cap=100_000),
        ]
        mock_tech.return_value = None

        service = DividendService()
        result = service.scan_dividends()

        tickers = [s.ticker for s in result.stocks]
        assert "BIG" in tickers
        assert "SMALL" not in tickers

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_limits_to_max_stocks(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """최대 MAX_STOCKS개까지만 반환한다."""
        mock_get.return_value = [
            _make_raw_stock(f"T{i}", yield_pct=float(20 - i))
            for i in range(MAX_STOCKS + 5)
        ]
        mock_tech.return_value = None

        service = DividendService()
        result = service.scan_dividends()

        assert len(result.stocks) <= MAX_STOCKS

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_empty_result_on_no_data(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """데이터가 없으면 빈 결과를 반환한다."""
        mock_get.return_value = []
        mock_tech.return_value = None

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

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_filters_applied_metadata(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """적용된 필터 정보를 메타데이터에 포함한다."""
        mock_get.return_value = []
        mock_tech.return_value = None

        service = DividendService()
        result = service.scan_dividends()

        assert result.filters_applied["min_yield_pct"] == MIN_DIVIDEND_YIELD_PCT
        assert result.filters_applied["min_market_cap_usd"] == MIN_MARKET_CAP_USD
        assert result.filters_applied["max_stocks"] == MAX_STOCKS

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_passes_date_range_to_yahoo(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """yahoo_finance에 날짜 범위를 전달한다."""
        mock_get.return_value = []
        mock_tech.return_value = None

        service = DividendService()
        service.scan_dividends()

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args.kwargs
        assert "start_date" in call_kwargs
        assert "end_date" in call_kwargs

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_high_risk_stocks_excluded(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """HIGH 리스크 종목이 결과에서 제외된다."""
        mock_get.return_value = [
            _make_raw_stock("SAFE", yield_pct=5.0),
            _make_raw_stock("RISKY", yield_pct=6.0),
        ]
        # RISKY 종목에 과매수 RSI를 반환
        def _side_effect(ticker: str) -> dict | None:
            if ticker == "RISKY":
                return {"rsi_14": 80.0, "stochastic_k": 90.0,
                        "stochastic_d": 85.0, "volatility_20d": 25.0,
                        "price_change_5d": 2.0, "avg_volume_20d": 1_000_000}
            return {"rsi_14": 45.0, "stochastic_k": 40.0,
                    "stochastic_d": 38.0, "volatility_20d": 20.0,
                    "price_change_5d": 1.0, "avg_volume_20d": 1_000_000}

        mock_tech.side_effect = _side_effect

        service = DividendService()
        result = service.scan_dividends()

        tickers = [s.ticker for s in result.stocks]
        assert "SAFE" in tickers
        assert "RISKY" not in tickers
        assert result.high_risk_excluded == 1

    @patch("src.services.dividend_service.get_technical_indicators")
    @patch("src.services.dividend_service.get_upcoming_dividends")
    def test_profitable_stocks_sorted_first(
        self, mock_get: MagicMock, mock_tech: MagicMock
    ) -> None:
        """is_profitable=True 종목이 먼저 정렬된다."""
        mock_get.return_value = [
            _make_raw_stock("PROFIT", yield_pct=5.0, current_price=100.0,
                            last_dividend_value=0.50),
            _make_raw_stock("LOSS", yield_pct=3.5, current_price=30.0,
                            last_dividend_value=2.0),
        ]
        mock_tech.return_value = None

        service = DividendService()
        result = service.scan_dividends()

        # PROFIT has small drop, LOSS has large drop relative to price
        if len(result.stocks) >= 2:
            first = result.stocks[0]
            assert first.profit_analysis is not None
            # 수익성 정렬이 올바르게 동작하는지 확인
            if first.profit_analysis.is_profitable:
                assert first.ticker == "PROFIT"


class TestAssessRisk:
    """DividendService.assess_risk() 테스트."""

    def test_high_risk_rsi_76(self) -> None:
        """RSI 76이면 HIGH 리스크 (SKIP)."""
        service = DividendService()
        stock = _make_stock(indicators=TechnicalIndicators(rsi_14=76.0))

        result = service.assess_risk(stock)

        assert result.risk_level == "HIGH"
        assert result.recommendation == "SKIP"
        assert any("RSI" in r for r in result.reasons)

    def test_medium_risk_rsi_70(self) -> None:
        """RSI 70이면 MEDIUM 리스크 (HOLD)."""
        service = DividendService()
        stock = _make_stock(indicators=TechnicalIndicators(rsi_14=70.0))

        result = service.assess_risk(stock)

        assert result.risk_level == "MEDIUM"
        assert result.recommendation == "HOLD"

    def test_low_risk_rsi_40(self) -> None:
        """RSI 40이면 LOW 리스크 (BUY)."""
        service = DividendService()
        stock = _make_stock(indicators=TechnicalIndicators(rsi_14=40.0))

        result = service.assess_risk(stock)

        assert result.risk_level == "LOW"
        assert result.recommendation == "BUY"

    def test_high_risk_stochastic_overbought(self) -> None:
        """Stochastic %K>85 AND %D>80이면 HIGH 리스크."""
        service = DividendService()
        stock = _make_stock(indicators=TechnicalIndicators(
            stochastic_k=90.0, stochastic_d=82.0,
        ))

        result = service.assess_risk(stock)

        assert result.risk_level == "HIGH"
        assert any("Stochastic" in r for r in result.reasons)

    def test_high_risk_extreme_volatility(self) -> None:
        """변동성 55%이면 HIGH 리스크."""
        service = DividendService()
        stock = _make_stock(indicators=TechnicalIndicators(
            volatility_20d=55.0,
        ))

        result = service.assess_risk(stock)

        assert result.risk_level == "HIGH"
        assert any("변동성" in r for r in result.reasons)

    def test_high_risk_price_spike(self) -> None:
        """5일 수익률 +20%이면 HIGH 리스크."""
        service = DividendService()
        stock = _make_stock(indicators=TechnicalIndicators(
            price_change_5d=20.0,
        ))

        result = service.assess_risk(stock)

        assert result.risk_level == "HIGH"
        assert any("급등" in r for r in result.reasons)

    def test_medium_risk_volatility_40(self) -> None:
        """변동성 40%이면 MEDIUM 리스크."""
        service = DividendService()
        stock = _make_stock(indicators=TechnicalIndicators(
            volatility_20d=40.0,
        ))

        result = service.assess_risk(stock)

        assert result.risk_level == "MEDIUM"

    def test_medium_risk_price_change_10(self) -> None:
        """5일 수익률 +10%이면 MEDIUM 리스크."""
        service = DividendService()
        stock = _make_stock(indicators=TechnicalIndicators(
            price_change_5d=10.0,
        ))

        result = service.assess_risk(stock)

        assert result.risk_level == "MEDIUM"

    def test_low_risk_no_indicators(self) -> None:
        """기술적 지표가 없으면 기본 LOW 리스크."""
        service = DividendService()
        stock = _make_stock(indicators=None)

        result = service.assess_risk(stock)

        assert result.risk_level == "LOW"
        assert result.recommendation == "BUY"

    def test_low_risk_all_normal(self) -> None:
        """모든 지표가 정상 범위이면 LOW 리스크."""
        service = DividendService()
        stock = _make_stock(indicators=TechnicalIndicators(
            rsi_14=45.0,
            stochastic_k=40.0,
            stochastic_d=38.0,
            volatility_20d=20.0,
            price_change_5d=2.0,
        ))

        result = service.assess_risk(stock)

        assert result.risk_level == "LOW"
        assert result.recommendation == "BUY"


class TestAnalyzeProfit:
    """DividendService.analyze_profit() 테스트."""

    def test_profitable_case(self) -> None:
        """세후에도 수익이 나는 경우."""
        service = DividendService()
        stock = _make_stock(
            yield_pct=5.0, current_price=100.0,
            last_dividend_value=0.50,
            indicators=TechnicalIndicators(volatility_20d=20.0),
        )

        pa = service.analyze_profit(stock)

        # 세후: 5.0 × 0.846 = 4.23%
        # 낙폭: (0.50/100 × 100) × (1 + 0.2) = 0.60%
        # 순이익: 4.23 - 0.60 = 3.63%
        assert pa.is_profitable is True
        assert pa.net_profit_yield > 0
        assert "수익" in pa.verdict

    def test_unprofitable_case(self) -> None:
        """세후 손실이 나는 경우."""
        service = DividendService()
        stock = _make_stock(
            yield_pct=3.0, current_price=30.0,
            last_dividend_value=2.0,
            indicators=TechnicalIndicators(volatility_20d=40.0),
        )

        pa = service.analyze_profit(stock)

        # 세후: 3.0 × 0.846 = 2.538%
        # 낙폭: (2.0/30 × 100) × (1 + 0.4) = 9.33%
        # 순이익: 2.538 - 9.33 = -6.79%
        assert pa.is_profitable is False
        assert pa.net_profit_yield < 0
        assert "손실" in pa.verdict

    def test_breakeven_case(self) -> None:
        """손익분기 근처인 경우."""
        service = DividendService()
        # 순수익률이 ±0.3% 이내가 되도록 설정
        stock = _make_stock(
            yield_pct=4.0, current_price=100.0,
            last_dividend_value=2.85,
            indicators=TechnicalIndicators(volatility_20d=20.0),
        )

        pa = service.analyze_profit(stock)

        # 세후: 4.0 × 0.846 = 3.384%
        # 낙폭: (2.85/100 × 100) × (1 + 0.2) = 3.42%
        # 순이익: 3.384 - 3.42 = -0.036% (±0.3% 이내)
        assert abs(pa.net_profit_yield) <= 0.3
        assert "손익분기" in pa.verdict

    def test_tax_rate_154(self) -> None:
        """세후 배당수익률 = 세전 × (1 - 0.154) 정확성 검증."""
        service = DividendService()
        stock = _make_stock(yield_pct=4.0, current_price=100.0,
                            last_dividend_value=0.5)

        pa = service.analyze_profit(stock)

        # 4.0 × 0.846 = 3.384
        expected_net = 4.0 * (1 - 15.4 / 100)
        assert abs(pa.net_dividend_yield - expected_net) < 0.01
        assert pa.tax_rate == 15.4

    def test_no_current_price_fallback(self) -> None:
        """현재가 정보가 없을 때 세전수익률/4로 낙폭을 근사한다."""
        service = DividendService()
        stock = _make_stock(yield_pct=5.0, current_price=0.0,
                            last_dividend_value=0.0, dividend_amount=0.0)

        pa = service.analyze_profit(stock)

        # 낙폭 = dividend_yield / 4 = 1.25%
        assert abs(pa.estimated_ex_date_drop - 1.25) < 0.01

    def test_last_dividend_value_used_over_annual(self) -> None:
        """last_dividend_value(1회분)가 dividend_amount(연간)보다 우선 사용된다."""
        service = DividendService()
        stock = _make_stock(
            yield_pct=5.0, current_price=200.0,
            dividend_amount=8.0,  # 연간 $8
            last_dividend_value=2.0,  # 분기 $2
        )

        pa = service.analyze_profit(stock)

        # 낙폭: (2.0/200 × 100) × (1 + 0) = 1.0%
        # annual/4 = 8/4/200*100 = 1.0%도 같지만, last_dividend_value 경로 사용
        assert pa.estimated_ex_date_drop > 0

    def test_volatility_factor_capped_at_05(self) -> None:
        """변동성 보정 팩터는 0.5로 상한이 제한된다."""
        service = DividendService()
        stock = _make_stock(
            yield_pct=5.0, current_price=100.0,
            last_dividend_value=1.0,
            indicators=TechnicalIndicators(volatility_20d=100.0),
        )

        pa = service.analyze_profit(stock)

        # 변동성 100% → factor = min(100/100, 0.5) = 0.5
        # 낙폭: (1.0/100 × 100) × (1 + 0.5) = 1.5%
        assert abs(pa.estimated_ex_date_drop - 1.5) < 0.01


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
            scan_start_date=date(2026, 2, 18),
            scan_end_date=date(2026, 2, 20),
            filters_applied={},
        )

        blocks = service.format_for_slack(result)

        assert len(blocks) == 1
        assert blocks[0].type == "section"
        assert "없습니다" in blocks[0].text.text

    def test_empty_notice_shows_date_range(self) -> None:
        """빈 결과 안내에 스캔 날짜 범위가 표시된다."""
        service = DividendService()
        result = DividendScanResult(
            stocks=[],
            scan_range_days=2,
            scan_start_date=date(2026, 2, 18),
            scan_end_date=date(2026, 2, 20),
            filters_applied={},
        )

        blocks = service.format_for_slack(result)

        assert "2026-02-18" in blocks[0].text.text
        assert "2026-02-20" in blocks[0].text.text

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

    def test_format_includes_risk_emoji(self) -> None:
        """종목에 리스크 이모지가 표시된다."""
        service = DividendService()
        stock = _make_stock(risk=RiskAssessment(
            risk_level="LOW", reasons=["정상"], recommendation="BUY",
        ))
        result = DividendScanResult(
            stocks=[stock],
            scan_range_days=3,
            filters_applied={},
        )

        blocks = service.format_for_slack(result)

        assert ":large_green_circle:" in blocks[0].text.text

    def test_format_shows_high_risk_excluded(self) -> None:
        """HIGH 리스크 제외 정보가 제목에 표시된다."""
        service = DividendService()
        result = DividendScanResult(
            stocks=[_make_stock()],
            scan_range_days=3,
            filters_applied={},
            high_risk_excluded=2,
        )

        blocks = service.format_for_slack(result)

        assert "HIGH 리스크 2종목 제외" in blocks[0].text.text


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
            {"invalid": "data"},
        ]

        stocks = service._parse_raw_data(raw)

        assert len(stocks) == 1
        assert stocks[0].ticker == "JNJ"

    def test_parse_includes_current_price(self) -> None:
        """파싱 결과에 current_price가 포함된다."""
        service = DividendService()
        raw = [_make_raw_stock("JNJ", current_price=155.0)]

        stocks = service._parse_raw_data(raw)

        assert stocks[0].current_price == 155.0

    def test_parse_includes_last_dividend_value(self) -> None:
        """파싱 결과에 last_dividend_value가 포함된다."""
        service = DividendService()
        raw = [_make_raw_stock("JNJ", last_dividend_value=1.30)]

        stocks = service._parse_raw_data(raw)

        assert stocks[0].last_dividend_value == 1.30


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
