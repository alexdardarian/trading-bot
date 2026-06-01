from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from dotenv import load_dotenv
import os

load_dotenv()

client = TradingClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_SECRET_KEY"),
    paper=True
)

def get_account():
    account = client.get_account()
    return {
        "cash": float(account.cash),
        "portfolio_value": float(account.portfolio_value)
    }

def place_buy(ticker, dollars):
    order = MarketOrderRequest(
        symbol=ticker,
        notional=dollars,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY
    )
    return client.submit_order(order)

def is_market_open():
    return client.get_clock().is_open

def place_sell(ticker, qty=None):
    if qty is None:
        for p in client.get_all_positions():
            if p.symbol == ticker:
                qty = float(p.qty)
                break
    if qty is None:
        return None
    order = MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY
    )
    return client.submit_order(order)

def get_positions():
    return client.get_all_positions()