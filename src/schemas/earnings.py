"""미국 주식 실적발표 일정 관련 데이터 타입 정의 모듈.

실적발표 종목 정보, EPS 추정치, 서프라이즈 이력,
스캔 결과를 Pydantic 모델로 타입 안전하게 관리한다.
EarningsService와 Yahoo Finance 도구 모듈이 이 스키마를 통해 데이터를 주고받는다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class EarningsStock(BaseModel):
    """실적발표 예정 종목 정보.

    yfinance에서 수집한 개별 종목의 실적발표 관련 데이터를 담는다.
    EPS 추정치, 직전 분기 서프라이즈 이력 등을 선택적으로 포함한다.

    Attributes:
        ticker: 종목 심볼.
        company_name: 회사명.
        earnings_date: 실적발표 예정일.
        earnings_timing: 발표 시점 (장전/장후/미지정).
        eps_estimate: 애널리스트 EPS 추정치.
        revenue_estimate: 매출 추정치.
        market_cap: 시가총액 (USD).
        current_price: 현재 주가 (USD).
        sector: 섹터.
        last_eps_actual: 직전 분기 실제 EPS.
        last_eps_estimate: 직전 분기 EPS 추정치.
        last_surprise_pct: 직전 분기 서프라이즈 (%).
        yahoo_finance_url: Yahoo Finance 종목 페이지 URL.
    """

    ticker: str = Field(description="종목 심볼 (예: AAPL, MSFT)")
    company_name: str = Field(description="회사명 (예: Apple Inc.)")
    earnings_date: date = Field(description="실적발표 예정일")
    earnings_timing: Literal["BMO", "AMC", "TAS"] | None = Field(
        default=None,
        description=(
            "발표 시점. BMO: Before Market Open (장전), "
            "AMC: After Market Close (장후), "
            "TAS: Time Not Supplied (미지정)"
        ),
    )
    eps_estimate: float | None = Field(
        default=None,
        description="애널리스트 EPS 추정치 (USD)",
    )
    revenue_estimate: float | None = Field(
        default=None,
        description="매출 추정치 (USD, 있을 경우)",
    )
    market_cap: int = Field(
        description="시가총액 (USD, 예: 1000000000 = $1B)",
    )
    current_price: float = Field(
        default=0.0,
        description="현재 주가 (USD)",
    )
    sector: str | None = Field(
        default=None,
        description="섹터 (예: Technology, Healthcare)",
    )
    last_eps_actual: float | None = Field(
        default=None,
        description="직전 분기 실제 EPS (USD)",
    )
    last_eps_estimate: float | None = Field(
        default=None,
        description="직전 분기 EPS 추정치 (USD)",
    )
    last_surprise_pct: float | None = Field(
        default=None,
        description="직전 분기 서프라이즈 (%, 양수면 beat, 음수면 miss)",
    )
    yahoo_finance_url: str = Field(
        description="Yahoo Finance 종목 페이지 URL",
    )


class EarningsScanResult(BaseModel):
    """실적발표 일정 스캔 결과.

    EarningsService.scan_earnings() 호출 후 반환되는
    필터링된 종목 목록과 메타데이터를 담는다.

    Attributes:
        stocks: 실적발표 예정 종목 리스트.
        scanned_at: 스캔 실행 시각.
        scan_range_days: 스캔 범위 (일).
        scan_start_date: 스캔 시작일 (포함).
        scan_end_date: 스캔 종료일 (포함).
        total_scanned: 전체 스캔 대상 종목 수.
    """

    stocks: list[EarningsStock] = Field(
        description="실적발표 예정 종목 리스트 (날짜순 정렬)",
    )
    scanned_at: datetime = Field(
        default_factory=datetime.now,
        description="스캔 실행 시각 (ISO 8601 형식)",
    )
    scan_range_days: int = Field(
        description="스캔 범위 (오늘로부터 N일 이내)",
    )
    scan_start_date: date | None = Field(
        default=None,
        description="스캔 시작일 (포함)",
    )
    scan_end_date: date | None = Field(
        default=None,
        description="스캔 종료일 (포함)",
    )
    total_scanned: int = Field(
        description="전체 스캔 대상 종목 수",
    )


if __name__ == "__main__":
    """스키마 모델 생성 및 직렬화를 검증한다."""
    stock = EarningsStock(
        ticker="AAPL",
        company_name="Apple Inc.",
        earnings_date=date(2026, 3, 5),
        earnings_timing="AMC",
        eps_estimate=1.42,
        revenue_estimate=94_000_000_000,
        market_cap=3_500_000_000_000,
        current_price=225.0,
        sector="Technology",
        last_eps_actual=1.40,
        last_eps_estimate=1.35,
        last_surprise_pct=3.7,
        yahoo_finance_url="https://finance.yahoo.com/quote/AAPL",
    )
    print(f"종목: {stock.model_dump_json(indent=2)}")

    result = EarningsScanResult(
        stocks=[stock],
        scan_range_days=14,
        scan_start_date=date(2026, 3, 2),
        scan_end_date=date(2026, 3, 16),
        total_scanned=102,
    )
    print(f"스캔 결과: {result.model_dump_json(indent=2)}")
