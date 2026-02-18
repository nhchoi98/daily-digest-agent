"""Slack Bolt SDK (Socket Mode) 기반 슬래시 커맨드 및 인터랙티브 핸들러 모듈.

라우팅(핸들러 등록)만 담당하며, 모든 비즈니스 로직은
SlackService에 위임한다.
/digest 슬래시 커맨드와 인터랙티브 버튼 핸들러를 제공한다.
"""

import logging
from typing import Any

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.schemas.slack import DigestResult, SlackConfig
from src.services.slack_service import RERUN_ACTION_ID, SlackService

logger = logging.getLogger(__name__)


def create_bolt_app(config: SlackConfig) -> App:
    """Slack Bolt App 인스턴스를 생성하고 핸들러를 등록한다.

    SlackService 인스턴스를 내부에서 생성하여
    모든 핸들러가 동일한 서비스를 공유하도록 한다.

    Args:
        config: Slack 연동 설정값 (bot_token 포함).

    Returns:
        App: 핸들러가 등록된 Slack Bolt App 인스턴스.
    """
    app = App(token=config.bot_token.get_secret_value())
    service = SlackService(config)

    _register_digest_command(app, service)
    _register_rerun_action(app, service)

    return app


def _register_digest_command(app: App, service: SlackService) -> None:
    """슬래시 커맨드 /digest 핸들러를 등록한다.

    서브커맨드에 따라 분기:
    - now: 다이제스트 즉시 실행
    - status: 마지막 실행 상태 조회
    - 그 외: 사용법 안내

    Args:
        app: Slack Bolt App 인스턴스.
        service: 비즈니스 로직을 위임할 SlackService.
    """

    @app.command("/digest")
    def handle_digest_command(
        ack: Any, command: dict[str, Any], respond: Any
    ) -> None:
        """슬래시 커맨드 /digest를 처리한다.

        Args:
            ack: Slack 요청 확인(acknowledge) 콜백.
            command: 슬래시 커맨드 페이로드.
            respond: 사용자에게 응답을 보내는 콜백.
        """
        # Slack은 3초 이내 ack()를 요구하므로 즉시 호출
        ack()
        subcommand = command.get("text", "").strip().lower()

        if subcommand == "now":
            _handle_digest_now(service, respond)
        elif subcommand == "status":
            _handle_digest_status(service, respond)
        else:
            respond("사용법: `/digest now` | `/digest status`")


def _respond_with_result(result: DigestResult, respond: Any) -> None:
    """DigestResult에 따라 사용자에게 성공/실패 응답을 보낸다.

    Args:
        result: 다이제스트 실행 결과.
        respond: 사용자에게 응답을 보내는 콜백.
    """
    if result.success:
        respond(
            f":white_check_mark: 발송 완료! "
            f"({result.stock_count}개 종목, "
            f"소요 {result.duration_sec}초)"
        )
    else:
        respond(f":x: {result.message}")


def _handle_digest_now(service: SlackService, respond: Any) -> None:
    """다이제스트 즉시 실행을 처리한다.

    SlackService.run_digest() 자체는 예외를 전파하지 않으나,
    네트워크 장애 등 예상치 못한 오류에 대비해 최상위에서 catch한다.

    Args:
        service: 비즈니스 로직을 위임할 SlackService.
        respond: 사용자에게 응답을 보내는 콜백.
    """
    respond(":hourglass_flowing_sand: 다이제스트 생성 중...")

    try:
        result = service.run_digest()
        _respond_with_result(result, respond)
    except Exception as e:
        logger.error("다이제스트 실행 중 오류: %s", e)
        respond(f":warning: 오류 발생: {e}")


def _handle_digest_status(service: SlackService, respond: Any) -> None:
    """마지막 실행 상태 조회를 처리한다.

    모든 예외를 내부에서 catch하여 respond()를 통해
    사용자에게 오류 메시지로 전달한다.

    Args:
        service: 비즈니스 로직을 위임할 SlackService.
        respond: 사용자에게 응답을 보내는 콜백.
    """
    try:
        status = service.get_last_status()
        respond(status.summary)
    except Exception as e:
        logger.error("상태 조회 중 오류: %s", e)
        respond(f":warning: 오류 발생: {e}")


def _register_rerun_action(app: App, service: SlackService) -> None:
    """'다시 실행' 버튼 액션 핸들러를 등록한다.

    Args:
        app: Slack Bolt App 인스턴스.
        service: 비즈니스 로직을 위임할 SlackService.
    """

    @app.action(RERUN_ACTION_ID)
    def handle_rerun_button(
        ack: Any, body: dict[str, Any], respond: Any
    ) -> None:
        """'다시 실행' 버튼 클릭을 처리한다.

        Args:
            ack: Slack 요청 확인 콜백.
            body: 인터랙션 페이로드.
            respond: 사용자에게 응답을 보내는 콜백.
        """
        # Slack은 3초 이내 ack()를 요구하므로 즉시 호출
        ack()
        respond(":hourglass_flowing_sand: 다시 실행 중...")

        try:
            result = service.run_digest()
            _respond_with_result(result, respond)
        except Exception as e:
            logger.error("다시 실행 중 오류: %s", e)
            respond(f":warning: 오류 발생: {e}")


def start_socket_mode(config: SlackConfig) -> None:
    """Socket Mode로 Bolt App을 시작한다.

    이 함수는 블로킹 호출이며, Ctrl+C로 종료할 때까지 실행된다.

    Args:
        config: Slack 연동 설정값 (app_token 포함).
    """
    app = create_bolt_app(config)
    handler = SocketModeHandler(
        app=app,
        app_token=config.app_token.get_secret_value(),
    )

    logger.info("Slack Bolt App Socket Mode 시작")
    handler.start()


if __name__ == "__main__":
    """Socket Mode로 Bolt App을 실행한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    config = SlackConfig()  # type: ignore[call-arg]
    start_socket_mode(config)
