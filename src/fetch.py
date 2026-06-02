import os
import time
import numpy as np
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_DIR     = "data/v2"
MAX_AGE_DAYS  = 7       # historical prices don't change; refresh weekly
MIN_DAYS      = 300     # drop tickers with less than this much history


def fetch_price_history(ticker: str, start: str, end: str) -> pd.Series:
    """
    Returns dividend-adjusted Close prices as a tz-naive DatetimeIndex Series.
    Caches to data/v2/{ticker}.csv; stale after MAX_AGE_DAYS.
    Raises ValueError if fewer than MIN_DAYS trading days returned.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = f"{CACHE_DIR}/{ticker}.csv"

    if os.path.exists(path):
        age = (time.time() - os.path.getmtime(path)) / 86400
        if age <= MAX_AGE_DAYS:
            s = pd.read_csv(path, index_col=0, parse_dates=True).squeeze()
            if isinstance(s, pd.Series):
                s.index = pd.DatetimeIndex(s.index).tz_localize(None)
                return s

    df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    if df.empty:
        raise ValueError(f"{ticker}: no data returned")

    s = df["Close"].copy()
    if s.index.tz is not None:
        s.index = s.index.tz_convert(None)

    if len(s) < MIN_DAYS:
        raise ValueError(f"{ticker}: only {len(s)} days (need {MIN_DAYS})")

    s.to_csv(path)
    return s


def fetch_all(tickers: list, start: str, end: str,
              max_workers: int = 10) -> dict:
    """Parallel fetch. Returns {ticker: Series}. Prints summary of dropped tickers."""
    prices, failed = {}, []

    def _fetch(t):
        try:
            return t, fetch_price_history(t, start, end)
        except Exception as e:
            return t, None

    print(f"  Fetching {len(tickers)} tickers in parallel...", flush=True)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch, t): t for t in tickers}
        for f in as_completed(futures):
            t, s = f.result()
            if s is not None:
                prices[t] = s
                print(f"    {t} OK ({len(s)} days)", flush=True)
            else:
                failed.append(t)
                print(f"    {t} DROPPED", flush=True)

    print(f"\n  Fetched {len(prices)} tickers, dropped {len(failed)}: {failed}\n")
    return prices


def build_price_matrix(prices: dict) -> pd.DataFrame:
    """
    Aligns all tickers to a common calendar.
    Forward-fills up to 5 consecutive NaN days (holidays, halts).
    Drops dates where >10% of tickers have no price.
    Returns DataFrame: rows=dates (DatetimeIndex), cols=tickers.
    """
    df = pd.DataFrame(prices).sort_index()
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    df = df.ffill(limit=5)
    min_valid = int(len(df.columns) * 0.90)
    df = df.dropna(thresh=min_valid)
    return df
