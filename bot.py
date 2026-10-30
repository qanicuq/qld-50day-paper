"""QLD 50-day paper bot (paper money only, no real orders).

Rule: after each close, if QLD's close is above its 50-day average, hold QLD
from the next day's open; if not, be in cash from the next day's open.
Runs once per weekday after the close (GitHub Actions). State lives in
state.json, trades in trades.csv, daily account value in equity.csv.
"""
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SYMBOL = "QLD"
SMA_DAYS = 50
SLIPPAGE = 0.0002
START_CASH = 10000.0
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
TRADES = os.path.join(HERE, "trades.csv")
EQUITY = os.path.join(HERE, "equity.csv")


def fetch_daily():
    """Return [(date 'YYYY-MM-DD', open, close)] oldest first, split-adjusted."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}"
           "?range=1y&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)["chart"]["result"][0]
    offset = data["meta"]["gmtoffset"]
    q = data["indicators"]["quote"][0]
    rows = []
    for ts, o, c in zip(data["timestamp"], q["open"], q["close"]):
        if o is None or c is None or o <= 0 or c <= 0:
            continue
        day = datetime.fromtimestamp(ts + offset, timezone.utc).strftime("%Y-%m-%d")
        rows.append((day, float(o), float(c)))
    return rows


def notify(title, message):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("No NTFY_TOPIC set; alert not sent:", title)
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}", data=message.encode(), method="POST",
        headers={"Title": title})
    urllib.request.urlopen(req, timeout=30)


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"cash": START_CASH, "shares": 0.0, "holding": False,
            "pending": None, "last_date": None}


def append_csv(path, header, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerow(row)


def step(state, rows, i, alerts):
    """Process one finished trading day rows[i]."""
    day, op, cl = rows[i]
    # 1. Fill yesterday's order at today's open.
    if state["pending"] == "BUY":
        px = op * (1 + SLIPPAGE)
        state["shares"] = state["cash"] / px
        state["cash"] = 0.0
        state["holding"] = True
        state["buy_price"] = px
        append_csv(TRADES, ["date", "action", "price", "account_value"],
                   [day, "BUY", round(px, 4), round(state["shares"] * px, 2)])
        alerts.append(("QLD paper: BOUGHT", f"{day}: bought QLD at ${px:.2f} (paper)."))
    elif state["pending"] == "SELL":
        px = op * (1 - SLIPPAGE)
        state["cash"] = state["shares"] * px
        gain = (px / state.get("buy_price", px) - 1) * 100
        state["shares"] = 0.0
        state["holding"] = False
        append_csv(TRADES, ["date", "action", "price", "account_value"],
                   [day, "SELL", round(px, 4), round(state["cash"], 2)])
        alerts.append(("QLD paper: SOLD",
                       f"{day}: sold QLD at ${px:.2f} (paper), trade {gain:+.1f}%. "
                       f"Account ${state['cash']:,.0f}."))
    state["pending"] = None

    # 2. Mark the account to today's close.
    value = state["cash"] + state["shares"] * cl
    append_csv(EQUITY, ["date", "account_value", "holding"],
               [day, round(value, 2), int(state["holding"])])

    # 3. Decide for tomorrow's open.
    closes = [r[2] for r in rows[max(0, i - SMA_DAYS + 1): i + 1]]
    if len(closes) < SMA_DAYS:
        return
    sma = sum(closes) / SMA_DAYS
    want = cl > sma
    if want and not state["holding"]:
        state["pending"] = "BUY"
        alerts.append(("QLD paper: BUY signal",
                       f"{day}: QLD closed ${cl:.2f}, above its 50-day average "
                       f"${sma:.2f}. Paper BUY at next open."))
    elif state["holding"] and not want:
        state["pending"] = "SELL"
        alerts.append(("QLD paper: SELL signal",
                       f"{day}: QLD closed ${cl:.2f}, below its 50-day average "
                       f"${sma:.2f}. Paper SELL at next open."))


def run(rows):
    state = load_state()
    alerts = []
    if state["last_date"] is None:
        # First run: only use the latest finished day to set the first signal.
        start = len(rows) - 1
    else:
        start = next((i for i, r in enumerate(rows) if r[0] > state["last_date"]), None)
        if start is None:
            print("No new trading day; nothing to do.")
            return state, alerts
    for i in range(start, len(rows)):
        step(state, rows, i, alerts)
        state["last_date"] = rows[i][0]
    with open(STATE, "w") as f:
        json.dump(state, f, indent=2)
    return state, alerts


def main():
    rows = fetch_daily()
    if len(rows) < SMA_DAYS:
        raise SystemExit(f"Only {len(rows)} daily bars from Yahoo; need {SMA_DAYS}.")
    # Skip today's bar if the run happens before the market has closed.
    now_ny = datetime.now(ZoneInfo("America/New_York"))
    if rows[-1][0] == now_ny.strftime("%Y-%m-%d") and now_ny.hour < 16:
        rows = rows[:-1]
    state, alerts = run(rows)
    for title, msg in alerts:
        print(title, "|", msg)
        notify(title, msg)
    print("State:", {k: state[k] for k in ("holding", "pending", "last_date")})


if __name__ == "__main__":
    main()
