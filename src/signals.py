def add_signals(df, rsi_buy=45, rsi_sell=50):
    df["buy"] = (df["RSI"] < rsi_buy) & (df["MACD"] > df["Signal"])
    df["sell"] = (df["RSI"] > rsi_sell) & (df["MACD"] < df["Signal"])
    return df

def add_momentum_signals(df):
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    df["buy"] = (
        (df["Close"] > df["MA50"]) &
        (df["MA50"] > df["MA200"]) &
        (df["RSI"] < 65) &
        (df["MA50"].diff(10) > 0)  # MA50 must be trending upward, not just above MA200
    )
    # Two consecutive closes below MA50 required — filters out single-bar noise
    # while still exiting quickly during genuine sustained breakdowns
    df["sell"] = (
        (df["Close"] < df["MA50"]) &
        (df["Close"].shift(1) < df["MA50"].shift(1))
    )
    return df