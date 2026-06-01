from src.portfolio import run_portfolio_backtest

TICKERS = [
    # Tech — XLK
    "AAPL","MSFT","NVDA","AMD","AVGO","META","GOOGL","ORCL","CRM","NOW",
    # Industrials — XLI
    "HON","GE","CAT","DE","RTX","LMT","UNP","ETN","NOC",
    # Consumer Discretionary — XLY
    "AMZN","HD","MCD","NKE","SBUX","LOW","TJX","COST",
    # Consumer Staples — XLP
    "WMT","KO","PG","PEP",
]

results = run_portfolio_backtest(
    TICKERS,
    starting_cash  = 100_000,
    max_positions  = 10,
    score_threshold= 60,
)

if not results:
    print("No results.")
else:
    print("\n" + "=" * 60)
    print("PORTFOLIO RESULTS  |  5yr  |  $100k starting capital")
    print("=" * 60)
    print(f"  Final value:       ${results['final_value']:>10,.2f}")
    print(f"  Total return:      {results['total_return']:>+8.2f}%")
    print(f"  SPY buy & hold:    {results['spy_return']:>+8.2f}%")
    print(f"  Alpha vs SPY:      {results['alpha']:>+8.2f}%")
    print(f"  Sharpe ratio:      {results['sharpe']:>8.2f}")
    print(f"  Max drawdown:      {results['max_drawdown']:>8.2f}%")
    print(f"  Win rate:          {results['win_rate']:>8.1f}%")
    print(f"  Avg capital used:  {results['avg_deployed_pct']:>8.1f}%")
    print(f"  Total trades:      {results['n_trades']:>8}")
    print()
    print("  Year-by-year:")
    for yr, ret in sorted(results["yearly_returns"].items()):
        bar = "█" * int(abs(ret) / 2)
        sign = "+" if ret >= 0 else "-"
        print(f"    {yr}  {ret:>+7.2f}%  {sign}{bar}")
    print("=" * 60)
