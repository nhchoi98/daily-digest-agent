"""Bull vs Bear 배당주 토론 에이전트 정의 모듈.

Bull(매수 추천), Bear(매수 비추천), Judge(심판) 세 역할의
crewAI Agent를 생성하는 팩토리 함수를 제공한다.
모든 에이전트는 OpenAI GPT-4o를 LLM으로 사용한다.
"""

import logging
import os

from crewai import Agent, LLM

from src.schemas.debate import DebateLLMConfig, _JUDGE_TEMPERATURE

logger = logging.getLogger(__name__)


def _create_openai_llm(config: DebateLLMConfig) -> LLM:
    """crewAI용 OpenAI LLM 인스턴스를 생성한다.

    OPENAI_API_KEY 환경변수가 설정되어 있는지 검증한 뒤
    crewAI LLM 객체를 반환한다.

    Args:
        config: LLM 모델명과 temperature 설정.

    Returns:
        crewAI LLM 인스턴스.

    Raises:
        ValueError: OPENAI_API_KEY 환경변수가 설정되지 않은 경우.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
            "Bull vs Bear 토론 기능에 OpenAI API Key가 필요합니다."
        )

    return LLM(
        model=config.model,
        temperature=config.temperature,
    )


def create_bull_agent(
    config: DebateLLMConfig | None = None,
) -> Agent:
    """Bull(매수 추천) 에이전트를 생성한다.

    20년 경력의 가치투자 애널리스트 페르소나로,
    배당주의 매수 논거를 체계적으로 제시한다.

    Args:
        config: LLM 설정. None이면 기본값(gpt-4o, temp=0.7) 사용.

    Returns:
        Bull 역할의 crewAI Agent 인스턴스.

    Raises:
        ValueError: OPENAI_API_KEY가 설정되지 않은 경우.
    """
    llm_config = config or DebateLLMConfig()
    llm = _create_openai_llm(llm_config)

    return Agent(
        role="Bull Analyst (매수 추천)",
        goal=(
            "배당 데이터를 분석하여 각 종목이 왜 좋은 배당 투자인지 "
            "설득력 있는 매수 논거를 제시한다."
        ),
        backstory=(
            "당신은 20년 경력의 가치투자 전문 애널리스트입니다. "
            "배당 성장, 기업 펀더멘털, 밸류에이션 관점에서 "
            "투자 기회를 발굴하는 것이 전문 분야입니다. "
            "배당 귀족주(Dividend Aristocrats)와 배당 킹(Dividend Kings)에 "
            "대한 깊은 이해를 바탕으로 장기 투자 가치를 평가합니다."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )


def create_bear_agent(
    config: DebateLLMConfig | None = None,
) -> Agent:
    """Bear(매수 비추천) 에이전트를 생성한다.

    리스크 매니저 출신 페르소나로,
    Bull 측 주장을 반박하고 매수 비추천 논거를 제시한다.

    Args:
        config: LLM 설정. None이면 기본값(gpt-4o, temp=0.7) 사용.

    Returns:
        Bear 역할의 crewAI Agent 인스턴스.

    Raises:
        ValueError: OPENAI_API_KEY가 설정되지 않은 경우.
    """
    llm_config = config or DebateLLMConfig()
    llm = _create_openai_llm(llm_config)

    return Agent(
        role="Bear Analyst (매수 비추천)",
        goal=(
            "Bull 측 주장의 약점을 파악하고, 각 종목의 리스크 요인을 "
            "근거로 매수 비추천 논거를 제시한다."
        ),
        backstory=(
            "당신은 15년간 대형 헤지펀드에서 리스크 매니저로 일한 "
            "숏셀러 출신 애널리스트입니다. "
            "기술적 지표 과열, 배당 함정(dividend trap), "
            "섹터 리스크, 밸류에이션 거품 등을 예리하게 포착합니다. "
            "Bull 측이 간과하는 위험 요소를 날카롭게 지적하여 "
            "투자자가 무비판적 매수를 피하도록 돕습니다."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )


def create_judge_agent(
    config: DebateLLMConfig | None = None,
) -> Agent:
    """Judge(심판) 에이전트를 생성한다.

    투자심사위원회 의장 페르소나로, Bull/Bear 양측을 비교하여
    종목별 최종 권고를 결정한다. temperature=0.3으로 결정론적 판정.

    Args:
        config: LLM 설정. None이면 기본값(gpt-4o, temp=0.3) 사용.
            temperature는 Judge용 0.3으로 오버라이드된다.

    Returns:
        Judge 역할의 crewAI Agent 인스턴스.

    Raises:
        ValueError: OPENAI_API_KEY가 설정되지 않은 경우.
    """
    llm_config = config or DebateLLMConfig()
    # Judge는 결정론적 판정을 위해 낮은 temperature 사용
    judge_config = DebateLLMConfig(
        model=llm_config.model,
        temperature=_JUDGE_TEMPERATURE,
    )
    llm = _create_openai_llm(judge_config)

    return Agent(
        role="Investment Judge (심판)",
        goal=(
            "Bull과 Bear 양측의 주장을 공정하게 비교 평가하여 "
            "종목별 승자와 최종 투자 권고를 결정한다."
        ),
        backstory=(
            "당신은 글로벌 자산운용사의 투자심사위원회(IC) 의장입니다. "
            "30년간 수천 건의 투자 제안을 심사하며 "
            "Bull과 Bear 양측의 논거를 균형 있게 평가해왔습니다. "
            "감정이 아닌 데이터와 논리에 기반하여 "
            "최종 투자 권고(STRONG_BUY/BUY/HOLD/AVOID)를 내립니다."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )


if __name__ == "__main__":
    """토론 에이전트 생성 및 정보를 출력한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    agents = {
        "bull": create_bull_agent,
        "bear": create_bear_agent,
        "judge": create_judge_agent,
    }

    for name, factory in agents.items():
        try:
            agent = factory()
            print(f"Agent [{name}]: {agent.role}")
        except ValueError as e:
            print(f"Agent [{name}] 생성 스킵: {e}")
