import time
import yfinance as yf
import pandas as pd
from datetime import datetime
from src.indicators import add_indicators
from src.signals import add_signals
from src.trader import place_buy, place_sell, get_account, get_positions
from dotenv import load_dotenv
from src.fetch import fetch_and_save, get_sp500_tickers

load_dotenv()

TICKERS = get_sp500_tickers()
TRADE_AMOUNT = 1000

def is_market_open():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0)
    market_close = now.replace(hour=16, minute=0, second=0)
    return market_open <= now <= market_close

def get_live_signal(ticker):
    stock = yf.Ticker(ticker)
    df = stock.history(period="3mo")
    df = df.ffill()
    df = add_indicators(df)
    df = add_signals(df, rsi_buy=45, rsi_sell=50)
    latest = df.iloc[-1]
    return latest["buy"], latest["sell"], latest["Close"]

def run():
    print(f"\n--- Trading bot started: {len(TICKERS)} stocks ---")
    account = get_account()
    print(f"Cash: ${account['cash']:.2f} | Portfolio: ${account['portfolio_value']:.2f}")

    while True:
        if not is_market_open():
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Market closed, waiting...")
            time.sleep(60)
            continue

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning {len(TICKERS)} stocks...")
        positions = get_positions()

        for ticker in TICKERS:
            try:
                time.sleep(1)
                buy_signal, sell_signal, price = get_live_signal(ticker)
                holding = any(p.symbol == ticker for p in positions)

                print(f"  {ticker} ${price:.2f} | Buy: {buy_signal} | Sell: {sell_signal} | Holding: {holding}")

                if buy_signal and not holding:
                    print(f"    --> BUY {ticker}, placing ${TRADE_AMOUNT} order...")
                    place_buy(ticker, TRADE_AMOUNT)

                elif sell_signal and holding:
                    print(f"    --> SELL {ticker}, closing position...")
                    place_sell(ticker)

            except Exception as e:
                print(f"  {ticker} error: {e}")

        account = get_account()
        print(f"  Portfolio: ${account['portfolio_value']:.2f} | Cash: ${account['cash']:.2f}")
        time.sleep(600)

if __name__ == "__main__":
    run()