"""
Experiment 02 — International diversification

Add ~15 large-cap international ADRs to the universe. These are foreign
companies that trade on US exchanges: ASML, TSM, NVO, SAP, AZN, etc.

Hypothesis: when US tech is expensive or in a concentrated rally, the
momentum factor rotates into European/Asian leaders instead of being
stuck inside a purely US universe. NVO (Ozempic) and ASML (EUV chips)
both had huge runs in 2023 that our US-only strategy missed entirely.

No code changes — purely a universe expansion experiment.
Walk-forward: 2005-2014 in-sample, 2015-2025 out-of-sample.
"""

from src.universe import UNIVERSE_2005, UNIVERSE_SCHEDULE, all_tickers
from src.fetch    import fetch_all, fetch_price_history, build_price_matrix
from src.backtest import run_backtest
from src.report   import compute_metrics

# International ADRs — all traded on US exchanges, most since before 2005
INTL_ADRS = [
    "ASML",  # Netherlands — EUV lithography monopoly (no chip without it)
    "TSM",   # Taiwan — foundry that actually manufactures NVDA/AMD chips
    "NVO",   # Denmark — Novo Nordisk, Ozempic/GLP-1 drugs
    "SAP",   # Germany — enterprise software
    "AZN",   # UK/Sweden — AstraZeneca pharma
    "TM",    # Japan — Toyota, largest automaker
    "SONY",  # Japan — electronics, gaming, entertainment
    "UL",    # UK/Netherlands — Unilever, consumer staples
    "SNY",   # France — Sanofi pharma
    "BHP",   # Australia — largest mining company
    "RIO",   # UK/Australia — Rio Tinto mining
    "BP",    # UK — energy
    "DEO",   # UK — Diageo (Johnnie Walker, Guinness)
    "INFY",  # India — Infosys, IT services
    "SHEL",  # Netherlands/UK — Shell energy
]

FETCH_START = "2003-01-01"
SIM_END     = "2025-12-31"

# Collect all tickers needed for both experiments
us_tickers   = all_tickers(UNIVERSE_2005, UNIVERSE_SCHEDULE)
intl_tickers = list(set(us_tickers) | set(INTL_ADRS))

print("── Loading data ────────────────────────────────────────────────────")
prices = fetch_all(intl_tickers, start=FETCH_START, end=SIM_END)
spy    = fetch_price_history("SPY", start=FETCH_START, end=SIM_END)
qqq    = fetch_price_history("QQQ", start=FETCH_START, end=SIM_END)
closes = build_price_matrix(prices)

# Figure out which international tickers actually loaded
loaded_intl = [t for t in INTL_ADRS if t in closes.columns]
print(f"\nLoaded international ADRs ({len(loaded_intl)}): {loaded_intl}")
print(f"Matrix: {len(closes)} days × {len(closes.columns)} tickers\n")

UNIVERSE_INTL = UNIVERSE_2005 + [t for t in loaded_intl if t not in UNIVERSE_2005]

shared = dict(
    closes=closes, spy=spy, qqq=qqq,
    starting_cash=100_000, n_stocks=30, max_weight=0.10,
    universe_schedule=UNIVERSE_SCHEDULE,
)

periods = [
    ("2005–2014  in-sample",     "2005-01-01", "2014-12-31"),
    ("2015–2025  out-of-sample", "2015-01-01", "2025-12-31"),
]

results = {}
for label, s, e in periods:
    for name, universe in [("US only", UNIVERSE_2005), ("+ International", UNIVERSE_INTL)]:
        key = (label, name)
        print(f"\n── {label} | {name} ─────────────────────────────────────────────")
        r = compute_metrics(run_backtest(**shared, initial_universe=universe,
                                         start_date=s, end_date=e))
        results[key] = r

# ── Comparison ────────────────────────────────────────────────────────────────
w = 74
print("\n\n" + "═" * w)
print("  Experiment 02: International Diversification")
print("═" * w)

col = 15
print(f"\n  {'':28} {'── 2005–2014 ──':^32} {'── 2015–2025 ──':^32}")
print(f"  {'':28} {'US only':>{col}} {'+ Intl':>{col}} {'US only':>{col}} {'+ Intl':>{col}}")
print(f"  {'─'*28} {'─'*col} {'─'*col} {'─'*col} {'─'*col}")

def row(label, fn):
    vals = [
        fn(results[("2005–2014  in-sample",     "US only")]),
        fn(results[("2005–2014  in-sample",     "+ International")]),
        fn(results[("2015–2025  out-of-sample", "US only")]),
        fn(results[("2015–2025  out-of-sample", "+ International")]),
    ]
    print(f"  {label:28} " + " ".join(f"{v:>{col}}" for v in vals))

row("Strategy CAGR",    lambda r: f"{r.cagr:>+.2f}%")
row("SPY CAGR",         lambda r: f"{r.spy_cagr:>+.2f}%")
row("Alpha vs SPY /yr", lambda r: f"{r.cagr - r.spy_cagr:>+.2f}%")
row("QQQ CAGR",         lambda r: f"{r.qqq_cagr:>+.2f}%")
row("Alpha vs QQQ /yr", lambda r: f"{r.cagr - r.qqq_cagr:>+.2f}%")
row("Sharpe",           lambda r: f"{r.sharpe:>.2f}")
row("Worst drawdown",   lambda r: f"{r.max_drawdown:>.1f}%")

print(f"\n  Out-of-sample year-by-year (2015–2025):")
print(f"  {'Year':5}  {'US only':>10}  {'+ Intl':>10}  {'SPY':>8}  {'QQQ':>8}  {'Δ':>8}")
print(f"  {'─'*5}  {'─'*10}  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*8}")

rus = results[("2015–2025  out-of-sample", "US only")]
rin = results[("2015–2025  out-of-sample", "+ International")]

for yr in sorted(rus.yearly_returns):
    us  = rus.yearly_returns[yr]
    intl = rin.yearly_returns.get(yr, 0)
    spy_ = rus.yearly_spy.get(yr, 0)
    qqq_ = rus.yearly_qqq.get(yr, 0)
    diff = intl - us
    flag = "  ◀ helped" if diff > 1 else ("  ◀ hurt" if diff < -1 else "")
    print(f"  {yr}   {us:>+8.1f}%  {intl:>+8.1f}%  {spy_:>+6.1f}%  {qqq_:>+6.1f}%  {diff:>+6.1f}%{flag}")

print("\n" + "═" * w)
us_oos  = rus.cagr - rus.spy_cagr
int_oos = rin.cagr - rin.spy_cagr
print(f"  Out-of-sample alpha vs SPY:  US only {us_oos:+.2f}%/yr  →  + Intl {int_oos:+.2f}%/yr")
if int_oos > us_oos + 0.3:
    print("  ✓ International diversification improved out-of-sample alpha.")
elif int_oos < us_oos - 0.3:
    print("  ✗ International diversification hurt out-of-sample performance.")
else:
    print("  ~ Negligible difference.")
print("═" * w)
