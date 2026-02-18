"""Pydantic 스키마 모델 테스트 모듈.

DigestBlock, DigestResult, DigestStatus, SlackConfig의
직렬화/역직렬화, 유효성 검증, 환경변수 로드를 테스트한다.
"""

from datetime import datetime

import pytest
from pydantic import SecretStr, ValidationError

from src.schemas.slack import (
    ButtonElement,
    DigestBlock,
    DigestResult,
    DigestStatus,
    SlackConfig,
    TextObject,
)


class TestDigestResult:
    """DigestResult 모델 테스트."""

    def test_serialize_success(self) -> None:
        """성공 결과를 JSON으로 직렬화한다."""
        result = DigestResult(
            success=True,
            message="다이제스트 발송 완료",
            duration_sec=1.5,
        )
        data = result.model_dump()

        assert data["success"] is True
        assert data["message"] == "다이제스트 발송 완료"
        assert data["duration_sec"] == 1.5
        assert "timestamp" in data

    def test_deserialize_from_dict(self) -> None:
        """dict에서 DigestResult를 역직렬화한다."""
        data = {
            "success": False,
            "message": "발송 실패: 네트워크 오류",
            "timestamp": "2026-02-18T09:00:00",
            "duration_sec": 0.3,
        }
        result = DigestResult(**data)

        assert result.success is False
        assert result.message == "발송 실패: 네트워크 오류"
        assert isinstance(result.timestamp, datetime)

    def test_json_roundtrip(self) -> None:
        """JSON 직렬화 후 역직렬화가 동일한 결과를 반환한다."""
        original = DigestResult(
            success=True,
            message="테스트",
            duration_sec=2.0,
        )
        json_str = original.model_dump_json()
        restored = DigestResult.model_validate_json(json_str)

        assert original.success == restored.success
        assert original.message == restored.message
        assert original.duration_sec == restored.duration_sec

    def test_missing_required_field_raises_error(self) -> None:
        """필수 필드 누락 시 ValidationError가 발생한다."""
        with pytest.raises(ValidationError):
            DigestResult(success=True)  # type: ignore[call-arg]

    def test_default_timestamp(self) -> None:
        """timestamp 미지정 시 현재 시각이 기본값으로 설정된다."""
        result = DigestResult(
            success=True,
            message="테스트",
            duration_sec=0.1,
        )
        assert isinstance(result.timestamp, datetime)


class TestDigestStatus:
    """DigestStatus 모델 테스트."""

    def test_no_run_history(self) -> None:
        """실행 이력이 없을 때 기본값을 확인한다."""
        status = DigestStatus(summary="아직 실행된 다이제스트가 없습니다.")

        assert status.last_run_at is None
        assert status.success is None
        assert status.summary == "아직 실행된 다이제스트가 없습니다."

    def test_with_run_history(self) -> None:
        """실행 이력이 있을 때 모든 필드가 설정된다."""
        now = datetime.now()
        status = DigestStatus(
            last_run_at=now,
            success=True,
            summary="발송 완료",
        )

        assert status.last_run_at == now
        assert status.success is True

    def test_missing_summary_raises_error(self) -> None:
        """필수 필드 summary 누락 시 ValidationError가 발생한다."""
        with pytest.raises(ValidationError):
            DigestStatus()  # type: ignore[call-arg]


class TestDigestBlock:
    """DigestBlock 모델 테스트."""

    def test_section_block(self) -> None:
        """section 타입 블록을 생성하고 dict로 변환한다."""
        block = DigestBlock(
            type="section",
            text=TextObject(type="mrkdwn", text="*테스트*"),
        )
        d = block.to_slack_dict()

        assert d["type"] == "section"
        assert d["text"]["type"] == "mrkdwn"
        assert d["text"]["text"] == "*테스트*"
        # None 값인 block_id, elements는 제외되어야 함
        assert "block_id" not in d
        assert "elements" not in d

    def test_divider_block(self) -> None:
        """divider 타입 블록은 type만 포함한다."""
        block = DigestBlock(type="divider")
        d = block.to_slack_dict()

        assert d == {"type": "divider"}

    def test_actions_block_with_button(self) -> None:
        """actions 블록에 버튼 요소를 포함한다."""
        block = DigestBlock(
            type="actions",
            elements=[
                ButtonElement(
                    text=TextObject(type="plain_text", text="클릭"),
                    action_id="test_action",
                    style="primary",
                ),
            ],
        )
        d = block.to_slack_dict()

        assert d["type"] == "actions"
        assert len(d["elements"]) == 1
        assert d["elements"][0]["action_id"] == "test_action"
        assert d["elements"][0]["style"] == "primary"

    def test_header_block(self) -> None:
        """header 타입 블록을 생성한다."""
        block = DigestBlock(
            type="header",
            text=TextObject(type="plain_text", text="제목"),
        )
        d = block.to_slack_dict()

        assert d["type"] == "header"
        assert d["text"]["type"] == "plain_text"

    def test_invalid_type_raises_error(self) -> None:
        """허용되지 않는 블록 타입은 ValidationError를 발생시킨다."""
        with pytest.raises(ValidationError):
            DigestBlock(type="invalid")  # type: ignore[arg-type]


class TestSlackConfig:
    """SlackConfig 환경변수 모델 테스트."""

    def test_load_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """환경변수에서 SlackConfig를 로드한다."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("SLACK_CHANNEL", "#test-channel")

        config = SlackConfig()  # type: ignore[call-arg]

        assert config.webhook_url.get_secret_value() == "https://hooks.slack.com/test"
        assert config.bot_token.get_secret_value() == "xoxb-test-token"
        assert config.channel == "#test-channel"

    def test_default_channel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """채널 미지정 시 기본값 #daily-digest를 사용한다."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
        monkeypatch.delenv("SLACK_CHANNEL", raising=False)

        config = SlackConfig(
            _env_file=None,  # type: ignore[call-arg]
        )

        assert config.channel == "#daily-digest"

    def test_secret_str_masking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SecretStr 필드는 문자열 변환 시 마스킹된다."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/secret")
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-secret")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-secret")

        config = SlackConfig()  # type: ignore[call-arg]

        # SecretStr의 str()은 '**********'를 반환
        assert "secret" not in str(config.webhook_url)
        assert isinstance(config.webhook_url, SecretStr)

    def test_missing_required_env_raises_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """필수 환경변수 누락 시 ValidationError가 발생한다."""
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)

        with pytest.raises(ValidationError):
            SlackConfig(_env_file=None)  # type: ignore[call-arg]


class TestTextObject:
    """TextObject 모델 테스트."""

    def test_default_type_is_mrkdwn(self) -> None:
        """기본 텍스트 타입은 mrkdwn이다."""
        text = TextObject(text="테스트")
        assert text.type == "mrkdwn"

    def test_plain_text_type(self) -> None:
        """plain_text 타입을 명시적으로 지정한다."""
        text = TextObject(type="plain_text", text="테스트")
        assert text.type == "plain_text"


class TestButtonElement:
    """ButtonElement 모델 테스트."""

    def test_button_without_style(self) -> None:
        """style 미지정 시 None이 기본값이다."""
        button = ButtonElement(
            text=TextObject(type="plain_text", text="버튼"),
            action_id="test",
        )
        assert button.style is None
        assert button.type == "button"

    def test_button_with_style(self) -> None:
        """style을 지정한 버튼을 생성한다."""
        button = ButtonElement(
            text=TextObject(type="plain_text", text="삭제"),
            action_id="delete",
            style="danger",
        )
        assert button.style == "danger"
