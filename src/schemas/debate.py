"""Bull vs Bear 배당주 토론 입출력 데이터 타입 정의 모듈.

토론 LLM 설정, 종목별 주장, 심판 판정, 토론 전체 결과를
Pydantic 모델로 타입 안전하게 관리한다.
debate_crew와 debate_service가 이 스키마를 통해 데이터를 주고받는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# LLM 모델 기본값 상수
_DEFAULT_MODEL = "openai/gpt-4o"
_DEFAULT_TEMPERATURE = 0.7
_JUDGE_TEMPERATURE = 0.3


class DebateLLMConfig(BaseModel):
    """토론 에이전트용 LLM 설정.

    crewAI LLM 인스턴스 생성 시 사용하는 모델명과 temperature를 담는다.

    Attributes:
        model: crewAI LLM 모델 식별자 (예: "openai/gpt-4o").
        temperature: LLM 응답의 창의성 조절 (0.0~1.0).
    """

    model: str = Field(
        default=_DEFAULT_MODEL,
        description="crewAI LLM 모델 식별자 (예: openai/gpt-4o)",
    )
    temperature: float = Field(
        default=_DEFAULT_TEMPERATURE,
        description="LLM temperature (0.0=결정론적, 1.0=창의적)",
    )


class StockArgument(BaseModel):
    """종목별 Bull 또는 Bear 측 주장.

    토론 에이전트가 개별 종목에 대해 제시하는 투자 논거를 담는다.

    Attributes:
        ticker: 종목 심볼.
        stance: 투자 입장 (BULLISH 또는 BEARISH).
        thesis: 핵심 주장 한줄 요약.
        arguments: 구체적 논거 리스트.
        confidence: 확신도 (1~10).
    """

    ticker: str = Field(description="종목 심볼 (예: AAPL, JNJ)")
    stance: Literal["BULLISH", "BEARISH"] = Field(
        description="투자 입장 (BULLISH=매수 추천, BEARISH=매수 비추천)",
    )
    thesis: str = Field(
        description="핵심 주장 한줄 요약 (예: '안정적 배당 성장 + 저평가')",
    )
    arguments: list[str] = Field(
        description="구체적 논거 리스트 (3~5개 권장)",
    )
    confidence: int = Field(
        ge=1,
        le=10,
        description="확신도 (1=매우 낮음, 10=매우 높음)",
    )


class StockVerdict(BaseModel):
    """종목별 심판 판정 결과.

    Judge 에이전트가 Bull/Bear 양측의 주장을 비교 평가한 결과를 담는다.

    Attributes:
        ticker: 종목 심볼.
        winner: 승리 측 (BULL 또는 BEAR).
        verdict_summary: 판정 요약.
        final_recommendation: 최종 투자 권고.
        key_factor: 판정을 결정지은 핵심 요인.
    """

    ticker: str = Field(description="종목 심볼 (예: AAPL, JNJ)")
    winner: Literal["BULL", "BEAR"] = Field(
        description="토론 승리 측 (BULL=매수 추천 승, BEAR=매수 비추천 승)",
    )
    verdict_summary: str = Field(
        description="판정 요약 (2~3문장)",
    )
    final_recommendation: Literal[
        "STRONG_BUY", "BUY", "HOLD", "AVOID"
    ] = Field(
        description="최종 투자 권고 (STRONG_BUY/BUY/HOLD/AVOID)",
    )
    key_factor: str = Field(
        description="판정을 결정지은 핵심 요인 (예: '배당 성장률 vs 밸류에이션 리스크')",
    )


class DebateResult(BaseModel):
    """Bull vs Bear 토론 전체 결과.

    run_debate() 호출 후 반환되는 종목별 판정 목록과 메타데이터를 담는다.

    Attributes:
        verdicts: 종목별 심판 판정 리스트.
        debate_timestamp: 토론 실행 시각.
        model_used: 사용된 LLM 모델명.
        stock_count: 토론 대상 종목 수.
    """

    verdicts: list[StockVerdict] = Field(
        description="종목별 심판 판정 리스트",
    )
    debate_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="토론 실행 시각 (ISO 8601 형식)",
    )
    model_used: str = Field(
        default=_DEFAULT_MODEL,
        description="토론에 사용된 LLM 모델 식별자",
    )
    stock_count: int = Field(
        default=0,
        description="토론 대상 종목 수",
    )


if __name__ == "__main__":
    """스키마 모델 생성 및 직렬화를 검증한다."""
    config = DebateLLMConfig()
    print(f"LLM 설정: {config.model_dump_json(indent=2)}")

    argument = StockArgument(
        ticker="JNJ",
        stance="BULLISH",
        thesis="안정적 배당 성장 + 저평가",
        arguments=[
            "60년 이상 배당 증가 기록",
            "헬스케어 섹터 방어적 성격",
            "현재 PER 역사적 저점 부근",
        ],
        confidence=8,
    )
    print(f"Bull 주장: {argument.model_dump_json(indent=2)}")

    verdict = StockVerdict(
        ticker="JNJ",
        winner="BULL",
        verdict_summary="안정적 배당 성장 이력과 저평가 매력이 단기 리스크를 상쇄한다.",
        final_recommendation="BUY",
        key_factor="60년 연속 배당 증가 기록의 신뢰성",
    )
    print(f"판정: {verdict.model_dump_json(indent=2)}")

    result = DebateResult(
        verdicts=[verdict],
        model_used="openai/gpt-4o",
        stock_count=1,
    )
    print(f"토론 결과: {result.model_dump_json(indent=2)}")
