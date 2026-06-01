import yfinance as yf
import numpy as np

def earnings_score(ticker):
    try:
        stock = yf.Ticker(ticker)
        earnings = stock.earnings_history
        if earnings is None or len(earnings) == 0:
            return 50.0
        recent = earnings.head(4)
        if "epsActual" not in recent.columns or "epsEstimate" not in recent.columns:
            return 50.0
        recent = recent.dropna(subset=["epsActual", "epsEstimate"])
        if len(recent) == 0:
            return 50.0
        surprises = []
        for _, row in recent.iterrows():
            if row["epsEstimate"] != 0:
                surprise_pct = (row["epsActual"] - row["epsEstimate"]) / abs(row["epsEstimate"])
                surprises.append(surprise_pct)
        if not surprises:
            return 50.0
        score = 50
        score += surprises[0] * 100
        score += np.mean(surprises) * 50
        score += (sum(1 for s in surprises if s > 0) / len(surprises)) * 20
        return float(min(max(score, 0), 100))
    except Exception:
        return 50.0