"""crewAI Publisher Agent 정의 모듈.

다이제스트 콘텐츠를 Slack으로 발송하는 퍼블리셔 Agent를 정의한다.
slack_webhook.py의 send_digest를 crewAI Tool로 래핑하여 사용한다.
"""

import json
import logging

from crewai import Agent
from crewai.tools import BaseTool
from pydantic import Field, ValidationError

from src.schemas.slack import DigestBlock, SlackConfig
from src.tools.slack_webhook import send_digest

logger = logging.getLogger(__name__)


class SendDigestTool(BaseTool):
    """Slack으로 다이제스트 메시지를 발송하는 crewAI Tool.

    crewAI Agent가 수집한 콘텐츠를 Block Kit 형식으로
    Slack 채널에 발송할 때 사용한다.

    Attributes:
        name: 도구 이름.
        description: 도구 설명 (Agent가 사용 시점을 판단하는 기준).
        config: Slack 연동 설정.
    """

    name: str = Field(
        default="send_slack_digest",
        description="crewAI에서 이 도구를 식별하는 고유 이름",
    )
    description: str = Field(
        default=(
            "Block Kit 형식의 다이제스트 메시지를 Slack 채널로 발송한다. "
            "blocks 파라미터에 DigestBlock 리스트의 JSON 문자열을 전달해야 한다."
        ),
        description="Agent가 이 도구의 사용 시점을 판단하기 위한 설명",
    )
    config: SlackConfig = Field(description="Slack 연동 설정값")

    def _run(self, blocks_json: str) -> str:
        """다이제스트 블록을 Slack으로 발송한다.

        crewAI Agent는 인자를 문자열로 전달하므로
        JSON 파싱 후 DigestBlock 리스트로 변환한다.

        모든 예외를 내부에서 catch하여 실패 메시지 문자열로 반환하므로
        호출자에게 예외가 전파되지 않는다.

        Args:
            blocks_json: DigestBlock 리스트의 JSON 문자열 표현.
                예: '[{"type": "section", "text": {"type": "mrkdwn", "text": "..."}}]'

        Returns:
            발송 성공/실패 메시지 문자열.
        """
        try:
            # crewAI Agent가 전달한 JSON 문자열을 파싱
            raw_blocks = json.loads(blocks_json)
            blocks = [DigestBlock(**block) for block in raw_blocks]

            send_digest(blocks, self.config)
            return "다이제스트 발송 성공"
        except json.JSONDecodeError as e:
            logger.error("블록 JSON 파싱 실패: %s", e)
            return f"발송 실패: JSON 파싱 오류 - {e}"
        except ValidationError as e:
            logger.error("블록 유효성 검증 실패: %s", e)
            return f"발송 실패: 데이터 검증 오류 - {e}"
        except (ValueError, RuntimeError) as e:
            logger.error("Slack API 호출 실패: %s", e)
            return f"발송 실패: {e}"


def create_publisher_agent(config: SlackConfig) -> Agent:
    """퍼블리셔 Agent를 생성한다.

    다이제스트 콘텐츠를 수집하여 Slack으로 발송하는 역할을 담당하는
    crewAI Agent를 구성하여 반환한다.

    Args:
        config: Slack 연동 설정값.

    Returns:
        Agent: 구성 완료된 crewAI Agent 인스턴스.
    """
    tool = SendDigestTool(config=config)

    return Agent(
        role="Daily Digest Publisher",
        goal=(
            "수집된 주식 정보와 프로그래밍 트렌드를 정리하여 "
            "Slack 채널에 발송한다."
        ),
        backstory=(
            "당신은 매일 아침 팀원들에게 유용한 정보를 요약하여 "
            "전달하는 퍼블리셔입니다. 국내/미국 주식 동향과 "
            "프로그래밍 트렌드를 깔끔한 Block Kit 형식으로 정리하여 "
            "Slack에 발송합니다."
        ),
        tools=[tool],
        verbose=True,
        allow_delegation=False,
    )


if __name__ == "__main__":
    """Publisher Agent 생성 및 정보를 출력한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    config = SlackConfig()  # type: ignore[call-arg]
    agent = create_publisher_agent(config)

    print(f"Role: {agent.role}")
    print(f"Goal: {agent.goal}")
    print(f"Tools: {[t.name for t in agent.tools]}")
