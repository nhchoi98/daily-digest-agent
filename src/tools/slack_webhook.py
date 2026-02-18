"""Slack Incoming Webhook을 통한 Block Kit 메시지 발송 모듈.

slack_sdk.webhook.WebhookClient를 사용하여 Incoming Webhook URL로
Block Kit 형식의 메시지를 전달한다.
비즈니스 로직 없이 순수 API 호출만 담당한다.
"""

import logging

from slack_sdk.webhook import WebhookClient

from src.schemas.slack import DigestBlock, SlackConfig

logger = logging.getLogger(__name__)


def send_digest(blocks: list[DigestBlock], config: SlackConfig) -> bool:
    """Block Kit 메시지를 Slack Webhook URL로 발송한다.

    전달받은 DigestBlock 리스트를 Slack API 형식의 dict로 변환하여
    Incoming Webhook URL로 POST 요청을 보낸다.

    Args:
        blocks: 발송할 Block Kit 블록 목록.
        config: Slack 연동 설정값 (webhook_url 포함).

    Returns:
        발송 성공 시 True.

    Raises:
        ValueError: blocks가 빈 리스트인 경우.
        RuntimeError: Slack API 응답 상태 코드가 200이 아닌 경우.
    """
    if not blocks:
        raise ValueError("발송할 블록이 비어 있습니다.")

    # SecretStr에서 실제 URL 추출
    webhook_url = config.webhook_url.get_secret_value()
    client = WebhookClient(url=webhook_url)

    # 각 DigestBlock을 Slack API가 기대하는 dict 형태로 변환
    block_dicts = [block.to_slack_dict() for block in blocks]

    logger.info("Slack Webhook 메시지 발송 시도 (블록 %d개)", len(block_dicts))
    response = client.send(blocks=block_dicts)

    if response.status_code != 200:
        raise RuntimeError(
            f"Slack Webhook 발송 실패: "
            f"status_code={response.status_code}, body={response.body}"
        )

    logger.info("Slack Webhook 메시지 발송 성공")
    return True


if __name__ == "__main__":
    """테스트 메시지를 Slack Webhook으로 발송한다."""
    from dotenv import load_dotenv

    from src.schemas.slack import TextObject

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    config = SlackConfig()  # type: ignore[call-arg]

    # 테스트용 섹션 블록 생성
    test_blocks = [
        DigestBlock(
            type="header",
            text=TextObject(
                type="plain_text",
                text="Daily Digest 테스트",
            ),
        ),
        DigestBlock(type="divider"),
        DigestBlock(
            type="section",
            text=TextObject(
                type="mrkdwn",
                text=":white_check_mark: *테스트 섹션*\n  • 항목 1: 테스트 데이터\n  • 항목 2: Webhook 연동 확인",
            ),
        ),
    ]

    success = send_digest(test_blocks, config)
    print(f"발송 결과: {'성공' if success else '실패'}")
