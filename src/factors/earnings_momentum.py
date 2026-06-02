import yfinance as yf
import pandas as pd

_cache = {}


def _get_beats(ticker, beat_threshold=0.05):
    """
    Returns sorted list of (date_str, surprise_pct) for quarters where the
    company beat EPS estimates by at least beat_threshold (0.05 = 5%).

    Earnings results are publicly announced — using historical actuals in a
    backtest is not look-ahead bias, the information existed at the time.
    """
    if ticker in _cache:
        return _cache[ticker]
    try:
        hist = yf.Ticker(ticker).earnings_history
        if hist is None or len(hist) == 0:
            _cache[ticker] = []
            return []
        beats = []
        for date, row in hist.iterrows():
            est = row.get("epsEstimate")
            act = row.get("epsActual")
            if est is None or act is None or float(est) == 0:
                continue
            surprise = (float(act) - float(est)) / abs(float(est))
            if surprise >= beat_threshold:
                beats.append((str(date)[:10], round(surprise, 4)))
        _cache[ticker] = sorted(beats)
        return _cache[ticker]
    except Exception:
        _cache[ticker] = []
        return []


def earnings_momentum_mask(ticker, df, beat_threshold=0.05, pead_days=90, entry_delay=2):
    """
    Post-Earnings Announcement Drift (PEAD) signal.

    Returns boolean Series — True on dates inside the drift window after a
    strong earnings beat.

    How it works:
      - Company beats EPS estimates by >= beat_threshold
      - entry_delay calendar days later, the PEAD window opens
      - The window stays open for pead_days calendar days (~1 quarter)
      - During this window the stock statistically keeps drifting upward

    entry_delay=2 skips the gap-open chaos on announcement day and gives the
    earnings_blackout filter time to clear.
    """
    beats = _get_beats(ticker, beat_threshold)
    if not beats:
        return pd.Series(False, index=df.index)

    active_dates = set()
    for earnings_date, _ in beats:
        try:
            ts = pd.Timestamp(earnings_date)
            start = ts + pd.Timedelta(days=entry_delay)
            end   = ts + pd.Timedelta(days=entry_delay + pead_days)
            day = start
            while day <= end:
                active_dates.add(str(day)[:10])
                day += pd.Timedelta(days=1)
        except Exception:
            pass

    return pd.Series(
        [str(d)[:10] in active_dates for d in df.index],
        index=df.index, dtype=bool
    )
