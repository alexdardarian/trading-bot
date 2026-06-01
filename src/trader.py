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

def place_sell(ticker):
    positions = client.get_all_positions()
    for p in positions:
        if p.symbol == ticker:
            order = MarketOrderRequest(
                symbol=ticker,
                qty=float(p.qty),
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            return client.submit_order(order)
    return None

def get_positions():
    return client.get_all_positions()