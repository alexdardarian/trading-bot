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

    # ── Monthly rebalance dates: last trading day of each calendar month ──────
    month_ends = pd.date_range(start_date, end_date, freq="BME")
    rebal_set  = set()
    for me in month_ends:
        before = sim_dates[sim_dates <= me]
        if len(before):
            rebal_set.add(before[-1])

    print(f"\nSimulating {len(sim_dates)} days | universe {len(closes.columns)} tickers | "
          f"{len(rebal_set)} monthly rebalances | ${starting_cash:,.0f}\n", flush=True)

    # ── Universe schedule — sorted and ready ──────────────────────────────────
    active_universe = set(initial_universe or closes.columns.tolist())
    pending_changes = sorted(universe_schedule or [], key=lambda x: x[0])

    # ── State ─────────────────────────────────────────────────────────────────
    cash     = float(starting_cash)
    holdings = {}                          # ticker -> shares
    brake    = risk.BrakeState(peak=cash)

    spy_clean = spy.copy()
    if spy_clean.index.tz is not None:
        spy_clean.index = spy_clean.index.tz_convert(None)
    spy_shares = None

    daily_values = []
    all_trades   = []
    total_sold   = 0.0

    # ── Main loop ─────────────────────────────────────────────────────────────
    for date in sim_dates:
        row         = closes.loc[date]
        prices_day  = row.dropna().to_dict()

        # Mark to market
        held = pd.Series(holdings)
        if len(held):
            shared_tickers = held.index.intersection(row.index)
            pos_val = (held[shared_tickers] * row[shared_tickers].fillna(0)).sum()
        else:
            pos_val = 0.0
        port_val = cash + pos_val

        # SPY parallel buy-and-hold
        spy_px = spy_clean.get(date)
        if spy_px and not np.isnan(spy_px):
            if spy_shares is None:
                spy_shares = cash / spy_px
            spy_val = spy_shares * spy_px
        else:
            spy_val = (spy_shares or 0) * (spy_clean.get(date, 0) or 0)

        # Drawdown brake (state update every day, trades only on rebalance)
        brake = risk.update(brake, port_val)

        daily_values.append((
            str(date.date()), port_val, spy_val,
            brake.active, len(holdings)
        ))

        # ── Rebalance ─────────────────────────────────────────────────────────
        if date not in rebal_set:
            continue

        # Apply any pending universe changes effective on or before this date
        date_str_today = str(date.date())
        fired = [c for c in pending_changes if c[0] <= date_str_today]
        for change in fired:
            _, adds, removes = change
            for t in adds:
                active_universe.add(t)
                print(f"  [{date_str_today}] Universe + {adds}  - {removes}")
            for t in removes:
                active_universe.discard(t)
            pending_changes.remove(change)

        scores_today = combined.loc[date] if date in combined.index else pd.Series(dtype=float)
        # Restrict selection to currently active universe
        scores_today = scores_today[scores_today.index.isin(active_universe)]
        target_tickers = factors.select_portfolio(scores_today, n=n_stocks)

        if not target_tickers:
            continue

        raw_weights = portfolio.compute_target_weights(
            target_tickers, closes, date, max_weight=max_weight
        )

        eq_frac = risk.equity_fraction(brake)
        target_weights = {t: w * eq_frac for t, w in raw_weights.items()}

        trades = rebalance.compute_trades(
            str(date.date()), holdings, target_weights,
            prices_day, port_val, cash
        )

        holdings, cash = rebalance.apply_trades(holdings, cash, trades)
        all_trades.extend(trades)
        total_sold += sum(tr.value for tr in trades if tr.action == "SELL")

    # ── Liquidate at end ──────────────────────────────────────────────────────
    last_row = closes.loc[sim_dates[-1]]
    for t, shares in list(holdings.items()):
        px = last_row.get(t)
        if px and not np.isnan(px):
            cash += shares * px * (1 - rebalance.SLIPPAGE)

    # Rough annual turnover (refined in report.compute_metrics)
    avg_pv = np.mean([v[1] for v in daily_values]) if daily_values else starting_cash
    n_yrs  = (sim_dates[-1] - sim_dates[0]).days / 365.25
    annual_turnover = (total_sold / avg_pv / n_yrs * 100) if (avg_pv > 0 and n_yrs > 0) else 0

    return Results(
        daily_values=daily_values,
        trades=all_trades,
        starting_cash=starting_cash,
        annual_turnover=annual_turnover,
    )
