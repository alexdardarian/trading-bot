# Rules-based large-cap universe: top ~115 S&P 500 stocks across all 11 GICS sectors.
# Selected by sector representation at design time — NOT by outcome.
# Stocks that IPO'd after 2005 (META, NOW, AVGO) are included but will simply have
# no factor scores in the years before they went public.
#
# Known limitation: this is a point-in-2026 snapshot. Companies that went bankrupt
# or were acquired between 2005-2025 (Lehman, Bear Stearns, Sears) are absent.
# This introduces survivorship bias — results will be modestly overstated.

UNIVERSE = [
    # Technology (20)
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ORCL", "CRM", "ADBE", "CSCO",
    "QCOM", "TXN", "INTC", "AMD",   "IBM",  "AMAT", "MU",   "ADI",  "INTU", "NOW",

    # Financials (18)
    "JPM",  "BAC",  "WFC",  "GS",   "MS",   "BLK",  "V",    "MA",   "AXP",  "SCHW",
    "SPGI", "MCO",  "ICE",  "CME",  "CB",   "AON",  "MMC",  "USB",

    # Healthcare (16)
    "UNH",  "LLY",  "JNJ",  "ABT",  "MRK",  "ABBV", "TMO",  "DHR",  "ISRG", "SYK",
    "BSX",  "AMGN", "GILD", "VRTX", "REGN", "PFE",

    # Consumer Discretionary (12)
    "AMZN", "HD",   "MCD",  "NKE",  "SBUX", "LOW",  "TJX",  "TGT",  "BKNG", "NFLX",
    "F",    "GM",

    # Consumer Staples (9)
    "WMT",  "KO",   "PG",   "PEP",  "COST", "PM",   "MO",   "MDLZ", "CL",

    # Industrials (14)
    "HON",  "GE",   "CAT",  "DE",   "RTX",  "LMT",  "UNP",  "ETN",  "NOC",  "EMR",
    "ITW",  "GD",   "UPS",  "MMM",

    # Energy (8)
    "XOM",  "CVX",  "COP",  "EOG",  "SLB",  "MPC",  "PSX",  "OXY",

    # Materials (5)
    "LIN",  "APD",  "SHW",  "FCX",  "NEM",

    # Communication Services (5)
    "T",    "VZ",   "CMCSA","DIS",  "CHTR",

    # Utilities (4)
    "NEE",  "DUK",  "SO",   "D",

    # Real Estate (4)
    "PLD",  "AMT",  "WELL", "PSA",
]
