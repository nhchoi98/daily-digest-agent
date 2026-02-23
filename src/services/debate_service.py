"""Bull vs Bear 배당주 토론 비즈니스 로직 및 Slack 포맷팅 모듈.

토론 실행을 오케스트레이션하고, 결과를 Slack Block Kit 포맷으로 변환한다.
SlackService가 이 서비스를 통해 토론 섹션을 생성한다.
"""

import logging

from src.crews.debate_crew import run_debate
from src.schemas.debate import DebateLLMConfig, DebateResult, StockVerdict
from src.schemas.slack import DigestBlock, TextObject
from src.schemas.stock import DividendScanResult

logger = logging.getLogger(__name__)

# 최종 권고별 이모지 매핑
_RECOMMENDATION_EMOJI: dict[str, str] = {
    "STRONG_BUY": ":rocket:",
    "BUY": ":chart_with_upwards_trend:",
    "HOLD": ":eyes:",
    "AVOID": ":no_entry_sign:",
}

# 승자별 이모지 매핑
_WINNER_EMOJI: dict[str, str] = {
    "BULL": ":ox:",
    "BEAR": ":bear:",
}


class DebateService:
    """Bull vs Bear 토론 실행 및 Slack 포맷팅 서비스.

    토론 Crew 실행을 오케스트레이션하고,
    결과를 Slack Block Kit 블록으로 변환한다.

    Attributes:
        _llm_config: LLM 설정 (모델, temperature).
    """

    def __init__(
        self,
        llm_config: DebateLLMConfig | None = None,
    ) -> None:
        """DebateService를 초기화한다.

        Args:
            llm_config: LLM 설정. None이면 기본값(gpt-4o) 사용.
        """
        self._llm_config = llm_config or DebateLLMConfig()

    def run_debate(
        self,
        scan_result: DividendScanResult,
    ) -> DebateResult | None:
        """토론을 실행한다.

        예외 발생 시 None을 반환하여 전체 파이프라인을 중단시키지 않는다.

        Args:
            scan_result: 배당 스캔 결과 (토론 대상 데이터).

        Returns:
            DebateResult 또는 실패 시 None.
        """
        try:
            return run_debate(scan_result, self._llm_config)
        except (ValueError, RuntimeError, ConnectionError, OSError) as e:
            logger.error("Bull vs Bear 토론 실행 실패 (격리 처리): %s", e)
            return None

    def format_for_slack(
        self,
        debate_result: DebateResult | None,
    ) -> list[DigestBlock]:
        """토론 결과를 Slack Block Kit 블록으로 변환한다.

        Args:
            debate_result: 토론 결과. None이면 안내 블록 반환.

        Returns:
            Slack Block Kit 블록 리스트.
        """
        if debate_result is None or not debate_result.verdicts:
            return [self._build_empty_notice()]

        blocks: list[DigestBlock] = [
            DigestBlock(
                type="header",
                text=TextObject(
                    type="plain_text",
                    text="Bull vs Bear Debate",
                ),
            ),
        ]

        verdict_lines = [
            self._format_verdict_line(v)
            for v in debate_result.verdicts
        ]
        verdict_text = "\n".join(verdict_lines)

        blocks.append(
            DigestBlock(
                type="section",
                text=TextObject(
                    type="mrkdwn",
                    text=verdict_text,
                ),
            ),
        )

        # 모델 정보 표시
        blocks.append(
            DigestBlock(
                type="section",
                text=TextObject(
                    type="mrkdwn",
                    text=(
                        f"_Model: {debate_result.model_used} | "
                        f"{debate_result.stock_count}종목 분석_"
                    ),
                ),
            ),
        )

        return blocks

    def _format_verdict_line(self, verdict: StockVerdict) -> str:
        """개별 종목 판정을 mrkdwn 포맷 문자열로 변환한다.

        Args:
            verdict: 종목별 심판 판정.

        Returns:
            Slack mrkdwn 포맷 문자열.
        """
        winner_emoji = _WINNER_EMOJI.get(verdict.winner, "")
        rec_emoji = _RECOMMENDATION_EMOJI.get(
            verdict.final_recommendation, ""
        )

        return (
            f"{rec_emoji} *{verdict.ticker}* — "
            f"{winner_emoji} {verdict.winner} 승 → "
            f"*{verdict.final_recommendation}*\n"
            f"  _{verdict.verdict_summary}_\n"
            f"  핵심: {verdict.key_factor}"
        )

    def _build_empty_notice(self) -> DigestBlock:
        """토론 결과가 없을 때 안내 블록을 생성한다.

        Returns:
            안내 메시지가 담긴 section DigestBlock.
        """
        return DigestBlock(
            type="section",
            text=TextObject(
                type="mrkdwn",
                text=(
                    ":speech_balloon: *Bull vs Bear 토론*\n"
                    "  토론 대상 종목이 없거나 실행에 실패했습니다."
                ),
            ),
        )


if __name__ == "__main__":
    """DebateService의 포맷팅 기능을 테스트한다."""
    from src.schemas.debate import DebateResult, StockVerdict

    # 테스트 데이터로 포맷팅 확인
    service = DebateService()

    test_result = DebateResult(
        verdicts=[
            StockVerdict(
                ticker="JNJ",
                winner="BULL",
                verdict_summary="안정적 배당 성장 이력이 단기 리스크를 상쇄한다.",
                final_recommendation="BUY",
                key_factor="60년 연속 배당 증가 기록",
            ),
            StockVerdict(
                ticker="MO",
                winner="BEAR",
                verdict_summary="규제 리스크와 매출 감소 추세가 높은 배당률을 상쇄한다.",
                final_recommendation="AVOID",
                key_factor="담배 산업 구조적 쇠퇴",
            ),
        ],
        model_used="openai/gpt-4o",
        stock_count=2,
    )

    blocks = service.format_for_slack(test_result)
    for block in blocks:
        print(block.model_dump_json(indent=2))

    # None 입력 테스트
    empty_blocks = service.format_for_slack(None)
    print(f"\n빈 결과 블록: {empty_blocks[0].model_dump_json(indent=2)}")
