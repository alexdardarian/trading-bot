"""
Sector classification and sector-capped portfolio selection.

8 broad buckets keep the cap meaningful at 25%:
  max 7–8 stocks per sector in a 30-stock portfolio.

Any ticker not in SECTOR_MAP defaults to "Other" — it can still enter the
portfolio but won't be double-counted against any sector's cap.
"""

MAX_SECTOR_FRAC = 0.25   # no single sector may exceed 25% of n_stocks

SECTOR_MAP: dict[str, str] = {
    # ── Technology (hardware, semis, software, internet, cloud) ─────────────
    "AAPL": "Technology",  "MSFT": "Technology",  "NVDA": "Technology",
    "INTC": "Technology",  "CSCO": "Technology",  "IBM":  "Technology",
    "ORCL": "Technology",  "TXN":  "Technology",  "QCOM": "Technology",
    "ADBE": "Technology",  "AMD":  "Technology",  "MU":   "Technology",
    "AMAT": "Technology",  "ADI":  "Technology",  "KLAC": "Technology",
    "INTU": "Technology",  "CRM":  "Technology",  "AVGO": "Technology",
    "NOW":  "Technology",  "META": "Technology",  "GOOGL":"Technology",
    "NFLX": "Technology",  "AMZN": "Technology",  "HPQ":  "Technology",
    "FB":   "Technology",
    # Added 2026
    "CDNS": "Technology",  "SNPS": "Technology",  "LRCX": "Technology",
    "MCHP": "Technology",  "TER":  "Technology",  "ANSS": "Technology",
    "ON":   "Technology",  "ENTG": "Technology",  "KEYS": "Technology",
    "FTNT": "Technology",  "PANW": "Technology",  "WDAY": "Technology",
    "CRWD": "Technology",  "DDOG": "Technology",  "ZS":   "Technology",
    "NET":  "Technology",  "SNOW": "Technology",

    # ── Financials (banks, insurance, exchanges, asset managers) ────────────
    "JPM":   "Financials", "BAC":   "Financials", "C":     "Financials",
    "WFC":   "Financials", "GS":    "Financials", "MS":    "Financials",
    "AIG":   "Financials", "AXP":   "Financials", "SCHW":  "Financials",
    "USB":   "Financials", "CME":   "Financials", "MCO":   "Financials",
    "SPGI":  "Financials", "MET":   "Financials", "ALL":   "Financials",
    # Added 2026
    "BRK-B": "Financials", "V":     "Financials", "MA":    "Financials",
    "COF":   "Financials", "BLK":   "Financials", "TROW":  "Financials",
    "PGR":   "Financials", "TRV":   "Financials", "HIG":   "Financials",
    "BK":    "Financials", "STT":   "Financials",

    # ── Healthcare (pharma, biotech, devices, managed care) ─────────────────
    "JNJ":  "Healthcare",  "PFE":  "Healthcare",  "MRK":  "Healthcare",
    "ABT":  "Healthcare",  "LLY":  "Healthcare",  "AMGN": "Healthcare",
    "GILD": "Healthcare",  "TMO":  "Healthcare",  "BSX":  "Healthcare",
    "SYK":  "Healthcare",  "MDT":  "Healthcare",  "UNH":  "Healthcare",
    "ISRG": "Healthcare",  "ABBV": "Healthcare",  "REGN": "Healthcare",
    # Added 2026
    "VRTX": "Healthcare",  "BMY":  "Healthcare",  "CI":   "Healthcare",
    "CVS":  "Healthcare",  "HUM":  "Healthcare",  "IDXX": "Healthcare",
    "EW":   "Healthcare",  "ZBH":  "Healthcare",  "A":    "Healthcare",
    "MRNA": "Healthcare",  "HCA":  "Healthcare",

    # ── Consumer (discretionary + staples) ──────────────────────────────────
    "HD":   "Consumer",    "MCD":  "Consumer",    "NKE":  "Consumer",
    "SBUX": "Consumer",    "LOW":  "Consumer",    "TJX":  "Consumer",
    "TGT":  "Consumer",    "BKNG": "Consumer",    "GM":   "Consumer",
    "DIS":  "Consumer",    "WMT":  "Consumer",    "KO":   "Consumer",
    "PG":   "Consumer",    "PEP":  "Consumer",    "COST": "Consumer",
    "CL":   "Consumer",    "F":    "Consumer",    "MO":   "Consumer",
    # Added 2026
    "ROST": "Consumer",    "DLTR": "Consumer",    "YUM":  "Consumer",
    "DRI":  "Consumer",    "CMG":  "Consumer",    "LULU": "Consumer",
    "DG":   "Consumer",

    # ── Industrials (manufacturing, defense, construction, logistics) ────────
    "GE":   "Industrials", "HON":  "Industrials", "CAT":  "Industrials",
    "DE":   "Industrials", "BA":   "Industrials", "LMT":  "Industrials",
    "UNP":  "Industrials", "MMM":  "Industrials", "NOC":  "Industrials",
    "EMR":  "Industrials", "ITW":  "Industrials", "GD":   "Industrials",
    "UPS":  "Industrials", "RTX":  "Industrials",
    # Added 2026
    "WM":   "Industrials", "RSG":  "Industrials", "ROP":  "Industrials",
    "AME":  "Industrials", "CTAS": "Industrials", "PAYX": "Industrials",
    "FAST": "Industrials", "GWW":  "Industrials", "DHI":  "Industrials",
    "LEN":  "Industrials", "PHM":  "Industrials", "CARR": "Industrials",
    "OTIS": "Industrials",

    # ── Energy ──────────────────────────────────────────────────────────────
    "XOM":  "Energy",      "CVX":  "Energy",      "COP":  "Energy",
    "EOG":  "Energy",      "SLB":  "Energy",      "HAL":  "Energy",
    "DVN":  "Energy",      "OXY":  "Energy",      "VLO":  "Energy",
    # Added 2026
    "WMB":  "Energy",      "EQT":  "Energy",

    # ── Materials ───────────────────────────────────────────────────────────
    "APD":  "Materials",   "SHW":  "Materials",   "FCX":  "Materials",
    "NEM":  "Materials",
    # Added 2026
    "ECL":  "Materials",   "PPG":  "Materials",

    # ── Other (utilities, telecom, media) ────────────────────────────────────
    "NEE":  "Other",       "DUK":  "Other",       "SO":   "Other",
    "D":    "Other",       "T":    "Other",        "VZ":   "Other",
    "CMCSA":"Other",
    # Added 2026
    "EA":   "Other",       "TTWO": "Other",
}


def sector_capped_portfolio(
    scores: "pd.Series",       # noqa: F821 — avoid circular import
    n: int = 30,
    max_frac: float = MAX_SECTOR_FRAC,
    min_valid: int = 15,
) -> list[str]:
    """
    Select top-n tickers by score with a per-sector cap.

    Iterates scores in descending order; skips a ticker whose sector has
    already filled its allocation (max_frac × n slots).  Continues past
    capped sectors rather than stopping, so lower-ranked tickers from
    under-represented sectors can fill remaining slots.

    Returns [] if fewer than min_valid tickers have valid scores.
    """
    valid = scores.dropna().sort_values(ascending=False)
    if len(valid) < min_valid:
        return []

    max_per_sector = max(1, int(n * max_frac))
    sector_counts: dict[str, int] = {}
    result: list[str] = []

    for ticker in valid.index:
        sector = SECTOR_MAP.get(ticker, "Other")
        if sector_counts.get(sector, 0) < max_per_sector:
            result.append(ticker)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            if len(result) == n:
                break

    return result


def sector_breakdown(tickers: list[str]) -> dict[str, int]:
    """Returns {sector: count} for a list of tickers, sorted by count desc."""
    counts: dict[str, int] = {}
    for t in tickers:
        s = SECTOR_MAP.get(t, "Other")
        counts[s] = counts.get(s, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
