"""
V2 Quarterly Rebalance Bot
─────────────────────────────────────────────────────────────────────────
Run once at the end of each quarter (last trading day of March, June,
September, December).

  python3 bot.py             # dry run — shows what would happen, no orders
  python3 bot.py --execute   # places real orders (paper account)
  python3 bot.py --status    # shows current portfolio + live factor scores

State is persisted in bot_state.json between runs so the exit buffer
(2-quarter confirmation before selling) survives across quarters.
"""

import sys
import json
import os
from datetime import date
from dotenv import load_dotenv
import pandas as pd

from src.universe import UNIVERSE_2005, UNIVERSE_SCHEDULE
from src.fetch    import fetch_all, fetch_price_history, build_price_matrix
from src.factors  import (compute_momentum_matrix, compute_quality_matrix,
                           compute_combined_scores)
from src.portfolio import compute_target_weights
from src import broker

load_dotenv()

STATE_FILE    = "bot_state.json"
FETCH_START   = "2003-01-01"
N_STOCKS      = 30
MAX_WEIGHT    = 0.10
EXIT_BUFFER_NEEDED = 2   # consecutive quarters out of top-N before selling


# ── Universe ──────────────────────────────────────────────────────────────────

def current_universe() -> list:
    """Apply the schedule up to today to get the active universe."""
    today = str(date.today())
    u = set(UNIVERSE_2005)
    for d, adds, removes in sorted(UNIVERSE_SCHEDULE, key=lambda x: x[0]):
        if d <= today:
            u.update(adds)
            u -= set(removes)
    return sorted(u)


# ── State persistence ─────────────────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_run": None, "exit_buffer": {}, "quarter": 0}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Factor scoring on live data ───────────────────────────────────────────────

def compute_live_scores(universe: list) -> pd.Series:
    """
    Fetch recent price history for every ticker in the universe and return
    the latest combined factor scores as a Series indexed by ticker.
    """
    end = str(date.today())
    all_needed = list(set(universe))

    print(f"  Fetching prices for {len(all_needed)} tickers...", flush=True)
    prices = fetch_all(all_needed, start=FETCH_START, end=end)
    closes = build_price_matrix(prices)

    mom      = compute_momentum_matrix(closes)
    qual     = compute_quality_matrix(closes)
    combined = compute_combined_scores(mom, qual)

    # Return scores on the most recent date that has valid data
    latest = combined.dropna(how="all").iloc[-1]
    return latest


# ── Main ──────────────────────────────────────────────────────────────────────

def run(execute: bool = False, status_only: bool = False):
    w = 62
    today = str(date.today())

    print("\n" + "═" * w)
    print(f"  V2 QUARTERLY REBALANCE BOT — {today}")
    if execute:
        print("  ⚡ EXECUTE MODE — orders will be placed")
    elif status_only:
        print("  STATUS MODE — no changes")
    else:
        print("  DRY RUN — pass --execute to place orders")
    print("═" * w)

    # ── Connect ───────────────────────────────────────────────────────────────
    print("\n  Connecting to Alpaca (paper)...")
    client   = broker.get_client(paper=True)
    acct     = broker.account_info(client)
    open_    = broker.is_market_open(client)

    print(f"  Portfolio value:  ${acct['portfolio_value']:>10,.2f}")
    print(f"  Cash:             ${acct['cash']:>10,.2f}")
    print(f"  Market:           {'OPEN' if open_ else 'CLOSED'}")

    if execute and not open_:
        print("\n  ✗ Market is closed. Run during market hours to execute.")
        print("    (Dry run still works — remove --execute to preview.)")
        sys.exit(1)

    # ── Current holdings from Alpaca ──────────────────────────────────────────
    held_shares = broker.get_positions(client)
    held_values = broker.get_position_values(client)
    held_tickers = set(held_shares)

    print(f"\n  Current holdings:  {len(held_tickers)} positions")
    if held_tickers:
        for t in sorted(held_tickers):
            print(f"    {t:<6}  ${held_values.get(t, 0):>9,.2f}")

    if status_only:
        # Just show factor scores and bail out
        universe = current_universe()
        print(f"\n  Computing factor scores ({len(universe)} tickers)...")
        scores = compute_live_scores(universe)
        valid  = scores[scores.index.isin(universe)].dropna().sort_values(ascending=False)
        print(f"\n  Top 30 by factor score:")
        print(f"  {'Rank':>4}  {'Ticker':<7} {'Score':>7}  {'Held':>5}")
        print(f"  {'─'*4}  {'─'*7} {'─'*7}  {'─'*5}")
        for i, (t, s) in enumerate(valid.head(30).items(), 1):
            held_flag = "YES" if t in held_tickers else "—"
            print(f"  {i:>4}  {t:<7} {s:>7.3f}  {held_flag:>5}")
        print()
        return

    # ── Load persisted state ──────────────────────────────────────────────────
    state = load_state()
    exit_buffer: dict = state.get("exit_buffer", {})
    print(f"\n  Last run:  {state['last_run'] or 'never'}")
    print(f"  Quarter:   #{state['quarter']}")

    # ── Compute live factor scores ────────────────────────────────────────────
    universe = current_universe()
    print(f"\n  Active universe: {len(universe)} tickers")
    print(f"  Computing factor scores...")
    scores      = compute_live_scores(universe)
    scores_u    = scores[scores.index.isin(universe)].dropna()
    top_tickers = scores_u.nlargest(N_STOCKS).index.tolist()
    top_set     = set(top_tickers)

    # ── Update exit buffer ────────────────────────────────────────────────────
    # Reset stocks that returned to the top-N
    for t in list(exit_buffer):
        if t in top_set:
            del exit_buffer[t]

    # Increment stocks that are held but outside the top-N
    for t in held_tickers:
        if t not in top_set:
            exit_buffer[t] = exit_buffer.get(t, 0) + 1

    confirmed_exits = {t for t, c in exit_buffer.items() if c >= EXIT_BUFFER_NEEDED}
    new_entries     = top_set - held_tickers

    # ── Compute buy sizes ─────────────────────────────────────────────────────
    # New entries are sized by risk-parity, funded by exit proceeds + idle cash
    # We approximate available cash: current cash + value of confirmed exits
    exit_cash = sum(held_values.get(t, 0) for t in confirmed_exits)
    avail     = acct["cash"] + exit_cash

    entry_weights = {}
    if new_entries:
        closes_for_weight = build_price_matrix(
            fetch_all(list(new_entries), start=FETCH_START, end=today)
        )
        entry_weights = compute_target_weights(
            list(new_entries), closes_for_weight,
            closes_for_weight.index[-1], max_weight=1.0
        )
        total_ew = sum(entry_weights.values())
        entry_dollars = {t: (entry_weights[t] / total_ew) * avail
                         for t in entry_weights}
    else:
        entry_dollars = {}

    # ── Print proposal ────────────────────────────────────────────────────────
    print(f"\n  {'─'*w}")
    print(f"  PROPOSED REBALANCE")
    print(f"  {'─'*w}")

    # Sells
    if confirmed_exits:
        print(f"\n  SELL — confirmed {EXIT_BUFFER_NEEDED} quarters outside top-{N_STOCKS}:")
        for t in sorted(confirmed_exits):
            v = held_values.get(t, 0)
            q = exit_buffer.get(t, 0)
            print(f"    {t:<6}  ${v:>9,.2f}   ({q} qtrs out)")
    else:
        print(f"\n  SELL — none")

    # Buys
    if new_entries:
        print(f"\n  BUY — new top-{N_STOCKS} entrants:")
        for t in sorted(new_entries):
            dollars = entry_dollars.get(t, 0)
            score   = float(scores_u.get(t, 0))
            print(f"    {t:<6}  ${dollars:>9,.2f}   (score {score:.3f})")
    else:
        print(f"\n  BUY — none")

    # Watch list (1 quarter in exit buffer, not yet confirmed)
    watching = {t: c for t, c in exit_buffer.items()
                if c < EXIT_BUFFER_NEEDED and t in held_tickers}
    if watching:
        print(f"\n  WATCH — held but outside top-{N_STOCKS} (will sell next quarter if still out):")
        for t, c in sorted(watching.items()):
            score = float(scores_u.get(t, 0)) if t in scores_u.index else 0
            print(f"    {t:<6}  score {score:.3f}  ({c}/{EXIT_BUFFER_NEEDED} qtrs)")

    # Unchanged holdings
    kept = held_tickers - confirmed_exits - new_entries
    if kept:
        print(f"\n  HOLD — {len(kept)} unchanged positions (no trades)")

    print(f"\n  Estimated trades: {len(confirmed_exits)} sells, {len(new_entries)} buys")
    print(f"  Available for buys: ${avail:,.2f}")

    if not execute:
        print(f"\n  Dry run complete. Pass --execute to place orders.")
        print("═" * w + "\n")
        # Still save state so the exit buffer accumulates correctly each quarter
        state["last_run"]     = today
        state["exit_buffer"]  = exit_buffer
        state["quarter"]      = state.get("quarter", 0) + 1
        save_state(state)
        return

    # ── Execute ───────────────────────────────────────────────────────────────
    print(f"\n  {'─'*w}")
    print(f"  EXECUTING ORDERS")
    print(f"  {'─'*w}\n")

    for t in sorted(confirmed_exits):
        try:
            broker.sell_all(client, t)
            print(f"  ✓ SOLD   {t}")
        except Exception as e:
            print(f"  ✗ SELL {t} failed: {e}")

    for t in sorted(new_entries):
        dollars = entry_dollars.get(t, 0)
        if dollars < 1:
            print(f"  – SKIP {t} (${dollars:.2f} too small)")
            continue
        try:
            broker.buy_notional(client, t, dollars)
            print(f"  ✓ BOUGHT {t}  ${dollars:,.2f}")
        except Exception as e:
            print(f"  ✗ BUY {t} failed: {e}")

    # Save state
    state["last_run"]    = today
    state["exit_buffer"] = exit_buffer
    state["quarter"]     = state.get("quarter", 0) + 1
    save_state(state)

    print(f"\n  State saved to {STATE_FILE}")
    print("═" * w + "\n")


if __name__ == "__main__":
    execute     = "--execute" in sys.argv
    status_only = "--status"  in sys.argv
    run(execute=execute, status_only=status_only)
