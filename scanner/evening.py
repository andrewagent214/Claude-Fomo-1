#!/usr/bin/env python3
"""One command for your 9-10pm PT session: checks what you hold, scans for new
coins, and writes a single brief to output/reports/evening_<date>.md.

Usage:
    python3 scanner/evening.py              # full brief
    python3 scanner/evening.py --no-scan    # positions only (faster)
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import chart
import positions
import scan
import stats

try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:  # no tz database: fall back to UTC-7
    PT = timezone(timedelta(hours=-7))


def account_status(cfg):
    r = cfg["risk"]
    trades = stats.load_trades(os.path.join(scan.ROOT, "journal", "trades.csv"))
    realized = sum(t["pnl_usd"] for t in trades)
    today = datetime.now(PT).date().isoformat()
    today_pnl = sum(t["pnl_usd"] for t in trades if t["date"].startswith(today))
    return {"realized": realized, "cash_basis": r["account_size_usd"] + realized, "today": today_pnl,
            "halted": realized <= -r["total_loss_limit_usd"], "day_halted": today_pnl <= -r["daily_loss_limit_usd"]}


def brief(cfg, held, acct, watch):
    r = cfg["risk"]
    unreal = sum(x["value"] - x["size"] for x in held)
    lines = [f"# Evening brief · {datetime.now(PT):%a %b %d, %I:%M %p} PT", "",
             "## Account", "",
             f"- Realized P&L: **${acct['realized']:+,.2f}** · open P&L: **${unreal:+,.2f}**",
             f"- Estimated account: **${acct['cash_basis'] + unreal:,.2f}** (goal ${r['goal_usd']}, "
             f"stop-trading level ${r['account_size_usd'] - r['total_loss_limit_usd']})", ""]
    if acct["halted"]:
        lines += [f"> 🛑 **${r['total_loss_limit_usd']} loss limit reached. Don't open new trades.** Review the journal with Claude first.", ""]
    elif acct["day_halted"]:
        lines += [f"> 🛑 Daily loss limit (${r['daily_loss_limit_usd']}) hit. No new trades tonight.", ""]

    lines += ["## 1. Act on these first", ""]
    sells = [x for x in held if x["action"] == "SELL"]
    if sells:
        for x in sells:
            lines.append(f"- **SELL {x['token']}** now ({x['gain_pct']:+.1f}%). {'; '.join(x['warnings'])}")
    else:
        lines.append("- Nothing to sell. " + ("All positions are above their stops." if held else "No open positions."))
    for x in held:
        if x["action"] == "HOLD" and x["warnings"]:
            lines.append(f"- ⚠️ {x['token']}: {'; '.join(x['warnings'])}. Consider selling early.")
    lines.append("")

    if held:
        lines += ["## 2. Your coins", "", "| Action | Token | Gain | Now | Stop | Stop mode | Chart |", "|---|---|---|---|---|---|---|"]
        for x in held:
            lines.append(f"| {x['action']} | {x['token']} | {x['gain_pct']:+.1f}% | {x['price']:.8g} | "
                         f"{x['stop']:.8g} | {x['mode']} | {x['trend']} |")
        lines.append("")

    slots = r["max_open_positions"] - sum(x["action"] == "HOLD" for x in held)
    lines += ["## 3. New trade ideas", ""]
    if acct["halted"] or acct["day_halted"]:
        lines.append("Skipped: loss limit hit.")
    elif slots <= 0:
        lines.append(f"Skipped: you already hold {r['max_open_positions']} coins (max).")
    elif watch is None:
        lines.append("Scan not run (--no-scan).")
    elif not watch:
        lines.append("Nothing passed the filters tonight. Not trading is a valid outcome.")
    else:
        lines += [f"{slots} open slot(s). Top candidates (research each with docs/RESEARCH_CHECKLIST.md):", "",
                  "| Score | Token | Chart | Hype | Age | 1h | 24h | Buy size | Stop | 2x lock-in |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for w in watch[:5]:
            p = scan.trade_plan(w, cfg)
            age_h = (w["age_minutes"] or 0) / 60
            age = f"{age_h:.0f}h" if age_h < 48 else f"{age_h / 24:.0f}d"
            lines.append(f"| {w['score']} | [{w['symbol']}]({w['url']}) | {w.get('chart_trend', 'n/a')} | "
                         f"{' '.join(w['hype']) or '-'} | {age}{' ⚠️' if age_h < 24 else ''} | {w['change_1h_pct']:+.1f}% | "
                         f"{w['change_24h_pct']:+.1f}% | ${p['position_usd']} | {p['stop_price']:.8g} | {p['lock_in_price']:.8g} |")
        lines += ["", "⚠️ = under 24h old. These can crash overnight while you're offline. Only buy one if you'll "
                  "stay on longer tonight, and never one whose chart says EXTENDED."]
    lines += ["", "## 4. Before you log off", "",
              "- For each coin you hold, set a **limit sell order at the Stop price** above, if the Fomo app offers "
              "limit/stop orders. It's the only protection while you're away.",
              "- If the app has no such orders, only hold coins you're OK seeing drop sharply before tomorrow night.",
              "- Log any sells in journal/trades.csv and update journal/positions.csv (and the holders column).", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-scan", action="store_true")
    args = ap.parse_args()
    cfg = scan.load_config()
    held, _ = positions.run(cfg)
    watch = None
    if not args.no_scan:
        pairs = scan.fetch_candidate_pairs(cfg["chains"], cfg.get("hype_keywords", []))
        rows, _ = scan.run(pairs, cfg, os.path.join(scan.ROOT, "output", "scans"), candles_fn=chart.fetch_candles,
                           history_path=os.path.join(scan.ROOT, "output", "history.csv"))
        watch = [w for w in rows if w["verdict"] == "WATCH" and w.get("chart_trend") not in ("DOWNTREND", "EXTENDED")]
    out = os.path.join(scan.ROOT, "output", "reports")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"evening_{datetime.now(PT):%Y-%m-%d}.md")
    with open(path, "w") as f:
        f.write(brief(cfg, held, account_status(cfg), watch))
    print(path)


if __name__ == "__main__":
    sys.exit(main())
