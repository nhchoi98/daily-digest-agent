"""Slack Bolt App 핸들러 테스트 모듈.

/digest now, /digest status 커맨드 응답 및
인터랙티브 버튼 핸들러를 테스트한다.
핸들러 로직 테스트는 mock으로 수행하므로 토큰 불필요.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from src.schemas.slack import SlackConfig
from src.services.slack_service import SlackService
from src.tools.slack_bolt_app import (
    _handle_digest_now,
    _handle_digest_status,
    _respond_with_result,
)


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


class TestDigestNowHandler:
    """/digest now 핸들러 테스트."""

    @patch("src.services.slack_service.send_digest")
    def test_digest_now_success(self, mock_send: MagicMock) -> None:
        """발송 성공 시 성공 메시지를 respond로 전달한다."""
        mock_send.return_value = True
        respond = MagicMock()

        config = _make_config()
        service = SlackService(config)
        _handle_digest_now(service, respond)

        # 첫 번째 호출: "잠시만 기다려주세요..."
        assert "잠시만" in respond.call_args_list[0][0][0]
        # 두 번째 호출: 성공 메시지
        assert ":white_check_mark:" in respond.call_args_list[1][0][0]

    @patch("src.services.slack_service.send_digest")
    def test_digest_now_failure(self, mock_send: MagicMock) -> None:
        """발송 실패 시 실패 메시지를 respond로 전달한다."""
        mock_send.side_effect = RuntimeError("Webhook 오류")
        respond = MagicMock()

        config = _make_config()
        service = SlackService(config)
        _handle_digest_now(service, respond)

        # 두 번째 호출: 실패 메시지
        assert ":x:" in respond.call_args_list[1][0][0]


class TestDigestStatusHandler:
    """/digest status 핸들러 테스트."""

    def test_status_no_history(self) -> None:
        """실행 이력이 없을 때 안내 메시지를 반환한다."""
        respond = MagicMock()

        config = _make_config()
        service = SlackService(config)
        _handle_digest_status(service, respond)

        respond.assert_called_once()
        assert "아직 실행된" in respond.call_args[0][0]

    @patch("src.services.slack_service.send_digest")
    def test_status_after_run(self, mock_send: MagicMock) -> None:
        """실행 후 상태 조회 시 결과 메시지를 반환한다."""
        mock_send.return_value = True
        respond = MagicMock()

        config = _make_config()
        service = SlackService(config)
        service.run_digest()
        _handle_digest_status(service, respond)

        respond.assert_called_once()
        assert "다이제스트 발송 완료" in respond.call_args[0][0]


class TestRespondWithResult:
    """_respond_with_result 헬퍼 함수 테스트."""

    def test_success_response(self) -> None:
        """성공 결과에 대해 체크마크 이모지가 포함된 응답을 보낸다."""
        from src.schemas.slack import DigestResult

        result = DigestResult(
            success=True,
            message="완료",
            duration_sec=1.0,
        )
        respond = MagicMock()

        _respond_with_result(result, respond)

        respond.assert_called_once()
        assert ":white_check_mark:" in respond.call_args[0][0]
        assert "1.0초" in respond.call_args[0][0]

    def test_failure_response(self) -> None:
        """실패 결과에 대해 X 이모지가 포함된 응답을 보낸다."""
        from src.schemas.slack import DigestResult

        result = DigestResult(
            success=False,
            message="오류 발생",
            duration_sec=0.5,
        )
        respond = MagicMock()

        _respond_with_result(result, respond)

        respond.assert_called_once()
        assert ":x:" in respond.call_args[0][0]
