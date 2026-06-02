from dataclasses import dataclass

SLIPPAGE   = 0.001  # 0.1% per side — conservative for large-cap S&P 500 names
MIN_TRADE  = 500.0  # hard floor: never trade less than this in dollars
TOLERANCE  = 0.25   # relative weight tolerance: skip rebalance if actual weight is
                    # within 25% of target (e.g. target=3.5% → no trade if 2.6–4.4%).
                    # Only new entrants and dropped tickers are always traded.


@dataclass
class Trade:
    date:   str
    ticker: str
    action: str     # "BUY" | "SELL"
    shares: float
    price:  float
    value:  float   # gross dollar value
    cost:   float   # slippage cost


def compute_trades(date_str: str, holdings: dict, target_weights: dict,
                   prices: dict, portfolio_value: float, cash: float) -> list:
    """
    Computes the minimal set of trades to move from current_holdings to
    target_weights.  Sells before buys so that sell proceeds fund new entries.

    Algorithm:
      1. Compute current dollar value of each position.
      2. Compute target dollar value (weight × portfolio_value).
      3. Δ = target - current.  Negatives = sells, positives = buys.
      4. Dropped tickers (not in target_weights) are always fully liquidated.
      5. Tiny rebalances (|Δ| < MIN_TRADE) are skipped for non-dropped tickers.
      6. If sell proceeds are insufficient to fund all buys, buys are scaled
         proportionally (largest first) to preserve relative factor weights.
    """
    current_val = {}
    for t, shares in holdings.items():
        price = prices.get(t)
        if price and price == price:  # not NaN
            current_val[t] = shares * price

    target_val = {t: w * portfolio_value for t, w in target_weights.items()}

    all_tickers = set(holdings) | set(target_weights)
    sells, buys = [], []

    total_val = sum(current_val.values()) + cash

    for t in all_tickers:
        cur = current_val.get(t, 0.0)
        tgt = target_val.get(t, 0.0)
        delta = tgt - cur

        dropped  = (t in holdings) and (t not in target_weights)
        new_entry = (t not in holdings) and (t in target_weights)

        if dropped:
            sells.append((t, cur))       # always fully exit dropped tickers
        elif new_entry:
            buys.append((t, tgt))        # always fully enter new tickers
        else:
            # Continuing position: skip if within tolerance band
            actual_w = cur / total_val if total_val > 0 else 0.0
            target_w = tgt / total_val if total_val > 0 else 0.0
            rel_drift = abs(actual_w - target_w) / target_w if target_w > 0 else 0.0
            if rel_drift < TOLERANCE or abs(delta) < MIN_TRADE:
                continue
            if delta < 0:
                sells.append((t, abs(delta)))
            else:
                buys.append((t, delta))

    sells.sort(key=lambda x: x[1], reverse=True)
    buys.sort(key=lambda x: x[1], reverse=True)

    trades = []
    available_cash = cash

    for t, sell_usd in sells:
        price = prices.get(t)
        if not price or price != price:
            continue
        max_shares = holdings.get(t, 0.0)
        shares = min(sell_usd / price, max_shares)
        actual = shares * price
        cost   = actual * SLIPPAGE
        available_cash += actual - cost
        trades.append(Trade(date_str, t, "SELL", shares, price, actual, cost))

    total_buy = sum(v for _, v in buys)
    scale = min(1.0, available_cash / total_buy) if total_buy > 0 else 0.0

    for t, buy_usd in buys:
        price = prices.get(t)
        if not price or price != price:
            continue
        actual = buy_usd * scale
        cost   = actual * SLIPPAGE
        shares = (actual - cost) / price
        trades.append(Trade(date_str, t, "BUY", shares, price, actual, cost))

    return trades


def apply_trades(holdings: dict, cash: float, trades: list) -> tuple:
    """Returns updated (holdings, cash). Mutates a copy of holdings."""
    holdings = dict(holdings)

    for tr in trades:
        if tr.action == "SELL":
            remaining = holdings.get(tr.ticker, 0.0) - tr.shares
            if remaining <= 1e-9:
                holdings.pop(tr.ticker, None)
            else:
                holdings[tr.ticker] = remaining
            cash += tr.value - tr.cost

        else:  # BUY
            holdings[tr.ticker] = holdings.get(tr.ticker, 0.0) + tr.shares
            cash -= tr.value

    return holdings, max(cash, 0.0)
