"""Slack 다이제스트 실행 및 상태 관리 서비스 모듈.

다이제스트 블록 생성, Webhook 발송, 실행 상태 관리 등
Slack 관련 비즈니스 로직을 전담한다.
Bolt 핸들러와 crewAI Agent 모두 이 서비스를 통해 다이제스트를 실행한다.
"""

import logging
import time
from datetime import datetime

from src.schemas.slack import (
    ButtonElement,
    DigestBlock,
    DigestResult,
    DigestStatus,
    SlackConfig,
    TextObject,
)
from src.schemas.stock import DividendScanResult
from src.services.debate_service import DebateService
from src.services.dividend_service import DividendService
from src.tools.slack_webhook import send_digest

logger = logging.getLogger(__name__)

# 인터랙티브 버튼의 action_id 상수
RERUN_ACTION_ID = "rerun_digest_action"


def format_section(
    title: str, items: list[str], emoji: str
) -> DigestBlock:
    """제목과 항목 리스트로 Block Kit section 블록을 생성한다.

    마크다운 형식으로 제목과 불릿 리스트를 조합하여
    하나의 section 블록을 만든다.

    Args:
        title: 섹션 제목 텍스트.
        items: 불릿 포인트로 표시할 항목 리스트.
        emoji: 제목 앞에 표시할 이모지 (예: ":chart_with_upwards_trend:").

    Returns:
        section 타입의 DigestBlock 인스턴스.

    Raises:
        ValueError: title이 빈 문자열이거나, items가 빈 리스트인 경우.
    """
    if not title:
        raise ValueError("섹션 제목이 비어 있습니다.")
    if not items:
        raise ValueError("섹션 항목 리스트가 비어 있습니다.")

    # 마크다운 형식으로 제목과 불릿 리스트를 조합
    bullet_list = "\n".join(f"  • {item}" for item in items)
    markdown_text = f"{emoji} *{title}*\n{bullet_list}"

    return DigestBlock(
        type="section",
        text=TextObject(type="mrkdwn", text=markdown_text),
    )


class SlackService:
    """Slack 다이제스트 실행 및 상태 관리 서비스.

    Bolt 핸들러와 crewAI Agent 모두 이 서비스를 통해
    다이제스트를 실행하고 상태를 조회한다.
    DividendService를 통해 배당 데이터를 수집하고,
    tools 레이어의 순수 API 호출을 오케스트레이션한다.

    Attributes:
        _config: Slack 연동 설정.
        _last_result: 마지막 실행 결과 (없으면 None).
        _dividend_service: 배당 데이터 수집 서비스.
    """

    def __init__(self, config: SlackConfig) -> None:
        """SlackService를 초기화한다.

        Args:
            config: Slack 환경변수 설정값 (SlackConfig 인스턴스).
        """
        self._config = config
        self._last_result: DigestResult | None = None
        self._dividend_service = DividendService()
        self._debate_service = DebateService()

    def run_digest(self) -> DigestResult:
        """다이제스트를 생성하고 Slack으로 발송한다.

        배당 데이터를 수집하여 Block Kit 메시지로 구성한 뒤
        Webhook으로 발송한다. 배당 스캔 실패 시에도
        나머지 콘텐츠는 정상 발송된다 (격리 처리).

        내부에서 예외를 catch하여 DigestResult로 래핑하므로
        호출자에게 예외가 전파되지 않는다.

        Returns:
            DigestResult: 실행 결과 (성공 여부, 메시지, 타임스탬프,
                소요 시간, 종목 수).
                실패 시에도 예외 대신 success=False인 결과를 반환한다.
        """
        start_time = time.time()

        try:
            blocks, stock_count = self._build_digest_blocks()
            send_digest(blocks, self._config)
            elapsed = time.time() - start_time

            result = DigestResult(
                success=True,
                message="다이제스트 발송 완료",
                duration_sec=round(elapsed, 2),
                stock_count=stock_count,
            )
        except (ValueError, RuntimeError, ConnectionError, OSError) as e:
            elapsed = time.time() - start_time
            logger.error("다이제스트 발송 실패: %s", e)

            result = DigestResult(
                success=False,
                message=f"발송 실패: {e}",
                duration_sec=round(elapsed, 2),
                stock_count=0,
            )

        # 마지막 실행 결과를 저장하여 상태 조회에 활용
        self._last_result = result
        return result

    def get_last_status(self) -> DigestStatus:
        """마지막 다이제스트 실행 상태를 조회한다.

        Returns:
            DigestStatus: 마지막 실행 시각, 성공 여부, 종목 수, 요약 문자열.
        """
        if self._last_result is None:
            return DigestStatus(
                summary="아직 실행된 다이제스트가 없습니다.",
            )

        last = self._last_result
        time_str = last.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        status_emoji = ":white_check_mark:" if last.success else ":x:"
        status_text = "성공" if last.success else "실패"

        summary = (
            f"{status_emoji} 마지막 실행: {time_str}\n"
            f"  상태: {status_text} | "
            f"종목 수: {last.stock_count}개 | "
            f"소요: {last.duration_sec}초"
        )

        return DigestStatus(
            last_run_at=last.timestamp,
            success=last.success,
            stock_count=last.stock_count,
            summary=summary,
        )

    def _build_digest_blocks(self) -> tuple[list[DigestBlock], int]:
        """다이제스트 메시지의 Block Kit 블록 목록을 생성한다.

        배당 스캔을 1회만 실행하여 배당 섹션과 토론 섹션에서 공유한다.
        각 섹션 실패 시에도 나머지 블록은 정상 생성된다.

        Returns:
            tuple[list[DigestBlock], int]: (발송할 블록 목록, 배당 종목 수).
                블록: header → divider → 배당 → divider → 토론 → divider → actions.
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # 배당 스캔 1회 실행, 결과를 배당 섹션 + 토론 섹션에서 공유
        scan_result = self._scan_dividends_once()
        dividend_blocks, stock_count = (
            self._build_dividend_section_from_result(scan_result)
        )
        debate_blocks = self._build_debate_section(scan_result)

        blocks = [
            self._build_header_block(today),
            DigestBlock(type="divider"),
            *dividend_blocks,
            DigestBlock(type="divider"),
            *debate_blocks,
            DigestBlock(type="divider"),
            self._build_rerun_action_block(),
        ]

        return blocks, stock_count

    def _scan_dividends_once(self) -> DividendScanResult | None:
        """배당 스캔을 1회 실행하고 결과를 반환한다.

        스캔 실패 시 None을 반환하여 전체 파이프라인을 중단시키지 않는다.

        Returns:
            DividendScanResult 또는 실패 시 None.
        """
        try:
            return self._dividend_service.scan_dividends()
        except (ConnectionError, ValueError, TypeError, OSError) as e:
            logger.error("배당 스캔 실패 (격리 처리): %s", e)
            return None

    def _build_header_block(self, date_str: str) -> DigestBlock:
        """날짜를 포함한 헤더 블록을 생성한다.

        Args:
            date_str: 표시할 날짜 문자열 (예: "2026-02-18").

        Returns:
            header 타입의 DigestBlock.
        """
        return DigestBlock(
            type="header",
            text=TextObject(
                type="plain_text",
                text=f"Daily Digest - {date_str}",
            ),
        )

    def _build_dividend_section_from_result(
        self,
        scan_result: DividendScanResult | None,
    ) -> tuple[list[DigestBlock], int]:
        """배당 스캔 결과로부터 배당락일 섹션 블록을 생성한다.

        Args:
            scan_result: 배당 스캔 결과. None이면 에러 안내 블록 반환.

        Returns:
            tuple[list[DigestBlock], int]: (배당 관련 블록 목록, 종목 수).
        """
        if scan_result is None:
            return [
                DigestBlock(
                    type="section",
                    text=TextObject(
                        type="mrkdwn",
                        text=":warning: *배당 데이터 수집 실패*\n  일시적 오류가 발생했습니다.",
                    ),
                ),
            ], 0

        try:
            blocks = self._dividend_service.format_for_slack(scan_result)
            return blocks, len(scan_result.stocks)
        except (ValueError, TypeError) as e:
            logger.error("배당 섹션 포맷팅 실패 (격리 처리): %s", e)
            return [
                DigestBlock(
                    type="section",
                    text=TextObject(
                        type="mrkdwn",
                        text=":warning: *배당 데이터 포맷팅 실패*\n  일시적 오류가 발생했습니다.",
                    ),
                ),
            ], 0

    def _build_debate_section(
        self,
        scan_result: DividendScanResult | None,
    ) -> list[DigestBlock]:
        """Bull vs Bear 토론 섹션 블록을 생성한다.

        배당 스캔 결과를 토론 서비스에 전달하여 토론을 실행하고
        결과를 Slack Block Kit 포맷으로 변환한다.
        스캔 결과가 없거나 토론 실패 시에도 안내 블록을 반환한다.

        Args:
            scan_result: 배당 스캔 결과. None이면 빈 안내 블록 반환.

        Returns:
            토론 관련 Slack Block Kit 블록 리스트.
        """
        if scan_result is None or not scan_result.stocks:
            return self._debate_service.format_for_slack(None)

        try:
            debate_result = self._debate_service.run_debate(scan_result)
            return self._debate_service.format_for_slack(debate_result)
        except (ValueError, RuntimeError, ConnectionError, OSError) as e:
            logger.error("토론 섹션 생성 실패 (격리 처리): %s", e)
            return self._debate_service.format_for_slack(None)

    def _build_rerun_action_block(self) -> DigestBlock:
        """'다시 실행' 인터랙티브 버튼 블록을 생성한다.

        Returns:
            actions 타입의 DigestBlock.
        """
        return DigestBlock(
            type="actions",
            elements=[
                ButtonElement(
                    text=TextObject(
                        type="plain_text",
                        text="다시 실행",
                    ),
                    action_id=RERUN_ACTION_ID,
                    style="primary",
                ),
            ],
        )


if __name__ == "__main__":
    """SlackService의 run_digest와 get_last_status를 테스트한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    config = SlackConfig()  # type: ignore[call-arg]
    service = SlackService(config)

    # 다이제스트 실행
    result = service.run_digest()
    print(f"실행 결과: {result.model_dump_json(indent=2)}")

    # 상태 조회
    status = service.get_last_status()
    print(f"상태: {status.model_dump_json(indent=2)}")
