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
from src.factors.earnings_momentum import earnings_momentum_mask

SLIPPAGE     = 0.001
MIN_TRAIN    = 252
SCORE_UPDATE = 63

_VIX_THRESHOLDS = {
    "fear":        {"mom": 80, "rev": 55},
    "normal":      {"mom": 70, "rev": 70},
    "complacency": {"mom": 60, "rev": 80},
}

# ── Mode presets ──────────────────────────────────────────────────────────────
# Conservative: capital-preservation focus, aggressive filters, tight stops
# Aggressive:   fully deployed, trailing stops, fewer filters blocking entries
MODES = {
    "conservative": {
        "score_threshold":  60,
        "use_spy_filter":   True,
        "use_sector_filter":True,
        "use_vol_filter":   True,
        "trailing_stop_pct":None,   # use fixed stop instead
        "stop_loss_pct":    0.03,
        "size_brackets":    (0.08, 0.10, 0.12),  # (marginal, decent, strong)
    },
    "aggressive": {
        "score_threshold":  55,
        "use_spy_filter":   False,  # don't sit in cash during bear markets
        "use_sector_filter":False,  # individual stock can break out vs sector
        "use_vol_filter":   False,  # high vol = high opportunity for momentum
        "trailing_stop_pct":0.15,   # trail 15% from high watermark
        "stop_loss_pct":    0.15,   # hard floor before we ever made gains
        "size_brackets":    (0.10, 0.12, 0.15),  # bigger positions
    },
}


def _position_size(portfolio_value, score, brackets):
    s1, s2, s3 = brackets
    if score >= 80:
        return portfolio_value * s3
    elif score >= 70:
        return portfolio_value * s2
    return portfolio_value * s1


def _prepare_ticker(ticker, rsi_buy=45, rsi_sell=50, score_threshold=60,
                    use_spy_filter=True, use_sector_filter=True,
                    use_vol_filter=True, period="5y"):
    try:
        raw = fetch_and_save(ticker, period=period)
    except Exception:
        return None
    if len(raw) < MIN_TRAIN + SCORE_UPDATE:
        return None

    df = raw.copy()
    df = add_indicators(df)

    df_mom = add_momentum_signals(df.copy())
    df_rev = add_signals(df.copy(), rsi_buy=rsi_buy, rsi_sell=rsi_sell)
    df_hyb = df.copy()
    df_hyb["buy"]  = df_mom["buy"] | df_rev["buy"]
    df_hyb["sell"] = df_mom["sell"] & df_rev["sell"]
    variants = {"momentum breakout": df_mom, "mean reversion": df_rev, "hybrid": df_hyb}

    # Build entry filter — each component optional based on mode
    dates = [str(d)[:10] for d in df.index]
    entry_ok = pd.Series(True, index=df.index)

    if use_spy_filter or use_sector_filter:
        spy_reg = get_spy_regime()
        sec_etf = SECTOR_ETFS.get(ticker)
        sec_reg = get_sector_regime(sec_etf) if (use_sector_filter and sec_etf) else {}
        regime_mask = pd.Series(
            [(spy_reg.get(d, True) if use_spy_filter else True) and
             (sec_reg.get(d, True) if use_sector_filter else True)
             for d in dates],
            index=df.index, dtype=bool
        )
        entry_ok = entry_ok & regime_mask

    if use_vol_filter:
        entry_ok = entry_ok & vol_spike_mask(df)

    # Earnings blackout always on — binary event risk regardless of mode
    entry_ok = entry_ok & earnings_blackout_mask(ticker, df)

    for v in variants.values():
        v["buy"] = v["buy"] & entry_ok

    # Quarterly expanding-window scores
    score_cache = {}
    last_score, last_bd = 0.0, {}
    for i in range(MIN_TRAIN, len(df)):
        if i == MIN_TRAIN or (i - MIN_TRAIN) % SCORE_UPDATE == 0:
            last_score, last_bd = composite_score(ticker, df.iloc[:i], use_live_data=False)
        score_cache[dates[i]] = (last_score, last_bd)

    # PEAD signal — strong earnings beats create a 90-day drift window
    # entry_delay=2 skips the gap-open chaos right after announcement
    pead_raw     = earnings_momentum_mask(ticker, df, beat_threshold=0.05,
                                          pead_days=90, entry_delay=2)
    pead_signal  = pead_raw & entry_ok   # still apply regime/earnings filters

    buy_d, sell_d, score_d = {}, {}, {}
    for i in range(MIN_TRAIN, len(df)):
        d = dates[i]
        s_val, bd = score_cache[d]

        # Routing — always compute so sell signals work even when score is low
        _, vix_reg = vix_regime_at(d)
        thr = _VIX_THRESHOLDS[vix_reg]
        mom, rev = bd.get("momentum", 50), bd.get("mean_reversion", 50)
        strat = (
            "momentum breakout" if mom > thr["mom"] and rev < thr["rev"] else
            "mean reversion"    if rev > thr["rev"] and mom < thr["mom"] else
            "hybrid"
        )

        # Sell signal set for ALL dates past min_train — needed to exit existing positions
        # even when the stock's composite score has temporarily dropped.
        sell_d[d] = bool(variants[strat]["sell"].iloc[i])

        # Buy signal: regular technical (score >= threshold) OR PEAD (score >= 45 minimum)
        regular_buy = bool(variants[strat]["buy"].iloc[i]) and s_val >= score_threshold
        pead_buy    = bool(pead_signal.iloc[i]) and s_val >= 45

        if regular_buy or pead_buy:
            buy_d[d]   = True
            score_d[d] = s_val if regular_buy else 65  # PEAD entries get default score 65

    prices = {dates[i]: float(df["Close"].iloc[i]) for i in range(len(df))}
    return {"prices": prices, "buy": buy_d, "sell": sell_d, "scores": score_d}


def run_portfolio_backtest(tickers, mode="aggressive", starting_cash=100_000,
                           max_positions=10, rsi_buy=45, rsi_sell=50, period="5y"):

    cfg = MODES[mode]
    score_threshold  = cfg["score_threshold"]
    trailing_stop    = cfg["trailing_stop_pct"]
    stop_loss_pct    = cfg["stop_loss_pct"]
    size_brackets    = cfg["size_brackets"]
    use_spy_filter   = cfg["use_spy_filter"]
    use_sector_filter= cfg["use_sector_filter"]
    use_vol_filter   = cfg["use_vol_filter"]

    # ── Phase 1: Pre-compute ──────────────────────────────────────────────────
    print(f"Mode: {mode.upper()} | Pre-computing signals...")
    ticker_info = {}
    for t in tickers:
        print(f"  {t}...", end="", flush=True)
        info = _prepare_ticker(
            t, rsi_buy, rsi_sell, score_threshold,
            use_spy_filter, use_sector_filter, use_vol_filter, period
        )
        if info:
            ticker_info[t] = info
            print(" OK")
        else:
            print(" skip")

    if not ticker_info:
        return None

    # ── Phase 2: Align dates ──────────────────────────────────────────────────
    common_dates = sorted(set.intersection(*[set(v["prices"]) for v in ticker_info.values()]))
    print(f"\nSimulating {len(common_dates)} trading days | {len(ticker_info)} stocks | ${starting_cash:,.0f}")
    if trailing_stop:
        print(f"  Trailing stop: {trailing_stop*100:.0f}% from peak | Score threshold: {score_threshold}")
    else:
        print(f"  Fixed stop: {stop_loss_pct*100:.0f}% | Score threshold: {score_threshold}")

    spy_df    = fetch_and_save("SPY", period=period)
    spy_px    = {str(d)[:10]: float(row["Close"]) for d, row in spy_df.iterrows()}
    spy_start = spy_px.get(common_dates[0],  next(iter(spy_px.values())))
    spy_end   = spy_px.get(common_dates[-1], list(spy_px.values())[-1])
    spy_ret   = (spy_end - spy_start) / spy_start * 100

    # ── Phase 3: Simulate ─────────────────────────────────────────────────────
    cash       = float(starting_cash)
    positions  = {}
    daily_pv   = []
    trades     = []
    deployed_h = []

    for date_str in common_dates:
        pos_val  = sum(
            positions[t]["shares"] * ticker_info[t]["prices"].get(date_str, positions[t]["entry_price"])
            for t in positions
        )
        port_val = cash + pos_val
        daily_pv.append(port_val)
        deployed_h.append(pos_val / port_val * 100 if port_val > 0 else 0)

        # Exits
        for t in list(positions):
            price = ticker_info[t]["prices"].get(date_str)
            if price is None:
                continue

            pos = positions[t]
            entry = pos["entry_price"]

            # Update high watermark for trailing stop
            if price > pos["high_watermark"]:
                pos["high_watermark"] = price

            pnl_pct = (price - entry) / entry

            if trailing_stop:
                trail_drop = (price - pos["high_watermark"]) / pos["high_watermark"]
                is_stop    = trail_drop <= -trailing_stop
            else:
                is_stop = pnl_pct <= -stop_loss_pct

            is_sell = ticker_info[t]["sell"].get(date_str, False)

            if is_stop or is_sell:
                cash += pos["shares"] * price * (1 - SLIPPAGE)
                trades.append({
                    "date": date_str, "ticker": t,
                    "action": "TRAIL_STOP" if (is_stop and trailing_stop) else
                              "STOP"       if is_stop else "SELL",
                    "price": price, "pnl_pct": round(pnl_pct * 100, 2),
                    "peak_gain": round((pos["high_watermark"] - entry) / entry * 100, 2),
                })
                del positions[t]

        # Entries — best score first
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
                size  = _position_size(port_val, score, size_brackets)
                if size > cash or size < 1:
                    continue
                shares = size * (1 - SLIPPAGE) / price
                cash  -= size
                positions[t] = {
                    "shares":         shares,
                    "entry_price":    price,
                    "entry_date":     date_str,
                    "high_watermark": price,
                }
                trades.append({
                    "date": date_str, "ticker": t, "action": "BUY",
                    "price": price, "size_usd": round(size, 2), "score": score,
                })

    # Liquidate remaining
    for t in list(positions):
        price = ticker_info[t]["prices"].get(common_dates[-1], positions[t]["entry_price"])
        cash += positions[t]["shares"] * price * (1 - SLIPPAGE)

    # ── Phase 4: Metrics ──────────────────────────────────────────────────────
    pv_series = pd.Series(daily_pv, index=common_dates)
    daily_ret = pv_series.pct_change().dropna()
    total_ret = (pv_series.iloc[-1] - starting_cash) / starting_cash * 100
    sharpe    = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    max_dd    = ((pv_series - pv_series.cummax()) / pv_series.cummax()).min() * 100

    exits     = [t for t in trades if t["action"] in ("SELL","STOP","TRAIL_STOP")]
    win_rate  = sum(1 for t in exits if t.get("pnl_pct", 0) > 0) / len(exits) * 100 if exits else 0
    avg_dep   = float(np.mean(deployed_h))

    yearly = {}
    for d, v in zip(common_dates, daily_pv):
        yearly.setdefault(d[:4], []).append(v)
    yearly_returns = {}
    yrs = sorted(yearly)
    for i, yr in enumerate(yrs):
        start = yearly[yrs[i-1]][-1] if i > 0 else starting_cash
        yearly_returns[yr] = (yearly[yr][-1] - start) / start * 100

    return {
        "mode":            mode,
        "total_return":    total_ret,
        "spy_return":      spy_ret,
        "alpha":           total_ret - spy_ret,
        "sharpe":          sharpe,
        "max_drawdown":    max_dd,
        "win_rate":        win_rate,
        "avg_deployed_pct":avg_dep,
        "n_trades":        len(trades),
        "final_value":     pv_series.iloc[-1],
        "yearly_returns":  yearly_returns,
        "portfolio_values":pv_series,
        "trades":          trades,
    }
