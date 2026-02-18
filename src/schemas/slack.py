"""Slack 알림 모듈의 입출력 데이터 타입 정의 모듈.

Block Kit 메시지 구조, 실행 결과, 상태 조회 응답, 환경변수 설정을
Pydantic 모델로 타입 안전하게 관리한다.
모든 Slack 관련 모듈은 이 스키마를 통해 데이터를 주고받는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SlackConfig(BaseSettings):
    """Slack 연동에 필요한 환경변수 설정값.

    pydantic-settings의 BaseSettings를 활용하여
    .env 파일 또는 환경변수에서 자동으로 값을 로드한다.
    env_prefix="SLACK_"으로 필드명이 SLACK_* 환경변수에 자동 매핑된다.

    Attributes:
        webhook_url: Slack Incoming Webhook URL.
        bot_token: Slack Bot User OAuth Token (xoxb-).
        app_token: Slack App-Level Token (xapp-).
        channel: 메시지를 발송할 Slack 채널명.
    """

    model_config = SettingsConfigDict(
        env_prefix="SLACK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    webhook_url: SecretStr = Field(
        description="Slack Incoming Webhook URL (https://hooks.slack.com/...)"
    )
    bot_token: SecretStr = Field(
        description="Slack Bot User OAuth Token (xoxb-로 시작)"
    )
    app_token: SecretStr = Field(
        description="Slack App-Level Token, Socket Mode용 (xapp-로 시작)"
    )
    channel: str = Field(
        default="#daily-digest",
        description="메시지를 발송할 Slack 채널명",
    )


class TextObject(BaseModel):
    """Block Kit의 텍스트 오브젝트.

    Slack Block Kit에서 텍스트를 표현하는 기본 단위.
    mrkdwn 또는 plain_text 타입을 지원한다.

    Attributes:
        type: 텍스트 렌더링 타입.
        text: 실제 텍스트 내용.
    """

    type: Literal["mrkdwn", "plain_text"] = Field(
        default="mrkdwn",
        description="텍스트 렌더링 타입 (mrkdwn 또는 plain_text)",
    )
    text: str = Field(description="표시할 텍스트 내용")


class ButtonElement(BaseModel):
    """Block Kit의 버튼 요소.

    actions 블록 내에서 인터랙티브 버튼을 표현한다.
    action_id로 클릭 이벤트를 식별한다.

    Attributes:
        type: 요소 타입 (항상 "button").
        text: 버튼에 표시할 텍스트.
        action_id: 버튼 클릭 시 전달되는 액션 식별자.
        style: 버튼 스타일 (primary/danger, 선택적).
    """

    type: Literal["button"] = Field(
        default="button",
        description="요소 타입 (항상 button)",
    )
    text: TextObject = Field(description="버튼에 표시할 텍스트 오브젝트")
    action_id: str = Field(
        description="버튼 클릭 시 전달되는 고유 액션 식별자"
    )
    style: Literal["primary", "danger"] | None = Field(
        default=None,
        description="버튼 스타일 (primary=초록, danger=빨강, None=기본)",
    )


class DigestBlock(BaseModel):
    """Slack Block Kit 메시지의 단일 블록.

    Slack API의 blocks 배열에 들어가는 개별 블록을 표현한다.
    section, header, divider, actions 타입을 지원한다.

    Attributes:
        type: 블록 타입.
        text: 블록의 텍스트 오브젝트 (section, header에서 사용).
        block_id: 블록 고유 식별자 (선택적).
        elements: 인터랙티브 요소 목록 (actions 블록에서 사용).
    """

    type: Literal["section", "header", "divider", "actions"] = Field(
        description="블록 타입 (section, header, divider, actions)"
    )
    text: TextObject | None = Field(
        default=None,
        description="블록의 텍스트 오브젝트 (section/header에서 필수)",
    )
    block_id: str | None = Field(
        default=None,
        description="블록 고유 식별자 (선택적)",
    )
    elements: list[ButtonElement] | None = Field(
        default=None,
        description="인터랙티브 요소 목록 (actions 블록에서 사용)",
    )

    def to_slack_dict(self) -> dict[str, Any]:
        """Slack API 전송용 dict로 변환한다.

        None 값을 가진 필드는 제외하여 Slack API가
        기대하는 형태의 dict를 반환한다.

        Returns:
            dict[str, Any]: Slack API 전송용 딕셔너리.
        """
        return self.model_dump(exclude_none=True)


class DigestResult(BaseModel):
    """다이제스트 실행 결과.

    run_digest() 호출 후 성공/실패 여부와 상세 정보를 담는다.
    실패 시에도 예외를 던지지 않고 이 모델로 결과를 래핑한다.

    Attributes:
        success: 실행 성공 여부.
        message: 결과 메시지.
        timestamp: 실행 완료 시각.
        duration_sec: 실행 소요 시간 (초).
        stock_count: 다이제스트에 포함된 배당 종목 수.
    """

    success: bool = Field(description="다이제스트 실행 성공 여부")
    message: str = Field(
        description="결과 메시지 (성공 시 발송 요약, 실패 시 에러 내용)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="실행 완료 시각 (ISO 8601 형식)",
    )
    duration_sec: float = Field(
        description="실행 소요 시간 (초 단위, 소수점 포함)"
    )
    stock_count: int = Field(
        default=0,
        description="다이제스트에 포함된 배당 종목 수",
    )


class DigestStatus(BaseModel):
    """마지막 다이제스트 실행 상태 조회 응답.

    get_last_status() 호출 시 반환되는 상태 정보.
    실행 이력이 없으면 last_run_at, success가 None이 된다.

    Attributes:
        last_run_at: 마지막 실행 시각.
        success: 마지막 실행 성공 여부.
        stock_count: 마지막 실행에서 포함된 종목 수.
        summary: 상태 요약 문자열.
    """

    last_run_at: datetime | None = Field(
        default=None,
        description="마지막 다이제스트 실행 시각 (실행 이력이 없으면 None)",
    )
    success: bool | None = Field(
        default=None,
        description="마지막 실행 성공 여부 (실행 이력이 없으면 None)",
    )
    stock_count: int | None = Field(
        default=None,
        description="마지막 실행에서 포함된 배당 종목 수 (실행 이력이 없으면 None)",
    )
    summary: str = Field(
        description="사용자에게 표시할 상태 요약 문자열"
    )


if __name__ == "__main__":
    """각 스키마 모델의 생성 및 직렬화를 검증한다."""
    from dotenv import load_dotenv

    load_dotenv()

    # SlackConfig 환경변수 로드 테스트
    config = SlackConfig()  # type: ignore[call-arg]
    print(f"채널: {config.channel}")
    print(f"Webhook URL 로드됨: {bool(config.webhook_url)}")

    # DigestBlock 생성 테스트
    block = DigestBlock(
        type="section",
        text=TextObject(text="테스트 블록"),
    )
    print(f"블록 dict: {block.to_slack_dict()}")

    # DigestResult 생성 테스트
    result = DigestResult(
        success=True,
        message="테스트 완료",
        duration_sec=1.5,
    )
    print(f"결과: {result.model_dump_json(indent=2)}")

    # DigestStatus 생성 테스트
    status = DigestStatus(summary="아직 실행된 다이제스트가 없습니다.")
    print(f"상태: {status.model_dump_json(indent=2)}")
