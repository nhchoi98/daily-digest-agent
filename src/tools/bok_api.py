"""한국은행 경제통계시스템 (ECOS) API를 통한 한국 금리 데이터 수집 모듈.

한국은행 Open API를 사용하여 기준금리, 콜금리, CD금리, 국고채 수익률 등
주요 금리 지표를 수집한다.
비즈니스 로직 없이 순수 API 호출만 담당한다.
"""

import logging
import os
from datetime import date, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 한국은행 ECOS API 기본 URL
_BOK_BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"

# API 요청 타임아웃 (초)
_REQUEST_TIMEOUT_SEC = 10

# 모니터링 대상 한국 금리 시리즈
# 형식: stat_code(통계표코드), item_code1(항목코드1), cycle(주기), name(한글명)
# 왜 이 시리즈들인가: 한국 통화정책(기준금리), 단기 금리(콜/CD),
# 장기 금리(국고채 3/10년)를 조합하면 국내 금리 환경을 파악할 수 있다.
BOK_SERIES: list[dict[str, str]] = [
    {
        "stat_code": "722Y001",
        "item_code1": "0101000",
        "cycle": "D",
        "name": "한국 기준금리",
    },
    {
        "stat_code": "817Y002",
        "item_code1": "010200000",
        "cycle": "D",
        "name": "한국 콜금리 (익일물)",
    },
    {
        "stat_code": "817Y002",
        "item_code1": "010200101",
        "cycle": "D",
        "name": "한국 CD금리 (91일)",
    },
    {
        "stat_code": "817Y002",
        "item_code1": "010210000",
        "cycle": "D",
        "name": "한국 국고채 3년",
    },
    {
        "stat_code": "817Y002",
        "item_code1": "010220000",
        "cycle": "D",
        "name": "한국 국고채 10년",
    },
]

# 과거 데이터 조회 기간 (일)
# 왜 45일인가: 주간/월간 변동 계산에 필요한 거래일 확보를 위해
# 비거래일(주말/공휴일)을 감안하여 45캘린더일을 조회한다.
_LOOKBACK_DAYS = 45


def get_bok_series(
    stat_code: str,
    item_code1: str,
    cycle: str = "D",
    start_date: date | None = None,
    end_date: date | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """한국은행 ECOS API에서 단일 통계 시계열을 조회한다.

    Args:
        stat_code: 통계표코드 (예: "722Y001").
        item_code1: 통계항목코드1 (예: "0101000").
        cycle: 주기 (D=일, M=월, Q=분기, A=연).
        start_date: 조회 시작일. None이면 45일 전.
        end_date: 조회 종료일. None이면 오늘.
        api_key: BOK API 키. None이면 환경변수 BOK_API_KEY 사용.

    Returns:
        관측값 dict 리스트. 각 dict에는 date(str), value(float) 키가 포함된다.
        날짜 오름차순 정렬.

    Raises:
        ValueError: API 키가 설정되지 않은 경우.
        ConnectionError: BOK API 호출 실패 시.
    """
    key = api_key or os.environ.get("BOK_API_KEY")
    if not key:
        raise ValueError(
            "BOK_API_KEY가 설정되지 않았습니다. "
            "환경변수 또는 api_key 인자로 전달하세요."
        )

    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=_LOOKBACK_DAYS)

    # 한국은행 API는 날짜 형식이 YYYYMMDD
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    # URL 형식: /StatisticSearch/{KEY}/json/kr/1/100/{통계표코드}/{주기}/{시작}/{끝}/{항목1}
    url = (
        f"{_BOK_BASE_URL}/{key}/json/kr/1/100/"
        f"{stat_code}/{cycle}/{start_str}/{end_str}/{item_code1}"
    )

    try:
        response = requests.get(url, timeout=_REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(
            f"BOK API 호출 실패 (stat={stat_code}): {e}"
        ) from e

    data = response.json()

    # BOK API 에러 응답 처리
    if "StatisticSearch" not in data:
        error_msg = data.get("RESULT", {}).get("MESSAGE", "알 수 없는 오류")
        raise ConnectionError(f"BOK API 에러: {error_msg}")

    rows = data["StatisticSearch"].get("row", [])

    return [
        {
            "date": _parse_bok_date(row["TIME"], cycle),
            "value": float(row["DATA_VALUE"]),
        }
        for row in rows
        if row.get("DATA_VALUE") is not None
    ]


def _parse_bok_date(time_str: str, cycle: str) -> str:
    """BOK API의 시간 문자열을 ISO 날짜 형식으로 변환한다.

    Args:
        time_str: BOK TIME 필드 (예: "20260301", "202603").
        cycle: 주기 (D, M, Q, A).

    Returns:
        ISO 날짜 문자열 (YYYY-MM-DD).
    """
    if cycle == "D" and len(time_str) == 8:
        return f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]}"
    if cycle == "M" and len(time_str) == 6:
        return f"{time_str[:4]}-{time_str[4:6]}-01"
    # 기타 주기는 원본 반환
    return time_str


def get_all_kr_rates(
    api_key: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """모니터링 대상 모든 한국 금리 시리즈를 조회한다.

    BOK_SERIES에 정의된 모든 시리즈를 순차 조회하여
    지표명을 키로 하는 딕셔너리로 반환한다.
    개별 시리즈 조회 실패 시 해당 시리즈만 건너뛴다.

    Args:
        api_key: BOK API 키. None이면 환경변수 사용.

    Returns:
        dict[str, list[dict]]: 지표명 → 관측값 리스트 매핑.
    """
    results: dict[str, list[dict[str, Any]]] = {}

    for series in BOK_SERIES:
        try:
            observations = get_bok_series(
                stat_code=series["stat_code"],
                item_code1=series["item_code1"],
                cycle=series["cycle"],
                api_key=api_key,
            )
            results[series["name"]] = observations
            logger.info(
                "BOK %s: %d개 관측값", series["name"], len(observations),
            )
        except (ValueError, ConnectionError) as e:
            logger.warning(
                "BOK %s 조회 실패 (스킵): %s", series["name"], e,
            )

    return results


if __name__ == "__main__":
    """한국은행 금리 데이터를 수집하여 출력한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    print("=== 한국 금리 데이터 ===")
    all_rates = get_all_kr_rates()
    for name, obs_list in all_rates.items():
        if obs_list:
            latest = obs_list[-1]
            print(f"  {name}: {latest['value']}% ({latest['date']})")
        else:
            print(f"  {name}: 데이터 없음")
