def add_signals(df, rsi_buy=45, rsi_sell=50):
    df["buy"] = (df["RSI"] < rsi_buy) & (df["MACD"] > df["Signal"])
    df["sell"] = (df["RSI"] > rsi_sell) | (df["MACD"] < df["Signal"])
    return df