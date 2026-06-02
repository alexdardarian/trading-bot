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

MODES = {
    "conservative": {
        "score_threshold":  60,
        "use_spy_filter":   True,
        "use_sector_filter":True,
        "use_vol_filter":   True,
        "trailing_stop_pct":None,
        "stop_loss_pct":    0.03,
        "size_brackets":    (0.08, 0.10, 0.12),
    },
    "aggressive": {
        "score_threshold":  55,
        "use_spy_filter":   False,
        "use_sector_filter":False,
        "use_vol_filter":   False,
        "trailing_stop_pct":0.15,
        "stop_loss_pct":    0.15,
        "size_brackets":    (0.10, 0.12, 0.15),
    },
}


def _dynamic_trailing_stop(price, high_watermark, entry_price, base_stop):
    """Widen trailing stop as gains accumulate so big winners aren't shaken out."""
    pnl_pct    = (price - entry_price) / entry_price
    trail_drop = (price - high_watermark) / high_watermark
    if pnl_pct >= 0.75:
        effective = base_stop * 3.0   # 45% if base is 15%
    elif pnl_pct >= 0.40:
        effective = base_stop * 2.0   # 30%
    elif pnl_pct >= 0.20:
        effective = base_stop * 1.5   # 22.5%
    else:
        effective = base_stop
    return trail_drop <= -effective


def _score_weighted_alloc(scored_tickers, total_cash):
    """Allocate capital proportionally to composite score."""
    total = sum(s for _, s in scored_tickers)
    if total == 0:
        n = len(scored_tickers)
        return {t: total_cash / n for t, _ in scored_tickers}
    return {t: total_cash * s / total for t, s in scored_tickers}


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

    dates    = [str(d)[:10] for d in df.index]
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

    entry_ok = entry_ok & earnings_blackout_mask(ticker, df)

    for v in variants.values():
        v["buy"] = v["buy"] & entry_ok

    score_cache = {}
    last_score, last_bd = 0.0, {}
    for i in range(MIN_TRAIN, len(df)):
        if i == MIN_TRAIN or (i - MIN_TRAIN) % SCORE_UPDATE == 0:
            last_score, last_bd = composite_score(ticker, df.iloc[:i], use_live_data=False)
        score_cache[dates[i]] = (last_score, last_bd)

    pead_raw    = earnings_momentum_mask(ticker, df, beat_threshold=0.05,
                                         pead_days=90, entry_delay=2)
    pead_signal = pead_raw & entry_ok

    buy_d, sell_d, score_d = {}, {}, {}
    for i in range(MIN_TRAIN, len(df)):
        d = dates[i]
        s_val, bd = score_cache[d]

        _, vix_reg = vix_regime_at(d)
        thr = _VIX_THRESHOLDS[vix_reg]
        mom, rev = bd.get("momentum", 50), bd.get("mean_reversion", 50)
        strat = (
            "momentum breakout" if mom > thr["mom"] and rev < thr["rev"] else
            "mean reversion"    if rev > thr["rev"] and mom < thr["mom"] else
            "hybrid"
        )

        sell_d[d] = bool(variants[strat]["sell"].iloc[i])

        regular_buy = bool(variants[strat]["buy"].iloc[i]) and s_val >= score_threshold
        pead_buy    = bool(pead_signal.iloc[i]) and s_val >= 45

        if regular_buy or pead_buy:
            buy_d[d]   = True
            score_d[d] = s_val if regular_buy else 65

    prices     = {dates[i]: float(df["Close"].iloc[i]) for i in range(len(df))}
    raw_scores = {d: s for d, (s, _) in score_cache.items()}
    return {"prices": prices, "buy": buy_d, "sell": sell_d,
            "scores": score_d, "raw_scores": raw_scores}


def _benchmarks(ticker_info, common_dates, period="5y"):
    spy_df    = fetch_and_save("SPY", period=period)
    spy_px    = {str(d)[:10]: float(row["Close"]) for d, row in spy_df.iterrows()}
    spy_ret   = (spy_px.get(common_dates[-1], list(spy_px.values())[-1]) -
                 spy_px.get(common_dates[0],  next(iter(spy_px.values())))) / \
                spy_px.get(common_dates[0], next(iter(spy_px.values()))) * 100

    universe_returns = []
    for info in ticker_info.values():
        p0 = info["prices"].get(common_dates[0])
        p1 = info["prices"].get(common_dates[-1])
        if p0 and p1 and p0 > 0:
            universe_returns.append((p1 - p0) / p0 * 100)
    universe_bh = float(np.mean(universe_returns)) if universe_returns else spy_ret
    return spy_ret, universe_bh


def _metrics(daily_pv, common_dates, starting_cash, trades, deployed_h, spy_ret, universe_bh):
    pv_series = pd.Series(daily_pv, index=common_dates)
    daily_ret = pv_series.pct_change().dropna()
    total_ret = (pv_series.iloc[-1] - starting_cash) / starting_cash * 100
    sharpe    = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    max_dd    = ((pv_series - pv_series.cummax()) / pv_series.cummax()).min() * 100

    exits    = [t for t in trades if t["action"] in ("SELL","STOP","TRAIL_STOP","CORE_SWAP")]
    win_rate = sum(1 for t in exits if t.get("pnl_pct", 0) > 0) / len(exits) * 100 if exits else 0
    avg_dep  = float(np.mean(deployed_h))

    yearly = {}
    for d, v in zip(common_dates, daily_pv):
        yearly.setdefault(d[:4], []).append(v)
    yearly_returns, yrs = {}, sorted(yearly)
    for i, yr in enumerate(yrs):
        start = yearly[yrs[i-1]][-1] if i > 0 else starting_cash
        yearly_returns[yr] = (yearly[yr][-1] - start) / start * 100

    return {
        "total_return":      total_ret,
        "spy_return":        spy_ret,
        "universe_bh":       universe_bh,
        "alpha_vs_spy":      total_ret - spy_ret,
        "alpha_vs_universe": total_ret - universe_bh,
        "sharpe":            sharpe,
        "max_drawdown":      max_dd,
        "win_rate":          win_rate,
        "avg_deployed_pct":  avg_dep,
        "n_trades":          len(trades),
        "final_value":       pv_series.iloc[-1],
        "yearly_returns":    yearly_returns,
        "portfolio_values":  pv_series,
        "trades":            trades,
    }


# ── Active-only portfolio (original approach) ─────────────────────────────────

def run_portfolio_backtest(tickers, mode="aggressive", starting_cash=100_000,
                           max_positions=10, rsi_buy=45, rsi_sell=50, period="5y"):

    cfg = MODES[mode]
    score_threshold   = cfg["score_threshold"]
    trailing_stop     = cfg["trailing_stop_pct"]
    stop_loss_pct     = cfg["stop_loss_pct"]
    size_brackets     = cfg["size_brackets"]
    use_spy_filter    = cfg["use_spy_filter"]
    use_sector_filter = cfg["use_sector_filter"]
    use_vol_filter    = cfg["use_vol_filter"]

    print(f"Mode: {mode.upper()} | Pre-computing signals...")
    ticker_info = {}
    for t in tickers:
        print(f"  {t}...", end="", flush=True)
        info = _prepare_ticker(t, rsi_buy, rsi_sell, score_threshold,
                               use_spy_filter, use_sector_filter, use_vol_filter, period)
        if info:
            ticker_info[t] = info
            print(" OK")
        else:
            print(" skip")

    if not ticker_info:
        return None

    common_dates = sorted(set.intersection(*[set(v["prices"]) for v in ticker_info.values()]))
    spy_ret, universe_bh = _benchmarks(ticker_info, common_dates, period)

    print(f"\nSimulating {len(common_dates)} days | {len(ticker_info)} stocks | ${starting_cash:,.0f}")

    cash = float(starting_cash)
    positions, daily_pv, trades, deployed_h = {}, [], [], []

    for date_str in common_dates:
        pos_val  = sum(positions[t]["shares"] *
                       ticker_info[t]["prices"].get(date_str, positions[t]["entry_price"])
                       for t in positions)
        port_val = cash + pos_val
        daily_pv.append(port_val)
        deployed_h.append(pos_val / port_val * 100 if port_val > 0 else 0)

        for t in list(positions):
            price = ticker_info[t]["prices"].get(date_str)
            if price is None:
                continue
            pos   = positions[t]
            entry = pos["entry_price"]
            if price > pos["high_watermark"]:
                pos["high_watermark"] = price
            pnl_pct = (price - entry) / entry
            if trailing_stop:
                is_stop = _dynamic_trailing_stop(price, pos["high_watermark"], entry, trailing_stop)
            else:
                is_stop = pnl_pct <= -stop_loss_pct
            raw_score = ticker_info[t]["raw_scores"].get(date_str, 0)
            is_sell = ticker_info[t]["sell"].get(date_str, False) and raw_score < score_threshold
            if is_stop or is_sell:
                cash += pos["shares"] * price * (1 - SLIPPAGE)
                trades.append({"date": date_str, "ticker": t,
                                "action": "TRAIL_STOP" if (is_stop and trailing_stop) else
                                          "STOP" if is_stop else "SELL",
                                "price": price, "pnl_pct": round(pnl_pct * 100, 2),
                                "peak_gain": round((pos["high_watermark"] - entry) / entry * 100, 2)})
                del positions[t]

        if len(positions) < max_positions:
            candidates = sorted(
                [(t, ticker_info[t]["scores"].get(date_str, 0)) for t in ticker_info
                 if t not in positions
                 and ticker_info[t]["buy"].get(date_str, False)
                 and ticker_info[t]["scores"].get(date_str, 0) >= score_threshold
                 and ticker_info[t]["prices"].get(date_str) is not None],
                key=lambda x: x[1], reverse=True
            )
            for t, score in candidates:
                if len(positions) >= max_positions:
                    break
                price = ticker_info[t]["prices"][date_str]
                size  = _position_size(port_val, score, size_brackets)
                if size > cash or size < 1:
                    continue
                shares = size * (1 - SLIPPAGE) / price
                cash  -= size
                positions[t] = {"shares": shares, "entry_price": price,
                                 "entry_date": date_str, "high_watermark": price}
                trades.append({"date": date_str, "ticker": t, "action": "BUY",
                                "price": price, "size_usd": round(size, 2), "score": score})

    for t in list(positions):
        price = ticker_info[t]["prices"].get(common_dates[-1], positions[t]["entry_price"])
        cash += positions[t]["shares"] * price * (1 - SLIPPAGE)

    result = _metrics(daily_pv, common_dates, starting_cash, trades, deployed_h, spy_ret, universe_bh)
    result["mode"] = mode
    return result


# ── Core-satellite portfolio ───────────────────────────────────────────────────

def run_core_satellite_backtest(tickers, starting_cash=100_000,
                                n_core=10, core_fraction=0.60,
                                max_satellite_positions=5,
                                rebalance_days=63,
                                core_catastrophic_stop=0.40,
                                satellite_trailing_stop=0.15,
                                score_threshold=55,
                                rsi_buy=45, rsi_sell=50, period="5y"):
    """
    60% of capital buys the top-N scored stocks and holds them passively.
    This captures multi-year winners (NVDA, META) without being stopped out.

    40% of capital actively trades the remaining stocks using all signals.
    This generates incremental returns on top of the passive core.

    Core is rebalanced quarterly — stocks that fall out of the top N are
    swapped for the new entrants.
    """
    print(f"Mode: CORE-SATELLITE | Pre-computing signals...")
    ticker_info = {}
    for t in tickers:
        print(f"  {t}...", end="", flush=True)
        # Use aggressive settings for both core and satellite signal computation
        info = _prepare_ticker(t, rsi_buy, rsi_sell, score_threshold,
                               use_spy_filter=False, use_sector_filter=False,
                               use_vol_filter=False, period=period)
        if info:
            ticker_info[t] = info
            print(" OK")
        else:
            print(" skip")

    if not ticker_info:
        return None

    common_dates = sorted(set.intersection(*[set(v["prices"]) for v in ticker_info.values()]))
    spy_ret, universe_bh = _benchmarks(ticker_info, common_dates, period)

    satellite_fraction = 1.0 - core_fraction
    core_budget    = starting_cash * core_fraction
    sat_budget     = starting_cash * satellite_fraction

    print(f"\nSimulating {len(common_dates)} days | {len(ticker_info)} stocks | ${starting_cash:,.0f}")
    print(f"  Core: top {n_core} stocks, {core_fraction*100:.0f}% capital, rebalance every {rebalance_days} days")
    print(f"  Satellite: active signals, {satellite_fraction*100:.0f}% capital, "
          f"max {max_satellite_positions} positions, {satellite_trailing_stop*100:.0f}% trailing stop\n")

    # ── Portfolio state ──────────────────────────────────────────────────────
    core_positions = {}   # ticker → {shares, entry_price}
    core_cash      = core_budget
    sat_cash       = sat_budget
    sat_positions  = {}   # ticker → {shares, entry_price, high_watermark}
    current_core_tickers = set()
    daily_pv       = []
    trades         = []
    deployed_h     = []
    next_rebalance = None

    def select_core(date_str):
        """Top N tickers by raw score at this date."""
        scored = [(t, ticker_info[t]["raw_scores"].get(date_str, 0))
                  for t in ticker_info
                  if ticker_info[t]["prices"].get(date_str)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [t for t, s in scored[:n_core] if s > 0]

    for idx, date_str in enumerate(common_dates):

        # ── Portfolio value ──────────────────────────────────────────────────
        core_val = sum(core_positions[t]["shares"] *
                       ticker_info[t]["prices"].get(date_str, core_positions[t]["entry_price"])
                       for t in core_positions)
        sat_val  = sum(sat_positions[t]["shares"] *
                       ticker_info[t]["prices"].get(date_str, sat_positions[t]["entry_price"])
                       for t in sat_positions)
        port_val = core_cash + core_val + sat_cash + sat_val
        daily_pv.append(port_val)
        deployed_h.append((core_val + sat_val) / port_val * 100 if port_val > 0 else 0)

        # ── Core: initialise on first qualifying day ─────────────────────────
        if not current_core_tickers and idx >= 0:
            top = select_core(date_str)
            if top:
                scored_top = [(t, ticker_info[t]["raw_scores"].get(date_str, 1)) for t in top]
                alloc = _score_weighted_alloc(scored_top, core_cash)
                for t in top:
                    price = ticker_info[t]["prices"].get(date_str)
                    amt = alloc[t]
                    if price and amt >= 1:
                        shares = amt * (1 - SLIPPAGE) / price
                        core_positions[t] = {"shares": shares, "entry_price": price}
                        core_cash -= amt
                        trades.append({"date": date_str, "ticker": t, "action": "CORE_BUY",
                                        "price": price, "size_usd": round(amt, 2)})
                current_core_tickers = set(core_positions.keys())
                next_rebalance = idx + rebalance_days
                print(f"  Core initialised ({date_str}): {sorted(current_core_tickers)}")

        # ── Core: quarterly rebalance ─────────────────────────────────────────
        elif next_rebalance and idx >= next_rebalance:
            new_top = set(select_core(date_str))
            dropped = current_core_tickers - new_top
            added   = new_top - current_core_tickers

            if dropped or added:
                for t in dropped:
                    price = ticker_info[t]["prices"].get(date_str, core_positions[t]["entry_price"])
                    proceeds = core_positions[t]["shares"] * price * (1 - SLIPPAGE)
                    pnl_pct  = (price - core_positions[t]["entry_price"]) / core_positions[t]["entry_price"]
                    core_cash += proceeds
                    trades.append({"date": date_str, "ticker": t, "action": "CORE_SWAP",
                                    "price": price, "pnl_pct": round(pnl_pct * 100, 2)})
                    del core_positions[t]

                if added:
                    scored_added = [(t, ticker_info[t]["raw_scores"].get(date_str, 1)) for t in added]
                    alloc = _score_weighted_alloc(scored_added, core_cash)
                    for t in added:
                        price = ticker_info[t]["prices"].get(date_str)
                        amt = alloc[t]
                        if price and amt >= 1:
                            shares = amt * (1 - SLIPPAGE) / price
                            core_positions[t] = {"shares": shares, "entry_price": price}
                            core_cash -= amt
                            trades.append({"date": date_str, "ticker": t, "action": "CORE_BUY",
                                            "price": price, "size_usd": round(amt, 2)})

                current_core_tickers = set(core_positions.keys())

            next_rebalance = idx + rebalance_days

        # ── Core: catastrophic stop only ─────────────────────────────────────
        for t in list(core_positions.keys()):
            price = ticker_info[t]["prices"].get(date_str)
            if price is None:
                continue
            pnl_pct = (price - core_positions[t]["entry_price"]) / core_positions[t]["entry_price"]
            if pnl_pct <= -core_catastrophic_stop:
                proceeds = core_positions[t]["shares"] * price * (1 - SLIPPAGE)
                core_cash += proceeds
                trades.append({"date": date_str, "ticker": t, "action": "CORE_STOP",
                                "price": price, "pnl_pct": round(pnl_pct * 100, 2)})
                del core_positions[t]
                current_core_tickers.discard(t)

        # ── Satellite: exits ─────────────────────────────────────────────────
        for t in list(sat_positions.keys()):
            price = ticker_info[t]["prices"].get(date_str)
            if price is None:
                continue
            pos   = sat_positions[t]
            entry = pos["entry_price"]
            if price > pos["high_watermark"]:
                pos["high_watermark"] = price
            pnl_pct  = (price - entry) / entry
            is_stop  = _dynamic_trailing_stop(price, pos["high_watermark"], entry, satellite_trailing_stop)
            raw_score = ticker_info[t]["raw_scores"].get(date_str, 0)
            is_sell  = ticker_info[t]["sell"].get(date_str, False) and raw_score < score_threshold
            if is_stop or is_sell:
                sat_cash += pos["shares"] * price * (1 - SLIPPAGE)
                trades.append({"date": date_str, "ticker": t,
                                "action": "TRAIL_STOP" if is_stop else "SELL",
                                "price": price, "pnl_pct": round(pnl_pct * 100, 2),
                                "peak_gain": round((pos["high_watermark"] - entry) / entry * 100, 2)})
                del sat_positions[t]

        # ── Satellite: entries (non-core stocks only) ─────────────────────────
        if len(sat_positions) < max_satellite_positions:
            candidates = sorted(
                [(t, ticker_info[t]["scores"].get(date_str, 0))
                 for t in ticker_info
                 if t not in sat_positions
                 and t not in current_core_tickers          # don't duplicate core holdings
                 and ticker_info[t]["buy"].get(date_str, False)
                 and ticker_info[t]["scores"].get(date_str, 0) >= score_threshold
                 and ticker_info[t]["prices"].get(date_str) is not None],
                key=lambda x: x[1], reverse=True
            )
            for t, score in candidates:
                if len(sat_positions) >= max_satellite_positions:
                    break
                price = ticker_info[t]["prices"][date_str]
                # Size relative to total portfolio, capped by available satellite cash
                size = _position_size(port_val, score, (0.10, 0.12, 0.15))
                if size > sat_cash or size < 1:
                    continue
                shares = size * (1 - SLIPPAGE) / price
                sat_cash -= size
                sat_positions[t] = {"shares": shares, "entry_price": price,
                                     "entry_date": date_str, "high_watermark": price}
                trades.append({"date": date_str, "ticker": t, "action": "SAT_BUY",
                                "price": price, "size_usd": round(size, 2), "score": score})

    # Liquidate everything
    for t in list(core_positions.keys()):
        price = ticker_info[t]["prices"].get(common_dates[-1], core_positions[t]["entry_price"])
        core_cash += core_positions[t]["shares"] * price * (1 - SLIPPAGE)
    for t in list(sat_positions.keys()):
        price = ticker_info[t]["prices"].get(common_dates[-1], sat_positions[t]["entry_price"])
        sat_cash += sat_positions[t]["shares"] * price * (1 - SLIPPAGE)

    result = _metrics(daily_pv, common_dates, starting_cash, trades, deployed_h, spy_ret, universe_bh)
    result["mode"] = "core-satellite"
    return result
