from src.universe import UNIVERSE_2005, UNIVERSE_SCHEDULE, all_tickers
from src.fetch    import fetch_all, fetch_price_history, build_price_matrix
from src.backtest import run_backtest
from src.report   import compute_metrics, print_results

FETCH_START = "2003-01-01"
SIM_START   = "2005-01-01"
SIM_END     = "2025-12-31"

# Every ticker that ever appears — initial list plus all future schedule additions
tickers_needed = all_tickers(UNIVERSE_2005, UNIVERSE_SCHEDULE)
print(f"Universe: {len(UNIVERSE_2005)} stocks in 2005, "
      f"{len(tickers_needed)} total across schedule  |  Sim: {SIM_START} → {SIM_END}\n")

print("── Fetching price history ──────────────────────────────────────────")
prices = fetch_all(tickers_needed, start=FETCH_START, end=SIM_END)
spy    = fetch_price_history("SPY", start=FETCH_START, end=SIM_END)

print("── Building price matrix ───────────────────────────────────────────")
closes = build_price_matrix(prices)
print(f"Matrix: {len(closes)} trading days × {len(closes.columns)} tickers\n")

print("── Running backtest ────────────────────────────────────────────────")
results = run_backtest(
    closes, spy,
    starting_cash     = 100_000,
    n_stocks          = 30,
    max_weight        = 0.10,
    start_date        = SIM_START,
    end_date          = SIM_END,
    initial_universe  = UNIVERSE_2005,
    universe_schedule = UNIVERSE_SCHEDULE,
)

results = compute_metrics(results)
print_results(results)
