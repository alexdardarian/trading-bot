import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from src import factors, portfolio, risk, rebalance


@dataclass
class Results:
    daily_values:    list         # (date_str, port_val, spy_val, brake_active, n_pos)
    trades:          list         # list of Trade objects
    starting_cash:   float
    # Populated by report.compute_metrics
    total_return:    float = 0.0
    spy_return:      float = 0.0
    cagr:            float = 0.0
    spy_cagr:        float = 0.0
    sharpe:          float = 0.0
    spy_sharpe:      float = 0.0
    max_drawdown:    float = 0.0
    spy_max_dd:      float = 0.0
    annual_turnover: float = 0.0
    yearly_returns:  dict  = field(default_factory=dict)
    yearly_spy:      dict  = field(default_factory=dict)


def run_backtest(closes: pd.DataFrame,
                 spy:    pd.Series,
                 starting_cash:    float = 100_000,
                 n_stocks:         int   = 30,
                 max_weight:       float = 0.10,
                 start_date:       str   = "2005-01-01",
                 end_date:         str   = "2025-12-31",
                 initial_universe: list  = None,
                 universe_schedule: list = None) -> Results:

    # ── Pre-compute factor scores (vectorized over full history) ──────────────
    print("Computing momentum scores...", flush=True)
    mom      = factors.compute_momentum_matrix(closes)
    print("Computing quality proxy scores...", flush=True)
    qual     = factors.compute_quality_matrix(closes)
    print("Computing combined factor scores...", flush=True)
    combined = factors.compute_combined_scores(mom, qual)

    # ── Simulation date range ─────────────────────────────────────────────────
    sim_idx   = (closes.index >= start_date) & (closes.index <= end_date)
    sim_dates = closes.index[sim_idx]

    if len(sim_dates) == 0:
        raise ValueError(f"No trading days between {start_date} and {end_date}")

    # ── Quarterly rebalance dates: last trading day of each calendar quarter ──
    # Quarterly (not monthly) dramatically reduces trades and taxable events.
    quarter_ends = pd.date_range(start_date, end_date, freq="BQE")
    rebal_set    = set()
    for qe in quarter_ends:
        before = sim_dates[sim_dates <= qe]
        if len(before):
            rebal_set.add(before[-1])

    print(f"\nSimulating {len(sim_dates)} days | universe {len(closes.columns)} tickers | "
          f"{len(rebal_set)} quarterly rebalances | ${starting_cash:,.0f}\n", flush=True)

    # ── Universe schedule ─────────────────────────────────────────────────────
    active_universe = set(initial_universe or closes.columns.tolist())
    pending_changes = sorted(universe_schedule or [], key=lambda x: x[0])

    # ── State ─────────────────────────────────────────────────────────────────
    cash     = float(starting_cash)
    holdings = {}                     # ticker -> shares
    brake    = risk.BrakeState(peak=cash)

    # Exit buffer: a stock must miss the top-N for 2 consecutive rebalances
    # before we sell it. Prevents selling on one bad quarter and re-buying next.
    exit_buffer = {}                  # ticker -> consecutive quarters out of top-N

    spy_clean = spy.copy()
    if spy_clean.index.tz is not None:
        spy_clean.index = spy_clean.index.tz_convert(None)
    spy_shares = None

    daily_values = []
    all_trades   = []
    total_sold   = 0.0

    # ── Main loop ─────────────────────────────────────────────────────────────
    for date in sim_dates:
        row        = closes.loc[date]
        prices_day = row.dropna().to_dict()

        # Mark to market
        held = pd.Series(holdings)
        if len(held):
            shared = held.index.intersection(row.index)
            pos_val = (held[shared] * row[shared].fillna(0)).sum()
        else:
            pos_val = 0.0
        port_val = cash + pos_val

        # SPY buy-and-hold
        spy_px = spy_clean.get(date)
        if spy_px and not np.isnan(spy_px):
            if spy_shares is None:
                spy_shares = cash / spy_px
            spy_val = spy_shares * spy_px
        else:
            spy_val = (spy_shares or 0) * (spy_clean.get(date, 0) or 0)

        brake = risk.update(brake, port_val)

        daily_values.append((
            str(date.date()), port_val, spy_val,
            brake.active, len(holdings)
        ))

        if date not in rebal_set:
            continue

        # ── Universe schedule: apply any changes due on or before this date ──
        date_str = str(date.date())
        fired    = [c for c in pending_changes if c[0] <= date_str]
        for _, adds, removes in fired:
            for t in adds:
                active_universe.add(t)
            for t in removes:
                active_universe.discard(t)
            print(f"  [{date_str}] Universe  +{adds}  -{removes}")
        for c in fired:
            pending_changes.remove(c)

        # ── Factor scores restricted to active universe ───────────────────────
        scores_today = combined.loc[date] if date in combined.index else pd.Series(dtype=float)
        scores_today = scores_today[scores_today.index.isin(active_universe)]
        target_tickers = factors.select_portfolio(scores_today, n=n_stocks)

        if not target_tickers:
            continue

        raw_weights = portfolio.compute_target_weights(
            target_tickers, closes, date, max_weight=max_weight
        )
        eq_frac = risk.equity_fraction(brake)

        # ── Membership diff ───────────────────────────────────────────────────
        current_members = {t for t, s in holdings.items() if s > 1e-9}
        new_members     = set(target_tickers)

        # Reset buffer for stocks that returned to top-N
        for t in list(exit_buffer):
            if t in new_members:
                del exit_buffer[t]

        # Accumulate buffer for stocks that dropped out
        for t in current_members - new_members:
            exit_buffer[t] = exit_buffer.get(t, 0) + 1

        # Only exit after 2 consecutive quarters out — avoids selling on noise
        confirmed_exits   = {t for t, c in exit_buffer.items() if c >= 2}
        confirmed_entries = new_members - current_members

        # Nothing changed (and nothing buffered long enough) → hold everything
        if not confirmed_exits and not confirmed_entries:
            continue

        # ── Sells ─────────────────────────────────────────────────────────────
        sell_trades = []
        for t in confirmed_exits:
            px     = prices_day.get(t)
            shares = holdings.get(t, 0.0)
            if px and shares > 1e-9:
                val  = shares * px
                cost = val * rebalance.SLIPPAGE
                sell_trades.append(
                    rebalance.Trade(date_str, t, "SELL", shares, px, val, cost)
                )
            holdings.pop(t, None)
            exit_buffer.pop(t, None)

        for tr in sell_trades:
            cash += tr.value - tr.cost
        total_sold += sum(tr.value for tr in sell_trades)

        # ── Buys: allocate available cash to new entrants only ────────────────
        # We never sell continuing positions to fund new entrants — that would
        # create unnecessary taxable events.
        buy_trades = []
        entry_list = [t for t in confirmed_entries if prices_day.get(t)]

        if entry_list and cash > 100:
            entry_w = portfolio.compute_target_weights(
                entry_list, closes, date, max_weight=1.0
            )
            total_ew = sum(entry_w.values())
            deploy   = cash * eq_frac   # respect drawdown brake

            for t, ew in sorted(entry_w.items(), key=lambda x: x[1], reverse=True):
                px = prices_day.get(t)
                if not px:
                    continue
                buy_val = (ew / total_ew) * deploy if total_ew > 0 else 0
                if buy_val < 100:
                    continue
                cost   = buy_val * rebalance.SLIPPAGE
                shares = (buy_val - cost) / px
                buy_trades.append(
                    rebalance.Trade(date_str, t, "BUY", shares, px, buy_val, cost)
                )
                holdings[t] = holdings.get(t, 0.0) + shares
                cash -= buy_val

        all_trades.extend(sell_trades + buy_trades)

    # ── Liquidate at end ──────────────────────────────────────────────────────
    last_row = closes.loc[sim_dates[-1]]
    for t, shares in list(holdings.items()):
        px = last_row.get(t)
        if px and not np.isnan(px):
            cash += shares * px * (1 - rebalance.SLIPPAGE)

    avg_pv = np.mean([v[1] for v in daily_values]) if daily_values else starting_cash
    n_yrs  = (sim_dates[-1] - sim_dates[0]).days / 365.25
    annual_turnover = total_sold / avg_pv / n_yrs * 100 if (avg_pv > 0 and n_yrs > 0) else 0

    return Results(
        daily_values    = daily_values,
        trades          = all_trades,
        starting_cash   = starting_cash,
        annual_turnover = annual_turnover,
    )
