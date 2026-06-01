import yfinance as yf

_spy_cache = None
_sector_cache = {}


def _fetch(ticker):
    return yf.Ticker(ticker).history(period="6y")["Close"]


def get_spy_regime():
    """
    Returns {date_str: bool} — True when SPY is above its 200-day MA.
    When False the broad market is in a confirmed downtrend.
    No new long positions should be opened.
    """
    global _spy_cache
    if _spy_cache is None:
        spy = _fetch("SPY")
        ma200 = spy.rolling(200).mean()
        above = spy > ma200
        _spy_cache = {str(d)[:10]: bool(v) for d, v in zip(above.index, above.values)}
    return _spy_cache


def get_sector_regime(etf_ticker):
    """
    Returns {date_str: bool} — True when the sector ETF is above its 50-day MA.
    Prevents buying individual stocks when their whole sector is trending down.
    Sector filter is more short-term (MA50) than the market filter (MA200).
    """
    if etf_ticker not in _sector_cache:
        data = _fetch(etf_ticker)
        ma50 = data.rolling(50).mean()
        above = data > ma50
        _sector_cache[etf_ticker] = {str(d)[:10]: bool(v) for d, v in zip(above.index, above.values)}
    return _sector_cache[etf_ticker]


def is_market_uptrend(date_str=None):
    """Convenience function for the live bot — checks today's SPY regime."""
    import time
    if date_str is None:
        date_str = time.strftime("%Y-%m-%d")
    return get_spy_regime().get(date_str, True)
