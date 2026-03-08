"""FRED API 도구 모듈 테스트.

get_fred_series, get_all_rates의 핵심 로직을 검증한다.
실제 API 호출은 mock으로 대체한다.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.tools.fred_api import get_fred_series, get_all_rates, FRED_SERIES


class TestGetFredSeries:
    """get_fred_series 함수 테스트."""

    def test_missing_api_key(self) -> None:
        """API 키가 없으면 ValueError를 발생시킨다."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="FRED_API_KEY"):
                get_fred_series("DGS10", api_key=None)

    @patch("src.tools.fred_api.requests.get")
    def test_successful_fetch(self, mock_get: MagicMock) -> None:
        """정상 응답 시 관측값 리스트를 반환한다."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "observations": [
                {"date": "2026-03-05", "value": "4.25"},
                {"date": "2026-03-06", "value": "4.28"},
                {"date": "2026-03-07", "value": "."},
            ]
        }
        mock_get.return_value = mock_response

        result = get_fred_series("DGS10", api_key="test_key")

        assert len(result) == 2
        assert result[0]["date"] == "2026-03-05"
        assert result[0]["value"] == 4.25
        assert result[1]["value"] == 4.28

    @patch("src.tools.fred_api.requests.get")
    def test_filters_dot_values(self, mock_get: MagicMock) -> None:
        """'.' 값(데이터 없음)을 필터링한다."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "observations": [
                {"date": "2026-03-05", "value": "."},
                {"date": "2026-03-06", "value": "4.28"},
            ]
        }
        mock_get.return_value = mock_response

        result = get_fred_series("DGS10", api_key="test_key")
        assert len(result) == 1

    @patch("src.tools.fred_api.requests.get")
    def test_connection_error(self, mock_get: MagicMock) -> None:
        """네트워크 오류 시 ConnectionError를 발생시킨다."""
        import requests
        mock_get.side_effect = requests.RequestException("timeout")

        with pytest.raises(ConnectionError, match="FRED API 호출 실패"):
            get_fred_series("DGS10", api_key="test_key")


class TestGetAllRates:
    """get_all_rates 함수 테스트."""

    @patch("src.tools.fred_api.get_fred_series")
    def test_collects_all_series(
        self, mock_series: MagicMock,
    ) -> None:
        """모든 시리즈를 순차 조회하여 결과를 반환한다."""
        mock_series.return_value = [
            {"date": "2026-03-06", "value": 4.25},
        ]

        result = get_all_rates(api_key="test_key")

        assert len(result) == len(FRED_SERIES)
        for series_id in FRED_SERIES:
            assert series_id in result

    @patch("src.tools.fred_api.get_fred_series")
    def test_skips_failed_series(
        self, mock_series: MagicMock,
    ) -> None:
        """개별 시리즈 실패 시 해당 시리즈만 건너뛴다."""
        def side_effect(series_id: str, **kwargs) -> list:
            if series_id == "DFF":
                raise ConnectionError("DFF failed")
            return [{"date": "2026-03-06", "value": 4.25}]

        mock_series.side_effect = side_effect

        result = get_all_rates(api_key="test_key")

        assert "DFF" not in result
        assert "DGS10" in result
