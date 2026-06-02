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

from src.universe     import UNIVERSE_2005, UNIVERSE_SCHEDULE
from src.fetch        import fetch_all, build_price_matrix, fetch_price_history
from src.factors      import (compute_momentum_matrix, compute_quality_matrix,
                               compute_combined_scores)
from src.portfolio    import compute_target_weights
from src.sectors      import sector_capped_portfolio, sector_breakdown
from src.intelligence import score_tickers
from src              import broker, risk

load_dotenv()

STATE_FILE    = "bot_state.json"
FETCH_START   = "2003-01-01"
N_STOCKS      = 30
N_STOCKS_CONCENTRATED = 15   # used when regime is narrow (SPY >> RSP)
REGIME_THRESHOLD = -0.03     # RSP/SPY 63-day spread below this → concentrate
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
    return {"last_run": None, "exit_buffer": {}, "quarter": 0,
            "peak_value": 0.0, "brake_active": False}


def save_state(state: dict):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)   # atomic on POSIX — crash-safe


# ── Regime detection ──────────────────────────────────────────────────────────

def detect_regime(lookback: int = 63) -> tuple[str, float]:
    """
    Compare RSP (equal-weight S&P 500) vs SPY (cap-weight) over the past
    `lookback` trading days.

    When SPY beats RSP by REGIME_THRESHOLD (3%+), a handful of mega-caps are
    driving everything → concentrate into top N_STOCKS_CONCENTRATED.
    When the market is broad (RSP keeping up), hold the full top N_STOCKS.

    Returns (regime_label, spread) where spread = RSP/SPY ratio change over
    the lookback window. Negative spread means SPY is beating RSP.
    """
    end = str(date.today())
    try:
        rsp = fetch_price_history("RSP", start=FETCH_START, end=end)
        spy = fetch_price_history("SPY", start=FETCH_START, end=end)
        common = rsp.index.intersection(spy.index)
        ratio  = (rsp[common] / spy[common]).sort_index()
        hist   = ratio.tail(lookback + 1)
        if len(hist) < lookback:
            return "broad (insufficient data)", 0.0
        spread = float(hist.iloc[-1] / hist.iloc[0] - 1)
        if spread < REGIME_THRESHOLD:
            return f"narrow (RSP-SPY {spread*100:+.1f}%)", spread
        return f"broad (RSP-SPY {spread*100:+.1f}%)", spread
    except Exception as e:
        return f"broad (RSP fetch failed: {e})", 0.0


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

    # ── Brake state (load before displaying, so status shows it) ─────────────
    state_pre    = load_state()
    brake        = risk.BrakeState(
        active=state_pre.get("brake_active", False),
        peak=state_pre.get("peak_value", acct["portfolio_value"]),
    )
    brake        = risk.update(brake, acct["portfolio_value"])
    eq_frac      = risk.equity_fraction(brake)
    pv           = acct["portfolio_value"]
    dd_from_peak = (pv - brake.peak) / brake.peak * 100 if brake.peak > 0 else 0.0

    print(f"  Portfolio value:  ${pv:>10,.2f}")
    print(f"  Cash:             ${acct['cash']:>10,.2f}")
    print(f"  Market:           {'OPEN' if open_ else 'CLOSED'}")
    print(f"  Peak value:       ${brake.peak:>10,.2f}   drawdown {dd_from_peak:+.2f}%")
    if brake.active:
        print(f"  ⚠  DRAWDOWN BRAKE ACTIVE — deploying {eq_frac*100:.0f}% of cash on new buys")

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
        universe = current_universe()
        regime_label, regime_spread = detect_regime()
        n_target = N_STOCKS_CONCENTRATED if regime_spread < REGIME_THRESHOLD else N_STOCKS
        print(f"\n  Regime: {regime_label}  →  targeting {n_target} stocks")
        print(f"  Computing factor scores ({len(universe)} tickers)...")
        scores   = compute_live_scores(universe)
        valid    = scores[scores.index.isin(universe)].dropna()
        top_30   = sector_capped_portfolio(valid, n=n_target)

        print(f"\n  Top {N_STOCKS} (sector-capped) — factor scores:")
        print(f"  {'Rank':>4}  {'Ticker':<7} {'Score':>7}  {'Sector':<12}  {'Held':>5}")
        print(f"  {'─'*4}  {'─'*7} {'─'*7}  {'─'*12}  {'─'*5}")
        for i, t in enumerate(top_30, 1):
            from src.sectors import SECTOR_MAP
            sector    = SECTOR_MAP.get(t, "Other")
            held_flag = "YES" if t in held_tickers else "—"
            print(f"  {i:>4}  {t:<7} {valid[t]:>7.3f}  {sector:<12}  {held_flag:>5}")

        breakdown = sector_breakdown(top_30)
        print(f"\n  Sector breakdown:")
        for sector, count in breakdown.items():
            bar = "█" * count
            print(f"    {sector:<14} {count:>2}  {bar}")
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
    print(f"  Detecting market regime...")
    regime_label, regime_spread = detect_regime()
    n_target = N_STOCKS_CONCENTRATED if regime_spread < REGIME_THRESHOLD else N_STOCKS
    print(f"  Regime: {regime_label}  →  targeting {n_target} stocks")

    print(f"  Computing factor scores...")
    scores      = compute_live_scores(universe)
    scores_u    = scores[scores.index.isin(universe)].dropna()
    top_tickers = sector_capped_portfolio(scores_u, n=n_target)
    top_set     = set(top_tickers)

    # ── Update exit buffer ────────────────────────────────────────────────────
    # Drop any stale buffer entries for stocks no longer held in Alpaca.
    # This happens when a previous run's orders filled without the bot knowing.
    for t in list(exit_buffer):
        if t not in held_tickers:
            del exit_buffer[t]

    # Reset buffer for stocks that returned to the top-N
    for t in list(exit_buffer):
        if t in top_set:
            del exit_buffer[t]

    # Increment buffer for stocks that are held but outside the top-N
    for t in held_tickers:
        if t not in top_set:
            exit_buffer[t] = exit_buffer.get(t, 0) + 1

    confirmed_exits = {t for t, c in exit_buffer.items() if c >= EXIT_BUFFER_NEEDED}
    new_entries     = top_set - held_tickers

    # ── Compute buy sizes ─────────────────────────────────────────────────────
    # New entries are sized by risk-parity, funded by exit proceeds + idle cash.
    # eq_frac scales deployment down when the drawdown brake is active (e.g. 0.5
    # when the portfolio is down 20%+ from its peak), matching backtest behaviour.
    exit_cash    = sum(held_values.get(t, 0) for t in confirmed_exits)
    avail        = acct["cash"] + exit_cash
    avail_deploy = avail * eq_frac   # apply brake fraction

    entry_weights      = {}
    entry_dollars      = {}
    entry_prices       = {}   # latest close price per new entrant (used for qty calc)
    closes_for_weight  = None

    if brake.active:
        print(f"\n  ⚠ Brake active: deploying {eq_frac*100:.0f}% of ${avail:,.2f} = ${avail_deploy:,.2f}")
    else:
        print(f"\n  Available cash for buys: ${avail_deploy:,.2f}")

    if new_entries:
        closes_for_weight = build_price_matrix(
            fetch_all(list(new_entries), start=FETCH_START, end=today)
        )
        entry_weights = compute_target_weights(
            list(new_entries), closes_for_weight,
            closes_for_weight.index[-1], max_weight=1.0
        )
        total_ew = sum(entry_weights.values())
        if total_ew <= 0:
            print("  ✗ Could not compute entry weights — all tickers missing volatility data")
        else:
            latest = closes_for_weight.iloc[-1]
            for t, wt in entry_weights.items():
                dollars = (wt / total_ew) * avail_deploy
                price   = float(latest.get(t, 0))
                if price > 0:
                    entry_dollars[t] = dollars
                    entry_prices[t]  = price
                else:
                    print(f"  ✗ No price for {t} — skipping")

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
    print(f"  Deploying: ${avail_deploy:,.2f}"
          + (f"  (brake: {eq_frac*100:.0f}% of ${avail:,.2f})" if brake.active else ""))

    if not execute:
        print(f"\n  Dry run complete. Pass --execute to place orders.")
        print("═" * w + "\n")
        # Still save state so exit buffer and brake accumulate correctly each quarter
        state["last_run"]     = today
        state["exit_buffer"]  = exit_buffer
        state["quarter"]      = state.get("quarter", 0) + 1
        state["peak_value"]   = brake.peak
        state["brake_active"] = brake.active
        save_state(state)
        return

    # ── Execute ───────────────────────────────────────────────────────────────
    print(f"\n  {'─'*w}")
    print(f"  EXECUTING ORDERS")
    print(f"  {'─'*w}\n")

    # Cancel any pending orders from previous runs before placing new ones.
    # Without this, sells fail with "held_for_orders" if a DAY order is still queued.
    print("  Cancelling any open orders...", flush=True)
    try:
        broker.cancel_all_orders(client)
        print("  ✓ Open orders cleared\n")
    except Exception as e:
        print(f"  ! Could not cancel orders: {e}\n")

    # Re-fetch positions so we only sell what Alpaca actually holds right now.
    # exit_buffer can be stale if positions were closed by a previous run's orders.
    live_positions = broker.get_positions(client)
    live_tickers   = set(live_positions)

    for t in sorted(confirmed_exits):
        if t not in live_tickers:
            print(f"  – SKIP  {t:<6}  (not in Alpaca — already sold or never held)")
            exit_buffer.pop(t, None)   # clean stale entry from buffer
            continue
        try:
            broker.sell_all(client, t)
            print(f"  ✓ SOLD   {t}")
            exit_buffer.pop(t, None)
        except Exception as e:
            print(f"  ✗ SELL {t} failed: {e}")

    for t in sorted(new_entries):
        dollars = entry_dollars.get(t, 0)
        price   = entry_prices.get(t, 0)

        if dollars < 1 or price <= 0:
            print(f"  – SKIP  {t:<6}  ${dollars:.2f}  @ ${price:.2f}  (too small or no price)")
            continue

        qty = dollars / price
        print(f"  → ORDER {t:<6}  {qty:.4f} shares  @ ~${price:.2f}  = ${dollars:,.2f}", end="  ")

        try:
            broker.buy_qty(client, t, qty)
            print("✓")
        except Exception as e:
            print(f"✗  {e}")

    # Save state
    state["last_run"]    = today
    state["exit_buffer"]  = exit_buffer
    state["quarter"]      = state.get("quarter", 0) + 1
    state["peak_value"]   = brake.peak
    state["brake_active"] = brake.active
    save_state(state)

    print(f"\n  State saved to {STATE_FILE}")
    print("═" * w + "\n")


SCOUT_CANDIDATES = 40   # top-N by quant score to send to Claude


def scout():
    """
    Full intelligence analysis: quant scores + Claude reading news, analyst
    consensus, and earnings surprises for the top SCOUT_CANDIDATES tickers.

    python3 bot.py --scout
    """
    w = 72
    today = str(date.today())

    print("\n" + "═" * w)
    print(f"  INTELLIGENCE SCOUT — {today}")
    print("═" * w)

    universe = current_universe()
    print(f"\n  Universe: {len(universe)} tickers → computing quant scores...")
    scores = compute_live_scores(universe)

    scores_u   = scores[scores.index.isin(universe)].dropna()
    candidates = scores_u.nlargest(SCOUT_CANDIDATES).index.tolist()
    quant_dict = scores_u.to_dict()

    print(f"  Candidates: top {len(candidates)} by quant score\n")

    intel = score_tickers(candidates, quant_dict)

    if not intel:
        print("  ✗ No results returned from Claude.")
        print("═" * w + "\n")
        return

    # Build blended score: 60% normalised quant + 40% Claude confidence
    q_vals = [quant_dict.get(r.ticker, 0.0) for r in intel]
    q_min, q_max = min(q_vals), max(q_vals)
    q_range = (q_max - q_min) or 1.0

    rows = []
    for r in intel:
        q_norm   = (quant_dict.get(r.ticker, 0.0) - q_min) / q_range
        blended  = 0.6 * q_norm + 0.4 * r.confidence
        rows.append((blended, r))
    rows.sort(key=lambda x: x[0], reverse=True)

    # Verdict abbreviations for compact display
    verdict_abbr = {
        "strong_buy": "STRONG BUY",
        "buy":        "BUY      ",
        "hold":       "HOLD     ",
        "avoid":      "AVOID    ",
    }
    earn_abbr    = {"beat": "beat", "miss": "MISS", "mixed": "mix", "no_data": "—"}
    analyst_abbr = {"buy": "buy", "hold": "hld", "sell": "SEL",
                    "insufficient_data": "—"}
    news_abbr    = {"positive": "pos", "neutral": "neu",
                    "negative": "NEG", "mixed": "mix"}

    print(f"\n  {'─'*w}")
    print(f"  BLENDED RANKINGS  (60% quant + 40% AI confidence)")
    print(f"  {'─'*w}")
    hdr = f"  {'Rank':>4}  {'Ticker':<6}  {'Quant':>6}  {'AI':>5}  {'Blend':>5}  " \
          f"{'Verdict':<10}  {'Earn':<5}  {'Anl':<4}  News"
    print(hdr)
    print("  " + "─" * (w - 2))

    for rank, (blend, r) in enumerate(rows, 1):
        q = quant_dict.get(r.ticker, 0.0)
        print(
            f"  {rank:>4}  {r.ticker:<6}  {q:>6.3f}  {r.confidence:>5.2f}  "
            f"{blend:>5.3f}  {verdict_abbr.get(r.verdict, r.verdict):<10}  "
            f"{earn_abbr.get(r.earnings_trend, '?'):<5}  "
            f"{analyst_abbr.get(r.analyst_signal, '?'):<4}  "
            f"{news_abbr.get(r.news_sentiment, '?')}"
        )

    # Detailed theses for top 10
    print(f"\n  {'─'*w}")
    print(f"  TOP 10 THESES")
    print(f"  {'─'*w}")
    for _, r in rows[:10]:
        conf_pct = int(r.confidence * 100)
        print(f"\n  {r.ticker}  ({conf_pct}% confidence)  —  {r.verdict.upper().replace('_', ' ')}")
        print(f"  Bull: {r.bull_thesis}")
        print(f"  Bear: {r.bear_thesis}")

    print("\n" + "═" * w + "\n")


if __name__ == "__main__":
    execute     = "--execute" in sys.argv
    status_only = "--status"  in sys.argv
    scout_mode  = "--scout"   in sys.argv

    if scout_mode:
        scout()
    else:
        run(execute=execute, status_only=status_only)
