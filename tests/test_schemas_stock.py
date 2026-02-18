"""DividendStock, DividendScanResult 및 관련 Pydantic 모델 테스트 모듈.

직렬화/역직렬화, 유효성 검증, 기본값 동작을 테스트한다.
TechnicalIndicators, RiskAssessment, DividendProfitAnalysis도 포함한다.
"""

from datetime import date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.schemas.stock import (
    DividendProfitAnalysis,
    DividendScanResult,
    DividendStock,
    RiskAssessment,
    TechnicalIndicators,
)


def _make_stock(**overrides: Any) -> DividendStock:
    """테스트용 DividendStock 인스턴스를 생성한다.

    Args:
        **overrides: 기본값을 덮어쓸 필드값.

    Returns:
        DividendStock: 테스트용 인스턴스.
    """
    defaults: dict[str, Any] = {
        "ticker": "JNJ",
        "company_name": "Johnson & Johnson",
        "ex_dividend_date": date(2026, 2, 20),
        "dividend_yield": 3.5,
        "dividend_amount": 5.2,
        "market_cap": 400_000_000_000,
        "yahoo_finance_url": "https://finance.yahoo.com/quote/JNJ",
    }
    defaults.update(overrides)
    return DividendStock(**defaults)


class TestDividendStock:
    """DividendStock 모델 테스트."""

    def test_create_valid_stock(self) -> None:
        """유효한 입력으로 DividendStock을 생성한다."""
        stock = _make_stock()

        assert stock.ticker == "JNJ"
        assert stock.company_name == "Johnson & Johnson"
        assert stock.ex_dividend_date == date(2026, 2, 20)
        assert stock.dividend_yield == 3.5
        assert stock.dividend_amount == 5.2
        assert stock.market_cap == 400_000_000_000

    def test_serialize_to_dict(self) -> None:
        """DividendStock을 dict로 직렬화한다."""
        stock = _make_stock()
        data = stock.model_dump()

        assert data["ticker"] == "JNJ"
        assert data["ex_dividend_date"] == date(2026, 2, 20)
        assert isinstance(data["dividend_yield"], float)

    def test_json_roundtrip(self) -> None:
        """JSON 직렬화 후 역직렬화가 동일한 결과를 반환한다."""
        original = _make_stock()
        json_str = original.model_dump_json()
        restored = DividendStock.model_validate_json(json_str)

        assert original.ticker == restored.ticker
        assert original.dividend_yield == restored.dividend_yield
        assert original.ex_dividend_date == restored.ex_dividend_date

    def test_missing_required_field_raises_error(self) -> None:
        """필수 필드 누락 시 ValidationError가 발생한다."""
        with pytest.raises(ValidationError):
            DividendStock(
                ticker="JNJ",
                company_name="Johnson & Johnson",
                # ex_dividend_date 누락
            )  # type: ignore[call-arg]

    def test_invalid_date_format_raises_error(self) -> None:
        """유효하지 않은 날짜 형식은 ValidationError를 발생시킨다."""
        with pytest.raises(ValidationError):
            _make_stock(ex_dividend_date="not-a-date")

    def test_negative_yield_accepted(self) -> None:
        """음수 배당수익률은 유효하다 (모델 레벨에서 제한 없음)."""
        stock = _make_stock(dividend_yield=-1.0)
        assert stock.dividend_yield == -1.0

    def test_zero_market_cap(self) -> None:
        """시가총액 0은 유효하다 (필터링은 서비스 레이어에서)."""
        stock = _make_stock(market_cap=0)
        assert stock.market_cap == 0

    def test_default_optional_fields(self) -> None:
        """선택 필드의 기본값이 올바르다."""
        stock = _make_stock()

        assert stock.current_price == 0.0
        assert stock.last_dividend_value == 0.0
        assert stock.indicators is None
        assert stock.risk is None
        assert stock.profit_analysis is None

    def test_stock_with_all_optional_fields(self) -> None:
        """모든 선택 필드를 포함한 종목을 생성한다."""
        stock = _make_stock(
            current_price=150.0,
            last_dividend_value=1.30,
            indicators=TechnicalIndicators(rsi_14=45.0),
            risk=RiskAssessment(
                risk_level="LOW",
                reasons=["정상"],
                recommendation="BUY",
            ),
            profit_analysis=DividendProfitAnalysis(
                gross_dividend_yield=3.5,
                net_dividend_yield=2.96,
                estimated_ex_date_drop=1.0,
                net_profit_yield=1.96,
                is_profitable=True,
                verdict="테스트",
            ),
        )

        assert stock.current_price == 150.0
        assert stock.last_dividend_value == 1.30
        assert stock.indicators is not None
        assert stock.risk is not None
        assert stock.profit_analysis is not None


class TestTechnicalIndicators:
    """TechnicalIndicators 모델 테스트."""

    def test_all_none_defaults(self) -> None:
        """모든 필드의 기본값이 None이다."""
        ti = TechnicalIndicators()

        assert ti.rsi_14 is None
        assert ti.stochastic_k is None
        assert ti.stochastic_d is None
        assert ti.volatility_20d is None
        assert ti.price_change_5d is None
        assert ti.avg_volume_20d is None

    def test_set_all_values(self) -> None:
        """모든 필드에 값을 설정한다."""
        ti = TechnicalIndicators(
            rsi_14=45.2,
            stochastic_k=32.1,
            stochastic_d=35.0,
            volatility_20d=22.5,
            price_change_5d=-1.3,
            avg_volume_20d=7_500_000.0,
        )

        assert ti.rsi_14 == 45.2
        assert ti.stochastic_k == 32.1
        assert ti.stochastic_d == 35.0
        assert ti.volatility_20d == 22.5
        assert ti.price_change_5d == -1.3
        assert ti.avg_volume_20d == 7_500_000.0

    def test_json_roundtrip(self) -> None:
        """JSON 직렬화/역직렬화 라운드트립."""
        original = TechnicalIndicators(
            rsi_14=50.0, volatility_20d=25.0,
        )
        json_str = original.model_dump_json()
        restored = TechnicalIndicators.model_validate_json(json_str)

        assert restored.rsi_14 == 50.0
        assert restored.volatility_20d == 25.0
        assert restored.stochastic_k is None


class TestRiskAssessment:
    """RiskAssessment 모델 테스트."""

    def test_valid_low_risk(self) -> None:
        """LOW 리스크 생성."""
        ra = RiskAssessment(
            risk_level="LOW",
            reasons=["모든 지표 정상"],
            recommendation="BUY",
        )

        assert ra.risk_level == "LOW"
        assert ra.recommendation == "BUY"
        assert len(ra.reasons) == 1

    def test_valid_high_risk(self) -> None:
        """HIGH 리스크 생성."""
        ra = RiskAssessment(
            risk_level="HIGH",
            reasons=["RSI 80", "변동성 55%"],
            recommendation="SKIP",
        )

        assert ra.risk_level == "HIGH"
        assert len(ra.reasons) == 2

    def test_invalid_risk_level(self) -> None:
        """유효하지 않은 risk_level은 ValidationError를 발생시킨다."""
        with pytest.raises(ValidationError):
            RiskAssessment(
                risk_level="EXTREME",  # type: ignore[arg-type]
                reasons=["테스트"],
                recommendation="BUY",
            )

    def test_invalid_recommendation(self) -> None:
        """유효하지 않은 recommendation은 ValidationError를 발생시킨다."""
        with pytest.raises(ValidationError):
            RiskAssessment(
                risk_level="LOW",
                reasons=["테스트"],
                recommendation="SELL",  # type: ignore[arg-type]
            )

    def test_json_roundtrip(self) -> None:
        """JSON 직렬화/역직렬화 라운드트립."""
        original = RiskAssessment(
            risk_level="MEDIUM",
            reasons=["RSI 70", "주의"],
            recommendation="HOLD",
        )
        json_str = original.model_dump_json()
        restored = RiskAssessment.model_validate_json(json_str)

        assert restored.risk_level == "MEDIUM"
        assert restored.reasons == ["RSI 70", "주의"]


class TestDividendProfitAnalysis:
    """DividendProfitAnalysis 모델 테스트."""

    def test_profitable_analysis(self) -> None:
        """수익 케이스."""
        pa = DividendProfitAnalysis(
            gross_dividend_yield=5.0,
            net_dividend_yield=4.23,
            estimated_ex_date_drop=1.0,
            net_profit_yield=3.23,
            is_profitable=True,
            verdict="세후에도 +3.23% 수익 예상",
        )

        assert pa.is_profitable is True
        assert pa.net_profit_yield == 3.23
        assert pa.tax_rate == 15.4  # 기본값

    def test_unprofitable_analysis(self) -> None:
        """손실 케이스."""
        pa = DividendProfitAnalysis(
            gross_dividend_yield=3.0,
            net_dividend_yield=2.54,
            estimated_ex_date_drop=5.0,
            net_profit_yield=-2.46,
            is_profitable=False,
            verdict="세후 -2.46% 손실 예상",
        )

        assert pa.is_profitable is False
        assert pa.net_profit_yield == -2.46

    def test_default_tax_rate(self) -> None:
        """기본 세율이 15.4%이다."""
        pa = DividendProfitAnalysis(
            gross_dividend_yield=4.0,
            net_dividend_yield=3.38,
            estimated_ex_date_drop=1.0,
            net_profit_yield=2.38,
            is_profitable=True,
            verdict="테스트",
        )

        assert pa.tax_rate == 15.4

    def test_tax_calculation_accuracy(self) -> None:
        """세후 배당수익률 계산이 정확하다 (4.0 × 0.846 = 3.384)."""
        gross = 4.0
        net = gross * (1 - 15.4 / 100)

        pa = DividendProfitAnalysis(
            gross_dividend_yield=gross,
            net_dividend_yield=round(net, 2),
            estimated_ex_date_drop=1.0,
            net_profit_yield=round(net - 1.0, 2),
            is_profitable=True,
            verdict="테스트",
        )

        assert abs(pa.net_dividend_yield - 3.38) < 0.01

    def test_json_roundtrip(self) -> None:
        """JSON 직렬화/역직렬화 라운드트립."""
        original = DividendProfitAnalysis(
            gross_dividend_yield=5.0,
            net_dividend_yield=4.23,
            estimated_ex_date_drop=1.5,
            net_profit_yield=2.73,
            is_profitable=True,
            verdict="수익 예상",
        )
        json_str = original.model_dump_json()
        restored = DividendProfitAnalysis.model_validate_json(json_str)

        assert restored.net_profit_yield == 2.73
        assert restored.is_profitable is True


class TestDividendScanResult:
    """DividendScanResult 모델 테스트."""

    def test_create_with_stocks(self) -> None:
        """종목 목록이 있는 스캔 결과를 생성한다."""
        stocks = [_make_stock(), _make_stock(ticker="PFE")]
        result = DividendScanResult(
            stocks=stocks,
            scan_range_days=3,
            filters_applied={"min_yield_pct": 3.0},
        )

        assert len(result.stocks) == 2
        assert result.scan_range_days == 3
        assert result.filters_applied["min_yield_pct"] == 3.0

    def test_empty_stocks_list(self) -> None:
        """빈 종목 목록으로 스캔 결과를 생성한다."""
        result = DividendScanResult(
            stocks=[],
            scan_range_days=3,
            filters_applied={},
        )

        assert len(result.stocks) == 0

    def test_default_scanned_at(self) -> None:
        """scanned_at 미지정 시 현재 시각이 기본값으로 설정된다."""
        result = DividendScanResult(
            stocks=[],
            scan_range_days=3,
            filters_applied={},
        )

        assert isinstance(result.scanned_at, datetime)

    def test_default_high_risk_excluded(self) -> None:
        """high_risk_excluded 기본값이 0이다."""
        result = DividendScanResult(
            stocks=[],
            scan_range_days=3,
            filters_applied={},
        )

        assert result.high_risk_excluded == 0

    def test_json_roundtrip(self) -> None:
        """JSON 직렬화 후 역직렬화가 동일한 결과를 반환한다."""
        original = DividendScanResult(
            stocks=[_make_stock()],
            scan_range_days=7,
            filters_applied={"min_yield_pct": 3.0, "max_stocks": 10},
            high_risk_excluded=2,
        )
        json_str = original.model_dump_json()
        restored = DividendScanResult.model_validate_json(json_str)

        assert len(restored.stocks) == 1
        assert restored.stocks[0].ticker == "JNJ"
        assert restored.scan_range_days == 7
        assert restored.high_risk_excluded == 2

    def test_missing_required_field_raises_error(self) -> None:
        """필수 필드 누락 시 ValidationError가 발생한다."""
        with pytest.raises(ValidationError):
            DividendScanResult(
                stocks=[],
                # scan_range_days 누락
            )  # type: ignore[call-arg]
