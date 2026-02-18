"""미국 주식 배당락일 관련 데이터 타입 정의 모듈.

배당 종목 정보, 기술적 지표, 위험도 평가, 세후 수익성 분석,
스캔 결과를 Pydantic 모델로 타입 안전하게 관리한다.
DividendService와 Yahoo Finance 도구 모듈이 이 스키마를 통해 데이터를 주고받는다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TechnicalIndicators(BaseModel):
    """기술적 지표 모음.

    배당락일 전후 주가 변동 위험을 판단하기 위한
    모멘텀, 변동성, 거래량 지표를 담는다.

    Attributes:
        rsi_14: 14일 RSI (Relative Strength Index).
        stochastic_k: 스토캐스틱 %K.
        stochastic_d: 스토캐스틱 %D.
        volatility_20d: 20일 변동성 (연환산 %).
        price_change_5d: 최근 5거래일 수익률 (%).
        avg_volume_20d: 20일 평균 거래량.
    """

    rsi_14: float | None = Field(
        default=None,
        description="14일 RSI. 70 이상 과매수, 30 이하 과매도",
    )
    stochastic_k: float | None = Field(
        default=None,
        description="스토캐스틱 %K (14,3). 80 이상 과매수",
    )
    stochastic_d: float | None = Field(
        default=None,
        description="스토캐스틱 %D (14,3,3). %K와 교차 시그널",
    )
    volatility_20d: float | None = Field(
        default=None,
        description="20일 변동성 (일간 수익률의 표준편차, 연환산 %)",
    )
    price_change_5d: float | None = Field(
        default=None,
        description="최근 5거래일 수익률 (%)",
    )
    avg_volume_20d: float | None = Field(
        default=None,
        description="20일 평균 거래량",
    )


class RiskAssessment(BaseModel):
    """위험도 평가 결과.

    기술적 지표 기반으로 배당락일 전후 낙폭 위험을 판단한 결과를 담는다.

    Attributes:
        risk_level: 위험 등급 (LOW / MEDIUM / HIGH).
        reasons: 위험 판단 근거 리스트.
        recommendation: 투자 권고 (BUY / HOLD / SKIP).
    """

    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        description="위험 등급. LOW: 안전, MEDIUM: 주의, HIGH: 고위험",
    )
    reasons: list[str] = Field(
        description="위험 판단 근거 리스트 (예: 'RSI 78 — 과매수 구간')",
    )
    recommendation: Literal["BUY", "HOLD", "SKIP"] = Field(
        description="투자 권고. BUY: 매수 적합, HOLD: 관망, SKIP: 회피 권고",
    )


class DividendProfitAnalysis(BaseModel):
    """배당 소득세 감안 수익성 분석 결과.

    배당 소득세(15.4%)를 감안하여 배당락일 전후의 실질 수익을 추정한다.

    Attributes:
        gross_dividend_yield: 세전 배당수익률 (%).
        tax_rate: 배당 소득세율 (%).
        net_dividend_yield: 세후 배당수익률 (%).
        estimated_ex_date_drop: 배당락일 예상 주가 하락률 (%).
        net_profit_yield: 세후 배당 - 예상 낙폭 = 순수익률 (%).
        is_profitable: 순수익률이 양수인지 여부.
        verdict: 한줄 판단 문자열.
    """

    gross_dividend_yield: float = Field(
        description="세전 배당수익률 (%)",
    )
    # 한국 배당소득세 15.4% = 소득세 14% + 지방소득세 1.4%
    tax_rate: float = Field(
        default=15.4,
        description="배당 소득세율 (%, 한국 기준 15.4 = 소득세 14% + 지방소득세 1.4%)",
    )
    net_dividend_yield: float = Field(
        description="세후 배당수익률 (%) = 세전 × (1 - 세율/100)",
    )
    estimated_ex_date_drop: float = Field(
        description="배당락일 예상 주가 하락률 (%, 배당금/현재가 × 변동성 보정)",
    )
    net_profit_yield: float = Field(
        description="순수익률 (%) = 세후 배당수익률 - 예상 낙폭률",
    )
    is_profitable: bool = Field(
        description="순수익률이 양수인지 여부 (True면 세후에도 수익 기대)",
    )
    verdict: str = Field(
        description="한줄 판단 (예: '세후에도 +1.2% 수익 예상')",
    )


class DividendStock(BaseModel):
    """배당 종목 정보.

    yfinance에서 수집한 개별 종목의 배당 관련 데이터를 담는다.
    기술적 지표, 위험도 평가, 수익성 분석 결과도 선택적으로 포함한다.

    Attributes:
        ticker: 종목 심볼.
        company_name: 회사명.
        ex_dividend_date: 배당락일.
        dividend_yield: 배당수익률 (%).
        dividend_amount: 연간 배당금 (USD).
        market_cap: 시가총액 (USD).
        current_price: 현재 주가 (USD).
        yahoo_finance_url: Yahoo Finance 종목 페이지 URL.
        indicators: 기술적 지표 (조회 실패 시 None).
        risk: 위험도 평가 결과 (평가 전 None).
        profit_analysis: 세후 수익성 분석 결과 (분석 전 None).
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
    current_price: float = Field(
        default=0.0,
        description="현재 주가 (USD). 수익성 분석 시 낙폭 추정에 사용",
    )
    last_dividend_value: float = Field(
        default=0.0,
        description="마지막 실제 배당금 (USD, 주당 1회분). 낙폭 추정에 사용",
    )
    yahoo_finance_url: str = Field(
        description="Yahoo Finance 종목 페이지 URL"
    )
    indicators: TechnicalIndicators | None = Field(
        default=None,
        description="기술적 지표 (조회 실패 시 None)",
    )
    risk: RiskAssessment | None = Field(
        default=None,
        description="위험도 평가 결과 (평가 전 None)",
    )
    profit_analysis: DividendProfitAnalysis | None = Field(
        default=None,
        description="세후 수익성 분석 결과 (분석 전 None)",
    )


class DividendScanResult(BaseModel):
    """배당락일 스캔 결과.

    DividendService.scan_dividends() 호출 후 반환되는
    필터링된 배당 종목 목록과 메타데이터를 담는다.

    Attributes:
        stocks: 필터링된 배당 종목 리스트.
        scanned_at: 스캔 실행 시각.
        scan_range_days: 스캔 범위 (일).
        scan_start_date: 스캔 시작일 (포함).
        scan_end_date: 스캔 종료일 (포함).
        filters_applied: 적용된 필터 조건 정보.
        high_risk_excluded: HIGH 리스크로 제외된 종목 수.
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
    scan_start_date: date | None = Field(
        default=None,
        description="스캔 시작일 (포함, calculate_scan_range 결과)",
    )
    scan_end_date: date | None = Field(
        default=None,
        description="스캔 종료일 (포함, calculate_scan_range 결과)",
    )
    filters_applied: dict[str, Any] = Field(
        description="적용된 필터 조건 (min_yield, min_market_cap, max_stocks 등)"
    )
    high_risk_excluded: int = Field(
        default=0,
        description="HIGH 리스크로 제외된 종목 수",
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
        current_price=152.0,
        last_dividend_value=1.30,
        yahoo_finance_url="https://finance.yahoo.com/quote/JNJ",
        indicators=TechnicalIndicators(
            rsi_14=45.2,
            stochastic_k=32.1,
            stochastic_d=35.0,
            volatility_20d=22.5,
            price_change_5d=-1.3,
            avg_volume_20d=7_500_000,
        ),
        risk=RiskAssessment(
            risk_level="LOW",
            reasons=["모든 지표 정상 범위"],
            recommendation="BUY",
        ),
        profit_analysis=DividendProfitAnalysis(
            gross_dividend_yield=2.14,
            net_dividend_yield=1.81,
            estimated_ex_date_drop=1.5,
            net_profit_yield=0.31,
            is_profitable=True,
            verdict="세후에도 +0.31% 수익 예상",
        ),
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
        high_risk_excluded=2,
    )
    print(f"스캔 결과: {result.model_dump_json(indent=2)}")
