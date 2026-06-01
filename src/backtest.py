SLIPPAGE = 0.001  # 0.1% per trade


def run_backtest(df, starting_cash=10000):
    cash = starting_cash
    shares = 0
    trades = []
    pending_buy = False
    pending_sell = False

    for date, row in df.iterrows():
        price = row["Close"]

        # Execute orders from the PREVIOUS bar's signal — can't trade at the
        # same close that generated the signal.
        if pending_buy and cash > 0 and shares == 0:
            shares = (cash * (1 - SLIPPAGE)) / price
            cash = 0
            trades.append({"date": date, "action": "BUY", "price": price})
            pending_buy = False
        elif pending_sell and shares > 0:
            cash = shares * price * (1 - SLIPPAGE)
            trades.append({"date": date, "action": "SELL", "price": price, "value": cash})
            shares = 0
            pending_sell = False

        if row.get("buy", False) and shares == 0:
            pending_buy = True
            pending_sell = False
        elif row.get("sell", False) and shares > 0:
            pending_sell = True
            pending_buy = False

    final_value = cash if shares == 0 else shares * df["Close"].iloc[-1] * (1 - SLIPPAGE)
    returns = ((final_value - starting_cash) / starting_cash) * 100
    return {"final_value": final_value, "returns": returns, "trades": trades}
