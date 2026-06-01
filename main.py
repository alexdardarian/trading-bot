import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from src.fetch import fetch_and_save
from src.indicators import add_indicators
from src.signals import add_signals
from src.backtest import run_backtest
from src.trader import get_account, get_positions
from dotenv import load_dotenv
import os

load_dotenv()

st.title("Trading bot dashboard")

st.subheader("Live account")
try:
    account = get_account()
    positions = get_positions()

    col1, col2, col3 = st.columns(3)
    col1.metric("Portfolio value", f"${account['portfolio_value']:,.2f}")
    col2.metric("Cash", f"${account['cash']:,.2f}")
    col3.metric("Open positions", len(positions))

    if positions:
        st.subheader("Current positions")
        rows = []
        for p in positions:
            rows.append({
                "Ticker": p.symbol,
                "Qty": float(p.qty),
                "Avg entry": f"${float(p.avg_entry_price):.2f}",
                "Current price": f"${float(p.current_price):.2f}",
                "Market value": f"${float(p.market_value):.2f}",
                "P&L": f"${float(p.unrealized_pl):.2f}",
                "P&L %": f"{float(p.unrealized_plpc)*100:.2f}%"
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
except Exception as e:
    st.error(f"Could not connect to Alpaca: {e}")

st.divider()
st.subheader("Backtest analyzer")

col1, col2 = st.columns(2)
ticker = col1.text_input("Ticker", value="AAPL").upper()
period = col2.selectbox("Period", ["6mo", "1y", "2y"])

col3, col4 = st.columns(2)
rsi_buy = col3.slider("RSI buy threshold", 20, 60, 45)
rsi_sell = col4.slider("RSI sell threshold", 40, 80, 50)

if st.button("Run backtest"):
    cache = f"data/{ticker}.csv"
    if os.path.exists(cache):
        os.remove(cache)

    df = fetch_and_save(ticker, period)
    df = add_indicators(df)
    df = add_signals(df, rsi_buy, rsi_sell)
    results = run_backtest(df)

    col1, col2, col3 = st.columns(3)
    col1.metric("Final value", f"${results['final_value']:,.2f}")
    col2.metric("Return", f"{results['returns']:.2f}%")
    col3.metric("Trades", len(results['trades']))

    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"]
    )])

    buys = df[df["buy"]]
    sells = df[df["sell"]]

    fig.add_scatter(x=buys.index, y=buys["Close"], mode="markers",
        marker=dict(symbol="triangle-up", size=10, color="green"), name="Buy")
    fig.add_scatter(x=sells.index, y=sells["Close"], mode="markers",
        marker=dict(symbol="triangle-down", size=10, color="red"), name="Sell")

    fig.update_layout(
        title=f"{ticker} — signals",
        xaxis_rangeslider_visible=False
    )
    st.plotly_chart(fig)

    if results['trades']:
        st.subheader("Trades")
        for t in results['trades']:
            if t['action'] == 'BUY':
                st.write(f"BUY on {str(t['date'])[:10]} at ${t['price']:.2f}")
            else:
                st.write(f"SELL on {str(t['date'])[:10]} at ${t['price']:.2f} → ${t['value']:.2f}")