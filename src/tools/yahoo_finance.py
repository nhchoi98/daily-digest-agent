"""Yahoo Finance API를 통한 배당 데이터 수집 모듈.

yfinance 라이브러리를 사용하여 미국 주식의 배당락일, 배당수익률,
시가총액 등 원시 데이터를 수집한다.
비즈니스 로직(필터링, 정렬) 없이 순수 API 호출만 담당한다.
"""

import logging
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
        market_cap, yahoo_finance_url 키가 포함된다.
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
        dividend_amount, market_cap, yahoo_finance_url.

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
            "yahoo_finance_url": _YAHOO_FINANCE_URL_TEMPLATE.format(
                ticker=ticker
            ),
        }
    except (KeyError, TypeError, ValueError, OSError) as e:
        # OSError: yfinance 내부의 네트워크/HTTP 오류를 포괄한다
        logger.warning("종목 %s 데이터 수집 실패: %s", ticker, e)
        return None


if __name__ == "__main__":
    """배당락일 원시 데이터를 수집하여 출력한다."""
    import json

    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

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
