def mean_reversion_score(df):
    if len(df) < 21:
        return 50.0
    close = df["Close"]
    rolling_mean = close.rolling(21).mean()
    rolling_std = close.rolling(21).std()
    z_score = (close.iloc[-1] - rolling_mean.iloc[-1]) / rolling_std.iloc[-1]
    bb_upper = rolling_mean + (2 * rolling_std)
    bb_lower = rolling_mean - (2 * rolling_std)
    bb_position = (close - bb_lower) / (bb_upper - bb_lower)
    bb_width = (bb_upper - bb_lower) / rolling_mean
    score = 50 - (z_score * 15)
    if bb_position.iloc[-1] < 0.2:
        score += 20
    elif bb_position.iloc[-1] > 0.8:
        score -= 20
    score += min(bb_width.iloc[-1] * 100, 10)
    return float(min(max(score, 0), 100))