# Trading bot

An automated multi-stock paper trading bot that analyzes live market data, generates buy/sell signals using technical indicators, and executes trades via the Alpaca API.

## Features

- Live market data pipeline via yfinance with local CSV caching
- RSI and MACD technical indicators for signal generation
- Backtesting engine with P&L tracking against historical data
- Automated paper trading across multiple stocks simultaneously via Alpaca
- Interactive Streamlit dashboard with candlestick charts and live portfolio view

## Tech stack

Python, pandas, yfinance, TA, Plotly, Streamlit, Alpaca API

## How it works

The bot fetches historical price data and computes two indicators:
- RSI (Relative Strength Index) — measures momentum, flags oversold/overbought conditions
- MACD (Moving Average Convergence Divergence) — identifies trend direction and reversals

When both indicators align, the bot places a market order via Alpaca's paper trading API. Signals are checked every 5 minutes during market hours.

## Run the dashboard

```bash
pip install -r requirements.txt
streamlit run main.py
```

## Run the live bot

```bash
python3 bot.py
```

## Project structure
src/
├── fetch.py        # data pipeline with caching
├── indicators.py   # RSI and MACD computation
├── signals.py      # buy/sell signal logic
├── backtest.py     # historical simulation engine
└── trader.py       # Alpaca API integration
main.py             # Streamlit dashboard
bot.py              # live trading engine

## Setup

Create a `.env` file with your Alpaca paper trading keys:
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret

