import numpy as np

def momentum_score(df):
    if len(df) < 252:
        return 50.0
    close = df["Close"].dropna()
    if len(close) < 252:
        return 50.0
    ret_12m = (close.iloc[-1] - close.iloc[-252]) / close.iloc[-252]
    ret_1m  = (close.iloc[-1] - close.iloc[-21])  / close.iloc[-21]
    ret_12_1 = ret_12m - ret_1m
    if np.isnan(ret_12_1):
        return 50.0
    trend_filter = close.iloc[-1] > close.rolling(200).mean().iloc[-1]
    volatility = close.pct_change().rolling(21).std().iloc[-1]
    risk_adjusted = ret_12_1 / volatility if volatility > 0 else 0
    score = 50 + float(np.clip(risk_adjusted * 5, -50, 50))
    score = score + (10 if trend_filter else -10)
    return float(min(max(score, 0), 100))