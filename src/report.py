import numpy as np
import pandas as pd
from src.backtest import Results


def compute_metrics(results: Results) -> Results:
    dates = [r[0] for r in results.daily_values]
    port  = pd.Series([r[1] for r in results.daily_values], index=pd.to_datetime(dates))
    spy   = pd.Series([r[2] for r in results.daily_values], index=pd.to_datetime(dates))

    sc = results.starting_cash

    results.total_return = (port.iloc[-1] - sc) / sc * 100
    results.spy_return   = (spy.iloc[-1]  - sc) / sc * 100

    n_yrs = (port.index[-1] - port.index[0]).days / 365.25
    results.cagr     = ((port.iloc[-1] / sc) ** (1 / n_yrs) - 1) * 100 if n_yrs > 0 else 0
    results.spy_cagr = ((spy.iloc[-1]  / sc) ** (1 / n_yrs) - 1) * 100 if n_yrs > 0 else 0

    def sharpe(s):
        r = s.pct_change().dropna()
        return float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0

    def maxdd(s):
        return float(((s - s.cummax()) / s.cummax()).min() * 100)

    results.sharpe      = sharpe(port)
    results.spy_sharpe  = sharpe(spy)
    results.max_drawdown = maxdd(port)
    results.spy_max_dd   = maxdd(spy)

    # Refined annual turnover
    avg_pv = port.mean()
    total_sold = sum(tr.value for tr in results.trades if tr.action == "SELL")
    results.annual_turnover = total_sold / avg_pv / n_yrs * 100 if (avg_pv > 0 and n_yrs > 0) else 0

    # Year-by-year returns
    def yearly(s):
        out = {}
        by_yr = {}
        for d, v in s.items():
            by_yr.setdefault(d.year, []).append(v)
        for yr in sorted(by_yr):
            prev = by_yr.get(yr - 1, [sc])[-1]
            out[str(yr)] = (by_yr[yr][-1] - prev) / prev * 100
        return out

    results.yearly_returns = yearly(port)
    results.yearly_spy     = yearly(spy)
    return results


def print_results(results: Results) -> None:
    tot  = results.total_return
    spyr = results.spy_return
    alph = tot - spyr

    w = 66
    print("\n" + "═" * w)
    print("  V2  ·  Momentum + Quality  ·  Risk-Parity  ·  S&P 500 universe")
    print("═" * w)
    print(f"  Final value:         ${results.starting_cash * (1 + tot/100):>12,.2f}")
    print(f"  Total return:        {tot:>+8.2f}%")
    print(f"  CAGR:                {results.cagr:>+8.2f}%   (SPY: {results.spy_cagr:>+.2f}%)")
    print(f"  SPY total:           {spyr:>+8.2f}%")
    print(f"  Alpha vs SPY:        {alph:>+8.2f}%")
    print()
    print(f"  Sharpe:              {results.sharpe:>8.2f}   (SPY: {results.spy_sharpe:.2f})")
    print(f"  Max drawdown:        {results.max_drawdown:>8.2f}%  (SPY: {results.spy_max_dd:.2f}%)")
    print(f"  Annual turnover:     {results.annual_turnover:>8.1f}%")
    print(f"  Total trades:        {len(results.trades):>8}")
    print()
    print(f"  {'Year':5}  {'Strategy':>10}  {'SPY':>8}  {'Alpha':>8}")
    print(f"  {'─'*5}  {'─'*10}  {'─'*8}  {'─'*8}")

    for yr in sorted(results.yearly_returns):
        s = results.yearly_returns[yr]
        b = results.yearly_spy.get(yr, 0)
        a = s - b
        bar  = "█" * min(int(abs(s) / 2), 20)
        sign = "+" if s >= 0 else "-"
        print(f"  {yr}   {s:>+8.2f}%  {b:>+6.2f}%  {a:>+6.2f}%  {sign}{bar}")

    print("═" * w)
    print()
    print("  Caveats:")
    print("  ▸ Universe fixed at 2026 — survivorship bias overstates returns.")
    print("  ▸ Quality factor uses price-based proxy (52wk-high + neg-vol),")
    print("    not Novy-Marx gross profitability (needs point-in-time financials).")
    print("  ▸ No transaction tax or market-impact costs beyond 0.1% slippage.")
    print("═" * w)
