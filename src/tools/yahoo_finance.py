"""Yahoo Finance API를 통한 배당 데이터 수집 모듈.

yfinance 라이브러리를 사용하여 미국 주식의 배당락일, 배당수익률,
시가총액 등 원시 데이터를 수집한다.
기술적 지표(RSI, Stochastic, 변동성) 계산 기능도 제공한다.
비즈니스 로직(필터링, 정렬, 판단) 없이 순수 API 호출 + 계산만 담당한다.
"""

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

# 미국 주요 배당주 티커 목록
# 배당 귀족(Dividend Aristocrats) + 고배당 대형주를 포함한다.
# 왜 이 목록인가: S&P 500 구성종목 중 배당수익률이 높고
# 배당 이력이 안정적인 대형주를 선별하여 스캔 효율을 높인다.
DIVIDEND_TICKERS: list[str] = [
    # 헬스케어
    "JNJ", "PFE", "ABBV", "MRK", "BMY", "AMGN", "GILD",
    # 소비재
    "KO", "PEP", "PG", "CL", "MO", "PM", "KMB",
    # 통신/유틸리티
    "T", "VZ", "SO", "DUK", "NEE", "D", "AEP", "XEL",
    # 에너지
    "XOM", "CVX", "COP", "EOG", "SLB", "PSX",
    # 금융
    "JPM", "BAC", "WFC", "C", "USB", "PNC", "TFC",
    # 산업재
    "MMM", "CAT", "HON", "RTX", "LMT", "GD",
    # 기술 (배당 지급)
    "IBM", "CSCO", "TXN", "AVGO", "INTC", "QCOM",
    # REITs / 배당 ETF 대용
    "O", "SCHD", "VYM",
    # 기타 고배당
    "DOW", "LYB", "KHC", "F",
]

# Yahoo Finance 종목 페이지 URL 템플릿
_YAHOO_FINANCE_URL_TEMPLATE = "https://finance.yahoo.com/quote/{ticker}"


# 날짜 범위 미지정 시 기본 스캔 일수
_DEFAULT_DAYS_AHEAD = 3

# 기술적 지표 계산에 사용하는 기간 파라미터
_RSI_PERIOD = 14          # RSI 계산 기간 (Wilder's standard)
_STOCHASTIC_K_PERIOD = 14  # Stochastic %K look-back 기간
_STOCHASTIC_K_SMOOTH = 3   # %K smoothing (SMA 기간)
_STOCHASTIC_D_PERIOD = 3   # %D signal line (SMA 기간)
_VOLATILITY_PERIOD = 20    # 변동성 계산에 사용하는 거래일 수
_PRICE_CHANGE_DAYS = 5     # 최근 수익률 계산 기간
_TRADING_DAYS_PER_YEAR = 252  # 연환산에 사용하는 연간 거래일 수


def get_upcoming_dividends(
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    """yfinance로 배당락일 임박 종목의 원시 데이터를 수집한다.

    DIVIDEND_TICKERS 목록의 각 종목에 대해 yfinance API를 호출하여
    배당 관련 정보를 수집한다. 필터링 없이 원시 데이터만 반환한다.

    Args:
        start_date: 스캔 시작일 (포함). None이면 오늘 날짜를 사용한다.
        end_date: 스캔 종료일 (포함). None이면 start_date + 3일.

    Returns:
        배당 정보 dict 리스트. 각 dict에는 ticker, company_name,
        ex_dividend_date, dividend_yield, dividend_amount,
        market_cap, current_price, yahoo_finance_url 키가 포함된다.
        API 호출 실패한 종목은 제외된다.
    """
    results: list[dict[str, Any]] = []
    if start_date is None:
        start_date = date.today()
    if end_date is None:
        end_date = start_date + timedelta(days=_DEFAULT_DAYS_AHEAD)

    logger.info(
        "배당락일 스캔 시작: %s ~ %s (%d개 종목)",
        start_date, end_date, len(DIVIDEND_TICKERS),
    )

    for ticker in DIVIDEND_TICKERS:
        stock_data = _fetch_ticker_dividend_info(ticker, start_date, end_date)
        if stock_data is not None:
            results.append(stock_data)

    logger.info("배당락일 스캔 완료: %d개 종목 수집", len(results))
    return results


def _fetch_ticker_dividend_info(
    ticker: str, start_date: date, end_date: date
) -> dict[str, Any] | None:
    """단일 종목의 배당 정보를 yfinance에서 조회한다.

    Args:
        ticker: 종목 심볼 (예: "AAPL", "JNJ").
        start_date: 스캔 시작일 (포함).
        end_date: 스캔 종료일 (포함).

    Returns:
        배당 정보 dict 또는 None. 배당락일이 범위 밖이거나
        데이터가 없으면 None을 반환한다.
        dict 키: ticker, company_name, ex_dividend_date,
        dividend_yield (%, 퍼센트 변환 완료),
        dividend_amount, market_cap, current_price, yahoo_finance_url.

    Note:
        내부에서 모든 예외를 catch하여 None을 반환하므로
        호출자에게 예외가 전파되지 않는다.
    """
    try:
        info = yf.Ticker(ticker).info

        ex_div_timestamp = info.get("exDividendDate")
        if ex_div_timestamp is None:
            return None

        # yfinance는 exDividendDate를 Unix timestamp(초)로 반환한다
        ex_div_date = datetime.fromtimestamp(
            ex_div_timestamp, tz=timezone.utc
        ).date()

        # 스캔 범위 밖이면 건너뛴다 (필터링이 아닌 수집 범위 설정)
        if not (start_date <= ex_div_date <= end_date):
            return None

        return {
            "ticker": ticker,
            "company_name": info.get("shortName", ticker),
            "ex_dividend_date": ex_div_date.isoformat(),
            # yfinance의 dividendYield는 이미 퍼센트 값(3.5 = 3.5%)으로 반환된다.
            # `or 0.0`: yfinance가 None을 반환할 수 있어 기본값을 설정한다.
            "dividend_yield": info.get("dividendYield") or 0.0,
            "dividend_amount": info.get("dividendRate", 0.0),
            "market_cap": info.get("marketCap", 0),
            # 수익성 분석(배당낙폭 추정)에 현재 주가가 필요하다
            "current_price": info.get("currentPrice")
            or info.get("regularMarketPrice", 0.0),
            # lastDividendValue: 마지막 실제 배당금(1회분).
            # dividendRate는 연간 합계이므로 1회 낙폭 추정에는 부적합하다.
            "last_dividend_value": info.get("lastDividendValue", 0.0),
            "yahoo_finance_url": _YAHOO_FINANCE_URL_TEMPLATE.format(
                ticker=ticker
            ),
        }
    except (KeyError, TypeError, ValueError, OSError) as e:
        # OSError: yfinance 내부의 네트워크/HTTP 오류를 포괄한다
        logger.warning("종목 %s 데이터 수집 실패: %s", ticker, e)
        return None


def get_technical_indicators(
    ticker: str, period: str = "3mo"
) -> dict[str, Any] | None:
    """단일 종목의 기술적 지표를 계산한다.

    yfinance에서 가격 데이터를 가져와 RSI, Stochastic, 변동성 등을
    계산한다. 순수 데이터 수집 + 수학적 계산만 수행하며,
    위험도 판단(HIGH/MEDIUM/LOW) 같은 비즈니스 로직은 포함하지 않는다.

    Args:
        ticker: 종목 심볼 (예: "AAPL").
        period: yfinance 가격 데이터 조회 기간 (기본 "3mo").
            RSI(14일) + Stochastic(14일) + 변동성(20일) 계산에
            최소 2개월 이상의 데이터가 필요하므로 3개월을 기본값으로 사용.

    Returns:
        기술적 지표 dict 또는 None (데이터 부족 / API 오류 시).
        dict 키: rsi_14, stochastic_k, stochastic_d,
        volatility_20d, price_change_5d, avg_volume_20d.
    """
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty or len(hist) < _RSI_PERIOD + _STOCHASTIC_K_SMOOTH:
            logger.warning("종목 %s 가격 데이터 부족 (%d행)", ticker, len(hist))
            return None

        close = hist["Close"]
        volume = hist["Volume"]

        rsi = _calculate_rsi(close)
        stoch_k, stoch_d = _calculate_stochastic(hist)
        volatility = _calculate_volatility(close)
        price_change = _calculate_price_change(close)
        avg_vol = _calculate_avg_volume(volume)

        return {
            "rsi_14": round(rsi, 2) if rsi is not None else None,
            "stochastic_k": round(stoch_k, 2) if stoch_k is not None else None,
            "stochastic_d": round(stoch_d, 2) if stoch_d is not None else None,
            "volatility_20d": round(volatility, 2) if volatility is not None else None,
            "price_change_5d": round(price_change, 2) if price_change is not None else None,
            "avg_volume_20d": round(avg_vol, 0) if avg_vol is not None else None,
        }
    except (KeyError, TypeError, ValueError, OSError) as e:
        logger.warning("종목 %s 기술적 지표 조회 실패: %s", ticker, e)
        return None


def _calculate_rsi(close: Any) -> float | None:
    """14일 RSI를 Wilder's smoothing 방식으로 계산한다.

    Wilder's smoothing은 일반 EMA와 달리 alpha = 1/N 을 사용하며,
    첫 N일의 평균을 시드(seed)로 사용하여 이후 지수이동평균을 구한다.
    일반 SMA 기반 RSI보다 변동이 부드럽고 추세 반영이 정확하다.

    Args:
        close: pandas Series of closing prices.

    Returns:
        RSI 값 (0~100) 또는 None (데이터 부족 시).
    """
    if len(close) < _RSI_PERIOD + 1:
        return None

    # 일간 가격 변동 = 당일 종가 - 전일 종가
    delta = close.diff()

    # 상승분(gain)과 하락분(loss) 분리
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Wilder's smoothing: 첫 N일은 SMA로 시드, 이후 지수이동평균
    # alpha = 1/N (Wilder 방식). pandas의 EMA에서 alpha=1/N, adjust=False 사용.
    avg_gain = gain.ewm(alpha=1 / _RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / _RSI_PERIOD, adjust=False).mean()

    # RS = avg_gain / avg_loss
    # RSI = 100 - (100 / (1 + RS))
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    last_rsi = rsi.iloc[-1]
    if math.isnan(last_rsi):
        return None
    return float(last_rsi)


def _calculate_stochastic(hist: Any) -> tuple[float | None, float | None]:
    """스토캐스틱 오실레이터 %K(14,3)와 %D(3)를 계산한다.

    %K = SMA( (Close - Low_14) / (High_14 - Low_14) × 100, 3 )
    %D = SMA(%K, 3)

    여기서 (14,3,3)은:
    - 14: 최고/최저가 look-back 기간
    - 3: %K의 SMA smoothing 기간 (Slow %K)
    - 3: %D의 SMA 기간 (Signal line)

    Args:
        hist: yfinance history DataFrame (High, Low, Close 컬럼 필요).

    Returns:
        tuple[float | None, float | None]: (%K, %D) 또는 (None, None).
    """
    if len(hist) < _STOCHASTIC_K_PERIOD + _STOCHASTIC_K_SMOOTH:
        return None, None

    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]

    # 14일 최고가 / 최저가 (rolling window)
    low_14 = low.rolling(window=_STOCHASTIC_K_PERIOD).min()
    high_14 = high.rolling(window=_STOCHASTIC_K_PERIOD).max()

    # Raw %K = (종가 - 14일 최저) / (14일 최고 - 14일 최저) × 100
    range_14 = high_14 - low_14
    # 0으로 나누기 방지: 14일간 가격 변동이 없으면 50 (중립) 처리
    raw_k = ((close - low_14) / range_14.replace(0, float("nan"))) * 100

    # Slow %K = Raw %K의 3일 SMA (smoothing으로 노이즈 감소)
    stoch_k = raw_k.rolling(window=_STOCHASTIC_K_SMOOTH).mean()
    # %D = Slow %K의 3일 SMA (시그널 라인)
    stoch_d = stoch_k.rolling(window=_STOCHASTIC_D_PERIOD).mean()

    last_k = stoch_k.iloc[-1]
    last_d = stoch_d.iloc[-1]

    k_val = None if math.isnan(last_k) else float(last_k)
    d_val = None if math.isnan(last_d) else float(last_d)
    return k_val, d_val


def _calculate_volatility(close: Any) -> float | None:
    """20일 변동성을 연환산(annualized)으로 계산한다.

    변동성 = 일간 수익률의 표준편차 × √252
    - 일간 수익률 = (당일종가 / 전일종가) - 1
    - √252: 연간 거래일 기준으로 환산 (일간 → 연간)
    - 20일: 약 1개월 거래일에 해당하며, 단기 변동성 측정에 적합

    Args:
        close: pandas Series of closing prices.

    Returns:
        연환산 변동성 (%) 또는 None.
    """
    if len(close) < _VOLATILITY_PERIOD + 1:
        return None

    # 일간 수익률 (pct_change = (t - t-1) / t-1)
    daily_returns = close.pct_change().dropna()
    if len(daily_returns) < _VOLATILITY_PERIOD:
        return None

    # 최근 20일의 표준편차
    recent_std = daily_returns.tail(_VOLATILITY_PERIOD).std()
    if math.isnan(recent_std):
        return None

    # 연환산: 일간 σ × √252 → 연간 σ, × 100으로 퍼센트 변환
    annualized = float(recent_std) * math.sqrt(_TRADING_DAYS_PER_YEAR) * 100
    return annualized


def _calculate_price_change(close: Any) -> float | None:
    """최근 5거래일 수익률을 계산한다.

    Args:
        close: pandas Series of closing prices.

    Returns:
        수익률 (%) 또는 None.
    """
    if len(close) < _PRICE_CHANGE_DAYS + 1:
        return None

    current = float(close.iloc[-1])
    past = float(close.iloc[-1 - _PRICE_CHANGE_DAYS])

    if past == 0:
        return None

    # 5일 수익률 = (현재가 - 5일전가) / 5일전가 × 100
    return ((current - past) / past) * 100


def _calculate_avg_volume(volume: Any) -> float | None:
    """20일 평균 거래량을 계산한다.

    Args:
        volume: pandas Series of trading volumes.

    Returns:
        평균 거래량 또는 None.
    """
    if len(volume) < _VOLATILITY_PERIOD:
        return None

    avg = volume.tail(_VOLATILITY_PERIOD).mean()
    if math.isnan(avg):
        return None
    return float(avg)


if __name__ == "__main__":
    """배당락일 원시 데이터 + 기술적 지표를 수집하여 출력한다."""
    import json

    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    # 기술적 지표 테스트 (대형주 1개)
    print("=== AAPL 기술적 지표 ===")
    indicators = get_technical_indicators("AAPL")
    if indicators:
        print(json.dumps(indicators, indent=2, ensure_ascii=False))
    else:
        print("기술적 지표 조회 실패")

    # 배당락일 스캔
    today = date.today()
    end_7d = today + timedelta(days=7)
    results = get_upcoming_dividends(start_date=today, end_date=end_7d)

    if results:
        print(f"\n=== 배당락일 임박 종목 ({len(results)}개) ===")
        for stock in results:
            print(json.dumps(stock, indent=2, ensure_ascii=False))
    else:
        print("\n배당락일 임박 종목이 없습니다. (7일 이내)")
        # 범위를 넓혀서 데이터 확인
        print("\n--- 30일 범위로 재스캔 ---")
        end_30d = today + timedelta(days=30)
        results_30 = get_upcoming_dividends(
            start_date=today, end_date=end_30d,
        )
        for stock in results_30[:5]:
            print(json.dumps(stock, indent=2, ensure_ascii=False))
