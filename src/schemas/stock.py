"""미국 주식 배당락일 관련 데이터 타입 정의 모듈.

배당 종목 정보, 스캔 결과를 Pydantic 모델로 타입 안전하게 관리한다.
DividendService와 Yahoo Finance 도구 모듈이 이 스키마를 통해 데이터를 주고받는다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class DividendStock(BaseModel):
    """배당 종목 정보.

    yfinance에서 수집한 개별 종목의 배당 관련 데이터를 담는다.

    Attributes:
        ticker: 종목 심볼.
        company_name: 회사명.
        ex_dividend_date: 배당락일.
        dividend_yield: 배당수익률 (%).
        dividend_amount: 연간 배당금 (USD).
        market_cap: 시가총액 (USD).
        yahoo_finance_url: Yahoo Finance 종목 페이지 URL.
    """

    ticker: str = Field(description="종목 심볼 (예: AAPL, JNJ)")
    company_name: str = Field(description="회사명 (예: Apple Inc.)")
    ex_dividend_date: date = Field(description="배당락일 (ex-dividend date)")
    dividend_yield: float = Field(
        description="배당수익률 (%, 예: 3.5는 3.5%를 의미)"
    )
    dividend_amount: float = Field(
        description="연간 배당금 (USD, 주당)"
    )
    market_cap: int = Field(
        description="시가총액 (USD, 예: 1000000000 = $1B)"
    )
    yahoo_finance_url: str = Field(
        description="Yahoo Finance 종목 페이지 URL"
    )


class DividendScanResult(BaseModel):
    """배당락일 스캔 결과.

    DividendService.scan_dividends() 호출 후 반환되는
    필터링된 배당 종목 목록과 메타데이터를 담는다.

    Attributes:
        stocks: 필터링된 배당 종목 리스트.
        scanned_at: 스캔 실행 시각.
        scan_range_days: 스캔 범위 (일).
        filters_applied: 적용된 필터 조건 정보.
    """

    stocks: list[DividendStock] = Field(
        description="필터링된 배당 종목 리스트 (수익률 내림차순 정렬)"
    )
    scanned_at: datetime = Field(
        default_factory=datetime.now,
        description="스캔 실행 시각 (ISO 8601 형식)",
    )
    scan_range_days: int = Field(
        description="배당락일 스캔 범위 (오늘로부터 N일 이내)"
    )
    filters_applied: dict[str, Any] = Field(
        description="적용된 필터 조건 (min_yield, min_market_cap, max_stocks 등)"
    )


if __name__ == "__main__":
    """스키마 모델 생성 및 직렬화를 검증한다."""
    stock = DividendStock(
        ticker="JNJ",
        company_name="Johnson & Johnson",
        ex_dividend_date=date(2026, 2, 20),
        dividend_yield=2.14,
        dividend_amount=5.2,
        market_cap=586_400_000_000,
        yahoo_finance_url="https://finance.yahoo.com/quote/JNJ",
    )
    print(f"종목: {stock.model_dump_json(indent=2)}")

    result = DividendScanResult(
        stocks=[stock],
        scan_range_days=3,
        filters_applied={
            "min_yield": 3.0,
            "min_market_cap": 1_000_000_000,
            "max_stocks": 10,
        },
    )
    print(f"스캔 결과: {result.model_dump_json(indent=2)}")
