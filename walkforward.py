"""
Walk-forward validation: split the 20-year history in half.

  First half  2005–2014: strategy "runs" on data it was built during
  Second half 2015–2025: genuinely out-of-sample — no parameters were
                          chosen by looking at this period

If alpha holds up in both halves, that's evidence the signal is real.
If it collapses in the second half, the first half was overfit.

Data is already cached so this runs without re-downloading anything.
"""

from src.universe import UNIVERSE_2005, UNIVERSE_SCHEDULE, all_tickers
from src.fetch    import fetch_all, fetch_price_history, build_price_matrix
from src.backtest import run_backtest
from src.report   import compute_metrics

FETCH_START = "2003-01-01"
SIM_END     = "2025-12-31"

tickers_needed = all_tickers(UNIVERSE_2005, UNIVERSE_SCHEDULE)

print("── Loading cached data ─────────────────────────────────────────────")
prices = fetch_all(tickers_needed, start=FETCH_START, end=SIM_END)
spy    = fetch_price_history("SPY", start=FETCH_START, end=SIM_END)
qqq    = fetch_price_history("QQQ", start=FETCH_START, end=SIM_END)
closes = build_price_matrix(prices)
print(f"Matrix: {len(closes)} days × {len(closes.columns)} tickers\n")

kwargs = dict(
    closes            = closes,
    spy               = spy,
    qqq               = qqq,
    starting_cash     = 100_000,
    n_stocks          = 30,
    max_weight        = 0.10,
    initial_universe  = UNIVERSE_2005,
    universe_schedule = UNIVERSE_SCHEDULE,
)

print("── Half 1: 2005–2014  (in-sample) ─────────────────────────────────")
r1 = compute_metrics(run_backtest(**kwargs, start_date="2005-01-01", end_date="2014-12-31"))

print("\n── Half 2: 2015–2025  (out-of-sample) ──────────────────────────────")
r2 = compute_metrics(run_backtest(**kwargs, start_date="2015-01-01", end_date="2025-12-31"))

# ── Side-by-side comparison ───────────────────────────────────────────────────
w = 70
print("\n\n" + "═" * w)
print("  Walk-Forward Results")
print("═" * w)

col = 16
print(f"\n  {'':24} {'2005–2014':>{col}} {'2015–2025':>{col}}")
print(f"  {'':24} {'(in-sample)':>{col}} {'(out-of-sample)':>{col}}")
print(f"  {'─'*24} {'─'*col} {'─'*col}")

def row(label, v1, v2):
    print(f"  {label:24} {v1:>{col}} {v2:>{col}}")

sc = 100_000
row("Strategy final value",
    f"${sc*(1+r1.total_return/100):>10,.0f}",
    f"${sc*(1+r2.total_return/100):>10,.0f}")
row("Strategy CAGR",      f"{r1.cagr:>+.2f}%",       f"{r2.cagr:>+.2f}%")
row("SPY CAGR",           f"{r1.spy_cagr:>+.2f}%",   f"{r2.spy_cagr:>+.2f}%")
row("QQQ CAGR",           f"{r1.qqq_cagr:>+.2f}%",   f"{r2.qqq_cagr:>+.2f}%")
row("Alpha vs SPY",       f"{r1.cagr-r1.spy_cagr:>+.2f}%/yr", f"{r2.cagr-r2.spy_cagr:>+.2f}%/yr")
row("Alpha vs QQQ",       f"{r1.cagr-r1.qqq_cagr:>+.2f}%/yr", f"{r2.cagr-r2.qqq_cagr:>+.2f}%/yr")
row("Sharpe",             f"{r1.sharpe:>.2f}",        f"{r2.sharpe:>.2f}")
row("SPY Sharpe",         f"{r1.spy_sharpe:>.2f}",    f"{r2.spy_sharpe:>.2f}")
row("Worst drawdown",     f"{r1.max_drawdown:>.1f}%", f"{r2.max_drawdown:>.1f}%")
row("Annual turnover",    f"{r1.annual_turnover:.0f}%", f"{r2.annual_turnover:.0f}%")

print(f"\n  {'Year':5}  {'Strategy':>10}  {'SPY':>8}  {'QQQ':>8}  {'vs SPY':>8}")
print(f"  {'─'*5}  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*8}")

for yr in sorted({**r1.yearly_returns, **r2.yearly_returns}):
    half  = r1 if int(yr) <= 2014 else r2
    label = " ◀ in" if int(yr) <= 2014 else "   out"
    s  = half.yearly_returns.get(yr, 0)
    b  = half.yearly_spy.get(yr, 0)
    q  = half.yearly_qqq.get(yr, 0)
    print(f"  {yr}   {s:>+8.1f}%  {b:>+6.1f}%  {q:>+6.1f}%  {s-b:>+6.1f}%  {label}")

print("\n" + "═" * w)
print("  Verdict:")
a1 = r1.cagr - r1.spy_cagr
a2 = r2.cagr - r2.spy_cagr
if a1 > 0 and a2 > 0:
    if abs(a1 - a2) < 1.5:
        print("  ✓ Positive alpha in BOTH halves, consistent magnitude.")
        print("    Strongest evidence we have that the signal is real.")
    else:
        print("  ~ Positive alpha in both halves but magnitude differs.")
        print(f"    In-sample: {a1:+.2f}%/yr  Out-of-sample: {a2:+.2f}%/yr")
        print("    Some degradation is normal. Not disqualifying.")
elif a1 > 0 and a2 <= 0:
    print("  ✗ Alpha positive in-sample but negative out-of-sample.")
    print("    Classic overfit pattern. Be very cautious.")
else:
    print(f"  In-sample alpha: {a1:+.2f}%/yr  Out-of-sample: {a2:+.2f}%/yr")
print("═" * w)
