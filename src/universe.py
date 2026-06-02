# ── 2005-era universe ─────────────────────────────────────────────────────────
# Large-caps as a thoughtful manager would have held in January 2005.
# Intentionally includes names that later failed or declined (AIG, C, GE, HPQ,
# INTC, MMM) — that's the point. No hindsight.
# Fully delisted names (Lehman, Bear Stearns, Wachovia, Washington Mutual) are
# excluded because yfinance has no data for them; this understates the damage
# from the 2008 crisis.

UNIVERSE_2005 = [
    # Technology — legacy-heavy. No NVDA/META/GOOGL/CRM/AVGO/NOW (not yet relevant)
    "AAPL", "MSFT", "INTC", "CSCO", "IBM",  "ORCL", "HPQ",  "TXN",  "QCOM",
    "ADBE", "AMD",  "MU",   "AMAT", "ADI",  "KLAC", "INTU",

    # Financials — includes pre-crisis names that nearly failed
    "JPM",  "BAC",  "C",    "WFC",  "GS",   "MS",   "AIG",  "AXP",  "SCHW",
    "USB",  "CME",  "MCO",  "SPGI", "MET",  "ALL",

    # Healthcare
    "JNJ",  "PFE",  "MRK",  "ABT",  "LLY",  "AMGN", "GILD", "TMO",
    "BSX",  "SYK",  "MDT",  "UNH",  "ISRG",

    # Consumer Discretionary
    "HD",   "MCD",  "NKE",  "SBUX", "LOW",  "TJX",  "TGT",  "AMZN",
    "F",    "GM",   "BKNG",

    # Consumer Staples
    "WMT",  "KO",   "PG",   "PEP",  "COST", "MO",   "CL",

    # Industrials — includes GE, MMM, EMR which all declined significantly
    "GE",   "HON",  "CAT",  "DE",   "BA",   "LMT",  "UNP",  "MMM",
    "NOC",  "EMR",  "ITW",  "GD",   "UPS",  "RTX",

    # Energy — heavy weighting, energy was dominant in 2005
    "XOM",  "CVX",  "COP",  "EOG",  "SLB",  "HAL",  "DVN",  "OXY",  "VLO",

    # Materials
    "APD",  "SHW",  "FCX",  "NEM",

    # Communication / Media
    "T",    "VZ",   "CMCSA","DIS",

    # Utilities
    "NEE",  "DUK",  "SO",   "D",
]

# ── Dynamic universe schedule ──────────────────────────────────────────────────
# Each entry: (effective_date, [tickers_to_add], [tickers_to_remove])
# Changes are applied at the first rebalance on or after the effective date.
# These represent decisions a thoughtful manager could have made with information
# available at the time — not hindsight.

UNIVERSE_SCHEDULE = [
    # Jan 2009 — AIG was effectively nationalized (US govt took 80% stake Sep 2008).
    # C needed a $45B bailout and was trading below $5. Both lose their spot.
    ("2009-01-01",
     [],
     ["AIG", "C"]),

    # Jan 2012 — Google is clearly the dominant internet company (been public 8 years).
    # Netflix streaming is beating DVD. HP is visibly in freefall (Fiorina → Hurd → Apotheker
    # disasters). Devon Energy is mid-tier shale, not worth a slot.
    ("2012-01-01",
     ["GOOGL", "NFLX"],
     ["HPQ",   "DVN"]),

    # Jan 2015 — Facebook has 1.4B users and is clearly a dominant ad platform.
    # NVDA gaming GPU business is booming (Maxwell architecture). Salesforce SaaS model proven.
    # Halliburton and Valero are oil-services / refining — volatile, low-quality businesses.
    # SLB is the best-in-class oilfield name; keep it. Remove the lower-quality energy.
    ("2015-01-01",
     ["FB",  "NVDA", "CRM"],
     ["HAL", "VLO",  "SLB"]),

    # Jan 2018 — ServiceNow and Broadcom are clearly dominant in enterprise IT and semis.
    # AbbVie (Humira) is the best pharma growth story. GE's conglomerate model publicly
    # collapsed (CEO Immelt out 2017, dividend cut coming). MMM and Emerson are stagnating
    # industrial conglomerates.
    ("2018-01-01",
     ["NOW",  "AVGO", "ABBV"],
     ["GE",   "MMM",  "EMR"]),

    # Jan 2021 — AMD's Zen architecture comeback is complete; EPYC taking data center share.
    # Regeneron is a biotech standout (COVID antibody, Eylea). MetLife and Allstate are
    # slow-growth insurance. Boeing is still deep in 737 MAX and COVID crisis.
    ("2021-01-01",
     ["AMD",  "REGN"],
     ["MET",  "ALL",  "BA"]),

    # Jan 2023 — META recovered from 2022 metaverse disaster; ad business re-accelerating.
    # Ford EV execution has been poor; legacy auto is not where the returns are.
    # Altria is a slow-growth tobacco company with declining volumes.
    ("2023-01-01",
     ["META"],
     ["F",   "MO"]),
]


def build_schedule_index(schedule: list) -> list:
    """Pre-sorts the schedule by date for efficient lookup during simulation."""
    return sorted(schedule, key=lambda x: x[0])


def all_tickers(universe_start: list, schedule: list) -> list:
    """Returns every ticker that appears anywhere — needed to fetch all data upfront."""
    tickers = set(universe_start)
    for _, adds, _ in schedule:
        tickers.update(adds)
    return sorted(tickers)
