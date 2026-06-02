import numpy as np
import pandas as pd


def compute_target_weights(tickers: list, closes: pd.DataFrame,
                            date: pd.Timestamp,
                            vol_window: int = 21,
                            max_weight: float = 0.10) -> dict:
    """
    Inverse-volatility (risk-parity) weights, capped at max_weight per stock.

    Each stock's dollar allocation is proportional to 1 / realized_vol so that
    every position contributes roughly equal risk to the portfolio.  The 10%
    cap prevents any single name from dominating even if it has unusually low
    volatility (e.g., utility stocks in calm markets).

    Falls back to equal-weight if no valid volatility data.
    Returns dict {ticker: weight} where weights sum to 1.0.
    """
    hist = closes.loc[:date].iloc[-(vol_window + 1):]
    vols = hist.pct_change().std()

    valid = {t: vols[t] for t in tickers
             if t in vols.index and vols[t] > 0 and not np.isnan(vols[t])}

    if not valid:
        n = len(tickers)
        return {t: 1.0 / n for t in tickers}

    inv_vol = {t: 1.0 / v for t, v in valid.items()}
    total   = sum(inv_vol.values())
    weights = {t: iv / total for t, iv in inv_vol.items()}

    # Cap-and-renormalize loop: redistribute excess above max_weight
    for _ in range(20):
        excess   = sum(max(0.0, w - max_weight) for w in weights.values())
        if excess < 1e-8:
            break
        weights  = {t: min(w, max_weight) for t, w in weights.items()}
        uncapped = [t for t, w in weights.items() if w < max_weight]
        if not uncapped:
            break
        add = excess / len(uncapped)
        weights = {t: min(w + (add if t in uncapped else 0.0), max_weight)
                   for t, w in weights.items()}

    total = sum(weights.values())
    return {t: w / total for t, w in weights.items()}
