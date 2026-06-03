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
    # EDA, test & measurement, analog semis — all dominant by 2005
    "CDNS", "SNPS", "LRCX", "MCHP", "TER",  "ANSS", "ON",   "ENTG",
    # ANSS (ANSYS) acquired by Synopsys Feb 2024; removed via schedule below

    # Financials — includes pre-crisis names that nearly failed
    "JPM",  "BAC",  "C",    "WFC",  "GS",   "MS",   "AIG",  "AXP",  "SCHW",
    "USB",  "CME",  "MCO",  "SPGI", "MET",  "ALL",
    # Asset managers, payment rails, insurers — all large and established by 2005
    "BRK-B","COF",  "BLK",  "TROW", "PGR",  "TRV",  "HIG",  "BNY",  "STT",

    # Healthcare
    "JNJ",  "PFE",  "MRK",  "ABT",  "LLY",  "AMGN", "GILD", "TMO",
    "BSX",  "SYK",  "MDT",  "UNH",  "ISRG",
    # Broader healthcare — pharma, devices, diagnostics, managed care
    "VRTX", "BMY",  "CI",   "CVS",  "HUM",  "IDXX", "EW",   "ZBH",  "A",

    # Consumer Discretionary
    "HD",   "MCD",  "NKE",  "SBUX", "LOW",  "TJX",  "TGT",  "AMZN",
    "F",    "GM",   "BKNG",
    # Restaurants, off-price, dollar stores
    "ROST", "DLTR", "YUM",  "DRI",

    # Consumer Staples
    "WMT",  "KO",   "PG",   "PEP",  "COST", "MO",   "CL",

    # Industrials — includes GE, MMM, EMR which all declined significantly
    "GE",   "HON",  "CAT",  "DE",   "BA",   "LMT",  "UNP",  "MMM",
    "NOC",  "EMR",  "ITW",  "GD",   "UPS",  "RTX",
    # Business services, homebuilders, distribution — all established by 2005
    "WM",   "RSG",  "ROP",  "AME",  "CTAS", "PAYX", "FAST", "GWW",
    "DHI",  "LEN",  "PHM",

    # Energy — heavy weighting, energy was dominant in 2005
    "XOM",  "CVX",  "COP",  "EOG",  "SLB",  "HAL",  "DVN",  "OXY",  "VLO",
    # Midstream pipelines
    "WMB",  "EQT",

    # Materials
    "APD",  "SHW",  "FCX",  "NEM",
    # Specialty chemicals
    "ECL",  "PPG",

    # Communication / Media
    "T",    "VZ",   "CMCSA","DIS",
    # Gaming
    "EA",   "TTWO",

    # Utilities
    "NEE",  "DUK",  "SO",   "D",
]

# ── Dynamic universe schedule ──────────────────────────────────────────────────
# Each entry: (effective_date, [tickers_to_add], [tickers_to_remove])
# Changes are applied at the first rebalance on or after the effective date.
# These represent decisions a thoughtful manager could have made with information
# available at the time — not hindsight.

UNIVERSE_SCHEDULE = [
    # Jan 2007 — Mastercard (IPO May 2006) is clearly the other dominant payment network.
    # Chipotle (IPO Jan 2006) is proving the fast-casual model at scale.
    ("2007-01-01",
     ["MA",  "CMG"],
     []),

    # Jan 2008 — Lululemon (IPO Jul 2007) is validating premium athletic apparel.
    ("2008-01-01",
     ["LULU"],
     []),

    # Jan 2009 — AIG was effectively nationalized (US govt took 80% stake Sep 2008).
    # C needed a $45B bailout and was trading below $5. Both lose their spot.
    # Visa (IPO Mar 2008) is now public and clearly the dominant card network alongside MA.
    ("2009-01-01",
     ["V"],
     ["AIG", "C"]),

    # Jan 2010 — Dollar General (IPO Nov 2009) and Fortinet (IPO Nov 2009) both
    # went public and represent high-quality franchises worth tracking from the start.
    ("2010-01-01",
     ["DG",  "FTNT"],
     []),

    # Jan 2012 — Google is clearly the dominant internet company (been public 8 years).
    # Netflix streaming is beating DVD. HP is visibly in freefall.
    # Devon Energy is mid-tier shale, not worth a slot.
    # HCA (re-IPO Mar 2011) is the dominant for-profit hospital chain.
    ("2012-01-01",
     ["GOOGL", "NFLX", "HCA"],
     ["HPQ",   "DVN"]),

    # Jan 2015 — Facebook has 1.4B users and is clearly a dominant ad platform.
    # NVDA gaming GPU business is booming (Maxwell architecture). Salesforce SaaS proven.
    # Palo Alto (IPO Jul 2012) and Workday (IPO Oct 2012) are now large enough to include.
    # Keysight (spun from Agilent Nov 2014) is the leading electronic test equipment company.
    # Halliburton and Valero are oil-services/refining — volatile, low-quality businesses.
    # SLB is best-in-class oilfield; keep it. Remove the lower-quality energy.
    ("2015-01-01",
     ["FB",   "NVDA", "CRM",  "PANW", "WDAY", "KEYS"],
     ["HAL",  "VLO",  "SLB"]),

    # Jan 2018 — ServiceNow and Broadcom are clearly dominant in enterprise IT and semis.
    # AbbVie (Humira) is the best pharma growth story. GE's conglomerate model publicly
    # collapsed (CEO Immelt out 2017, dividend cut coming). MMM and Emerson stagnating.
    ("2018-01-01",
     ["NOW",  "AVGO", "ABBV"],
     ["GE",   "MMM",  "EMR"]),

    # Jan 2021 — AMD's Zen architecture comeback is complete; EPYC taking data center share.
    # Regeneron is a biotech standout (COVID antibody, Eylea).
    # CrowdStrike (IPO Jun 2019) and Datadog (IPO Sep 2019) are now proven cloud-security
    # platforms with sufficient history. Moderna (IPO Dec 2018) proved out by COVID.
    # Carrier and Otis (spun from UTC Apr 2020) are now independent and trackable.
    # MetLife and Allstate are slow-growth insurance. Boeing is deep in 737 MAX crisis.
    ("2021-01-01",
     ["AMD",  "REGN", "CRWD", "DDOG", "MRNA", "CARR", "OTIS"],
     ["MET",  "ALL",  "BA"]),

    # Jan 2022 — Zscaler (IPO Mar 2018) and Cloudflare (IPO Sep 2019) now have 3+ years
    # of public history and are clearly dominant in cloud security and networking.
    # Snowflake (IPO Sep 2020) is the leading cloud data platform with 15+ months of history.
    ("2022-01-01",
     ["ZS",  "NET",  "SNOW"],
     []),

    # Jan 2024 — ANSYS (ANSS) acquired by Synopsys; delisted Feb 2024. Remove it.
    ("2024-01-01",
     [],
     ["ANSS"]),

    # Jan 2023 — META recovered from 2022 metaverse disaster; ad business re-accelerating.
    # Ford EV execution has been poor; legacy auto is not where the returns are.
    # Altria is a slow-growth tobacco company with declining volumes.
    # FB is the old ticker for META (renamed Oct 2021); remove it explicitly so it
    # doesn't linger as a dead slot that yfinance silently drops.
    ("2023-01-01",
     ["META"],
     ["F",   "MO",  "FB"]),
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
