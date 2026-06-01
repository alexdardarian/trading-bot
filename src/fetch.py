import yfinance as yf
import pandas as pd
import os

def fetch_and_save(ticker, period="1y"):
    path = f"data/{ticker}.csv"
    os.makedirs("data", exist_ok=True)
    if os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)
        df.to_csv(path)
    return df.ffill()