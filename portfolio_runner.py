from src.portfolio import run_portfolio_backtest, run_core_satellite_backtest

TICKERS = [
    "AAPL","MSFT","NVDA","AMD","AVGO","META","GOOGL","ORCL","CRM","NOW",
    "HON","GE","CAT","DE","RTX","LMT","UNP","ETN","NOC",
    "AMZN","HD","MCD","NKE","SBUX","LOW","TJX","COST",
    "WMT","KO","PG","PEP",
]


def print_results(r):
    print("\n" + "=" * 60)
    print(f"  MODE: {r['mode'].upper()}")
    print("=" * 60)
    print(f"  Final value:            ${r['final_value']:>10,.2f}")
    print(f"  Strategy return:        {r['total_return']:>+8.2f}%")
    print()
    print(f"  ── Benchmarks ──────────────────────────────────────")
    print(f"  SPY buy & hold:         {r['spy_return']:>+8.2f}%")
    print(f"  Universe buy & hold:    {r['universe_bh']:>+8.2f}%   ← honest benchmark")
    print()
    print(f"  ── Alpha ───────────────────────────────────────────")
    print(f"  vs SPY:                 {r['alpha_vs_spy']:>+8.2f}%")
    print(f"  vs Universe (real):     {r['alpha_vs_universe']:>+8.2f}%")
    print()
    print(f"  ── Risk ────────────────────────────────────────────")
    print(f"  Sharpe ratio:           {r['sharpe']:>8.2f}")
    print(f"  Max drawdown:           {r['max_drawdown']:>8.2f}%")
    print(f"  Win rate:               {r['win_rate']:>8.1f}%")
    print(f"  Avg capital deployed:   {r['avg_deployed_pct']:>8.1f}%")
    print(f"  Total trades:           {r['n_trades']:>8}")
    print()
    print("  Year-by-year:")
    for yr, ret in sorted(r["yearly_returns"].items()):
        bar  = "█" * int(abs(ret) / 2)
        sign = "+" if ret >= 0 else "-"
        print(f"    {yr}  {ret:>+7.2f}%  {sign}{bar}")
    print("=" * 60)


core_sat   = run_core_satellite_backtest(TICKERS, starting_cash=100_000)
aggressive = run_portfolio_backtest(TICKERS, mode="aggressive", starting_cash=100_000)

if core_sat:
    print_results(core_sat)
if aggressive:
    print_results(aggressive)

if core_sat and aggressive:
    print("\n  COMPARISON")
    print(f"  {'':28}  {'Core-Satellite':>14}  {'Aggressive':>12}  {'Universe B&H':>12}")
    ubh = core_sat["universe_bh"]
    print(f"  {'Return':28}  {core_sat['total_return']:>+13.2f}%  {aggressive['total_return']:>+11.2f}%  {ubh:>+11.2f}%")
    print(f"  {'Alpha vs universe':28}  {core_sat['alpha_vs_universe']:>+13.2f}%  {aggressive['alpha_vs_universe']:>+11.2f}%  {'0.00%':>12}")
    print(f"  {'Alpha vs SPY':28}  {core_sat['alpha_vs_spy']:>+13.2f}%  {aggressive['alpha_vs_spy']:>+11.2f}%")
    print(f"  {'Sharpe':28}  {core_sat['sharpe']:>14.2f}  {aggressive['sharpe']:>12.2f}")
    print(f"  {'Max drawdown':28}  {core_sat['max_drawdown']:>13.2f}%  {aggressive['max_drawdown']:>11.2f}%")
    print(f"  {'Avg deployed':28}  {core_sat['avg_deployed_pct']:>13.1f}%  {aggressive['avg_deployed_pct']:>11.1f}%")
