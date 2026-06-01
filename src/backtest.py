def run_backtest(df, starting_cash=10000):
    cash = starting_cash
    shares = 0
    trades = []

    for date, row in df.iterrows():
        if row["buy"] and cash > 0:
            shares = cash / row["Close"]
            cash = 0
            trades.append({"date": date, "action": "BUY", "price": row["Close"]})
        elif row["sell"] and shares > 0:
            cash = shares * row["Close"]
            trades.append({"date": date, "action": "SELL", "price": row["Close"], "value": cash})
            shares = 0

    final_value = cash if cash > 0 else shares * df["Close"].iloc[-1]
    returns = ((final_value - starting_cash) / starting_cash) * 100
    return {"final_value": final_value, "returns": returns, "trades": trades}