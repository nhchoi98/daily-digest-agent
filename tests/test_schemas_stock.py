"""DividendStock, DividendScanResult Pydantic 모델 테스트 모듈.

직렬화/역직렬화, 유효성 검증, 기본값 동작을 테스트한다.
"""

from datetime import date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.schemas.stock import DividendScanResult, DividendStock


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

    def test_json_roundtrip(self) -> None:
        """JSON 직렬화 후 역직렬화가 동일한 결과를 반환한다."""
        original = DividendScanResult(
            stocks=[_make_stock()],
            scan_range_days=7,
            filters_applied={"min_yield_pct": 3.0, "max_stocks": 10},
        )
        json_str = original.model_dump_json()
        restored = DividendScanResult.model_validate_json(json_str)

        assert len(restored.stocks) == 1
        assert restored.stocks[0].ticker == "JNJ"
        assert restored.scan_range_days == 7

    def test_missing_required_field_raises_error(self) -> None:
        """필수 필드 누락 시 ValidationError가 발생한다."""
        with pytest.raises(ValidationError):
            DividendScanResult(
                stocks=[],
                # scan_range_days 누락
            )  # type: ignore[call-arg]
