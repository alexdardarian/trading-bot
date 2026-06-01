import yfinance as yf

_cache = None

def _get_vix():
    global _cache
    if _cache is None:
        _cache = yf.Ticker("^VIX").history(period="6y")["Close"]
    return _cache

def vix_regime_at(date_str):
    """
    Returns (vix_level, regime) at or before a given date string (YYYY-MM-DD).
      'fear'         — VIX > 25: chaotic market, mean reversion dominates
      'complacency'  — VIX < 18: calm market, momentum/trend strategies work best
      'normal'       — VIX 18-25: no strong regime signal
    """
    try:
        vix = _get_vix()
        level = float(vix.loc[:date_str].iloc[-1])
        if level > 25:
            return level, "fear"
        elif level < 18:
            return level, "complacency"
        else:
            return level, "normal"
    except Exception:
        return 20.0, "normal"
