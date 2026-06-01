import yfinance as yf

def short_interest_score(ticker):
    """
    Measures short squeeze potential. High short interest + rising price
    forces short sellers to buy (to cut losses), which accelerates the move.
    Only valid for live trading — yfinance returns current data only,
    so this has look-ahead bias in backtests (disabled via use_live_data=False).
    """
    try:
        info = yf.Ticker(ticker).info
        short_ratio = float(info.get("shortRatio") or 0)   # days to cover
        short_float = float(info.get("shortPercentOfFloat") or 0)  # % of shares shorted
        score = 50.0
        # Days-to-cover: how many trading days it would take all shorts to buy back
        if short_ratio > 10:
            score += 25   # extreme — very high squeeze risk
        elif short_ratio > 5:
            score += 15
        elif short_ratio > 2:
            score += 5
        # Float short: what fraction of available shares is borrowed and sold short
        if short_float > 0.20:
            score += 15   # more than 20% shorted — significant overhang
        elif short_float > 0.10:
            score += 8
        return float(min(max(score, 0), 100))
    except Exception:
        return 50.0
