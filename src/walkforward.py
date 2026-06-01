import pandas as pd
import numpy as np
from src.indicators import add_indicators
from src.signals import add_signals, add_momentum_signals
from src.factors.scorer import composite_score
from src.factors.vix_regime import vix_regime_at
from src.factors.market_regime import get_spy_regime, get_sector_regime
from src.factors.relative_strength import SECTOR_ETFS
from src.filters import vol_spike_mask, earnings_blackout_mask

SLIPPAGE = 0.001  # 0.1% per trade (spread + market impact)

# VIX-adjusted routing thresholds.
# In fear regimes momentum strategies overshoot and mean reversion is more reliable.
# In calm regimes trends persist and momentum strategies outperform.
_VIX_THRESHOLDS = {
    "fear":        {"mom": 80, "rev": 55},  # hard to be momentum, easy to be mean-reversion
    "normal":      {"mom": 70, "rev": 70},
    "complacency": {"mom": 60, "rev": 80},  # easy to be momentum, hard to be mean-reversion
}


def walk_forward_backtest(df, ticker, min_train=252, test_size=63,
                          starting_cash=10000, rsi_buy=45, rsi_sell=50,
                          score_threshold=60):
    df = df.copy()
    df = add_indicators(df)

    if len(df) < min_train + test_size:
        print(f"  SKIPPED — insufficient data ({len(df)} bars, need {min_train + test_size})")
        return None

    # Pre-compute all signal variants once.
    # Indicators (RSI, MACD, MA50, MA200) are backward-looking — no look-ahead bias.
    df_momentum = add_momentum_signals(df.copy())
    df_reversion = add_signals(df.copy(), rsi_buy=rsi_buy, rsi_sell=rsi_sell)
    df_hybrid = df.copy()
    df_hybrid["buy"] = df_momentum["buy"] | df_reversion["buy"]
    df_hybrid["sell"] = df_momentum["sell"] & df_reversion["sell"]

    signal_dfs = {
        "momentum breakout": df_momentum,
        "mean reversion":    df_reversion,
        "hybrid":            df_hybrid,
    }

    # Build regime masks (vectorized — no per-row loops).
    # Buys are suppressed on dates where the broad market OR the stock's sector
    # is in a downtrend. Sells are never suppressed — we always want to be able to exit.
    spy_regime    = get_spy_regime()
    sector_etf    = SECTOR_ETFS.get(ticker)
    sector_regime = get_sector_regime(sector_etf) if sector_etf else {}

    date_strs = [str(d)[:10] for d in df.index]
    regime_ok = pd.Series(
        [spy_regime.get(d, True) and sector_regime.get(d, True) for d in date_strs],
        index=df.index, dtype=bool
    )

    # Entry filters — computed once on full df, applied to all strategy variants
    vol_ok      = vol_spike_mask(df)
    earnings_ok = earnings_blackout_mask(ticker, df)
    entry_ok    = regime_ok & vol_ok & earnings_ok

    for name in list(signal_dfs.keys()):
        sig = signal_dfs[name].copy()
        sig["buy"] = sig["buy"] & entry_ok
        signal_dfs[name] = sig

    folds = []
    fold_start = min_train

    while fold_start + test_size <= len(df):
        train_slice = df.iloc[:fold_start]
        fold_score, breakdown = composite_score(ticker, train_slice, use_live_data=False)

        if fold_score < score_threshold:
            fold_start += test_size
            continue

        momentum  = breakdown["momentum"]
        reversion = breakdown["mean_reversion"]

        # Route strategy based on factor scores AND current VIX regime.
        # VIX at the start of the test period is the "current conditions" signal.
        test_start_date = str(df.index[fold_start])[:10]
        vix_level, vix_regime = vix_regime_at(test_start_date)
        thr = _VIX_THRESHOLDS[vix_regime]

        if momentum > thr["mom"] and reversion < thr["rev"]:
            strategy = "momentum breakout"
        elif reversion > thr["rev"] and momentum < thr["mom"]:
            strategy = "mean reversion"
        else:
            strategy = "hybrid"

        test_slice = signal_dfs[strategy].iloc[fold_start:fold_start + test_size]

        fold_result = run_backtest(test_slice, starting_cash)
        bh = ((test_slice["Close"].iloc[-1] - test_slice["Close"].iloc[0])
              / test_slice["Close"].iloc[0]) * 100
        fold_result["buy_hold_return"] = bh
        fold_result["alpha"]    = fold_result["returns"] - bh
        fold_result["strategy"] = strategy
        fold_result["score"]    = fold_score
        fold_result["breakdown"] = breakdown
        fold_result["train_end"] = str(train_slice.index[-1])[:10]

        n = len(folds) + 1
        print(f"  Fold {n}: {str(test_slice.index[0])[:10]}→{str(test_slice.index[-1])[:10]} "
              f"| {strategy} | vix:{vix_level:.0f}({vix_regime[0]}) | score:{fold_score:.0f} "
              f"| return:{fold_result['returns']:.1f}% bh:{bh:.1f}%")

        folds.append(fold_result)
        fold_start += test_size

    if not folds:
        print(f"  SKIPPED — all folds scored below threshold {score_threshold}")
        return None

    bd = folds[0]["breakdown"]
    print(f"\n  Train period (first fold): {str(df.index[0])[:10]} → {folds[0]['train_end']}")
    print(f"  Score: {folds[0]['score']:.0f}/100 "
          f"| momentum:{bd['momentum']:.0f} "
          f"volume:{bd['volume']:.0f} "
          f"reversion:{bd['mean_reversion']:.0f} "
          f"rel_strength:{bd['relative_strength']:.0f} "
          f"| earnings/short_interest: N/A (live data disabled)")

    return {
        "returns":         np.mean([f["returns"] for f in folds]),
        "buy_hold_return": np.mean([f["buy_hold_return"] for f in folds]),
        "alpha":           np.mean([f["alpha"] for f in folds]),
        "sharpe":          np.mean([f["sharpe"] for f in folds]),
        "max_drawdown":    min(f["max_drawdown"] for f in folds),
        "trades":          [t for f in folds for t in f["trades"]],
        "strategy":        folds[0]["strategy"],
        "score":           folds[0]["score"],
        "n_folds":         len(folds),
    }


def run_backtest(df, starting_cash=10000):
    cash = starting_cash
    shares = 0
    trades = []
    portfolio_values = []
    pending_buy  = False
    pending_sell = False

    for date, row in df.iterrows():
        price = row["Close"]

        # Execute orders queued from PREVIOUS bar's signal.
        # Daily bars: the 2-consecutive-close sell signal is already well-confirmed,
        # so a full exit is correct here. Staged exits are reserved for the live bot
        # which scans every 10 minutes and needs to filter intraday noise.
        if pending_buy and cash > 0 and shares == 0:
            shares = (cash * (1 - SLIPPAGE)) / price
            cash = 0
            trades.append({"date": date, "action": "BUY", "price": price})
            pending_buy = False
        elif pending_sell and shares > 0:
            cash += shares * price * (1 - SLIPPAGE)
            trades.append({"date": date, "action": "SELL", "price": price, "value": cash})
            shares = 0
            pending_sell = False

        portfolio_values.append(cash + shares * price)

        if row.get("sell", False) and shares > 0:
            pending_sell = True
            pending_buy  = False
        elif row.get("buy", False) and shares == 0:
            pending_buy  = True
            pending_sell = False

    final_value = cash if shares == 0 else shares * df["Close"].iloc[-1] * (1 - SLIPPAGE)
    returns = ((final_value - starting_cash) / starting_cash) * 100

    portfolio_series = pd.Series(portfolio_values)
    daily_returns = portfolio_series.pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0

    rolling_max = portfolio_series.cummax()
    drawdown = (portfolio_series - rolling_max) / rolling_max
    max_drawdown = drawdown.min() * 100

    return {
        "final_value":      final_value,
        "returns":          returns,
        "trades":           trades,
        "sharpe":           sharpe,
        "max_drawdown":     max_drawdown,
        "portfolio_values": portfolio_values,
    }
