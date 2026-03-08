"""RateService 비즈니스 로직 테스트 모듈.

금리 변동 방향 판단, 수익률 곡선 분석, Slack 포맷팅 등
RateService의 핵심 로직을 검증한다.
"""

from datetime import date
from unittest.mock import patch

import pytest

from src.schemas.rate import RateDataPoint, RateMonitorResult, YieldCurveStatus
from src.services.rate_service import RateService


@pytest.fixture
def service() -> RateService:
    """RateService 인스턴스를 생성한다."""
    return RateService()


class TestDetermineDirection:
    """_determine_direction 메서드 테스트."""

    def test_up_direction(self, service: RateService) -> None:
        """양수 변동 시 UP을 반환한다."""
        assert service._determine_direction(0.05) == "UP"

    def test_down_direction(self, service: RateService) -> None:
        """음수 변동 시 DOWN을 반환한다."""
        assert service._determine_direction(-0.05) == "DOWN"

    def test_flat_direction_zero(self, service: RateService) -> None:
        """0 변동 시 FLAT을 반환한다."""
        assert service._determine_direction(0.0) == "FLAT"

    def test_flat_direction_small_positive(
        self, service: RateService,
    ) -> None:
        """1bp 미만 양수 변동 시 FLAT을 반환한다."""
        assert service._determine_direction(0.005) == "FLAT"

    def test_flat_direction_none(self, service: RateService) -> None:
        """None 입력 시 FLAT을 반환한다."""
        assert service._determine_direction(None) == "FLAT"


class TestCalculateChange:
    """_calculate_change 메서드 테스트."""

    def test_normal_change(self, service: RateService) -> None:
        """정상 변동을 계산한다."""
        observations = [
            {"date": f"2026-03-0{i}", "value": 4.0 + i * 0.01}
            for i in range(1, 8)
        ]
        # 최신(4.07) - 5거래일전(4.02) = 0.05
        change = service._calculate_change(observations, 5)
        assert change is not None
        assert abs(change - 0.05) < 0.001

    def test_insufficient_data(self, service: RateService) -> None:
        """데이터 부족 시 None을 반환한다."""
        observations = [
            {"date": "2026-03-01", "value": 4.0},
            {"date": "2026-03-02", "value": 4.01},
        ]
        assert service._calculate_change(observations, 5) is None


class TestAnalyzeYieldCurve:
    """_analyze_yield_curve 메서드 테스트."""

    def _make_rate(
        self, series_id: str, value: float,
    ) -> RateDataPoint:
        """테스트용 RateDataPoint를 생성한다."""
        return RateDataPoint(
            series_id=series_id,
            name=f"Test {series_id}",
            value=value,
            observed_date=date(2026, 3, 6),
        )

    def test_normal_curve(self, service: RateService) -> None:
        """정상 수익률 곡선을 감지한다."""
        rates = [
            self._make_rate("DGS2", 3.90),
            self._make_rate("DGS10", 4.30),
        ]
        result = service._analyze_yield_curve(rates)
        assert result is not None
        assert not result.is_inverted
        assert result.spread_10y_2y == 0.40

    def test_inverted_curve(self, service: RateService) -> None:
        """역전된 수익률 곡선을 감지한다."""
        rates = [
            self._make_rate("DGS2", 4.50),
            self._make_rate("DGS10", 4.20),
        ]
        result = service._analyze_yield_curve(rates)
        assert result is not None
        assert result.is_inverted
        assert result.spread_10y_2y == -0.30

    def test_flat_curve(self, service: RateService) -> None:
        """평탄화된 수익률 곡선을 감지한다."""
        rates = [
            self._make_rate("DGS2", 4.25),
            self._make_rate("DGS10", 4.30),
        ]
        result = service._analyze_yield_curve(rates)
        assert result is not None
        assert not result.is_inverted
        assert "평탄화" in result.status

    def test_fallback_to_t10y2y(self, service: RateService) -> None:
        """DGS2/DGS10이 없을 때 T10Y2Y 시리즈로 대체한다."""
        rates = [self._make_rate("T10Y2Y", -0.15)]
        result = service._analyze_yield_curve(rates)
        assert result is not None
        assert result.is_inverted

    def test_no_data(self, service: RateService) -> None:
        """금리 데이터 없으면 None을 반환한다."""
        result = service._analyze_yield_curve([])
        assert result is None


class TestFormatForSlack:
    """format_for_slack 메서드 테스트."""

    def test_empty_result(self, service: RateService) -> None:
        """데이터 없을 때 안내 블록을 반환한다."""
        result = RateMonitorResult()
        blocks = service.format_for_slack(result)
        assert len(blocks) == 1
        text = blocks[0].to_slack_dict()["text"]["text"]
        assert "금리 데이터를 가져올 수 없습니다" in text

    def test_with_us_rates(self, service: RateService) -> None:
        """미국 금리가 포함된 결과를 포맷팅한다."""
        result = RateMonitorResult(
            us_rates=[
                RateDataPoint(
                    series_id="DGS10",
                    name="미국 10년물 국채",
                    value=4.25,
                    observed_date=date(2026, 3, 6),
                    change_1w=-0.08,
                    direction="DOWN",
                ),
            ],
        )
        blocks = service.format_for_slack(result)
        assert len(blocks) == 1
        text = blocks[0].to_slack_dict()["text"]["text"]
        assert "미국 금리" in text
        assert "4.25%" in text
        assert "arrow_down" in text

    def test_with_yield_curve_inversion(
        self, service: RateService,
    ) -> None:
        """수익률 곡선 역전 경고가 표시된다."""
        result = RateMonitorResult(
            us_rates=[
                RateDataPoint(
                    series_id="DGS10",
                    name="미국 10년물 국채",
                    value=4.25,
                    observed_date=date(2026, 3, 6),
                ),
            ],
            yield_curve=YieldCurveStatus(
                spread_10y_2y=-0.15,
                is_inverted=True,
                status="역전 — 경기침체 경고 신호",
            ),
        )
        blocks = service.format_for_slack(result)
        text = blocks[0].to_slack_dict()["text"]["text"]
        assert "warning" in text
        assert "역전" in text


class TestBuildRateDataPoint:
    """_build_rate_data_point 메서드 테스트."""

    def test_normal_build(self, service: RateService) -> None:
        """정상 관측값으로 RateDataPoint를 생성한다."""
        observations = [
            {"date": f"2026-01-{5 + i:02d}", "value": 4.0 + i * 0.01}
            for i in range(25)
        ]
        result = service._build_rate_data_point(
            series_id="DGS10",
            name="미국 10년물 국채",
            observations=observations,
        )
        assert result is not None
        assert result.series_id == "DGS10"
        assert result.value == round(4.0 + 24 * 0.01, 2)
        assert result.change_1w is not None
        assert result.change_1m is not None

    def test_empty_observations(self, service: RateService) -> None:
        """빈 관측값이면 None을 반환한다."""
        result = service._build_rate_data_point(
            series_id="DGS10",
            name="미국 10년물 국채",
            observations=[],
        )
        assert result is None
