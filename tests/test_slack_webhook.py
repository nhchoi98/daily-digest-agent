"""Slack Webhook 발송 모듈 테스트.

send_digest 성공/실패, format_section Block Kit dict 검증,
Webhook URL 미설정 에러 처리를 테스트한다.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from src.schemas.slack import DigestBlock, SlackConfig, TextObject
from src.tools.slack_webhook import send_digest


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


def _make_blocks() -> list[DigestBlock]:
    """테스트용 DigestBlock 리스트를 생성한다.

    Returns:
        list[DigestBlock]: 테스트용 블록 리스트.
    """
    return [
        DigestBlock(
            type="section",
            text=TextObject(type="mrkdwn", text="*테스트*"),
        ),
    ]


class TestSendDigest:
    """send_digest 함수 테스트."""

    @patch("src.tools.slack_webhook.WebhookClient")
    def test_send_digest_success(
        self, mock_client_cls: MagicMock
    ) -> None:
        """Webhook 발송 성공 시 True를 반환한다."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client_cls.return_value.send.return_value = mock_response

        config = _make_config()
        blocks = _make_blocks()

        result = send_digest(blocks, config)

        assert result is True
        mock_client_cls.return_value.send.assert_called_once()

    @patch("src.tools.slack_webhook.WebhookClient")
    def test_send_digest_api_failure(
        self, mock_client_cls: MagicMock
    ) -> None:
        """Slack API 오류 시 RuntimeError가 발생한다."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.body = "internal_error"
        mock_client_cls.return_value.send.return_value = mock_response

        config = _make_config()
        blocks = _make_blocks()

        with pytest.raises(RuntimeError, match="Slack Webhook 발송 실패"):
            send_digest(blocks, config)

    def test_send_digest_empty_blocks(self) -> None:
        """빈 블록 리스트 전달 시 ValueError가 발생한다."""
        config = _make_config()

        with pytest.raises(ValueError, match="발송할 블록이 비어 있습니다"):
            send_digest([], config)

    @patch("src.tools.slack_webhook.WebhookClient")
    def test_send_digest_passes_correct_blocks(
        self, mock_client_cls: MagicMock
    ) -> None:
        """DigestBlock이 올바른 dict 형태로 변환되어 전달된다."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client_cls.return_value.send.return_value = mock_response

        config = _make_config()
        blocks = [
            DigestBlock(type="header", text=TextObject(type="plain_text", text="제목")),
            DigestBlock(type="divider"),
        ]

        send_digest(blocks, config)

        call_kwargs = mock_client_cls.return_value.send.call_args
        sent_blocks = call_kwargs.kwargs.get("blocks") or call_kwargs[1].get("blocks")

        assert len(sent_blocks) == 2
        assert sent_blocks[0]["type"] == "header"
        assert sent_blocks[1] == {"type": "divider"}
