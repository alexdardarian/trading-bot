def volume_score(df):
    if len(df) < 21:
        return 50.0
    avg_volume = df["Volume"].rolling(21).mean()
    volume_ratio = df["Volume"] / avg_volume
    price_change = df["Close"].pct_change()
    conviction = (volume_ratio.iloc[-5:] * price_change.iloc[-5:]).sum()
    volume_trend = volume_ratio.iloc[-5:].mean()
    score = 50 + (conviction * 25) + ((volume_trend - 1) * 10)
    return float(min(max(score, 0), 100))