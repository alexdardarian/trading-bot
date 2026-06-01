import numpy as np
from src.factors.momentum import momentum_score
from src.factors.volume import volume_score
from src.factors.mean_reversion import mean_reversion_score
from src.factors.earnings import earnings_score
from src.factors.relative_strength import relative_strength_score
from src.factors.short_interest import short_interest_score

WEIGHTS = {
    "momentum":          0.25,
    "volume":            0.10,
    "mean_reversion":    0.10,
    "earnings":          0.20,
    "relative_strength": 0.25,
    "short_interest":    0.10,
}

def volatility_filter(df, max_annual_vol=0.65):
    daily_returns = df["Close"].pct_change().dropna()
    annual_vol = daily_returns.std() * (252 ** 0.5)
    return annual_vol <= max_annual_vol

def composite_score(ticker, df, use_live_data=True):
    """
    use_live_data=False disables earnings and short_interest, which both
    use current API data and would introduce look-ahead bias in backtests.
    relative_strength uses historical ETF data and is always enabled.
    """
    if not volatility_filter(df):
        return 0, {k: 0 for k in WEIGHTS}

    scores = {
        "momentum":          momentum_score(df),
        "volume":            volume_score(df),
        "mean_reversion":    mean_reversion_score(df),
        "earnings":          earnings_score(ticker)       if use_live_data else 50.0,
        "relative_strength": relative_strength_score(ticker, df),
        "short_interest":    short_interest_score(ticker) if use_live_data else 50.0,
    }
    # Sanitize — a NaN from any factor would poison the composite
    scores = {k: (float(v) if not np.isnan(v) else 50.0) for k, v in scores.items()}
    total = sum(scores[k] * WEIGHTS[k] for k in scores)
    return (float(total) if not np.isnan(total) else 0.0), scores
