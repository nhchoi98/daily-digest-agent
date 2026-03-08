"""미국/한국 금리 모니터링 비즈니스 로직 서비스 모듈.

FRED API와 한국은행 API에서 수집한 금리 데이터를 가공하여
변동 방향, 수익률 곡선 상태, Slack 포맷 변환 등을 수행한다.
tools/fred_api.py와 tools/bok_api.py의 원시 데이터를
의미 있는 결과로 변환한다.
"""

import logging
from datetime import date
from typing import Any

from src.schemas.rate import (
    RateDataPoint,
    RateMonitorResult,
    YieldCurveStatus,
)
from src.schemas.slack import DigestBlock, TextObject
from src.tools.bok_api import BOK_SERIES, get_all_kr_rates
from src.tools.fred_api import FRED_SERIES, get_all_rates

logger = logging.getLogger(__name__)

# 변동 방향 판단 임계값 (percentage point)
# 왜 0.01인가: 금리는 소수점 이하 변동이 의미 있으므로
# 1bp(0.01pp) 이상 변동 시 방향을 표시한다.
_DIRECTION_THRESHOLD_PP = 0.01

# 주간 변동 비교 기간 (거래일)
_WEEK_TRADING_DAYS = 5
# 월간 변동 비교 기간 (거래일)
_MONTH_TRADING_DAYS = 20

# 수익률 곡선 상태 설명 상수
_INVERSION_WARNING = "역전 — 경기침체 경고 신호"
_NORMAL_CURVE = "정상 — 장기 금리가 단기보다 높음"
_FLAT_CURVE = "평탄화 — 스프레드 거의 0에 근접"

# 수익률 곡선 평탄화 판단 임계값 (pp)
# 왜 0.1인가: ±10bp 이내면 사실상 평탄화로 봐야 한다.
_FLAT_THRESHOLD = 0.1


class RateService:
    """미국/한국 금리 모니터링 서비스.

    FRED와 BOK API에서 수집한 금리 데이터를 가공하여
    변동 방향, 수익률 곡선 상태를 분석하고
    Slack Block Kit 포맷으로 변환한다.
    """

    def monitor_rates(self) -> RateMonitorResult:
        """미국/한국 금리를 모니터링한다.

        파이프라인:
        1. FRED API로 미국 금리 수집
        2. BOK API로 한국 금리 수집
        3. 각 시리즈별 변동 방향 계산
        4. 미국 수익률 곡선 상태 판단

        Returns:
            RateMonitorResult: 미국/한국 금리 데이터와 수익률 곡선 상태.
        """
        us_rates = self._fetch_us_rates()
        kr_rates = self._fetch_kr_rates()
        yield_curve = self._analyze_yield_curve(us_rates)

        return RateMonitorResult(
            us_rates=us_rates,
            kr_rates=kr_rates,
            yield_curve=yield_curve,
        )

    def format_for_slack(
        self, result: RateMonitorResult
    ) -> list[DigestBlock]:
        """모니터링 결과를 Slack Block Kit 블록으로 변환한다.

        Args:
            result: monitor_rates()의 반환값.

        Returns:
            list[DigestBlock]: Slack 발송용 블록 목록.
        """
        if not result.us_rates and not result.kr_rates:
            return [self._build_empty_notice()]

        lines: list[str] = []

        # 미국 금리
        if result.us_rates:
            lines.append("*미국 금리*")
            for rate in result.us_rates:
                lines.append(self._format_rate_line(rate))

        # 수익률 곡선
        if result.yield_curve is not None:
            curve = result.yield_curve
            curve_emoji = (
                ":warning:" if curve.is_inverted else ":white_check_mark:"
            )
            lines.append(
                f"  {curve_emoji} 수익률 곡선: {curve.status} "
                f"(스프레드 {curve.spread_10y_2y:+.2f}pp)"
            )

        # 한국 금리
        if result.kr_rates:
            lines.append("")
            lines.append("*한국 금리*")
            for rate in result.kr_rates:
                lines.append(self._format_rate_line(rate))

        markdown_text = ":bank: *금리 모니터*\n" + "\n".join(lines)

        return [
            DigestBlock(
                type="section",
                text=TextObject(type="mrkdwn", text=markdown_text),
            ),
        ]

    # --- Private methods ---

    def _fetch_us_rates(self) -> list[RateDataPoint]:
        """FRED API에서 미국 금리 데이터를 수집하고 가공한다.

        Returns:
            list[RateDataPoint]: 미국 금리 데이터 리스트.
        """
        try:
            raw_data = get_all_rates()
        except (ValueError, ConnectionError) as e:
            logger.error("미국 금리 수집 실패: %s", e)
            return []

        rates: list[RateDataPoint] = []
        for series_id, name in FRED_SERIES.items():
            obs_list = raw_data.get(series_id, [])
            if not obs_list:
                continue

            data_point = self._build_rate_data_point(
                series_id=series_id,
                name=name,
                observations=obs_list,
            )
            if data_point is not None:
                rates.append(data_point)

        return rates

    def _fetch_kr_rates(self) -> list[RateDataPoint]:
        """BOK API에서 한국 금리 데이터를 수집하고 가공한다.

        Returns:
            list[RateDataPoint]: 한국 금리 데이터 리스트.
        """
        try:
            raw_data = get_all_kr_rates()
        except (ValueError, ConnectionError) as e:
            logger.error("한국 금리 수집 실패: %s", e)
            return []

        rates: list[RateDataPoint] = []
        for series in BOK_SERIES:
            name = series["name"]
            obs_list = raw_data.get(name, [])
            if not obs_list:
                continue

            data_point = self._build_rate_data_point(
                series_id=series["stat_code"],
                name=name,
                observations=obs_list,
            )
            if data_point is not None:
                rates.append(data_point)

        return rates

    def _build_rate_data_point(
        self,
        series_id: str,
        name: str,
        observations: list[dict[str, Any]],
    ) -> RateDataPoint | None:
        """관측값 리스트에서 RateDataPoint를 생성한다.

        최신 값을 현재 금리로 사용하고,
        과거 데이터와 비교하여 변동 방향을 계산한다.

        Args:
            series_id: 시계열 식별자.
            name: 금리 지표명.
            observations: 관측값 dict 리스트 (날짜 오름차순).

        Returns:
            RateDataPoint 또는 데이터 부족 시 None.
        """
        if not observations:
            return None

        latest = observations[-1]
        current_value = latest["value"]
        obs_date = date.fromisoformat(latest["date"])

        change_1w = self._calculate_change(
            observations, _WEEK_TRADING_DAYS,
        )
        change_1m = self._calculate_change(
            observations, _MONTH_TRADING_DAYS,
        )
        direction = self._determine_direction(change_1w)

        return RateDataPoint(
            series_id=series_id,
            name=name,
            value=round(current_value, 2),
            observed_date=obs_date,
            change_1w=(
                round(change_1w, 2) if change_1w is not None else None
            ),
            change_1m=(
                round(change_1m, 2) if change_1m is not None else None
            ),
            direction=direction,
        )

    def _calculate_change(
        self,
        observations: list[dict[str, Any]],
        lookback_days: int,
    ) -> float | None:
        """N거래일 전 대비 변동을 계산한다.

        Args:
            observations: 관측값 리스트 (날짜 오름차순).
            lookback_days: 비교할 과거 거래일 수.

        Returns:
            변동폭 (percentage point) 또는 데이터 부족 시 None.
        """
        if len(observations) <= lookback_days:
            return None

        current = observations[-1]["value"]
        past = observations[-1 - lookback_days]["value"]
        return current - past

    def _determine_direction(
        self, change_1w: float | None
    ) -> str:
        """주간 변동을 기반으로 방향을 판단한다.

        Args:
            change_1w: 1주 전 대비 변동 (pp).

        Returns:
            "UP", "DOWN", 또는 "FLAT".
        """
        if change_1w is None:
            return "FLAT"
        if change_1w > _DIRECTION_THRESHOLD_PP:
            return "UP"
        if change_1w < -_DIRECTION_THRESHOLD_PP:
            return "DOWN"
        return "FLAT"

    def _analyze_yield_curve(
        self, us_rates: list[RateDataPoint]
    ) -> YieldCurveStatus | None:
        """미국 수익률 곡선 상태를 분석한다.

        10년물과 2년물 국채 수익률의 스프레드로
        수익률 곡선의 형태를 판단한다.
        두 시리즈가 모두 없으면 T10Y2Y 시리즈를 대안으로 사용한다.

        Args:
            us_rates: 미국 금리 데이터 리스트.

        Returns:
            YieldCurveStatus 또는 데이터 부족 시 None.
        """
        rate_10y = None
        rate_2y = None

        for rate in us_rates:
            if rate.series_id == "DGS10":
                rate_10y = rate.value
            elif rate.series_id == "DGS2":
                rate_2y = rate.value

        if rate_10y is not None and rate_2y is not None:
            spread = rate_10y - rate_2y
            return self._build_yield_curve_status(spread)

        # T10Y2Y 시리즈에서 직접 스프레드를 가져올 수도 있다
        for rate in us_rates:
            if rate.series_id == "T10Y2Y":
                return self._build_yield_curve_status(rate.value)

        return None

    def _build_yield_curve_status(
        self, spread: float
    ) -> YieldCurveStatus:
        """스프레드 값으로 YieldCurveStatus를 생성한다.

        Args:
            spread: 10년물 - 2년물 스프레드 (pp).

        Returns:
            YieldCurveStatus.
        """
        is_inverted = spread < 0

        if is_inverted:
            status = _INVERSION_WARNING
        elif abs(spread) < _FLAT_THRESHOLD:
            status = _FLAT_CURVE
        else:
            status = _NORMAL_CURVE

        return YieldCurveStatus(
            spread_10y_2y=round(spread, 2),
            is_inverted=is_inverted,
            status=status,
        )

    def _format_rate_line(self, rate: RateDataPoint) -> str:
        """단일 금리를 Slack mrkdwn 문자열로 포맷팅한다.

        Args:
            rate: 금리 데이터 포인트.

        Returns:
            Slack mrkdwn 형식 문자열.
        """
        direction_emoji = {
            "UP": ":arrow_up:",
            "DOWN": ":arrow_down:",
            "FLAT": ":left_right_arrow:",
        }
        emoji = direction_emoji.get(rate.direction, "")

        line = f"  {emoji} {rate.name}: *{rate.value:.2f}%*"

        changes: list[str] = []
        if rate.change_1w is not None:
            changes.append(f"1W {rate.change_1w:+.2f}")
        if rate.change_1m is not None:
            changes.append(f"1M {rate.change_1m:+.2f}")
        if changes:
            line += f" ({', '.join(changes)})"

        return line

    def _build_empty_notice(self) -> DigestBlock:
        """금리 데이터 없을 때 안내 블록을 생성한다.

        Returns:
            section 타입의 DigestBlock.
        """
        return DigestBlock(
            type="section",
            text=TextObject(
                type="mrkdwn",
                text=(
                    ":bank: *금리 모니터*\n"
                    "  금리 데이터를 가져올 수 없습니다."
                ),
            ),
        )


if __name__ == "__main__":
    """RateService 파이프라인 전체를 테스트한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    service = RateService()
    result = service.monitor_rates()

    print(f"=== 금리 모니터링 결과 ===")
    print(f"미국 금리: {len(result.us_rates)}개 시리즈")
    for rate in result.us_rates:
        change_str = ""
        if rate.change_1w is not None:
            change_str += f" | 1W: {rate.change_1w:+.2f}pp"
        if rate.change_1m is not None:
            change_str += f" | 1M: {rate.change_1m:+.2f}pp"
        print(
            f"  [{rate.direction:4s}] {rate.name}: "
            f"{rate.value:.2f}%{change_str}"
        )

    if result.yield_curve:
        curve = result.yield_curve
        print(
            f"\n수익률 곡선: {curve.status} "
            f"(스프레드: {curve.spread_10y_2y:+.2f}pp)"
        )

    print(f"\n한국 금리: {len(result.kr_rates)}개 시리즈")
    for rate in result.kr_rates:
        change_str = ""
        if rate.change_1w is not None:
            change_str += f" | 1W: {rate.change_1w:+.2f}pp"
        print(
            f"  [{rate.direction:4s}] {rate.name}: "
            f"{rate.value:.2f}%{change_str}"
        )

    # Slack 포맷 확인
    blocks = service.format_for_slack(result)
    for block in blocks:
        print(f"\nSlack 블록: {block.to_slack_dict()}")
