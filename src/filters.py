import pandas as pd
import yfinance as yf

_earnings_cache = {}


def vol_spike_mask(df, spike_percentile=75, min_history=63):
    """
    Returns a boolean Series — True where it's safe to enter, False during
    volatility spikes.

    At each bar, compares the current 21-day realized vol against the 75th
    percentile of ALL historical vols for this stock up to that bar.
    If it's in the top 25% of how volatile this stock has ever been, something
    unusual is happening — earnings rumor, news event, squeeze, etc. Skip entry.

    Uses an expanding window so only past data informs the threshold.
    No look-ahead bias.
    """
    daily_ret = df["Close"].pct_change()
    rolling_vol = daily_ret.rolling(21).std()
    threshold = rolling_vol.expanding(min_periods=min_history).quantile(spike_percentile / 100)
    return (rolling_vol <= threshold).fillna(True)


def earnings_blackout_mask(ticker, df, days_before=5):
    """
    Returns a boolean Series — True where it's safe to enter, False within
    the earnings blackout window (days_before before + 1 day after each date).

    Earnings dates are publicly announced in advance, so using them is not
    look-ahead bias — a real trader would know about them too.

    Protects against the most common cause of overnight gap blowups: a stock
    moves 10-20% on earnings and the strategy is caught mid-position.
    """
    if ticker not in _earnings_cache:
        try:
            dates_df = yf.Ticker(ticker).earnings_dates
            if dates_df is not None and len(dates_df) > 0:
                _earnings_cache[ticker] = [str(d)[:10] for d in dates_df.index]
            else:
                _earnings_cache[ticker] = []
        except Exception:
            _earnings_cache[ticker] = []

    blackout = set()
    for date_str in _earnings_cache[ticker]:
        try:
            ts = pd.Timestamp(date_str)
            for offset in range(-days_before, 2):  # 5 before, day of, 1 after
                blackout.add(str(ts + pd.Timedelta(days=offset))[:10])
        except Exception:
            pass

    if not blackout:
        return pd.Series(True, index=df.index)

    return pd.Series(
        [str(d)[:10] not in blackout for d in df.index],
        index=df.index, dtype=bool
    )
