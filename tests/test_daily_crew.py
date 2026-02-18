"""Daily Crew 파이프라인 테스트 모듈.

run_daily_digest() 실행 흐름과 get_crew_agents() LLM 미설정 처리를 검증한다.
crewAI Agent 생성은 LLM 설정에 의존하므로 mock으로 대체한다.
"""

from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from src.crews.daily_crew import get_crew_agents, run_daily_digest
from src.schemas.slack import SlackConfig


def _make_config() -> SlackConfig:
    """테스트용 SlackConfig를 생성한다.

    Returns:
        SlackConfig: 테스트용 설정 인스턴스.
    """
    return SlackConfig(
        webhook_url=SecretStr("https://hooks.slack.com/services/test"),
        bot_token=SecretStr("xoxb-test-token"),
        app_token=SecretStr("xapp-test-token"),
        channel="#test",
        _env_file=None,  # type: ignore[call-arg]
    )


class TestGetCrewAgents:
    """get_crew_agents() 테스트."""

    def test_returns_empty_dict_without_llm(self) -> None:
        """LLM 설정 없이 빈 딕셔너리를 반환한다."""
        config = _make_config()

        # lazy import 대상 모듈을 직접 패치
        with patch(
            "src.agents.us_dividend.create_us_dividend_agent",
            side_effect=ImportError("crewai not configured"),
        ):
            agents = get_crew_agents(config)

        assert agents == {}

    def test_returns_empty_dict_on_value_error(self) -> None:
        """ValueError(LLM 키 누락) 시 빈 딕셔너리를 반환한다."""
        config = _make_config()

        with patch(
            "src.agents.us_dividend.create_us_dividend_agent",
            side_effect=ValueError("ANTHROPIC_API_KEY not set"),
        ):
            agents = get_crew_agents(config)

        assert agents == {}

    @patch("src.agents.publisher.create_publisher_agent")
    @patch("src.agents.us_dividend.create_us_dividend_agent")
    def test_returns_agents_when_llm_available(
        self,
        mock_us_div: MagicMock,
        mock_publisher: MagicMock,
    ) -> None:
        """LLM 설정이 있을 때 Agent 딕셔너리를 반환한다."""
        mock_us_div.return_value = MagicMock(role="Scanner")
        mock_publisher.return_value = MagicMock(role="Publisher")

        config = _make_config()
        agents = get_crew_agents(config)

        assert "us_dividend" in agents
        assert "publisher" in agents
        mock_us_div.assert_called_once()
        mock_publisher.assert_called_once_with(config)


class TestRunDailyDigest:
    """run_daily_digest() 테스트."""

    @patch("src.crews.daily_crew.SlackService")
    def test_successful_run(
        self, mock_service_cls: MagicMock
    ) -> None:
        """성공적인 파이프라인 실행."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.message = "발송 완료"
        mock_result.duration_sec = 1.0
        mock_service_cls.return_value.run_digest.return_value = mock_result

        config = _make_config()
        run_daily_digest(config)

        mock_service_cls.assert_called_once_with(config)
        mock_service_cls.return_value.run_digest.assert_called_once()

    @patch("src.crews.daily_crew.SlackService")
    def test_failed_run_logs_error(
        self, mock_service_cls: MagicMock
    ) -> None:
        """실패한 파이프라인은 에러를 로그한다 (예외 전파 안 함)."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.message = "발송 실패"
        mock_service_cls.return_value.run_digest.return_value = mock_result

        config = _make_config()
        # 예외가 발생하지 않아야 한다
        run_daily_digest(config)

        mock_service_cls.return_value.run_digest.assert_called_once()
