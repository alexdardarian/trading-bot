"""
Experiment 01 — Regime-aware concentration

Hypothesis: when the market rally is narrow (SPY >> RSP), concentrate into
top 15 stocks. When it's broad, hold the full 30.

Validation: walk-forward, same two halves as before.
  In-sample  2005-2014
  Out-of-sample 2015-2025

We run each half TWICE — with and without regime detection — and compare.
If regime detection helps out-of-sample (especially 2023), it's real signal.
If it only helps in-sample, it's overfit.
"""

from src.universe import UNIVERSE_2005, UNIVERSE_SCHEDULE, all_tickers
from src.fetch    import fetch_all, fetch_price_history, build_price_matrix
from src.backtest import run_backtest
from src.report   import compute_metrics

FETCH_START = "2003-01-01"
SIM_END     = "2025-12-31"

print("── Loading data ────────────────────────────────────────────────────")
prices = fetch_all(all_tickers(UNIVERSE_2005, UNIVERSE_SCHEDULE),
                   start=FETCH_START, end=SIM_END)
spy = fetch_price_history("SPY", start=FETCH_START, end=SIM_END)
qqq = fetch_price_history("QQQ", start=FETCH_START, end=SIM_END)
rsp = fetch_price_history("RSP", start=FETCH_START, end=SIM_END)
closes = build_price_matrix(prices)
print(f"Matrix: {len(closes)} days × {len(closes.columns)} tickers\n")

shared = dict(
    closes=closes, spy=spy, qqq=qqq,
    starting_cash=100_000, n_stocks=30, max_weight=0.10,
    initial_universe=UNIVERSE_2005, universe_schedule=UNIVERSE_SCHEDULE,
)

periods = [
    ("2005–2014  in-sample",    "2005-01-01", "2014-12-31"),
    ("2015–2025  out-of-sample","2015-01-01", "2025-12-31"),
]

results = {}
for label, s, e in periods:
    for regime, rsp_arg in [("baseline", None), ("regime", rsp)]:
        key = (label, regime)
        print(f"\n── {label} | {regime} ──────────────────────────────────────")
        r = compute_metrics(run_backtest(**shared, rsp=rsp_arg,
                                         start_date=s, end_date=e))
        results[key] = r

# ── Print comparison ──────────────────────────────────────────────────────────
w = 74
print("\n\n" + "═" * w)
print("  Experiment 01: Regime-Aware Concentration")
print("═" * w)

col = 14
def pct(v):   return f"{v:>+.2f}%"
def pcty(v):  return f"{v:>+.1f}%"

print(f"\n  {'':28} {'── 2005–2014 ──':^30} {'── 2015–2025 ──':^30}")
print(f"  {'':28} {'Baseline':>{col}} {'+ Regime':>{col}} {'Baseline':>{col}} {'+ Regime':>{col}}")
print(f"  {'─'*28} {'─'*col} {'─'*col} {'─'*col} {'─'*col}")

def row(label, fn):
    vals = [
        fn(results[("2005–2014  in-sample",    "baseline")]),
        fn(results[("2005–2014  in-sample",    "regime")]),
        fn(results[("2015–2025  out-of-sample","baseline")]),
        fn(results[("2015–2025  out-of-sample","regime")]),
    ]
    print(f"  {label:28} " + " ".join(f"{v:>{col}}" for v in vals))

row("Strategy CAGR",     lambda r: pct(r.cagr))
row("SPY CAGR",          lambda r: pct(r.spy_cagr))
row("Alpha vs SPY /yr",  lambda r: pct(r.cagr - r.spy_cagr))
row("QQQ CAGR",          lambda r: pct(r.qqq_cagr))
row("Alpha vs QQQ /yr",  lambda r: pct(r.cagr - r.qqq_cagr))
row("Sharpe",            lambda r: f"{r.sharpe:>.2f}")
row("Worst drawdown",    lambda r: f"{r.max_drawdown:>.1f}%")

# Year-by-year for the out-of-sample half
print(f"\n  Out-of-sample year-by-year (2015–2025):")
print(f"  {'Year':5}  {'Baseline':>10}  {'+ Regime':>10}  {'SPY':>8}  {'QQQ':>8}  {'Δ (regime-base)':>16}")
print(f"  {'─'*5}  {'─'*10}  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*16}")

rb = results[("2015–2025  out-of-sample","baseline")]
rr = results[("2015–2025  out-of-sample","regime")]

for yr in sorted(rb.yearly_returns):
    base = rb.yearly_returns[yr]
    reg  = rr.yearly_returns.get(yr, 0)
    spy_ = rb.yearly_spy.get(yr, 0)
    qqq_ = rb.yearly_qqq.get(yr, 0)
    diff = reg - base
    flag = "  ◀ regime helped" if diff > 1 else ("  ◀ regime hurt" if diff < -1 else "")
    print(f"  {yr}   {base:>+8.1f}%  {reg:>+8.1f}%  {spy_:>+6.1f}%  {qqq_:>+6.1f}%  {diff:>+14.1f}%{flag}")

# Verdict
print("\n" + "═" * w)
base_oos_alpha = results[("2015–2025  out-of-sample","baseline")].cagr - \
                 results[("2015–2025  out-of-sample","baseline")].spy_cagr
reg_oos_alpha  = results[("2015–2025  out-of-sample","regime")].cagr   - \
                 results[("2015–2025  out-of-sample","regime")].spy_cagr

print(f"  Out-of-sample alpha vs SPY:  Baseline {base_oos_alpha:+.2f}%/yr  →  Regime {reg_oos_alpha:+.2f}%/yr")
if reg_oos_alpha > base_oos_alpha + 0.3:
    print("  ✓ Regime detection improved out-of-sample alpha. Signal looks real.")
elif reg_oos_alpha < base_oos_alpha - 0.3:
    print("  ✗ Regime detection hurt out-of-sample. Probably overfit to in-sample.")
else:
    print("  ~ Negligible difference. Regime detection neither helps nor hurts.")
print("═" * w)
