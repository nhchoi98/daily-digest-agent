"""금리 모니터링 관련 데이터 타입 정의 모듈.

미국(FRED) 및 한국(BOK) 금리 데이터, 금리 변동 정보,
수익률 곡선 상태를 Pydantic 모델로 타입 안전하게 관리한다.
RateService와 FRED/BOK API 도구 모듈이 이 스키마를 통해 데이터를 주고받는다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class RateDataPoint(BaseModel):
    """단일 금리 데이터 포인트.

    특정 시점의 금리 값과 변동 정보를 담는다.

    Attributes:
        series_id: FRED/BOK 시계열 식별자.
        name: 금리 지표명 (한글).
        value: 현재 금리 값 (%).
        observed_date: 관측일.
        change_1w: 1주 전 대비 변동 (pp).
        change_1m: 1개월 전 대비 변동 (pp).
        direction: 변동 방향 (UP / DOWN / FLAT).
    """

    series_id: str = Field(description="시계열 식별자 (예: DGS10, FEDFUNDS)")
    name: str = Field(description="금리 지표명 (예: '미국 10년물 국채')")
    value: float = Field(description="현재 금리 값 (%)")
    observed_date: date = Field(description="관측일")
    change_1w: float | None = Field(
        default=None,
        description="1주 전 대비 변동 (percentage point)",
    )
    change_1m: float | None = Field(
        default=None,
        description="1개월 전 대비 변동 (percentage point)",
    )
    direction: Literal["UP", "DOWN", "FLAT"] = Field(
        default="FLAT",
        description="변동 방향 (UP: 상승, DOWN: 하락, FLAT: 보합)",
    )


class YieldCurveStatus(BaseModel):
    """수익률 곡선 상태.

    미국 국채 10년물 - 2년물 스프레드로 수익률 곡선 형태를 판단한다.
    스프레드가 음수이면 장단기 금리 역전(inversion)으로 경기침체 신호로 해석한다.

    Attributes:
        spread_10y_2y: 10년물 - 2년물 스프레드 (pp).
        is_inverted: 역전 여부 (스프레드 < 0).
        status: 수익률 곡선 상태 설명.
    """

    spread_10y_2y: float = Field(
        description="10년물 - 2년물 스프레드 (percentage point)",
    )
    is_inverted: bool = Field(
        description="장단기 금리 역전 여부 (True면 경기침체 경고 신호)",
    )
    status: str = Field(
        description="수익률 곡선 상태 설명 (예: '정상', '역전 — 경기침체 경고')",
    )


class RateMonitorResult(BaseModel):
    """금리 모니터링 전체 결과.

    RateService.monitor_rates() 호출 후 반환되는
    미국/한국 금리 데이터와 수익률 곡선 상태를 담는다.

    Attributes:
        us_rates: 미국 금리 데이터 리스트 (FRED).
        kr_rates: 한국 금리 데이터 리스트 (BOK).
        yield_curve: 미국 수익률 곡선 상태.
        monitored_at: 모니터링 실행 시각.
    """

    us_rates: list[RateDataPoint] = Field(
        default_factory=list,
        description="미국 금리 데이터 리스트 (FRED 출처)",
    )
    kr_rates: list[RateDataPoint] = Field(
        default_factory=list,
        description="한국 금리 데이터 리스트 (BOK 출처)",
    )
    yield_curve: YieldCurveStatus | None = Field(
        default=None,
        description="미국 수익률 곡선 상태 (데이터 부족 시 None)",
    )
    monitored_at: datetime = Field(
        default_factory=datetime.now,
        description="모니터링 실행 시각 (ISO 8601 형식)",
    )


if __name__ == "__main__":
    """스키마 모델 생성 및 직렬화를 검증한다."""
    rate = RateDataPoint(
        series_id="DGS10",
        name="미국 10년물 국채",
        value=4.25,
        observed_date=date(2026, 3, 6),
        change_1w=-0.08,
        change_1m=0.15,
        direction="DOWN",
    )
    print(f"금리: {rate.model_dump_json(indent=2)}")

    curve = YieldCurveStatus(
        spread_10y_2y=0.35,
        is_inverted=False,
        status="정상 — 장기 금리가 단기보다 높음",
    )
    print(f"수익률 곡선: {curve.model_dump_json(indent=2)}")

    result = RateMonitorResult(
        us_rates=[rate],
        kr_rates=[],
        yield_curve=curve,
    )
    print(f"모니터링 결과: {result.model_dump_json(indent=2)}")
