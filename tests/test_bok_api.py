"""한국은행 BOK API 도구 모듈 테스트.

get_bok_series, get_all_kr_rates, _parse_bok_date의 핵심 로직을 검증한다.
실제 API 호출은 mock으로 대체한다.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.tools.bok_api import (
    BOK_SERIES,
    _parse_bok_date,
    get_all_kr_rates,
    get_bok_series,
)


class TestParseBokDate:
    """_parse_bok_date 함수 테스트."""

    def test_daily_format(self) -> None:
        """일간 데이터 날짜를 ISO 형식으로 변환한다."""
        assert _parse_bok_date("20260308", "D") == "2026-03-08"

    def test_monthly_format(self) -> None:
        """월간 데이터 날짜를 ISO 형식으로 변환한다."""
        assert _parse_bok_date("202603", "M") == "2026-03-01"

    def test_unknown_format(self) -> None:
        """알 수 없는 형식은 원본을 반환한다."""
        assert _parse_bok_date("2026", "A") == "2026"


class TestGetBokSeries:
    """get_bok_series 함수 테스트."""

    def test_missing_api_key(self) -> None:
        """API 키가 없으면 ValueError를 발생시킨다."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="BOK_API_KEY"):
                get_bok_series(
                    stat_code="722Y001",
                    item_code1="0101000",
                    api_key=None,
                )

    @patch("src.tools.bok_api.requests.get")
    def test_successful_fetch(self, mock_get: MagicMock) -> None:
        """정상 응답 시 관측값 리스트를 반환한다."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "StatisticSearch": {
                "row": [
                    {"TIME": "20260305", "DATA_VALUE": "3.00"},
                    {"TIME": "20260306", "DATA_VALUE": "3.00"},
                ]
            }
        }
        mock_get.return_value = mock_response

        result = get_bok_series(
            stat_code="722Y001",
            item_code1="0101000",
            api_key="test_key",
        )

        assert len(result) == 2
        assert result[0]["date"] == "2026-03-05"
        assert result[0]["value"] == 3.00

    @patch("src.tools.bok_api.requests.get")
    def test_api_error_response(self, mock_get: MagicMock) -> None:
        """BOK API 에러 응답 시 ConnectionError를 발생시킨다."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "RESULT": {"CODE": "ERROR", "MESSAGE": "해당 데이터가 없습니다."}
        }
        mock_get.return_value = mock_response

        with pytest.raises(ConnectionError, match="BOK API 에러"):
            get_bok_series(
                stat_code="722Y001",
                item_code1="0101000",
                api_key="test_key",
            )

    @patch("src.tools.bok_api.requests.get")
    def test_connection_error(self, mock_get: MagicMock) -> None:
        """네트워크 오류 시 ConnectionError를 발생시킨다."""
        import requests
        mock_get.side_effect = requests.RequestException("timeout")

        with pytest.raises(ConnectionError, match="BOK API 호출 실패"):
            get_bok_series(
                stat_code="722Y001",
                item_code1="0101000",
                api_key="test_key",
            )


class TestGetAllKrRates:
    """get_all_kr_rates 함수 테스트."""

    @patch("src.tools.bok_api.get_bok_series")
    def test_collects_all_series(
        self, mock_series: MagicMock,
    ) -> None:
        """모든 시리즈를 순차 조회하여 결과를 반환한다."""
        mock_series.return_value = [
            {"date": "2026-03-06", "value": 3.00},
        ]

        result = get_all_kr_rates(api_key="test_key")

        assert len(result) == len(BOK_SERIES)

    @patch("src.tools.bok_api.get_bok_series")
    def test_skips_failed_series(
        self, mock_series: MagicMock,
    ) -> None:
        """개별 시리즈 실패 시 해당 시리즈만 건너뛴다."""
        call_count = 0

        def side_effect(**kwargs) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("first series failed")
            return [{"date": "2026-03-06", "value": 3.00}]

        mock_series.side_effect = side_effect

        result = get_all_kr_rates(api_key="test_key")

        assert len(result) == len(BOK_SERIES) - 1
