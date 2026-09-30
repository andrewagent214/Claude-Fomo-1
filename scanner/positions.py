#!/usr/bin/env python3
"""Check your open positions against the exit rules and tell you HOLD or SELL.

Rules (from config.json "risk"):
  * Before a coin reaches 2x: sell if price falls to the initial stop (-25%).
  * Once it has reached 2x: the stop becomes the HIGHER of
      - entry +30%   (your "never give back below a 30% gain" floor)
      - peak  -35%   (trailing stop, so the floor rises as the coin runs)
    At exactly 2x both equal 1.3x entry; above that the trailing stop takes over.
  * Warnings (not automatic sells): chart DOWNTREND, sellers outnumbering buyers,
    liquidity or market cap shrinking, holder count falling.

Keep journal/positions.csv up to date (one row per coin you hold). This script
updates peak_price in that file and writes output/reports/positions.md.

Usage:
    python3 scanner/positions.py
"""
import csv
import os
import sys
import time
from datetime import datetime, timezone

import chart
import scan

ROOT = scan.ROOT
POSITIONS = os.path.join(ROOT, "journal", "positions.csv")


def exit_status(entry, price, peak, risk):
    """Return (action, stop_price, mode) for one position."""
    peak = max(peak, price)
    if peak >= entry * risk["lock_in_trigger_multiple"]:
        stop = max(entry * (1 + risk["lock_in_floor_gain_pct"] / 100),
                   peak * (1 - risk["trail_from_peak_pct"] / 100))
        mode = "LOCKED (reached 2x)"
    else:
        stop = entry * (1 - risk["stop_loss_pct"] / 100)
        mode = "INITIAL STOP"
    return ("SELL" if price <= stop else "HOLD"), stop, mode


def warnings(m, trend, holders_now, holders_before):
    w = []
    if trend == "DOWNTREND":
        w.append("chart in downtrend")
    if m["buy_sell_ratio_1h"] < 0.8:
        w.append(f"sellers outnumber buyers 1h ({m['buy_sell_ratio_1h']:.2f})")
    if m["change_1h_pct"] < -15:
        w.append(f"1h {m['change_1h_pct']:+.0f}%")
    if holders_now and holders_before and holders_now < holders_before:
        w.append(f"holders falling {holders_before}->{holders_now}")
    return w


def fetch_pair(chain, pair_address):
    data = scan.get_json(f"{scan.API}/latest/dex/pairs/{chain}/{pair_address}")
    pairs = data.get("pairs") or ([data["pair"]] if data.get("pair") else [])
    if not pairs:
        raise ValueError("pair not found")
    return pairs[0]


def check(rows, cfg, pair_fn=fetch_pair, candles_fn=chart.fetch_candles, now_ms=None):
    now_ms = now_ms or int(time.time() * 1000)
    results = []
    for row in rows:
        entry, size = float(row["entry_price"]), float(row["size_usd"])
        try:
            m = scan.metrics(pair_fn(row["chain"], row["pair_address"]), now_ms)
        except Exception as e:
            print(f"!! {row['token']}: could not fetch price ({e}). Check it manually in the app.", file=sys.stderr)
            continue
        price = m["price_usd"]
        peak = max(float(row.get("peak_price") or entry), price)
        action, stop, mode = exit_status(entry, price, peak, cfg["risk"])
        try:
            trend = chart.analyze(candles_fn(row["chain"], row["pair_address"]))["trend"]
        except Exception:
            trend = "n/a"
        holders = [int(h) for h in (row.get("holders") or "").split("/") if h.strip().isdigit()]
        warn = warnings(m, trend, holders[-1] if holders else None, holders[-2] if len(holders) > 1 else None)
        row["peak_price"] = f"{peak:.10g}"
        results.append({"token": row["token"], "entry": entry, "price": price, "peak": peak, "size": size,
                        "value": size * price / entry, "gain_pct": (price / entry - 1) * 100,
                        "action": action, "stop": stop, "mode": mode, "trend": trend, "warnings": warn,
                        "mcap": m["fdv_usd"], "liquidity": m["liquidity_usd"]})
    return results


def report(results, cfg):
    r = cfg["risk"]
    lines = [f"# Open positions ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)", ""]
    if not results:
        return "\n".join(lines + ["No open positions. Add rows to journal/positions.csv after you buy."]) + "\n"
    invested = sum(x["size"] for x in results)
    value = sum(x["value"] for x in results)
    lines += [f"Invested **${invested:,.2f}** → now worth **${value:,.2f}** ({(value / invested - 1) * 100:+.1f}%). "
              f"Goal: ${r['goal_usd']} account.", "",
              "| Action | Token | Entry | Now | Gain | Peak | Stop now | Stop mode | Chart | Mcap | Liquidity | Warnings |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in results:
        lines.append(f"| **{x['action']}** | {x['token']} | {x['entry']:.8g} | {x['price']:.8g} | {x['gain_pct']:+.1f}% | "
                     f"{x['peak']:.8g} | {x['stop']:.8g} | {x['mode']} | {x['trend']} | ${x['mcap']:,.0f} | "
                     f"${x['liquidity']:,.0f} | {'; '.join(x['warnings']) or '-'} |")
    lines += ["", "SELL = the price is at or below your stop, so sell now in the Fomo app, then move the row to "
              "journal/trades.csv. Warnings mean the hype is fading: consider selling early even if the stop hasn't hit."]
    return "\n".join(lines) + "\n"


def main():
    cfg = scan.load_config()
    with open(POSITIONS) as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    results = check(rows, cfg)
    with open(POSITIONS, "w", newline="") as f:  # save updated peak prices
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    out = os.path.join(ROOT, "output", "reports")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "positions.md")
    with open(path, "w") as f:
        f.write(report(results, cfg))
    for x in results:
        print(f"{x['action']:4} {x['token']}: {x['gain_pct']:+.1f}%  stop {x['stop']:.8g}  {'; '.join(x['warnings'])}")
    print(path)


if __name__ == "__main__":
    sys.exit(main())
