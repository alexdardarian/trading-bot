"""
Intelligence layer: yfinance news + analyst consensus + earnings momentum → Claude synthesis.

Produces a structured TickerIntelligence score per ticker that can be combined with
quant factor scores for a richer view of each candidate.
"""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic
import pandas as pd
import yfinance as yf


@dataclass
class TickerIntelligence:
    ticker: str
    confidence: float      # 0–1  (0 = avoid, 1 = highest conviction)
    verdict: str           # strong_buy | buy | hold | avoid
    bull_thesis: str
    bear_thesis: str
    news_sentiment: str    # positive | neutral | negative | mixed
    analyst_signal: str    # buy | hold | sell | insufficient_data
    earnings_trend: str    # beat | miss | mixed | no_data


# ── Data fetchers ─────────────────────────────────────────────────────────────

def _fetch_news_headlines(ticker: str, max_items: int = 8) -> list[str]:
    try:
        t = yf.Ticker(ticker)
        news = t.news or []
        cutoff = datetime.now(timezone.utc).timestamp() - 30 * 86400
        headlines = []
        for item in news:
            # New yfinance format (2025+): {'id': ..., 'content': {'title': ..., 'pubDate': 'ISO'}}
            if "content" in item:
                content = item["content"]
                title = content.get("title", "")
                pub = content.get("pubDate", "")
                try:
                    ts = datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp()
                except Exception:
                    ts = cutoff   # include if date unparseable
            else:
                # Legacy format: {'title': ..., 'providerPublishTime': unix}
                title = item.get("title", "")
                ts = item.get("providerPublishTime", cutoff)
            if title and ts >= cutoff:
                headlines.append(title)
        return headlines[:max_items]
    except Exception:
        return []


def _fetch_analyst_consensus(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        summary = t.recommendations_summary
        if summary is None or (isinstance(summary, pd.DataFrame) and summary.empty):
            return {}
        row = summary.iloc[0]
        return {
            "strong_buy":  int(row.get("strongBuy", 0)),
            "buy":         int(row.get("buy", 0)),
            "hold":        int(row.get("hold", 0)),
            "sell":        int(row.get("sell", 0)),
            "strong_sell": int(row.get("strongSell", 0)),
        }
    except Exception:
        return {}


def _fetch_earnings_surprises(ticker: str, n_quarters: int = 4) -> list[dict]:
    try:
        t = yf.Ticker(ticker)
        dates = t.earnings_dates
        if dates is None or (isinstance(dates, pd.DataFrame) and dates.empty):
            return []
        now = pd.Timestamp.now(tz="UTC")
        past = dates[dates.index < now].dropna(subset=["Reported EPS", "EPS Estimate"])
        result = []
        for dt, row in past.head(n_quarters).iterrows():
            actual   = float(row["Reported EPS"])
            estimate = float(row["EPS Estimate"])
            surprise = (actual - estimate) / abs(estimate) * 100 if estimate != 0 else 0.0
            result.append({
                "date":         str(dt.date()),
                "actual":       round(actual, 2),
                "estimate":     round(estimate, 2),
                "surprise_pct": round(surprise, 1),
            })
        return result
    except Exception:
        return []


# ── Claude prompt + tool ──────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a quantitative equity analyst at a systematic fund focused on large-cap US equities \
across technology, industrials, and consumer sectors.

Score each ticker using three data inputs:

1. NEWS SENTIMENT — recent headlines (past 30 days). Assess whether news flow is positive, \
negative, neutral, or mixed for the underlying business — not just stock price moves.

2. ANALYST CONSENSUS — current Wall Street buy/hold/sell counts. A strong buy-skew is a \
positive signal, but be skeptical of crowded consensus (good news may already be priced in).

3. EARNINGS MOMENTUM — last 4 quarters of EPS actual vs estimate. Consistent beats (≥+5% \
for 3+ quarters) signal a company systematically exceeding expectations. The trend direction \
matters as much as magnitude.

You also receive a QUANT SCORE (momentum + quality factor, price-based). Use it as context \
but add genuine insight from the qualitative data — do not simply echo the quant score.

Be concise in your theses (1–2 sentences each). Acknowledge when data is sparse. \
Always call the score_tickers tool with your complete analysis.\
"""

_SCORE_TOOL = {
    "name": "score_tickers",
    "description": "Return structured confidence scores for each analyzed ticker.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "confidence": {
                            "type": "number", "minimum": 0, "maximum": 1,
                            "description": "0=strong avoid, 1=highest conviction buy",
                        },
                        "verdict": {
                            "type": "string",
                            "enum": ["strong_buy", "buy", "hold", "avoid"],
                        },
                        "bull_thesis":    {"type": "string"},
                        "bear_thesis":    {"type": "string"},
                        "news_sentiment": {
                            "type": "string",
                            "enum": ["positive", "neutral", "negative", "mixed"],
                        },
                        "analyst_signal": {
                            "type": "string",
                            "enum": ["buy", "hold", "sell", "insufficient_data"],
                        },
                        "earnings_trend": {
                            "type": "string",
                            "enum": ["beat", "miss", "mixed", "no_data"],
                        },
                    },
                    "required": [
                        "ticker", "confidence", "verdict",
                        "bull_thesis", "bear_thesis",
                        "news_sentiment", "analyst_signal", "earnings_trend",
                    ],
                },
            }
        },
        "required": ["scores"],
    },
}


def _build_ticker_block(ticker: str, data: dict) -> str:
    lines = [f"### {ticker}", f"Quant score: {data['quant_score']}"]

    if data["news"]:
        lines.append(f"Recent news ({len(data['news'])} headlines):")
        for h in data["news"]:
            lines.append(f"  - {h}")
    else:
        lines.append("News: none available in past 30 days")

    if data["analyst"]:
        a = data["analyst"]
        total   = sum(a.values()) or 1
        pct_buy = round((a["strong_buy"] + a["buy"]) / total * 100)
        lines.append(
            f"Analyst consensus: {a['strong_buy']} strong-buy, {a['buy']} buy, "
            f"{a['hold']} hold, {a['sell']} sell, {a['strong_sell']} strong-sell "
            f"({pct_buy}% bullish)"
        )
    else:
        lines.append("Analyst consensus: no data")

    if data["earnings"]:
        parts = []
        for e in data["earnings"]:
            sign = "+" if e["surprise_pct"] >= 0 else ""
            parts.append(f"{e['date']}: {sign}{e['surprise_pct']}%")
        lines.append(f"Earnings surprises: {', '.join(parts)}")
    else:
        lines.append("Earnings: no data")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def score_tickers(
    tickers: list[str],
    quant_scores: dict[str, float],
    *,
    model: str = "claude-sonnet-4-6",
    batch_size: int = 20,
) -> list[TickerIntelligence]:
    """
    Fetch news + analyst consensus + earnings data for each ticker, then call
    Claude to synthesize a structured confidence score.

    tickers      — tickers to analyze
    quant_scores — ticker → raw factor score (context only, not used mechanically)
    model        — Claude model ID
    batch_size   — max tickers per API call (avoids hitting context limits)
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )

    n_batches = -(-len(tickers) // batch_size)   # ceiling division
    est_cost  = n_batches * 0.04
    print(f"  API budget: {n_batches} call(s) × ~$0.04 = ~${est_cost:.2f} max", flush=True)

    # max_retries=1 (one retry on transient errors, not the SDK default of 2)
    # timeout=120s — 30 tickers × ~4s generation each; default 600s is dangerous
    client = anthropic.Anthropic(max_retries=1, timeout=120.0)

    print(f"  Fetching market intelligence for {len(tickers)} tickers...", flush=True)
    ticker_data: dict[str, dict] = {}
    for i, ticker in enumerate(tickers, 1):
        print(f"    [{i:>2}/{len(tickers)}] {ticker:<6}", end="\r", flush=True)
        ticker_data[ticker] = {
            "quant_score": round(quant_scores.get(ticker, 0.0), 3),
            "news":        _fetch_news_headlines(ticker),
            "analyst":     _fetch_analyst_consensus(ticker),
            "earnings":    _fetch_earnings_surprises(ticker),
        }
        time.sleep(0.15)   # be gentle with yfinance
    print()

    all_results: list[TickerIntelligence] = []
    batches = [tickers[i : i + batch_size] for i in range(0, len(tickers), batch_size)]
    total_input_tokens  = 0
    total_output_tokens = 0

    for b_idx, batch in enumerate(batches, 1):
        label = f"batch {b_idx}/{len(batches)}" if len(batches) > 1 else model
        print(f"  Calling Claude ({label}) to synthesize scores...", flush=True)

        user_text = "Score the following tickers:\n\n" + "\n\n".join(
            _build_ticker_block(t, ticker_data[t]) for t in batch
        )

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[_SCORE_TOOL],
            tool_choice={"type": "tool", "name": "score_tickers"},
            messages=[{"role": "user", "content": user_text}],
        )

        usage = response.usage
        total_input_tokens  += usage.input_tokens
        total_output_tokens += usage.output_tokens
        cache_read   = getattr(usage, "cache_read_input_tokens",  0) or 0
        cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
        actual_cost  = (
            (usage.input_tokens - cache_read) * 3e-6
            + cache_read                      * 0.3e-6
            + cache_create                    * 3.75e-6
            + usage.output_tokens             * 15e-6
        )
        print(
            f"    tokens in={usage.input_tokens} (cache_hit={cache_read}) "
            f"out={usage.output_tokens}  cost≈${actual_cost:.4f}",
            flush=True,
        )

        tool_use = next(
            (block for block in response.content if block.type == "tool_use"), None
        )
        if tool_use is None:
            print(f"  ✗ Claude returned no tool use for batch {b_idx}")
            continue

        for s in tool_use.input.get("scores", []):
            all_results.append(
                TickerIntelligence(
                    ticker=s["ticker"],
                    confidence=float(s["confidence"]),
                    verdict=s["verdict"],
                    bull_thesis=s["bull_thesis"],
                    bear_thesis=s["bear_thesis"],
                    news_sentiment=s["news_sentiment"],
                    analyst_signal=s["analyst_signal"],
                    earnings_trend=s["earnings_trend"],
                )
            )

    print(
        f"  Total tokens: {total_input_tokens} in / {total_output_tokens} out  "
        f"({len(all_results)} tickers scored)",
        flush=True,
    )
    return all_results
