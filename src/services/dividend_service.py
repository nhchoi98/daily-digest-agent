"""미국 주식 배당락일 비즈니스 로직 서비스 모듈.

배당 종목 스캔, 필터링, 기술적 지표 기반 위험도 평가,
세후 수익성 분석, 정렬, Slack 포맷 변환 등
배당 관련 비즈니스 로직을 전담한다.
tools/yahoo_finance.py의 원시 데이터를 가공하여
의미 있는 결과로 변환한다.
"""

import calendar
import logging
from datetime import date, timedelta
from typing import Any

from src.schemas.slack import DigestBlock, TextObject
from src.schemas.stock import (
    DividendProfitAnalysis,
    DividendScanResult,
    DividendStock,
    RiskAssessment,
    TechnicalIndicators,
)
from src.tools.yahoo_finance import get_technical_indicators, get_upcoming_dividends

logger = logging.getLogger(__name__)

# 필터링 기준 상수
# 왜 3%인가: 미국 S&P 500 평균 배당수익률(~1.5%)의 약 2배로,
# 고배당주에 관심 있는 투자자에게 의미 있는 수준이다.
MIN_DIVIDEND_YIELD_PCT = 3.0

# 왜 $1B인가: 시가총액 $1B 이상은 미드캡 이상의 안정적인 기업으로,
# 배당 지속 가능성이 높다.
MIN_MARKET_CAP_USD = 1_000_000_000

# 왜 10개인가: Slack 메시지의 가독성을 위해
# 과도한 종목 수를 제한한다.
MAX_STOCKS = 10

# 기본 스캔 범위 (일) - scan_days 오버라이드 시 사용
DEFAULT_SCAN_DAYS = 5

# Yahoo Finance URL 서식
_YAHOO_URL_TEMPLATE = "<https://finance.yahoo.com/quote/{ticker}|{ticker}>"

# 요일별 스캔 확장 일수
# 왜 요일별로 다른가: 주말은 거래일이 아니므로,
# "배당락일까지 최소 영업일 4일 이상 남은 종목"을 놓치지 않기 위해
# 목/금에는 주말을 건너뛰어 범위를 더 확장한다.
_WEEKDAY_SCAN_DAYS: dict[int, int] = {
    0: 4,  # 월(Mon): +4일 → 금요일 (4영업일, 주말 미포함)
    1: 4,  # 화(Tue): +4일 → 토요일 (4영업일, 주말 포함)
    2: 4,  # 수(Wed): +4일 → 일요일 (4영업일, 주말 포함)
    3: 5,  # 목(Thu): +5일 → 화요일 (주말 포함)
    4: 5,  # 금(Fri): +5일 → 수요일 (주말 포함)
    5: 6,  # 토(Sat): +6일 → 금요일 (다음 월요일 기준 4영업일)
    6: 5,  # 일(Sun): +5일 → 금요일 (다음 월요일 기준 4영업일)
}

# --- 위험도 판단 임계값 상수 ---
# 왜 RSI 75인가: 전통적 과매수 기준(70)보다 약간 높게 설정.
# 배당주는 배당락일 직전 매수세로 RSI가 다소 높을 수 있으므로
# 70이 아닌 75를 HIGH 기준으로 사용하여 과도한 필터링을 방지한다.
_RSI_HIGH_THRESHOLD = 75
# RSI 65~75: 과매수에 접근 중이지만 아직 극단적이지 않은 구간
_RSI_MEDIUM_THRESHOLD = 65

# 왜 %K 85인가: Stochastic 80이 전통적 과매수 기준이지만,
# %K와 %D 동시 조건으로 더 엄격하게 필터링하므로 85를 사용한다.
_STOCH_K_HIGH_THRESHOLD = 85
_STOCH_D_HIGH_THRESHOLD = 80
_STOCH_K_MEDIUM_THRESHOLD = 75

# 왜 변동성 50%인가: S&P 500 평균 연환산 변동성이 ~15-20% 수준.
# 50%는 평균의 3배로, 매우 불안정한 종목을 의미한다.
# 배당락 시 낙폭이 배당금 이상으로 클 가능성이 높다.
_VOLATILITY_HIGH_THRESHOLD = 50.0
_VOLATILITY_MEDIUM_THRESHOLD = 35.0

# 왜 5일 수익률 15%인가: 5거래일에 15% 상승은 비정상적 급등.
# 이런 급등 후에는 되돌림(mean reversion)이 발생하기 쉬우며,
# 배당락 낙폭과 맞물려 큰 손실로 이어질 수 있다.
_PRICE_CHANGE_HIGH_THRESHOLD = 15.0
_PRICE_CHANGE_MEDIUM_THRESHOLD = 8.0

# --- 세후 수익성 분석 상수 ---
# 한국 배당소득세 15.4% = 소득세 14% + 지방소득세 1.4%
# 미국 원천징수세(15%)와 별도로, 한국 거주자가 미국 주식 배당을
# 받을 때 적용되는 실효 세율이다.
_TAX_RATE_PCT = 15.4

# 변동성 보정 팩터 상한
# 왜 0.5인가: 변동성이 극단적으로 높아도 낙폭 보정은 최대 +50%로 제한.
# 변동성 100%인 종목도 낙폭이 배당금의 1.5배를 넘지 않도록 캡을 설정한다.
_VOLATILITY_FACTOR_CAP = 0.5

# 순수익률 손익분기 판단 범위 (±0.3%)
# 왜 0.3%인가: 거래 수수료, 슬리피지 등 실제 비용을 감안하면
# ±0.3% 내의 순수익률은 사실상 손익분기로 봐야 한다.
_BREAKEVEN_THRESHOLD = 0.3


class DividendService:
    """미국 주식 배당락일 스캔 및 포맷팅 서비스.

    yahoo_finance.py에서 수집한 원시 데이터를 필터링, 정렬하여
    투자자에게 유용한 배당락일 정보를 제공한다.
    기술적 지표 기반 위험도 평가와 세후 수익성 분석도 수행한다.

    Attributes:
        _scan_days_override: 수동 스캔 범위 오버라이드 (None이면 동적 계산).
    """

    def __init__(self, scan_days: int | None = None) -> None:
        """DividendService를 초기화한다.

        Args:
            scan_days: 수동 스캔 범위 (일). None이면 요일별 동적 계산.
        """
        self._scan_days_override = scan_days

    def calculate_scan_range(self, today: date) -> tuple[date, date]:
        """오늘 요일에 따라 배당락일 스캔 범위를 계산한다.

        영업일 기준으로 최소 2일 이후 배당락일 종목까지 포착하기 위해
        주말을 고려하여 스캔 범위를 조정한다.

        - 월~수: today + 2캘린더일 (= 2영업일, 주말이 끼지 않음)
        - 목: today + 3캘린더일 (금요일 배당락 종목을 포함하기 위해)
        - 금: today + 3캘린더일 (월요일 배당락 종목을 포함하기 위해)
        - 토: today + 4캘린더일 (다음 월요일 기준 수요일까지)
        - 일: today + 3캘린더일 (다음 월요일 기준 수요일까지)

        Args:
            today: 기준 날짜.

        Returns:
            tuple[date, date]: (스캔 시작일, 스캔 종료일).
        """
        weekday = today.weekday()
        days_ahead = _WEEKDAY_SCAN_DAYS[weekday]
        end_date = today + timedelta(days=days_ahead)
        return (today, end_date)

    def scan_dividends(self) -> DividendScanResult:
        """배당락일 임박 종목을 스캔하고 필터링한다.

        파이프라인:
        1. 기본 필터 (배당수익률 3%+, 시가총액 $1B+)
        2. 기술적 지표 조회 + 위험도 평가 → HIGH 제외
        3. 세후 수익성 분석 (analyze_profit)
        4. 정렬: is_profitable True 먼저 → net_profit_yield 내림차순
        5. 최대 MAX_STOCKS개 제한

        Returns:
            DividendScanResult: 필터링된 종목 목록과 메타데이터.
        """
        today = date.today()

        # 수동 오버라이드가 있으면 고정 범위, 없으면 요일별 동적 계산
        if self._scan_days_override is not None:
            start_date = today
            end_date = today + timedelta(days=self._scan_days_override)
        else:
            start_date, end_date = self.calculate_scan_range(today)

        scan_range_days = (end_date - start_date).days
        day_name = calendar.day_name[today.weekday()]

        logger.info(
            "오늘: %s(%s), 스캔 범위: %s ~ %s (%d일)",
            today, day_name, start_date, end_date, scan_range_days,
        )

        filters = {
            "min_yield_pct": MIN_DIVIDEND_YIELD_PCT,
            "min_market_cap_usd": MIN_MARKET_CAP_USD,
            "max_stocks": MAX_STOCKS,
        }

        high_risk_excluded = 0

        try:
            raw_data = get_upcoming_dividends(
                start_date=start_date, end_date=end_date,
            )
            stocks = self._parse_raw_data(raw_data)

            logger.info(
                "필터링 전 종목 수: %d, 필터 조건: yield >= %.1f%%, "
                "market_cap >= $%s",
                len(stocks), MIN_DIVIDEND_YIELD_PCT,
                f"{MIN_MARKET_CAP_USD:,}",
            )

            # 1단계: 기본 필터 (배당수익률, 시가총액)
            filtered = self._apply_filters(stocks)

            # 2단계: 기술적 지표 조회 + 위험도 평가
            logger.info(
                "기술적 지표 조회 중... (%d개 종목, 예상 %d초)",
                len(filtered), len(filtered) * 2,
            )
            self._enrich_with_indicators(filtered)

            # 위험도 평가 후 HIGH 리스크 제외
            before_risk = len(filtered)
            filtered = [
                s for s in filtered
                if s.risk is None or s.risk.risk_level != "HIGH"
            ]
            high_risk_excluded = before_risk - len(filtered)
            if high_risk_excluded > 0:
                logger.info(
                    "HIGH 리스크 제외: %d개 종목", high_risk_excluded,
                )

            # 3단계: 세후 수익성 분석
            self._enrich_with_profit_analysis(filtered)

            # 4단계: 정렬 (is_profitable True 먼저, 그 다음 net_profit_yield 내림차순)
            sorted_stocks = self._sort_by_profitability(filtered)

            # 5단계: 최대 개수 제한
            sorted_stocks = sorted_stocks[:MAX_STOCKS]

            logger.info("최종 종목 수: %d", len(sorted_stocks))
        except (ConnectionError, ValueError, TypeError, OSError) as e:
            logger.error("배당 스캔 실패: %s", e)
            sorted_stocks = []

        return DividendScanResult(
            stocks=sorted_stocks,
            scan_range_days=scan_range_days,
            scan_start_date=start_date,
            scan_end_date=end_date,
            filters_applied=filters,
            high_risk_excluded=high_risk_excluded,
        )

    def assess_risk(self, stock: DividendStock) -> RiskAssessment:
        """기술적 지표 기반으로 배당락일 전후 위험도를 평가한다.

        판단 기준:
        - HIGH (SKIP): RSI>75, Stochastic K>85 AND D>80,
          변동성>50%, 5일 수익률>15% 중 하나라도 해당
        - MEDIUM (HOLD): RSI 65~75, Stochastic K>75,
          변동성 35~50%, 5일 수익률>8% 중 하나라도 해당
        - LOW (BUY): 위 조건 모두 해당 없음

        Args:
            stock: 기술적 지표가 포함된 배당 종목.

        Returns:
            RiskAssessment: 위험 등급, 판단 근거, 투자 권고.
        """
        indicators = stock.indicators
        high_reasons: list[str] = []
        medium_reasons: list[str] = []

        if indicators is None:
            return RiskAssessment(
                risk_level="LOW",
                reasons=["기술적 지표 데이터 없음 — 기본 LOW 처리"],
                recommendation="BUY",
            )

        # RSI 판단
        if indicators.rsi_14 is not None:
            if indicators.rsi_14 > _RSI_HIGH_THRESHOLD:
                high_reasons.append(
                    f"RSI {indicators.rsi_14:.0f} > {_RSI_HIGH_THRESHOLD} — 심한 과매수"
                )
            elif indicators.rsi_14 > _RSI_MEDIUM_THRESHOLD:
                medium_reasons.append(
                    f"RSI {indicators.rsi_14:.0f} — 과매수 접근 "
                    f"({_RSI_MEDIUM_THRESHOLD}~{_RSI_HIGH_THRESHOLD})"
                )

        # Stochastic 판단
        if indicators.stochastic_k is not None and indicators.stochastic_d is not None:
            if (
                indicators.stochastic_k > _STOCH_K_HIGH_THRESHOLD
                and indicators.stochastic_d > _STOCH_D_HIGH_THRESHOLD
            ):
                high_reasons.append(
                    f"Stochastic %K={indicators.stochastic_k:.0f}, "
                    f"%D={indicators.stochastic_d:.0f} — 과매수 구간"
                )
            elif indicators.stochastic_k > _STOCH_K_MEDIUM_THRESHOLD:
                medium_reasons.append(
                    f"Stochastic %K={indicators.stochastic_k:.0f} > "
                    f"{_STOCH_K_MEDIUM_THRESHOLD} — 주의"
                )

        # 변동성 판단
        if indicators.volatility_20d is not None:
            if indicators.volatility_20d > _VOLATILITY_HIGH_THRESHOLD:
                high_reasons.append(
                    f"변동성 {indicators.volatility_20d:.1f}% > "
                    f"{_VOLATILITY_HIGH_THRESHOLD}% — 극단적 변동"
                )
            elif indicators.volatility_20d > _VOLATILITY_MEDIUM_THRESHOLD:
                medium_reasons.append(
                    f"변동성 {indicators.volatility_20d:.1f}% — 높은 편 "
                    f"({_VOLATILITY_MEDIUM_THRESHOLD}~{_VOLATILITY_HIGH_THRESHOLD}%)"
                )

        # 5일 수익률 판단
        if indicators.price_change_5d is not None:
            if indicators.price_change_5d > _PRICE_CHANGE_HIGH_THRESHOLD:
                high_reasons.append(
                    f"5일 +{indicators.price_change_5d:.1f}% — "
                    f"급등 후 되돌림 위험"
                )
            elif indicators.price_change_5d > _PRICE_CHANGE_MEDIUM_THRESHOLD:
                medium_reasons.append(
                    f"5일 +{indicators.price_change_5d:.1f}% — "
                    f"상승 과열 주의"
                )

        # HIGH 리스크: 하나라도 해당 시
        if high_reasons:
            return RiskAssessment(
                risk_level="HIGH",
                reasons=high_reasons,
                recommendation="SKIP",
            )

        # MEDIUM 리스크: 하나라도 해당 시
        if medium_reasons:
            return RiskAssessment(
                risk_level="MEDIUM",
                reasons=medium_reasons,
                recommendation="HOLD",
            )

        # LOW 리스크: 위 조건 모두 해당 없음
        return RiskAssessment(
            risk_level="LOW",
            reasons=["모든 지표 정상 범위"],
            recommendation="BUY",
        )

    def analyze_profit(self, stock: DividendStock) -> DividendProfitAnalysis:
        """배당 소득세(15.4%)를 감안한 실질 수익성을 분석한다.

        계산 로직:
        1. 세후 배당수익률 = 세전 × (1 - 0.154)
        2. 예상 낙폭 = (배당금 / 현재가) × (1 + volatility_factor)
        3. 순수익률 = 세후 배당수익률 - 예상 낙폭
        4. 판정: 양수면 수익, 음수면 손실, ±0.3% 이내면 손익분기

        Args:
            stock: 배당 종목 (current_price, indicators 포함 권장).

        Returns:
            DividendProfitAnalysis: 세후 수익성 분석 결과.
        """
        gross_yield = stock.dividend_yield

        # 세후 배당수익률 = 세전 × (1 - 세율/100)
        # 15.4% = 소득세 14% + 지방소득세 1.4% (한국 거주자 기준)
        net_yield = gross_yield * (1 - _TAX_RATE_PCT / 100)

        # 배당락일 예상 주가 하락률 추정
        estimated_drop = self._estimate_ex_date_drop(stock)

        # 순수익률 = 세후 배당 - 예상 낙폭
        net_profit = net_yield - estimated_drop

        is_profitable = net_profit > 0
        verdict = self._build_profit_verdict(
            net_profit, net_yield, estimated_drop,
        )

        return DividendProfitAnalysis(
            gross_dividend_yield=round(gross_yield, 2),
            tax_rate=_TAX_RATE_PCT,
            net_dividend_yield=round(net_yield, 2),
            estimated_ex_date_drop=round(estimated_drop, 2),
            net_profit_yield=round(net_profit, 2),
            is_profitable=is_profitable,
            verdict=verdict,
        )

    def format_for_slack(
        self, result: DividendScanResult
    ) -> list[DigestBlock]:
        """스캔 결과를 Slack Block Kit 형식으로 변환한다.

        각 종목에 리스크 레벨 이모지, RSI, 변동성, 세후 수익성 정보를 포함한다.

        Args:
            result: DividendService.scan_dividends()의 반환값.

        Returns:
            list[DigestBlock]: Slack 발송용 블록 목록.
                종목이 없으면 "해당 없음" 안내 블록을 반환한다.
        """
        if not result.stocks:
            return [self._build_empty_notice(result)]

        items = [self._format_stock_line(stock) for stock in result.stocks]
        bullet_list = "\n".join(f"  {item}" for item in items)

        title = f"미국 배당락일 임박 ({len(result.stocks)}종목)"
        if result.high_risk_excluded > 0:
            title += f" | HIGH 리스크 {result.high_risk_excluded}종목 제외"

        markdown_text = f":moneybag: *{title}*\n{bullet_list}"

        section = DigestBlock(
            type="section",
            text=TextObject(type="mrkdwn", text=markdown_text),
        )

        return [section]

    # --- Private methods ---

    def _parse_raw_data(
        self, raw_data: list[dict[str, Any]]
    ) -> list[DividendStock]:
        """원시 dict 데이터를 DividendStock 모델로 변환한다.

        Args:
            raw_data: yahoo_finance.get_upcoming_dividends()의 반환값.

        Returns:
            list[DividendStock]: 변환된 종목 리스트.
                파싱 실패한 항목은 건너뛴다.
        """
        stocks: list[DividendStock] = []
        for item in raw_data:
            try:
                stock = DividendStock(
                    ticker=item["ticker"],
                    company_name=item["company_name"],
                    ex_dividend_date=date.fromisoformat(
                        item["ex_dividend_date"]
                    ),
                    dividend_yield=item.get("dividend_yield", 0.0),
                    dividend_amount=item.get("dividend_amount", 0.0),
                    market_cap=item.get("market_cap", 0),
                    current_price=item.get("current_price", 0.0),
                    last_dividend_value=item.get("last_dividend_value", 0.0),
                    yahoo_finance_url=item["yahoo_finance_url"],
                )
                stocks.append(stock)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning("종목 데이터 파싱 실패: %s", e)
        return stocks

    def _apply_filters(
        self, stocks: list[DividendStock]
    ) -> list[DividendStock]:
        """배당수익률과 시가총액 기준으로 필터링한다.

        Args:
            stocks: 필터링 전 종목 리스트.

        Returns:
            list[DividendStock]: 필터 조건을 충족하는 종목만 포함.
        """
        return [
            s for s in stocks
            if s.dividend_yield >= MIN_DIVIDEND_YIELD_PCT
            and s.market_cap >= MIN_MARKET_CAP_USD
        ]

    def _enrich_with_indicators(
        self, stocks: list[DividendStock]
    ) -> None:
        """종목 리스트에 기술적 지표와 위험도 평가를 추가한다.

        개별 종목의 지표 조회 실패 시 해당 종목만 스킵하고
        전체 프로세스는 계속된다.

        Args:
            stocks: 지표를 추가할 종목 리스트 (in-place 수정).
        """
        for stock in stocks:
            try:
                raw_indicators = get_technical_indicators(stock.ticker)
                if raw_indicators is not None:
                    stock.indicators = TechnicalIndicators(**raw_indicators)
            except (ConnectionError, ValueError, TypeError, OSError) as e:
                logger.warning(
                    "종목 %s 기술적 지표 조회 실패 (스킵): %s",
                    stock.ticker, e,
                )

            # 지표 유무와 관계없이 위험도 평가 수행
            stock.risk = self.assess_risk(stock)

    def _enrich_with_profit_analysis(
        self, stocks: list[DividendStock]
    ) -> None:
        """종목 리스트에 세후 수익성 분석을 추가한다.

        Args:
            stocks: 분석을 추가할 종목 리스트 (in-place 수정).
        """
        for stock in stocks:
            stock.profit_analysis = self.analyze_profit(stock)

    def _estimate_ex_date_drop(self, stock: DividendStock) -> float:
        """배당락일 예상 주가 하락률을 추정한다.

        일반적으로 1회 배당금만큼 주가가 하락하되,
        변동성이 높은 종목은 낙폭이 더 클 수 있으므로 보정한다.

        last_dividend_value(마지막 실제 배당금 1회분)를 사용한다.
        dividend_amount(연간 합계)를 사용하면 분기배당 종목에서
        낙폭이 ~4배 과대추정되기 때문이다.

        계산: estimated_drop = (1회 배당금 / 현재가 × 100) × (1 + vol_factor)
        vol_factor = min(volatility_20d / 100, 0.5)

        Args:
            stock: 배당 종목.

        Returns:
            예상 주가 하락률 (%).
        """
        # 1회 배당금 결정: last_dividend_value가 있으면 사용,
        # 없으면 dividend_amount(연간)를 4로 나누어 분기 근사
        per_payment = stock.last_dividend_value
        if per_payment <= 0:
            # 왜 4인가: 미국 주식의 ~80%가 분기 배당이므로
            # 연간 배당금 / 4가 합리적인 근사치
            per_payment = stock.dividend_amount / 4

        if stock.current_price <= 0 or per_payment <= 0:
            # 현재가 또는 배당금 정보 없으면 세전 배당수익률/4을 낙폭으로 근사
            return stock.dividend_yield / 4

        # 기본 낙폭 = 1회 배당금 / 현재가 × 100
        base_drop = (per_payment / stock.current_price) * 100

        # 변동성 보정: 변동성이 높을수록 낙폭이 클 가능성
        volatility_factor = 0.0
        if (
            stock.indicators is not None
            and stock.indicators.volatility_20d is not None
        ):
            # 변동성(%)를 0~0.5 범위의 보정 팩터로 변환
            volatility_factor = min(
                stock.indicators.volatility_20d / 100,
                _VOLATILITY_FACTOR_CAP,
            )

        # 보정된 낙폭 = 기본 낙폭 × (1 + 변동성 팩터)
        adjusted_drop = base_drop * (1 + volatility_factor)
        return adjusted_drop

    def _build_profit_verdict(
        self,
        net_profit: float,
        net_yield: float,
        estimated_drop: float,
    ) -> str:
        """수익성 판단 한줄 verdict 문자열을 생성한다.

        Args:
            net_profit: 순수익률 (%).
            net_yield: 세후 배당수익률 (%).
            estimated_drop: 예상 낙폭률 (%).

        Returns:
            판단 문자열.
        """
        if abs(net_profit) <= _BREAKEVEN_THRESHOLD:
            return (
                f"손익분기 근처 (세후배당 {net_yield:.2f}% "
                f"≈ 예상낙폭 {estimated_drop:.2f}%)"
            )
        if net_profit > 0:
            return (
                f"세후에도 +{net_profit:.2f}% 수익 예상 "
                f"(배당 {net_yield:.2f}% - 낙폭 {estimated_drop:.2f}%)"
            )
        return (
            f"세후 {net_profit:.2f}% 손실 예상 "
            f"(낙폭 {estimated_drop:.2f}%이 세후배당 {net_yield:.2f}% 초과)"
        )

    def _sort_by_profitability(
        self, stocks: list[DividendStock]
    ) -> list[DividendStock]:
        """수익성 기준으로 정렬한다.

        정렬 우선순위:
        1. is_profitable = True 먼저
        2. net_profit_yield 내림차순

        Args:
            stocks: 정렬 전 종목 리스트.

        Returns:
            list[DividendStock]: 정렬된 종목 리스트.
        """
        def _sort_key(s: DividendStock) -> tuple[int, float]:
            if s.profit_analysis is not None:
                # is_profitable True(1) → 0 (먼저), False(0) → 1 (나중)
                profitable_order = 0 if s.profit_analysis.is_profitable else 1
                # net_profit_yield 내림차순 → 부호 반전
                profit = -s.profit_analysis.net_profit_yield
                return (profitable_order, profit)
            # 분석 없으면 수익률로 대체
            return (1, -s.dividend_yield)

        return sorted(stocks, key=_sort_key)

    def _format_stock_line(self, stock: DividendStock) -> str:
        """단일 종목을 Slack 메시지용 문자열로 포맷팅한다.

        리스크 이모지, 종목 링크, 배당수익률, RSI, 변동성,
        세후 수익성 verdict를 한 줄로 표시한다.

        Args:
            stock: 포맷팅할 배당 종목.

        Returns:
            Slack mrkdwn 형식의 종목 정보 문자열.
        """
        # 리스크 레벨 이모지
        risk_emoji = self._get_risk_emoji(stock)

        url = _YAHOO_URL_TEMPLATE.format(ticker=stock.ticker)

        # 기본 정보
        line = f"{risk_emoji} {url} — 배당 {stock.dividend_yield:.1f}%"

        # 기술적 지표 간략 표시
        if stock.indicators is not None:
            parts: list[str] = []
            if stock.indicators.rsi_14 is not None:
                parts.append(f"RSI {stock.indicators.rsi_14:.0f}")
            if stock.indicators.volatility_20d is not None:
                parts.append(f"변동성 {stock.indicators.volatility_20d:.0f}%")
            if parts:
                line += f" | {' | '.join(parts)}"

        # 세후 수익성 한줄
        if stock.profit_analysis is not None:
            pa = stock.profit_analysis
            if pa.is_profitable:
                line += f" | 순이익 +{pa.net_profit_yield:.2f}%"
            else:
                line += f" | :warning: {pa.net_profit_yield:+.2f}%"

        return line

    def _get_risk_emoji(self, stock: DividendStock) -> str:
        """종목의 리스크 레벨에 맞는 이모지를 반환한다.

        Args:
            stock: 배당 종목.

        Returns:
            리스크 이모지 문자열.
        """
        if stock.risk is None:
            return ":white_circle:"
        emoji_map = {
            "LOW": ":large_green_circle:",
            "MEDIUM": ":large_yellow_circle:",
            "HIGH": ":red_circle:",
        }
        return emoji_map.get(stock.risk.risk_level, ":white_circle:")

    def _build_empty_notice(
        self, result: DividendScanResult
    ) -> DigestBlock:
        """배당락일 임박 종목이 없을 때의 안내 블록을 생성한다.

        Args:
            result: 스캔 결과 (범위 정보 표시에 사용).

        Returns:
            section 타입의 DigestBlock.
        """
        start = result.scan_start_date or "N/A"
        end = result.scan_end_date or "N/A"
        excluded_msg = ""
        if result.high_risk_excluded > 0:
            excluded_msg = (
                f"\n  (HIGH 리스크 {result.high_risk_excluded}종목 제외됨)"
            )
        return DigestBlock(
            type="section",
            text=TextObject(
                type="mrkdwn",
                text=(
                    ":moneybag: *미국 배당락일 임박*\n"
                    f"  {start} ~ {end} 범위에 "
                    f"배당락일 임박 종목이 없습니다."
                    f"{excluded_msg}"
                ),
            ),
        )


if __name__ == "__main__":
    """DividendService 파이프라인 전체를 테스트한다."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    # 요일별 스캔 범위 테스트
    service = DividendService()
    print("=== 요일별 스캔 범위 ===")
    for weekday in range(7):
        test_date = date(2026, 2, 16 + weekday)
        result_range = service.calculate_scan_range(test_date)
        day_name = calendar.day_name[test_date.weekday()]
        print(f"  {day_name:9s} ({test_date}): {result_range}")

    # 기본 동적 범위 스캔 (기술적 지표 + 수익성 분석 포함)
    result = service.scan_dividends()

    print(f"\n=== 스캔 결과 ({len(result.stocks)}개 종목) ===")
    print(f"스캔 범위: {result.scan_start_date} ~ {result.scan_end_date}")
    print(f"필터 조건: {result.filters_applied}")
    print(f"HIGH 리스크 제외: {result.high_risk_excluded}개")

    for stock in result.stocks:
        risk_str = f"[{stock.risk.risk_level}]" if stock.risk else "[N/A]"
        profit_str = ""
        if stock.profit_analysis:
            pa = stock.profit_analysis
            profit_str = (
                f" | 세후 {pa.net_dividend_yield:.2f}% "
                f"| 낙폭 {pa.estimated_ex_date_drop:.2f}% "
                f"| 순이익 {pa.net_profit_yield:+.2f}%"
            )
        indicator_str = ""
        if stock.indicators:
            ind = stock.indicators
            parts = []
            if ind.rsi_14 is not None:
                parts.append(f"RSI={ind.rsi_14:.1f}")
            if ind.volatility_20d is not None:
                parts.append(f"Vol={ind.volatility_20d:.1f}%")
            indicator_str = f" | {', '.join(parts)}" if parts else ""

        print(
            f"  {risk_str:8s} {stock.ticker:5s} | "
            f"{stock.company_name:30s} | "
            f"배당 {stock.dividend_yield:.1f}%"
            f"{indicator_str}{profit_str}"
        )

    # 종목이 없으면 7일로 재시도
    if not result.stocks:
        print("\n--- 7일 범위로 재스캔 ---")
        service_7d = DividendService(scan_days=7)
        result_7d = service_7d.scan_dividends()
        for stock in result_7d.stocks:
            print(
                f"  {stock.ticker:5s} | {stock.company_name:30s} | "
                f"수익률 {stock.dividend_yield:.1f}%"
            )

    # Slack 포맷 확인
    blocks = service.format_for_slack(result)
    for block in blocks:
        print(f"\nSlack 블록: {block.to_slack_dict()}")
