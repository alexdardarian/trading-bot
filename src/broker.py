import os
from dotenv import load_dotenv
from alpaca.trading.client   import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums    import OrderSide, TimeInForce

load_dotenv()


def get_client(paper: bool = True) -> TradingClient:
    key    = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise EnvironmentError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env"
        )
    return TradingClient(key, secret, paper=paper)


def account_info(client: TradingClient) -> dict:
    a = client.get_account()
    return {
        "cash":            float(a.cash),
        "portfolio_value": float(a.portfolio_value),
        "buying_power":    float(a.buying_power),
    }


def get_positions(client: TradingClient) -> dict:
    """Returns {ticker: shares} for every open position."""
    return {p.symbol: float(p.qty) for p in client.get_all_positions()}


def get_position_values(client: TradingClient) -> dict:
    """Returns {ticker: current_market_value} for every open position."""
    return {p.symbol: float(p.market_value) for p in client.get_all_positions()}


def is_market_open(client: TradingClient) -> bool:
    return client.get_clock().is_open


def buy_qty(client: TradingClient, ticker: str, qty: float):
    """
    Buy a specific quantity (fractional OK) at market.
    Using qty instead of notional because Alpaca silently fills notional
    orders at 0 shares for non-fractionable stocks in paper trading.
    """
    order = MarketOrderRequest(
        symbol=ticker,
        qty=round(qty, 9),
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )
    return client.submit_order(order)


def cancel_all_orders(client: TradingClient):
    """Cancel every open order. Call before placing new orders to avoid duplicates."""
    client.cancel_orders()


def sell_all(client: TradingClient, ticker: str):
    """Close the entire position in ticker at market."""
    client.close_position(ticker)
