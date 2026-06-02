import numpy as np
import pandas as pd
from src.backtest import Results


def compute_metrics(results: Results) -> Results:
    dates = [r[0] for r in results.daily_values]
    port  = pd.Series([r[1] for r in results.daily_values], index=pd.to_datetime(dates))
    spy   = pd.Series([r[2] for r in results.daily_values], index=pd.to_datetime(dates))

    sc    = results.starting_cash
    n_yrs = (port.index[-1] - port.index[0]).days / 365.25

    def total_ret(s):
        return (s.iloc[-1] - sc) / sc * 100

    def cagr(s):
        return ((s.iloc[-1] / sc) ** (1 / n_yrs) - 1) * 100 if n_yrs > 0 else 0

    def sharpe(s):
        r = s.pct_change().dropna()
        return float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0

    def maxdd(s):
        return float(((s - s.cummax()) / s.cummax()).min() * 100)

    def yearly(s):
        by_yr = {}
        for d, v in s.items():
            by_yr.setdefault(d.year, []).append(v)
        out = {}
        for yr in sorted(by_yr):
            prev = by_yr.get(yr - 1, [sc])[-1]
            out[str(yr)] = (by_yr[yr][-1] - prev) / prev * 100
        return out

    results.total_return  = total_ret(port)
    results.spy_return    = total_ret(spy)
    results.cagr          = cagr(port)
    results.spy_cagr      = cagr(spy)
    results.sharpe        = sharpe(port)
    results.spy_sharpe    = sharpe(spy)
    results.max_drawdown  = maxdd(port)
    results.spy_max_dd    = maxdd(spy)
    results.yearly_returns = yearly(port)
    results.yearly_spy    = yearly(spy)

    avg_pv     = port.mean()
    total_sold = sum(tr.value for tr in results.trades if tr.action == "SELL")
    results.annual_turnover = total_sold / avg_pv / n_yrs * 100 if (avg_pv > 0 and n_yrs > 0) else 0

    if results.qqq_values:
        qqq = pd.Series(results.qqq_values, index=port.index)
        results.qqq_return = total_ret(qqq)
        results.qqq_cagr   = cagr(qqq)
        results.qqq_sharpe = sharpe(qqq)
        results.qqq_max_dd = maxdd(qqq)
        results.yearly_qqq = yearly(qqq)

        # 60/40 blend: 60% QQQ buy-and-hold, 40% this strategy
        blend = 0.60 * qqq + 0.40 * port
        results.blend_return = total_ret(blend)
        results.blend_cagr   = cagr(blend)
        results.blend_sharpe = sharpe(blend)
        results.blend_max_dd = maxdd(blend)
        results.yearly_blend = yearly(blend)
    else:
        results.blend_return = 0.0
        results.blend_cagr   = 0.0
        results.blend_sharpe = 0.0
        results.blend_max_dd = 0.0
        results.yearly_blend = {}

    return results


def print_results(results: Results) -> None:
    sc      = results.starting_cash
    has_qqq = bool(results.qqq_values)

    def dollars(ret_pct):
        return sc * (1 + ret_pct / 100)

    w = 76
    print("\n" + "═" * w)
    print("  Roth IRA  ·  $100k invested Jan 2005  ·  no taxes  ·  20 years")
    print("═" * w)

    # ── Summary table ──────────────────────────────────────────────────────────
    col = 14
    headers = ["60/40 Blend", "QQQ only", "Strategy only", "SPY only"]
    vals = {
        "blend": (results.blend_return,  results.blend_cagr,  results.blend_sharpe,  results.blend_max_dd),
        "qqq":   (results.qqq_return,    results.qqq_cagr,    results.qqq_sharpe,    results.qqq_max_dd),
        "strat": (results.total_return,  results.cagr,        results.sharpe,        results.max_drawdown),
        "spy":   (results.spy_return,    results.spy_cagr,    results.spy_sharpe,    results.spy_max_dd),
    }
    keys = ["blend", "qqq", "strat", "spy"]

    print(f"\n  {'':22}", end="")
    for h in headers:
        print(f"  {h:>{col}}", end="")
    print()
    print(f"  {'─'*22}", end="")
    for _ in headers:
        print(f"  {'─'*col}", end="")
    print()

    def row(label, idx, fmt):
        print(f"  {label:22}", end="")
        for k in keys:
            print(f"  {fmt(vals[k][idx]):>{col}}", end="")
        print()

    row("$100k grew to", 0, lambda v: f"${dollars(v):>10,.0f}")
    row("Total return",  0, lambda v: f"{v:>+.1f}%")
    row("CAGR / yr",     1, lambda v: f"{v:>+.2f}%")
    row("Sharpe ratio",  2, lambda v: f"{v:>.2f}")
    row("Worst crash",   3, lambda v: f"{v:>.1f}%")

    n_sells = len([t for t in results.trades if t.action == "SELL"])
    print(f"\n  Blend turnover: ~{results.annual_turnover * 0.40:.0f}%/yr  "
          f"(40% of {results.annual_turnover:.0f}% strategy turnover · 60% QQQ never sells)")

    # ── Year-by-year ───────────────────────────────────────────────────────────
    ykeys   = ["blend", "qqq", "strat", "spy"]
    ygetters = {
        "blend": results.yearly_blend,
        "qqq":   results.yearly_qqq,
        "strat": results.yearly_returns,
        "spy":   results.yearly_spy,
    }

    print(f"\n  {'Year':5}", end="")
    for h in ["60/40 Blend", "QQQ", "Strategy", "SPY"]:
        print(f"  {h:>10}", end="")
    print()
    print(f"  {'─'*5}", end="")
    for _ in range(4):
        print(f"  {'─'*10}", end="")
    print()

    for yr in sorted(results.yearly_returns):
        print(f"  {yr}", end="")
        for k in ykeys:
            v = ygetters[k].get(yr, 0)
            print(f"  {v:>+8.1f}%", end="")
        print()

    print("\n" + "═" * w)
    print("  The 60/40 blend = $60k into QQQ (never touched) + $40k into the strategy.")
    print("  Caveats: survivorship bias, price-based quality proxy, 0.1% slippage only.")
    print("═" * w)
