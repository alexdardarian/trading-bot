import yfinance as yf
import pandas as pd
import ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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

df = fetch_and_save("AAPL")

df["RSI"] = ta.momentum.RSIIndicator(df["Close"], window=14).rsi()
macd = ta.trend.MACD(df["Close"])
df["MACD"] = macd.macd()
df["Signal"] = macd.macd_signal()

df["buy"] = (df["RSI"] < 45) & (df["MACD"] > df["Signal"])
df["sell"] = (df["RSI"] > 50) | (df["MACD"] < df["Signal"])

print(f"Buy signals:  {df['buy'].sum()}")
print(f"Sell signals: {df['sell'].sum()}")

cash = 10000
shares = 0
trades = []

for date, row in df.iterrows():
    if row["buy"] and cash > 0:
        shares = cash / row["Close"]
        cash = 0
        trades.append({"date": date, "action": "BUY", "price": row["Close"], "shares": shares})

    elif row["sell"] and shares > 0:
        cash = shares * row["Close"]
        trades.append({"date": date, "action": "SELL", "price": row["Close"], "value": cash})
        shares = 0

final_value = cash if cash > 0 else shares * df["Close"].iloc[-1]
returns = ((final_value - 10000) / 10000) * 100

print(f"\n--- Backtest results ---")
print(f"Starting capital: $10,000")
print(f"Final value:      ${final_value:.2f}")
print(f"Return:           {returns:.2f}%")
print(f"\nTrades:")
for t in trades:
    if t["action"] == "BUY":
        print(f"  BUY  on {str(t['date'])[:10]} at ${t['price']:.2f}")
    else:
        print(f"  SELL on {str(t['date'])[:10]} at ${t['price']:.2f} → ${t['value']:.2f}")