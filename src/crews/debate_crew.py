"""Bull vs Bear 배당주 토론 Crew 조합 및 실행 모듈.

Bull → Bear → Judge 순서로 crewAI Task를 실행하여
배당 종목에 대한 토론 결과를 생성한다.
context 파라미터로 이전 Task 결과를 다음 Task에 전달한다.
"""

import json
import logging
import re
from datetime import datetime

from crewai import Crew, Process, Task

from src.agents.debate import (
    create_bear_agent,
    create_bull_agent,
    create_judge_agent,
)
from src.schemas.debate import (
    DebateLLMConfig,
    DebateResult,
    StockVerdict,
)
from src.schemas.stock import DividendScanResult

logger = logging.getLogger(__name__)

# LLM 비용 제어를 위한 토론 대상 종목 수 상한
MAX_DEBATE_STOCKS = 5


def _build_stock_data_summary(scan_result: DividendScanResult) -> str:
    """DividendScanResult를 에이전트용 텍스트 요약으로 변환한다.

    각 종목의 핵심 데이터(배당률, 기술적 지표, 수익성 분석)를
    에이전트가 분석할 수 있는 구조화된 텍스트로 변환한다.

    Args:
        scan_result: 배당 스캔 결과.

    Returns:
        종목별 데이터 요약 텍스트.
    """
    stocks = scan_result.stocks[:MAX_DEBATE_STOCKS]
    lines = [
        f"## 배당 스캔 결과 ({len(stocks)}종목)",
        f"스캔 일시: {scan_result.scanned_at.strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    for stock in stocks:
        section = [
            f"### {stock.ticker} ({stock.company_name})",
            f"- 배당락일: {stock.ex_dividend_date}",
            f"- 배당수익률: {stock.dividend_yield:.2f}%",
            f"- 현재가: ${stock.current_price:.2f}",
            f"- 시가총액: ${stock.market_cap:,}",
        ]

        if stock.indicators:
            ind = stock.indicators
            section.append(f"- RSI(14): {ind.rsi_14}")
            section.append(f"- Stochastic %K/%D: {ind.stochastic_k}/{ind.stochastic_d}")
            section.append(f"- 변동성(20일): {ind.volatility_20d}%")
            section.append(f"- 5일 수익률: {ind.price_change_5d}%")

        if stock.risk:
            section.append(f"- 리스크: {stock.risk.risk_level} ({stock.risk.recommendation})")
            for reason in stock.risk.reasons:
                section.append(f"  - {reason}")

        if stock.profit_analysis:
            pa = stock.profit_analysis
            section.append(f"- 세후 배당수익률: {pa.net_dividend_yield:.2f}%")
            section.append(f"- 예상 낙폭: {pa.estimated_ex_date_drop:.2f}%")
            section.append(f"- 순수익률: {pa.net_profit_yield:.2f}%")
            section.append(f"- 판단: {pa.verdict}")

        lines.extend(section)
        lines.append("")

    return "\n".join(lines)


def _create_bull_task(
    agent: object,
    summary: str,
) -> Task:
    """Bull(매수 추천) Task를 생성한다.

    각 종목에 대해 매수 추천 논거를 제시하는 Task를 정의한다.

    Args:
        agent: Bull Agent 인스턴스.
        summary: 종목 데이터 요약 텍스트.

    Returns:
        Bull Task 인스턴스.
    """
    return Task(
        description=(
            f"아래 배당 종목 데이터를 분석하여 각 종목이 왜 좋은 배당 투자인지 "
            f"매수 추천 논거를 제시하세요.\n\n{summary}\n\n"
            f"각 종목에 대해 다음을 포함하세요:\n"
            f"1. 핵심 매수 논거 (thesis)\n"
            f"2. 구체적 근거 3~5개 (배당 성장, 밸류에이션, 섹터 강점 등)\n"
            f"3. 확신도 (1~10)\n"
        ),
        expected_output=(
            "JSON 배열 형식으로 응답하세요:\n"
            '[{"ticker": "XXX", "stance": "BULLISH", "thesis": "...", '
            '"arguments": ["...", "..."], "confidence": 8}]'
        ),
        agent=agent,
    )


def _create_bear_task(
    agent: object,
    summary: str,
    bull_task: Task,
) -> Task:
    """Bear(매수 비추천) Task를 생성한다.

    Bull 측 주장을 context로 받아 반박하고 매수 비추천 논거를 제시한다.

    Args:
        agent: Bear Agent 인스턴스.
        summary: 종목 데이터 요약 텍스트.
        bull_task: Bull Task (context로 결과 전달용).

    Returns:
        Bear Task 인스턴스.
    """
    return Task(
        description=(
            f"Bull Analyst의 매수 추천 주장을 검토하고, 각 종목에 대해 "
            f"매수 비추천 논거를 제시하세요. Bull 측 주장의 약점을 구체적으로 반박하세요.\n\n"
            f"종목 데이터:\n{summary}\n\n"
            f"각 종목에 대해 다음을 포함하세요:\n"
            f"1. Bull 측 주장에 대한 반박 (thesis)\n"
            f"2. 구체적 리스크/비추천 근거 3~5개 (과열 지표, 배당 함정, 섹터 리스크 등)\n"
            f"3. 확신도 (1~10)\n"
        ),
        expected_output=(
            "JSON 배열 형식으로 응답하세요:\n"
            '[{"ticker": "XXX", "stance": "BEARISH", "thesis": "...", '
            '"arguments": ["...", "..."], "confidence": 7}]'
        ),
        agent=agent,
        context=[bull_task],
    )


def _create_verdict_task(
    agent: object,
    bull_task: Task,
    bear_task: Task,
) -> Task:
    """Judge(심판) Task를 생성한다.

    Bull/Bear 양측 주장을 context로 받아 종목별 승자와 최종 권고를 판정한다.

    Args:
        agent: Judge Agent 인스턴스.
        bull_task: Bull Task (context 전달용).
        bear_task: Bear Task (context 전달용).

    Returns:
        Judge Task 인스턴스.
    """
    return Task(
        description=(
            "Bull Analyst와 Bear Analyst의 주장을 공정하게 비교 평가하여 "
            "종목별 승자와 최종 투자 권고를 결정하세요.\n\n"
            "판정 기준:\n"
            "1. 논거의 구체성과 데이터 근거\n"
            "2. 리스크 대비 수익성 분석의 설득력\n"
            "3. 현재 시장 상황과의 정합성\n\n"
            "최종 권고 기준:\n"
            "- STRONG_BUY: Bull 압도적 승리, 리스크 낮음\n"
            "- BUY: Bull 우세, 관리 가능한 리스크\n"
            "- HOLD: 양측 팽팽, 추가 관찰 필요\n"
            "- AVOID: Bear 우세, 리스크 과다\n"
        ),
        expected_output=(
            "JSON 배열 형식으로 응답하세요:\n"
            '[{"ticker": "XXX", "winner": "BULL", '
            '"verdict_summary": "...", '
            '"final_recommendation": "BUY", '
            '"key_factor": "..."}]'
        ),
        agent=agent,
        context=[bull_task, bear_task],
    )


def _parse_crew_result(
    crew_output: str,
    model: str,
    scan_result: DividendScanResult,
) -> DebateResult:
    """Crew 실행 결과를 DebateResult로 파싱한다.

    LLM 응답에서 JSON을 추출하고 StockVerdict 모델로 변환한다.
    마크다운 코드블록(```json ... ```)으로 감싸진 경우도 처리한다.

    Args:
        crew_output: Crew kickoff 결과 문자열.
        model: 사용된 LLM 모델명.
        scan_result: 원본 스캔 결과 (종목 수 메타데이터용).

    Returns:
        파싱된 DebateResult.

    Raises:
        ValueError: JSON 파싱에 실패한 경우.
    """
    raw = str(crew_output).strip()

    # 마크다운 코드블록 제거 (```json ... ``` 또는 ``` ... ```)
    code_block_match = re.search(
        r"```(?:json)?\s*\n?(.*?)```",
        raw,
        re.DOTALL,
    )
    if code_block_match:
        raw = code_block_match.group(1).strip()

    # JSON 배열 추출 (앞뒤 텍스트가 있을 수 있음)
    array_match = re.search(r"\[.*]", raw, re.DOTALL)
    if not array_match:
        raise ValueError(f"JSON 배열을 찾을 수 없습니다: {raw[:200]}")

    json_str = array_match.group(0)
    parsed = json.loads(json_str)

    verdicts = [StockVerdict(**item) for item in parsed]
    stock_count = min(
        len(scan_result.stocks), MAX_DEBATE_STOCKS
    )

    return DebateResult(
        verdicts=verdicts,
        model_used=model,
        stock_count=stock_count,
    )


def run_debate(
    scan_result: DividendScanResult,
    llm_config: DebateLLMConfig | None = None,
) -> DebateResult:
    """Bull vs Bear 토론을 실행한다.

    3개 Agent, 3개 Task로 구성된 Crew를 순차 실행하여
    종목별 투자 판정 결과를 반환한다.

    Args:
        scan_result: 배당 스캔 결과 (토론 대상 데이터).
        llm_config: LLM 설정. None이면 기본값(gpt-4o) 사용.

    Returns:
        DebateResult: 종목별 판정 결과.

    Raises:
        ValueError: 스캔 결과에 종목이 없거나 JSON 파싱 실패 시.
        RuntimeError: Crew 실행 중 오류 발생 시.
    """
    if not scan_result.stocks:
        raise ValueError("토론 대상 종목이 없습니다.")

    config = llm_config or DebateLLMConfig()
    summary = _build_stock_data_summary(scan_result)

    logger.info(
        "Bull vs Bear 토론 시작 (%d종목, 모델: %s)",
        min(len(scan_result.stocks), MAX_DEBATE_STOCKS),
        config.model,
    )

    # Agent 생성
    bull_agent = create_bull_agent(config)
    bear_agent = create_bear_agent(config)
    judge_agent = create_judge_agent(config)

    # Task 생성 (context 체이닝)
    bull_task = _create_bull_task(bull_agent, summary)
    bear_task = _create_bear_task(bear_agent, summary, bull_task)
    verdict_task = _create_verdict_task(
        judge_agent, bull_task, bear_task
    )

    # Crew 구성 및 실행
    crew = Crew(
        agents=[bull_agent, bear_agent, judge_agent],
        tasks=[bull_task, bear_task, verdict_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()
    logger.info("Crew 실행 완료, 결과 파싱 중...")

    return _parse_crew_result(
        crew_output=result.raw,
        model=config.model,
        scan_result=scan_result,
    )


if __name__ == "__main__":
    """배당 스캔 + Bull vs Bear 토론을 독립 실행한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    from src.services.dividend_service import DividendService

    # 배당 스캔
    dividend_service = DividendService()
    scan_result = dividend_service.scan_dividends()
    print(f"스캔 완료: {len(scan_result.stocks)}종목")

    if not scan_result.stocks:
        print("토론 대상 종목 없음")
    else:
        # 토론 실행
        debate_result = run_debate(scan_result)
        print(f"\n=== 토론 결과 ({debate_result.stock_count}종목) ===")
        for v in debate_result.verdicts:
            print(
                f"  {v.ticker}: {v.winner} 승 → {v.final_recommendation}"
            )
            print(f"    {v.verdict_summary}")
