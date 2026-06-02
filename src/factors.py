import numpy as np
import pandas as pd


def compute_momentum_matrix(closes: pd.DataFrame,
                             lookback: int = 252,
                             skip: int = 21) -> pd.DataFrame:
    """
    Jegadeesh-Titman 12-1 month momentum.

    For each date t:  (close[t - skip] / close[t - lookback]) - 1

    The 1-month skip removes the short-term reversal effect that would
    otherwise contaminate a naive 12-month return.  This is the standard
    specification from Jegadeesh & Titman (1993) and all major replications.

    Returns DataFrame[dates × tickers]. NaN where insufficient history.
    """
    return (closes.shift(skip) / closes.shift(lookback)) - 1


def compute_quality_matrix(closes: pd.DataFrame,
                            hi_window: int = 252,
                            vol_window: int = 63) -> pd.DataFrame:
    """
    Price-based quality proxy — no financial-statement data required.

    Two components:

    A) 52-week high ratio:  close[t] / max(close[t-252 : t])
       Stocks trading near their 52-week high embed strong fundamental
       signals per George & Hwang (2004).  Range: (0, 1].

    B) Negative realized volatility:  -std(daily_returns, 63d)
       The low-volatility premium (Frazzini & Pedersen 2014) is closely
       related to quality/stability.  Lower vol → higher quality score.
       Negated so direction is consistent with A.

    Components are combined BEFORE cross-sectional z-scoring (done in
    compute_combined_scores) so each contributes equally to the final signal.

    NOTE: this is NOT gross profitability (Novy-Marx 2013).  That factor
    requires point-in-time financial statement data not available via
    yfinance.  This proxy captures correlated quality characteristics
    through price dynamics only, with zero look-ahead bias.
    """
    hi_ratio = closes / closes.rolling(hi_window).max()   # (0, 1]
    neg_vol  = -closes.pct_change().rolling(vol_window).std()
    return (hi_ratio + neg_vol) / 2


def _zscore_rows(df: pd.DataFrame, winsor: float = 3.0) -> pd.DataFrame:
    """Cross-sectional z-score each date (row), then winsorise at ±winsor."""
    mean = df.mean(axis=1)
    std  = df.std(axis=1).replace(0, np.nan)
    z    = df.sub(mean, axis=0).div(std, axis=0)
    return z.clip(-winsor, winsor)


def compute_combined_scores(momentum: pd.DataFrame,
                             quality: pd.DataFrame,
                             mom_weight: float = 0.6,
                             qual_weight: float = 0.4) -> pd.DataFrame:
    """
    Cross-sectional z-score each factor independently, then blend.

    Momentum gets 60%: it is the primary documented anomaly with the
    most robust out-of-sample replication record.

    Quality gets 40%: reduces exposure to momentum crashes (high-momentum
    stocks often have fragile fundamentals) and adds diversification.

    Where a ticker has no quality score on a given date (NaN), it receives
    a quality z-score of 0 (neutral) and momentum is rescaled to full weight.
    """
    mom_z  = _zscore_rows(momentum)
    qual_z = _zscore_rows(quality)

    # Effective weights per cell: if quality is NaN treat it as neutral (0)
    has_qual = qual_z.notna().astype(float)
    combined = (mom_weight  * mom_z.fillna(0)
              + qual_weight * qual_z.fillna(0))

    # Where BOTH are NaN → NaN (ticker has no valid signal at all)
    both_nan = momentum.isna() & quality.isna()
    combined[both_nan] = np.nan

    return combined


def select_portfolio(scores: pd.Series, n: int = 30,
                     min_valid: int = 15) -> list:
    """
    Top-N tickers by combined score on a single date.
    Returns [] if fewer than min_valid tickers have valid scores.
    """
    valid = scores.dropna()
    if len(valid) < min_valid:
        return []
    return valid.nlargest(n).index.tolist()
