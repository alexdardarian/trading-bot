import time
import yfinance as yf
import pandas as pd
from src.indicators import add_indicators
from src.signals import add_signals, add_momentum_signals
from src.trader import place_buy, place_sell, get_account, get_positions, is_market_open
from src.fetch import get_sp500_tickers
from src.factors.scorer import composite_score
from src.factors.vix_regime import vix_regime_at
from src.factors.market_regime import is_market_uptrend
from src.filters import vol_spike_mask, earnings_blackout_mask
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    "trade_amount_pct": 0.02,
    "max_positions": 10,
    "stop_loss_pct": 0.03,
    "rsi_buy": 45,
    "rsi_sell": 50,
    "sectors": ["tech", "industrials", "consumer"],
}

SECTOR_TICKERS = {
    "tech": ["AAPL","MSFT","NVDA","AMD","AVGO","META","GOOGL","ORCL","CRM","NOW",
             "ADBE","QCOM","TXN","ADI","MU","AMAT","KLAC","LRCX","PANW","CSCO"],
    "industrials": ["HON","GE","CAT","DE","RTX","LMT","UNP","ETN","EMR","NOC",
                    "ITW","GD","UPS","FDX","MMM"],
    "consumer": ["AMZN","HD","MCD","NKE","SBUX","LOW","TJX","COST","NFLX","TSLA",
                 "WMT","KO","PG","PEP","MDLZ","PM","MO"],
}

SCORE_THRESHOLD = 60
_DATA_CACHE    = {}
_CACHE_TTL     = 600   # seconds — one scan cycle
_partial_exits = set() # tickers where first half has been sold; waiting for confirmation

def get_tickers():
    if CONFIG["sectors"] is None:
        return get_sp500_tickers()
    tickers = []
    for sector in CONFIG["sectors"]:
        tickers.extend(SECTOR_TICKERS.get(sector, []))
    return list(set(tickers))

def get_live_signal(ticker):
    now = time.time()
    cached = _DATA_CACHE.get(ticker)
    if cached is None or (now - cached["ts"]) > _CACHE_TTL:
        stock = yf.Ticker(ticker)
        _DATA_CACHE[ticker] = {"df": stock.history(period="2y"), "ts": now}
    df = _DATA_CACHE[ticker]["df"].copy().ffill()
    df = add_indicators(df)

    score, breakdown = composite_score(ticker, df, use_live_data=True)

    momentum  = breakdown["momentum"]
    reversion = breakdown["mean_reversion"]

    # VIX regime shifts the routing thresholds — same logic as the backtest
    _, vix_regime = vix_regime_at(time.strftime("%Y-%m-%d"))
    thresholds = {
        "fear":        (80, 55),
        "normal":      (70, 70),
        "complacency": (60, 80),
    }
    mom_thr, rev_thr = thresholds[vix_regime]

    if momentum > mom_thr and reversion < rev_thr:
        df = add_momentum_signals(df)
    elif reversion > rev_thr and momentum < mom_thr:
        df = add_signals(df, rsi_buy=CONFIG["rsi_buy"], rsi_sell=CONFIG["rsi_sell"])
    else:
        df_mom = add_momentum_signals(df.copy())
        df_rev = add_signals(df.copy(), rsi_buy=CONFIG["rsi_buy"], rsi_sell=CONFIG["rsi_sell"])
        df["buy"] = df_mom["buy"] | df_rev["buy"]
        df["sell"] = df_mom["sell"] & df_rev["sell"]

    latest    = df.iloc[-1]
    vol_safe  = bool(vol_spike_mask(df).iloc[-1])
    earn_safe = bool(earnings_blackout_mask(ticker, df).iloc[-1])
    buy       = bool(latest["buy"]) and vol_safe and earn_safe

    return buy, latest["sell"], latest["Close"], score, breakdown

def check_stop_losses(positions):
    sold_any = False
    for p in positions:
        loss_pct = float(p.unrealized_plpc)
        if loss_pct <= -CONFIG["stop_loss_pct"]:
            print(f"  --> STOP LOSS {p.symbol} ({loss_pct*100:.1f}%), selling...")
            place_sell(p.symbol, qty=float(p.qty))
            _partial_exits.discard(p.symbol)
            sold_any = True
    return get_positions() if sold_any else positions

def run():
    TICKERS = get_tickers()
    print(f"\n--- Trading bot started ---")
    print(f"  Stocks: {len(TICKERS)} | Max positions: {CONFIG['max_positions']} | Stop loss: {CONFIG['stop_loss_pct']*100}%")
    print(f"  RSI buy: {CONFIG['rsi_buy']} | RSI sell: {CONFIG['rsi_sell']} | Trade size: {CONFIG['trade_amount_pct']*100}% of portfolio")
    print(f"  Score threshold: {SCORE_THRESHOLD}/100")
    print(f"  Sectors: {CONFIG['sectors']}")

    account = get_account()
    print(f"  Cash: ${account['cash']:.2f} | Portfolio: ${account['portfolio_value']:.2f}")

    while True:
        if not is_market_open():
            print(f"[{time.strftime('%H:%M:%S')}] Market closed, waiting...")
            time.sleep(60)
            continue

        account = get_account()
        portfolio_value = float(account["portfolio_value"])
        available_cash = float(account["cash"])
        trade_amount = portfolio_value * CONFIG["trade_amount_pct"]
        positions = get_positions()

        positions = check_stop_losses(positions)

        market_up = is_market_uptrend()
        regime_label = "uptrend" if market_up else "DOWNTREND — buys paused"
        print(f"\n[{time.strftime('%H:%M:%S')}] Scanning {len(TICKERS)} stocks | Portfolio: ${portfolio_value:.2f} | Cash: ${available_cash:.2f} | Positions: {len(positions)}/{CONFIG['max_positions']} | Market: {regime_label}")

        for ticker in TICKERS:
            try:
                time.sleep(0.5)
                buy_signal, sell_signal, price, score, breakdown = get_live_signal(ticker)
                holding = any(p.symbol == ticker for p in positions)

                if buy_signal and score >= SCORE_THRESHOLD and not holding and len(positions) < CONFIG["max_positions"] and market_up:
                    # Score brackets: stronger signal = bigger position
                    if score >= 80:
                        size_pct = CONFIG["trade_amount_pct"] * 1.25  # 2.5% — strong conviction
                    elif score >= 70:
                        size_pct = CONFIG["trade_amount_pct"] * 0.75  # 1.5% — decent signal
                    else:
                        size_pct = CONFIG["trade_amount_pct"] * 0.50  # 1.0% — marginal, small bet
                    sized_amount = portfolio_value * size_pct
                    if sized_amount > available_cash:
                        print(f"  {ticker} skipped — insufficient cash (${available_cash:.0f} available, ${sized_amount:.0f} needed)")
                    else:
                        print(f"  --> BUY {ticker} at ${price:.2f} | score:{score:.0f}/100 | size:${sized_amount:.0f} ({size_pct*100:.1f}%)")
                        print(f"      momentum:{breakdown['momentum']:.0f} rel_strength:{breakdown['relative_strength']:.0f} volume:{breakdown['volume']:.0f} reversion:{breakdown['mean_reversion']:.0f} earnings:{breakdown['earnings']:.0f} short_int:{breakdown['short_interest']:.0f}")
                        place_buy(ticker, sized_amount)
                        available_cash -= sized_amount
                        _partial_exits.discard(ticker)
                        positions = get_positions()

                elif sell_signal and holding:
                    pos = next((p for p in positions if p.symbol == ticker), None)
                    if pos:
                        qty = float(pos.qty)
                        if ticker not in _partial_exits:
                            # First sell signal — exit half, wait for confirmation
                            half_qty = round(qty * 0.5, 6)
                            if half_qty * price >= 1.0:
                                place_sell(ticker, qty=half_qty)
                                _partial_exits.add(ticker)
                                print(f"  --> SELL HALF {ticker} at ${price:.2f} | {half_qty:.4f} shares | waiting for confirmation")
                            else:
                                place_sell(ticker, qty=qty)
                                print(f"  --> SELL (full — too small to split) {ticker} at ${price:.2f}")
                        else:
                            # Second consecutive sell signal — confirmed, exit rest
                            place_sell(ticker, qty=qty)
                            _partial_exits.discard(ticker)
                            print(f"  --> SELL REST {ticker} at ${price:.2f} | signal confirmed, full exit")
                    positions = get_positions()

                elif not sell_signal and ticker in _partial_exits:
                    # Sell signal reversed after first half-exit — hold the rest
                    _partial_exits.discard(ticker)
                    print(f"  {ticker} partial exit cleared — sell reversed, holding remainder")

                else:
                    vol_ok  = bool(vol_spike_mask(_DATA_CACHE[ticker]["df"].copy().ffill()).iloc[-1]) if ticker in _DATA_CACHE else True
                    earn_ok = bool(earnings_blackout_mask(ticker, _DATA_CACHE[ticker]["df"].copy().ffill()).iloc[-1]) if ticker in _DATA_CACHE else True
                    flags   = []
                    if not vol_ok:  flags.append("vol-spike")
                    if not earn_ok: flags.append("near-earnings")
                    flag_str = f" [{', '.join(flags)}]" if flags else ""
                    print(f"  {ticker} ${price:.2f} | score:{score:.0f} | buy:{buy_signal} sell:{sell_signal} holding:{holding}{flag_str}")

            except Exception as e:
                print(f"  {ticker} error: {e}")

        print(f"  Scan complete | Cash remaining: ${available_cash:.2f}")
        time.sleep(600)

if __name__ == "__main__":
    run()