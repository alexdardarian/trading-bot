import yfinance as yf

SECTOR_ETFS = {
    # Financials
    "JPM": "XLF", "BAC": "XLF", "WFC": "XLF", "GS": "XLF", "MS": "XLF",
    "BLK": "XLF", "SCHW": "XLF", "AXP": "XLF", "V": "XLF", "MA": "XLF",
    "SPGI": "XLF", "MCO": "XLF", "ICE": "XLF", "CME": "XLF", "CB": "XLF",
    "AON": "XLF", "MMC": "XLF", "PNC": "XLF", "USB": "XLF", "C": "XLF",
    # Energy
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE", "EOG": "XLE", "HAL": "XLE",
    "SLB": "XLE", "MPC": "XLE", "PSX": "XLE", "VLO": "XLE", "OXY": "XLE",
    # Consumer Discretionary
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY", "NKE": "XLY",
    "SBUX": "XLY", "TJX": "XLY", "LOW": "XLY", "TGT": "XLY", "NFLX": "XLY",
    # Consumer Staples
    "WMT": "XLP", "KO": "XLP", "PG": "XLP", "PEP": "XLP", "CL": "XLP",
    "MDLZ": "XLP", "PM": "XLP", "MO": "XLP", "COST": "XLP",
    # Healthcare
    "JNJ": "XLV", "UNH": "XLV", "LLY": "XLV", "ABT": "XLV", "PFE": "XLV",
    "MRK": "XLV", "BMY": "XLV", "AMGN": "XLV", "GILD": "XLV", "TMO": "XLV",
    "MDT": "XLV", "ISRG": "XLV", "SYK": "XLV", "BSX": "XLV", "ZTS": "XLV",
    "REGN": "XLV", "VRTX": "XLV", "CI": "XLV", "HUM": "XLV", "HCA": "XLV",
    # Utilities
    "NEE": "XLU", "DUK": "XLU", "SO": "XLU", "D": "XLU", "XEL": "XLU",
    # Industrials
    "HON": "XLI", "GE": "XLI", "CAT": "XLI", "DE": "XLI", "RTX": "XLI",
    "LMT": "XLI", "UNP": "XLI", "ETN": "XLI", "EMR": "XLI", "NOC": "XLI",
    "ITW": "XLI", "GD": "XLI", "UPS": "XLI", "FDX": "XLI", "MMM": "XLI",
    # Technology
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AMD": "XLK", "INTC": "XLK",
    "QCOM": "XLK", "AVGO": "XLK", "ADBE": "XLK", "CRM": "XLK", "NOW": "XLK",
    "PANW": "XLK", "KLAC": "XLK", "LRCX": "XLK", "AMAT": "XLK", "MU": "XLK",
    "TXN": "XLK", "ADI": "XLK", "ORCL": "XLK", "IBM": "XLK", "CSCO": "XLK",
}

_etf_cache = {}

def _get_etf(etf_ticker):
    if etf_ticker not in _etf_cache:
        _etf_cache[etf_ticker] = yf.Ticker(etf_ticker).history(period="6y")["Close"]
    return _etf_cache[etf_ticker]

def relative_strength_score(ticker, df):
    """
    Compares this stock's 3-month return vs its sector ETF.
    Uses string-date alignment to avoid timezone index mismatches.
    Only uses dates within df's range — no look-ahead into future ETF data.
    """
    etf = SECTOR_ETFS.get(ticker)
    if etf is None or len(df) < 63:
        return 50.0
    try:
        etf_close = _get_etf(etf)

        # Build date-keyed dicts using YYYY-MM-DD strings.
        # This sidesteps all timezone/datetime alignment issues between yfinance sources.
        stock_map = {str(d)[:10]: v for d, v in zip(df.index, df["Close"].values)}
        etf_map   = {str(d)[:10]: v for d, v in zip(etf_close.index, etf_close.values)}

        # Intersection bounded by df's date range — guarantees no look-ahead
        common = sorted(stock_map.keys() & etf_map.keys())
        if len(common) < 63:
            return 50.0

        recent = common[-63:]
        sc = [stock_map[d] for d in recent]
        ec = [etf_map[d]   for d in recent]

        if sc[0] == 0 or ec[0] == 0:
            return 50.0

        stock_3m = (sc[-1] - sc[0]) / sc[0]
        etf_3m   = (ec[-1] - ec[0]) / ec[0]
        relative = stock_3m - etf_3m

        score = 50 + (relative * 200)  # 10% outperformance vs sector → +20 pts
        return float(min(max(score, 0), 100))
    except Exception:
        return 50.0
