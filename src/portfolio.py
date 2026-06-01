import pandas as pd
import numpy as np
from src.fetch import fetch_and_save
from src.indicators import add_indicators
from src.signals import add_signals, add_momentum_signals
from src.factors.scorer import composite_score
from src.factors.vix_regime import vix_regime_at
from src.factors.market_regime import get_spy_regime, get_sector_regime
from src.factors.relative_strength import SECTOR_ETFS
from src.filters import vol_spike_mask, earnings_blackout_mask

SLIPPAGE     = 0.001
STOP_LOSS    = 0.03
MIN_TRAIN    = 252
SCORE_UPDATE = 63   # recompute composite score every quarter

_VIX_THRESHOLDS = {
    "fear":        {"mom": 80, "rev": 55},
    "normal":      {"mom": 70, "rev": 70},
    "complacency": {"mom": 60, "rev": 80},
}


def _position_size(portfolio_value, score):
    """Score bracket sizing — higher conviction = bigger bet.
    Sized for a standalone swing trading portfolio (not institutional multi-strategy).
    10 max positions × 10% = 100% deployed at full capacity."""
    if score >= 80:
        return portfolio_value * 0.12   # 12% — strong conviction
    elif score >= 70:
        return portfolio_value * 0.10   # 10% — solid setup
    return portfolio_value * 0.08       # 8%  — marginal, smaller bet


def _prepare_ticker(ticker, rsi_buy=45, rsi_sell=50, score_threshold=60, period="5y"):
    """
    Pre-computes all signals, scores, and prices for one ticker.
    Returns dicts keyed by YYYY-MM-DD date strings for O(1) lookup during simulation.
    """
    try:
        raw = fetch_and_save(ticker, period=period)
    except Exception:
        return None
    if len(raw) < MIN_TRAIN + SCORE_UPDATE:
        return None

    df = raw.copy()
    df = add_indicators(df)

    # All three signal variants — indicators are backward-looking, no look-ahead
    df_mom = add_momentum_signals(df.copy())
    df_rev = add_signals(df.copy(), rsi_buy=rsi_buy, rsi_sell=rsi_sell)
    df_hyb = df.copy()
    df_hyb["buy"]  = df_mom["buy"] | df_rev["buy"]
    df_hyb["sell"] = df_mom["sell"] & df_rev["sell"]
    variants = {"momentum breakout": df_mom, "mean reversion": df_rev, "hybrid": df_hyb}

    # Entry filters applied to all buy signals (sells are never blocked)
    spy_reg  = get_spy_regime()
    sec_etf  = SECTOR_ETFS.get(ticker)
    sec_reg  = get_sector_regime(sec_etf) if sec_etf else {}
    dates    = [str(d)[:10] for d in df.index]
    reg_ok   = pd.Series([spy_reg.get(d, True) and sec_reg.get(d, True) for d in dates],
                         index=df.index, dtype=bool)
    vol_ok   = vol_spike_mask(df)
    earn_ok  = earnings_blackout_mask(ticker, df)
    entry_ok = reg_ok & vol_ok & earn_ok
    for v in variants.values():
        v["buy"] = v["buy"] & entry_ok

    # Quarterly expanding-window composite scores
    score_cache = {}
    last_score, last_bd = 0.0, {}
    for i in range(MIN_TRAIN, len(df)):
        if i == MIN_TRAIN or (i - MIN_TRAIN) % SCORE_UPDATE == 0:
            last_score, last_bd = composite_score(ticker, df.iloc[:i], use_live_data=False)
        score_cache[dates[i]] = (last_score, last_bd)

    # Build final per-date signal dicts
    buy_d, sell_d, score_d = {}, {}, {}
    for i in range(MIN_TRAIN, len(df)):
        d = dates[i]
        s_val, bd = score_cache[d]
        if s_val < score_threshold:
            continue

        _, vix_reg = vix_regime_at(d)
        thr = _VIX_THRESHOLDS[vix_reg]
        mom, rev = bd.get("momentum", 50), bd.get("mean_reversion", 50)

        strat = (
            "momentum breakout" if mom > thr["mom"] and rev < thr["rev"] else
            "mean reversion"    if rev > thr["rev"] and mom < thr["mom"] else
            "hybrid"
        )
        buy_d[d]   = bool(variants[strat]["buy"].iloc[i])
        sell_d[d]  = bool(variants[strat]["sell"].iloc[i])
        score_d[d] = s_val

    prices = {dates[i]: float(df["Close"].iloc[i]) for i in range(len(df))}
    return {"prices": prices, "buy": buy_d, "sell": sell_d, "scores": score_d}


def run_portfolio_backtest(tickers, starting_cash=100_000, max_positions=10,
                           score_threshold=60, stop_loss_pct=STOP_LOSS,
                           rsi_buy=45, rsi_sell=50, period="5y"):

    # ── Phase 1: Pre-compute per-ticker data ──────────────────────────────────
    print("Pre-computing signals (this takes ~2 minutes)...")
    ticker_info = {}
    for t in tickers:
        print(f"  {t}...", end="", flush=True)
        info = _prepare_ticker(t, rsi_buy, rsi_sell, score_threshold, period)
        if info:
            ticker_info[t] = info
            print(" OK")
        else:
            print(" skip")

    if not ticker_info:
        print("No tickers survived preparation.")
        return None

    # ── Phase 2: Common date range ────────────────────────────────────────────
    common_dates = sorted(set.intersection(*[set(v["prices"]) for v in ticker_info.values()]))
    print(f"\nSimulating {len(common_dates)} trading days across {len(ticker_info)} stocks")
    print(f"Capital: ${starting_cash:,.0f} | Max positions: {max_positions}\n")

    # SPY buy-and-hold benchmark
    spy_df    = fetch_and_save("SPY", period=period)
    spy_px    = {str(d)[:10]: float(row["Close"]) for d, row in spy_df.iterrows()}
    spy_start = spy_px.get(common_dates[0],  next(iter(spy_px.values())))
    spy_end   = spy_px.get(common_dates[-1], list(spy_px.values())[-1])
    spy_ret   = (spy_end - spy_start) / spy_start * 100

    # ── Phase 3: Day-by-day portfolio simulation ──────────────────────────────
    cash      = float(starting_cash)
    positions = {}   # ticker → {shares, entry_price, entry_date}
    daily_pv  = []
    trades    = []
    deployed_pct_history = []

    for date_str in common_dates:

        # Current portfolio value
        pos_val  = sum(
            positions[t]["shares"] * ticker_info[t]["prices"].get(date_str, positions[t]["entry_price"])
            for t in positions
        )
        port_val = cash + pos_val
        daily_pv.append(port_val)
        deployed_pct_history.append(pos_val / port_val * 100 if port_val > 0 else 0)

        # Exits: stop losses first, then sell signals
        for t in list(positions):
            price = ticker_info[t]["prices"].get(date_str)
            if price is None:
                continue
            entry   = positions[t]["entry_price"]
            pnl_pct = (price - entry) / entry
            is_stop = pnl_pct <= -stop_loss_pct
            is_sell = ticker_info[t]["sell"].get(date_str, False)

            if is_stop or is_sell:
                cash += positions[t]["shares"] * price * (1 - SLIPPAGE)
                trades.append({
                    "date": date_str, "ticker": t,
                    "action": "STOP" if is_stop else "SELL",
                    "price": price, "pnl_pct": round(pnl_pct * 100, 2),
                })
                del positions[t]

        # Entries: sort by score so strongest signals get capital first
        if len(positions) < max_positions:
            candidates = [
                (t, ticker_info[t]["scores"].get(date_str, 0))
                for t in ticker_info
                if t not in positions
                and ticker_info[t]["buy"].get(date_str, False)
                and ticker_info[t]["scores"].get(date_str, 0) >= score_threshold
                and ticker_info[t]["prices"].get(date_str) is not None
            ]
            candidates.sort(key=lambda x: x[1], reverse=True)

            for t, score in candidates:
                if len(positions) >= max_positions:
                    break
                price = ticker_info[t]["prices"][date_str]
                size  = _position_size(port_val, score)
                if size > cash or size < 1:
                    continue
                shares = size * (1 - SLIPPAGE) / price
                cash  -= size
                positions[t] = {"shares": shares, "entry_price": price, "entry_date": date_str}
                trades.append({
                    "date": date_str, "ticker": t, "action": "BUY",
                    "price": price, "size_usd": round(size, 2), "score": score,
                })

    # Liquidate any open positions at final price
    for t in list(positions):
        price = ticker_info[t]["prices"].get(common_dates[-1], positions[t]["entry_price"])
        cash += positions[t]["shares"] * price * (1 - SLIPPAGE)

    # ── Phase 4: Metrics ──────────────────────────────────────────────────────
    pv_series  = pd.Series(daily_pv, index=common_dates)
    daily_ret  = pv_series.pct_change().dropna()
    total_ret  = (pv_series.iloc[-1] - starting_cash) / starting_cash * 100
    sharpe     = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    max_dd     = ((pv_series - pv_series.cummax()) / pv_series.cummax()).min() * 100

    sell_trades = [t for t in trades if t["action"] in ("SELL", "STOP")]
    win_rate    = sum(1 for t in sell_trades if t.get("pnl_pct", 0) > 0) / len(sell_trades) * 100 if sell_trades else 0
    avg_deploy  = float(np.mean(deployed_pct_history))

    # Yearly breakdown
    yearly = {}
    for d, v in zip(common_dates, daily_pv):
        yr = d[:4]
        yearly.setdefault(yr, []).append(v)
    yearly_returns = {}
    yrs = sorted(yearly)
    for i, yr in enumerate(yrs):
        start = yearly[yrs[i-1]][-1] if i > 0 else starting_cash
        end   = yearly[yr][-1]
        yearly_returns[yr] = (end - start) / start * 100

    return {
        "total_return":    total_ret,
        "spy_return":      spy_ret,
        "alpha":           total_ret - spy_ret,
        "sharpe":          sharpe,
        "max_drawdown":    max_dd,
        "win_rate":        win_rate,
        "avg_deployed_pct": avg_deploy,
        "n_trades":        len(trades),
        "final_value":     pv_series.iloc[-1],
        "yearly_returns":  yearly_returns,
        "portfolio_values": pv_series,
        "trades":          trades,
    }
