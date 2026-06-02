"""
Daily portfolio monitor — live dashboard, no trades, just watching.

  python3 monitor.py            # refreshes every 5 minutes during market hours
  python3 monitor.py --once     # print once and exit
  python3 monitor.py --fast     # refresh every 60 seconds
"""

import sys
import os
import json
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import yfinance as yf
from dotenv import load_dotenv

from src.broker import get_client, account_info, get_positions

load_dotenv()

STATE_FILE = "bot_state.json"
ET = ZoneInfo("America/New_York")

# ── ANSI colours ──────────────────────────────────────────────────────────────
G  = "\033[92m"   # green
R  = "\033[91m"   # red
Y  = "\033[93m"   # yellow
B  = "\033[96m"   # cyan / blue
W  = "\033[97m"   # bright white
DIM= "\033[2m"
BOLD="\033[1m"
X  = "\033[0m"    # reset

def green(s):  return f"{G}{s}{X}"
def red(s):    return f"{R}{s}{X}"
def yellow(s): return f"{Y}{s}{X}"
def cyan(s):   return f"{B}{s}{X}"
def dim(s):    return f"{DIM}{s}{X}"
def bold(s):   return f"{BOLD}{s}{X}"

def signed(val, pct=False, decimals=2):
    fmt = f"+.{decimals}f" if not pct else f"+.{decimals}f"
    s = f"{val:{fmt}}" + ("%" if pct else "")
    return green(s) if val >= 0 else red(s)


# ── Helpers ───────────────────────────────────────────────────────────────────

def next_quarter_end() -> date:
    today = date.today()
    y, m = today.year, today.month
    ends = [date(y, 3, 31), date(y, 6, 30), date(y, 9, 30), date(y, 12, 31),
            date(y + 1, 3, 31)]   # next year's Q1 as fallback
    return next(d for d in ends if d > today)


def fetch_spy_change() -> float:
    """Returns SPY's percentage change today."""
    try:
        hist = yf.Ticker("SPY").history(period="5d", auto_adjust=True)["Close"].dropna()
        if len(hist) >= 2:
            return float((hist.iloc[-1] / hist.iloc[-2] - 1) * 100)
    except Exception:
        pass
    return 0.0


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_run": None, "exit_buffer": {}, "quarter": 0}


def bar(pct: float, width: int = 10) -> str:
    """Small ASCII bar proportional to pct, capped at ±width."""
    filled = min(int(abs(pct) / 2), width)
    b = "█" * filled
    return (green if pct >= 0 else red)(b)


# ── Dashboard ─────────────────────────────────────────────────────────────────

def render(client):
    os.system("clear")
    now   = datetime.now(ET)
    today = date.today()
    w     = 66

    # ── Header ────────────────────────────────────────────────────────────────
    print(bold("═" * w))
    print(bold(f"  PORTFOLIO MONITOR  ·  {now.strftime('%a %b %d %Y')}  ·  {now.strftime('%I:%M %p ET')}"))
    print(bold("═" * w))

    # ── Account ───────────────────────────────────────────────────────────────
    acct    = account_info(client)
    port    = acct["portfolio_value"]
    cash    = acct["cash"]

    # Daily change: Alpaca exposes last_equity via the raw account object
    raw      = client.get_account()
    last_eq  = float(raw.last_equity) if raw.last_equity else port
    daily_pl = port - last_eq
    daily_pc = (daily_pl / last_eq * 100) if last_eq else 0

    spy_chg  = fetch_spy_change()
    vs_spy   = daily_pc - spy_chg
    rel      = green("▲ beating SPY") if vs_spy >= 0 else red("▼ trailing SPY")

    qend     = next_quarter_end()
    days_to  = (qend - today).days
    state    = load_state()
    last_run = state.get("last_run", "never")

    print()
    print(f"  Portfolio:    {bold(f'${port:>10,.2f}')}    "
          f"Today: {signed(daily_pl, decimals=2)} ({signed(daily_pc, pct=True)})  {rel}")
    print(f"  Cash:         ${cash:>10,.2f}    "
          f"SPY today: {signed(spy_chg, pct=True)}")
    print(f"  Next rebalance: {cyan(str(qend))}  "
          f"({days_to} days)    Last bot run: {dim(last_run)}")

    # ── Positions ─────────────────────────────────────────────────────────────
    positions = client.get_all_positions()
    exit_buf  = state.get("exit_buffer", {})

    print()
    print(bold(f"  POSITIONS ({len(positions)})"))
    print(dim("  " + "─" * (w - 2)))
    print(f"  {dim('Ticker'):<14} {dim('Value'):>10}  {dim('Today'):>8}  "
          f"{dim('Since Entry'):>12}  {dim('Status')}")
    print(dim("  " + "─" * (w - 2)))

    # Sort: biggest daily movers first
    positions_sorted = sorted(
        positions,
        key=lambda p: abs(float(p.unrealized_intraday_plpc or 0)),
        reverse=True
    )

    alerts = []
    for p in positions_sorted:
        sym       = p.symbol
        mval      = float(p.market_value or 0)
        unr_pct   = float(p.unrealized_plpc or 0) * 100
        # unrealized_intraday_plpc is today's % move vs yesterday's close — correct daily return
        intra_pct = float(p.unrealized_intraday_plpc or 0) * 100

        # Status
        buf_count = exit_buf.get(sym, 0)
        if buf_count >= 2:
            status = red(f"⚠ EXIT (2/2)")
        elif buf_count == 1:
            status = yellow(f"⚠ watch 1/2")
        else:
            status = green("✓ hold")

        # Collect alerts
        if abs(intra_pct) >= 3:
            alerts.append((sym, intra_pct, "daily move"))
        if unr_pct <= -20:
            alerts.append((sym, unr_pct, "big loss from entry"))

        sym_col = f"{sym:<6}"
        print(f"  {sym_col}  {dim('│')}  ${mval:>9,.2f}  "
              f"{signed(intra_pct, pct=True):>16}  "
              f"{signed(unr_pct, pct=True, decimals=1):>20}  "
              f"{bar(unr_pct, 8)}  {status}")

    # ── Alerts ────────────────────────────────────────────────────────────────
    watch_list = [t for t, c in exit_buf.items() if c >= 1]
    if alerts or watch_list:
        print()
        print(bold(f"  ALERTS"))
        print(dim("  " + "─" * (w - 2)))
        for sym, val, reason in alerts:
            flag = red("▼") if val < 0 else green("▲")
            print(f"  {flag} {bold(sym):<8} {signed(val, pct=True):>14}  {reason}")
        for t in watch_list:
            count = exit_buf[t]
            if count < 2:
                print(f"  {yellow('⚠')} {bold(t):<8} {'':>14}  outside top-30 ({count}/2 qtrs — will sell next run)")

    # ── Portfolio health ──────────────────────────────────────────────────────
    print()
    print(bold(f"  HEALTH"))
    print(dim("  " + "─" * (w - 2)))

    # Rough drawdown from last equity (proxy — real peak would need history)
    dd = (port - last_eq) / last_eq * 100 if last_eq else 0
    dd_bar = bar(dd, 6)
    print(f"  Daily drift:      {signed(dd, pct=True):>14}  {dd_bar}")

    # Capital deployment
    invested = port - cash
    deploy   = invested / port * 100 if port else 0
    d_bar    = (green if deploy >= 60 else yellow)("█" * int(deploy / 10))
    print(f"  Deployed:         {deploy:>13.1f}%  {d_bar}  (${invested:,.0f} in stocks, ${cash:,.0f} cash)")
    print(f"  Positions:        {len(positions):>13}    (target: 30)")
    print(f"  Quarter:          #{state.get('quarter', 0):>12}    (next rebalance in {days_to} days)")

    print()
    print(dim(f"  Refreshing every 5 min  ·  Ctrl+C to stop  ·  {now.strftime('%H:%M:%S')}"))
    print(bold("═" * w))


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    once     = "--once"  in sys.argv
    fast     = "--fast"  in sys.argv
    interval = 60 if fast else 300

    client = get_client(paper=True)

    try:
        while True:
            render(client)
            if once:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  Monitor stopped.")


if __name__ == "__main__":
    main()
