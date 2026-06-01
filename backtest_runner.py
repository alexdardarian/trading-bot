from src.fetch import fetch_and_save
from src.walkforward import walk_forward_backtest

TICKERS = [
    # Tech — XLK — high momentum, earnings-driven
    "AAPL","MSFT","NVDA","AMD","AVGO","META","GOOGL","ORCL","CRM","NOW",
    # Industrials — XLI — cyclical, capex-driven
    "HON","GE","CAT","DE","RTX","LMT","UNP","ETN","NOC",
    # Consumer Discretionary — XLY — momentum + cyclical
    "AMZN","HD","MCD","NKE","SBUX","LOW","TJX","COST",
    # Consumer Staples — XLP — defensive, mean-reverting
    "WMT","KO","PG","PEP",
]

print("=" * 60)
print("Multi-factor walk-forward backtest — tech / industrials / consumer")
print("=" * 60)

all_alpha = []
all_sharpe = []
skipped = []
traded = []

for ticker in TICKERS:
    print(f"\n{ticker}")
    df = fetch_and_save(ticker, period="5y")
    results = walk_forward_backtest(df, ticker=ticker, rsi_buy=45, rsi_sell=50, score_threshold=60)

    if results is None:
        skipped.append(ticker)
        continue

    traded.append(ticker)
    print(f"  Strategy return:  {results['returns']:.2f}%  (avg across {results['n_folds']} folds)")
    print(f"  Buy & hold:       {results['buy_hold_return']:.2f}%")
    print(f"  Alpha:            {results['alpha']:+.2f}%")
    print(f"  Sharpe ratio:     {results['sharpe']:.2f}")
    print(f"  Max drawdown:     {results['max_drawdown']:.2f}%")
    print(f"  Trades:           {len(results['trades'])}")
    print(f"  Strategy type:    {results['strategy']}")

    all_alpha.append(results["alpha"])
    all_sharpe.append(results["sharpe"])

print("\n" + "=" * 60)
print(f"Traded: {traded}")
print(f"Skipped: {skipped}")
if all_alpha:
    print(f"Average alpha:        {sum(all_alpha)/len(all_alpha):+.2f}%")
    print(f"Average Sharpe:       {sum(all_sharpe)/len(all_sharpe):.2f}")
    print(f"Stocks beating market: {sum(1 for a in all_alpha if a > 0)}/{len(all_alpha)}")
print("=" * 60)