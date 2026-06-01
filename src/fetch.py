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

def get_sp500_tickers():
    return [
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","BRK-B","LLY","AVGO",
        "TSLA","WMT","JPM","V","UNH","XOM","ORCL","MA","COST","HD","PG","JNJ",
        "ABBV","BAC","KO","MRK","CVX","CRM","NFLX","AMD","PEP","TMO","ACN","LIN",
        "MCD","CSCO","ABT","GE","TXN","DHR","ADBE","WFC","MS","INTU","AXP","IBM",
        "QCOM","RTX","GS","SPGI","AMGN","CAT","T","ISRG","BKNG","VRTX","PFE",
        "UBER","NOW","HON","AMAT","NEE","DE","UNP","LOW","ETN","TJX","SYK","GILD",
        "CMCSA","BSX","PLD","C","REGN","ADI","MDT","BLK","MMC","SCHW","CI","MU",
        "CB","SO","DUK","ZTS","BMY","MDLZ","ICE","CL","CME","APH","MCO","AON",
        "SHW","ITW","PNC","USB","NOC","EMR","INTC","MMM","HCA","EOG","PSA","F",
        "GM","PYPL","WELL","WM","ELV","GD","HUM","ADP","LRCX","PANW","KLAC"
    ]