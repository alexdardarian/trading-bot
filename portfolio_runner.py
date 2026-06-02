from src.portfolio import run_portfolio_backtest

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
    print(f"  Final value:       ${r['final_value']:>10,.2f}")
    print(f"  Total return:      {r['total_return']:>+8.2f}%")
    print(f"  SPY buy & hold:    {r['spy_return']:>+8.2f}%")
    print(f"  Alpha vs SPY:      {r['alpha']:>+8.2f}%")
    print(f"  Sharpe ratio:      {r['sharpe']:>8.2f}")
    print(f"  Max drawdown:      {r['max_drawdown']:>8.2f}%")
    print(f"  Win rate:          {r['win_rate']:>8.1f}%")
    print(f"  Avg capital used:  {r['avg_deployed_pct']:>8.1f}%")
    print(f"  Total trades:      {r['n_trades']:>8}")
    print()
    print("  Year-by-year:")
    for yr, ret in sorted(r["yearly_returns"].items()):
        bar  = "█" * int(abs(ret) / 2)
        sign = "+" if ret >= 0 else "-"
        print(f"    {yr}  {ret:>+7.2f}%  {sign}{bar}")
    print("=" * 60)


# Run both modes — conservative shows the safety tradeoff,
# aggressive shows what actually investing the money looks like
aggressive  = run_portfolio_backtest(TICKERS, mode="aggressive",   starting_cash=100_000)
conservative = run_portfolio_backtest(TICKERS, mode="conservative", starting_cash=100_000)

if aggressive:
    print_results(aggressive)
if conservative:
    print_results(conservative)

if aggressive and conservative:
    print("\n  SIDE BY SIDE")
    print(f"  {'':20}  {'Aggressive':>12}  {'Conservative':>12}")
    print(f"  {'Return':20}  {aggressive['total_return']:>+11.2f}%  {conservative['total_return']:>+11.2f}%")
    print(f"  {'Alpha vs SPY':20}  {aggressive['alpha']:>+11.2f}%  {conservative['alpha']:>+11.2f}%")
    print(f"  {'Sharpe':20}  {aggressive['sharpe']:>12.2f}  {conservative['sharpe']:>12.2f}")
    print(f"  {'Max drawdown':20}  {aggressive['max_drawdown']:>11.2f}%  {conservative['max_drawdown']:>11.2f}%")
    print(f"  {'Avg deployed':20}  {aggressive['avg_deployed_pct']:>11.1f}%  {conservative['avg_deployed_pct']:>11.1f}%")
    print(f"  {'Win rate':20}  {aggressive['win_rate']:>11.1f}%  {conservative['win_rate']:>11.1f}%")
