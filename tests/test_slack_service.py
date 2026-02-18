"""SlackService 비즈니스 로직 테스트 모듈.

run_digest() 성공/실패, get_last_status() 검증,
반환값이 올바른 Pydantic 모델인지 확인한다.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from src.schemas.slack import DigestResult, DigestStatus, SlackConfig
from src.services.slack_service import SlackService, format_section


def _make_config() -> SlackConfig:
    """테스트용 SlackConfig를 생성한다.

    Returns:
        SlackConfig: 테스트용 설정 인스턴스.
    """
    return SlackConfig(
        webhook_url=SecretStr("https://hooks.slack.com/services/test"),
        bot_token=SecretStr("xoxb-test-token"),
        app_token=SecretStr("xapp-test-token"),
        channel="#test",
        _env_file=None,  # type: ignore[call-arg]
    )


class TestSlackServiceRunDigest:
    """SlackService.run_digest() 테스트."""

    @patch("src.services.slack_service.send_digest")
    def test_run_digest_success(
        self, mock_send: MagicMock
    ) -> None:
        """발송 성공 시 success=True인 DigestResult를 반환한다."""
        mock_send.return_value = True

        service = SlackService(_make_config())
        result = service.run_digest()

        assert isinstance(result, DigestResult)
        assert result.success is True
        assert result.message == "다이제스트 발송 완료"
        assert result.duration_sec >= 0

    @patch("src.services.slack_service.send_digest")
    def test_run_digest_failure(
        self, mock_send: MagicMock
    ) -> None:
        """발송 실패 시 success=False인 DigestResult를 반환한다."""
        mock_send.side_effect = RuntimeError("Webhook 오류")

        service = SlackService(_make_config())
        result = service.run_digest()

        assert isinstance(result, DigestResult)
        assert result.success is False
        assert "발송 실패" in result.message
        assert "Webhook 오류" in result.message

    @patch("src.services.slack_service.send_digest")
    def test_run_digest_connection_error(
        self, mock_send: MagicMock
    ) -> None:
        """ConnectionError 발생 시 예외를 catch하여 실패 결과를 반환한다."""
        mock_send.side_effect = ConnectionError("네트워크 오류")

        service = SlackService(_make_config())
        result = service.run_digest()

        assert result.success is False
        assert "네트워크 오류" in result.message

    @patch("src.services.slack_service.send_digest")
    def test_run_digest_records_duration(
        self, mock_send: MagicMock
    ) -> None:
        """실행 소요 시간이 기록된다."""
        mock_send.return_value = True

        service = SlackService(_make_config())
        result = service.run_digest()

        assert result.duration_sec >= 0
        assert isinstance(result.duration_sec, float)


class TestSlackServiceGetLastStatus:
    """SlackService.get_last_status() 테스트."""

    def test_no_previous_run(self) -> None:
        """실행 이력이 없을 때 기본 상태를 반환한다."""
        service = SlackService(_make_config())
        status = service.get_last_status()

        assert isinstance(status, DigestStatus)
        assert status.last_run_at is None
        assert status.success is None
        assert "아직 실행된" in status.summary

    @patch("src.services.slack_service.send_digest")
    def test_after_successful_run(
        self, mock_send: MagicMock
    ) -> None:
        """성공적인 실행 후 상태를 조회한다."""
        mock_send.return_value = True

        service = SlackService(_make_config())
        service.run_digest()
        status = service.get_last_status()

        assert isinstance(status, DigestStatus)
        assert status.success is True
        assert status.last_run_at is not None
        assert status.summary == "다이제스트 발송 완료"

    @patch("src.services.slack_service.send_digest")
    def test_after_failed_run(
        self, mock_send: MagicMock
    ) -> None:
        """실패한 실행 후 상태를 조회한다."""
        mock_send.side_effect = RuntimeError("실패")

        service = SlackService(_make_config())
        service.run_digest()
        status = service.get_last_status()

        assert status.success is False
        assert "발송 실패" in status.summary


class TestFormatSection:
    """format_section 헬퍼 함수 테스트."""

    def test_format_section_valid(self) -> None:
        """유효한 입력으로 section 블록을 생성한다."""
        block = format_section(
            title="테스트 섹션",
            items=["항목 1", "항목 2"],
            emoji=":star:",
        )

        assert block.type == "section"
        assert block.text is not None
        assert block.text.type == "mrkdwn"
        assert ":star:" in block.text.text
        assert "*테스트 섹션*" in block.text.text
        assert "항목 1" in block.text.text
        assert "항목 2" in block.text.text

    def test_format_section_empty_title(self) -> None:
        """빈 제목은 ValueError를 발생시킨다."""
        with pytest.raises(ValueError, match="섹션 제목이 비어 있습니다"):
            format_section(title="", items=["항목"], emoji=":star:")

    def test_format_section_empty_items(self) -> None:
        """빈 항목 리스트는 ValueError를 발생시킨다."""
        with pytest.raises(ValueError, match="섹션 항목 리스트가 비어 있습니다"):
            format_section(title="제목", items=[], emoji=":star:")

    def test_format_section_block_kit_dict(self) -> None:
        """생성된 블록의 to_slack_dict() 결과가 올바른 구조인지 검증한다."""
        block = format_section(
            title="주식",
            items=["KOSPI: 2650"],
            emoji=":chart:",
        )
        d = block.to_slack_dict()

        assert d["type"] == "section"
        assert "text" in d
        assert d["text"]["type"] == "mrkdwn"
        # None 필드는 제외되어야 함
        assert "block_id" not in d
        assert "elements" not in d
