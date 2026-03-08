"""FRED (Federal Reserve Economic Data) API를 통한 미국 금리 데이터 수집 모듈.

FRED REST API를 사용하여 미국 연방기금금리, 국채 수익률 등
주요 금리 지표의 시계열 데이터를 수집한다.
비즈니스 로직(변동 판단, 위험 분석) 없이 순수 API 호출만 담당한다.
"""

import logging
import os
from datetime import date, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

# FRED API 기본 설정
_FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# API 요청 타임아웃 (초)
_REQUEST_TIMEOUT_SEC = 10

# 모니터링 대상 금리 시리즈
# 왜 이 시리즈들인가: 미국 채권 시장의 핵심 금리 지표로,
# 통화정책(DFF), 단기(DGS2)/장기(DGS10,DGS30) 금리 수준,
# 수익률 곡선 형태(T10Y2Y)를 한눈에 파악할 수 있다.
FRED_SERIES: dict[str, str] = {
    "DFF": "미국 연방기금금리",
    "DGS2": "미국 2년물 국채",
    "DGS10": "미국 10년물 국채",
    "DGS30": "미국 30년물 국채",
    "T10Y2Y": "미국 장단기 스프레드 (10Y-2Y)",
}

# 금리 변동 비교를 위한 과거 데이터 조회 기간 (일)
# 왜 45일인가: 주간(5거래일) + 월간(20거래일) 변동 계산에 필요하며,
# 주말/공휴일 등 비거래일을 감안하면 약 45캘린더일이 적합하다.
_LOOKBACK_DAYS = 45


def get_fred_series(
    series_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """FRED API에서 단일 시계열의 관측값을 조회한다.

    Args:
        series_id: FRED 시계열 식별자 (예: "DGS10", "DFF").
        start_date: 조회 시작일. None이면 45일 전.
        end_date: 조회 종료일. None이면 오늘.
        api_key: FRED API 키. None이면 환경변수 FRED_API_KEY 사용.

    Returns:
        관측값 dict 리스트. 각 dict에는 date(str), value(float) 키가 포함된다.
        날짜 오름차순 정렬. 값이 "."인 관측값(데이터 없음)은 제외된다.

    Raises:
        ValueError: API 키가 설정되지 않은 경우.
        ConnectionError: FRED API 호출 실패 시.
    """
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        raise ValueError(
            "FRED_API_KEY가 설정되지 않았습니다. "
            "환경변수 또는 api_key 인자로 전달하세요."
        )

    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=_LOOKBACK_DAYS)

    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "observation_start": start_date.isoformat(),
        "observation_end": end_date.isoformat(),
        "sort_order": "asc",
    }

    try:
        response = requests.get(
            _FRED_BASE_URL, params=params, timeout=_REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(
            f"FRED API 호출 실패 (series={series_id}): {e}"
        ) from e

    data = response.json()
    observations = data.get("observations", [])

    # "." 값은 FRED에서 데이터 없음을 의미하므로 제외한다
    return [
        {"date": obs["date"], "value": float(obs["value"])}
        for obs in observations
        if obs.get("value") != "."
    ]


def get_all_rates(
    api_key: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """모니터링 대상 모든 금리 시계열을 조회한다.

    FRED_SERIES에 정의된 모든 시리즈를 순차 조회하여
    시리즈 ID를 키로 하는 딕셔너리로 반환한다.
    개별 시리즈 조회 실패 시 해당 시리즈만 건너뛴다.

    Args:
        api_key: FRED API 키. None이면 환경변수 사용.

    Returns:
        dict[str, list[dict]]: 시리즈 ID → 관측값 리스트 매핑.
    """
    results: dict[str, list[dict[str, Any]]] = {}

    for series_id in FRED_SERIES:
        try:
            observations = get_fred_series(series_id, api_key=api_key)
            results[series_id] = observations
            logger.info(
                "FRED %s (%s): %d개 관측값",
                series_id, FRED_SERIES[series_id], len(observations),
            )
        except (ValueError, ConnectionError) as e:
            logger.warning("FRED %s 조회 실패 (스킵): %s", series_id, e)

    return results


if __name__ == "__main__":
    """FRED 금리 데이터를 수집하여 출력한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    # 개별 시리즈 테스트
    print("=== 미국 10년물 국채 ===")
    try:
        data = get_fred_series("DGS10")
        if data:
            latest = data[-1]
            print(f"  최신: {latest['date']} → {latest['value']}%")
            print(f"  조회 기간: {data[0]['date']} ~ {data[-1]['date']}")
            print(f"  데이터 포인트: {len(data)}개")
        else:
            print("  데이터 없음")
    except (ValueError, ConnectionError) as e:
        print(f"  조회 실패: {e}")

    # 전체 시리즈 조회
    print("\n=== 전체 금리 데이터 ===")
    all_rates = get_all_rates()
    for sid, obs_list in all_rates.items():
        if obs_list:
            latest = obs_list[-1]
            print(
                f"  {sid:10s} ({FRED_SERIES[sid]}): "
                f"{latest['value']}% ({latest['date']})"
            )
