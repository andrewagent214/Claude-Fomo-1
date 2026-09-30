#!/usr/bin/env python3
"""Compute real performance statistics from your own trade journal.

Reads journal/trades.csv (one row per closed trade) and writes
output/reports/performance.md. These are the only "true statistics" that
matter: your actual results, after fees, by setup.

Usage:
    python3 scanner/stats.py [--journal FILE] [--out DIR]
"""
import argparse
import csv
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_trades(path):
    trades = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if not row.get("exit_price"):
                continue  # still open
            entry, exit_, size = float(row["entry_price"]), float(row["exit_price"]), float(row["size_usd"])
            fees = float(row.get("fees_usd") or 0)
            pnl = size * (exit_ / entry - 1) - fees
            trades.append({**row, "pnl_usd": pnl, "return_pct": pnl / size * 100})
    return trades


def summarize(trades):
    if not trades:
        return None
    wins = [t["pnl_usd"] for t in trades if t["pnl_usd"] > 0]
    losses = [t["pnl_usd"] for t in trades if t["pnl_usd"] <= 0]
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        equity += t["pnl_usd"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    gross_loss = -sum(losses)
    return {
        "trades": len(trades),
        "win_rate_pct": len(wins) / len(trades) * 100,
        "net_pnl_usd": sum(t["pnl_usd"] for t in trades),
        "avg_win_usd": sum(wins) / len(wins) if wins else 0,
        "avg_loss_usd": sum(losses) / len(losses) if losses else 0,
        "profit_factor": sum(wins) / gross_loss if gross_loss else float("inf"),
        "expectancy_usd": sum(t["pnl_usd"] for t in trades) / len(trades),
        "max_drawdown_usd": max_dd,
        "best_usd": max(t["pnl_usd"] for t in trades),
        "worst_usd": min(t["pnl_usd"] for t in trades),
    }


def fmt(s):
    pf = "∞" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
    return (f"| {s['trades']} | {s['win_rate_pct']:.1f}% | ${s['net_pnl_usd']:,.2f} | ${s['avg_win_usd']:,.2f} | "
            f"${s['avg_loss_usd']:,.2f} | {pf} | ${s['expectancy_usd']:,.2f} | ${s['max_drawdown_usd']:,.2f} |")


HEADER = ["| Trades | Win rate | Net P&L | Avg win | Avg loss | Profit factor | Expectancy/trade | Max drawdown |",
          "|---|---|---|---|---|---|---|---|"]


def report(trades):
    s = summarize(trades)
    if not s:
        return "# Performance\n\nNo closed trades in the journal yet.\n"
    lines = ["# Performance", "", "## Overall", "", *HEADER, fmt(s), ""]
    if s["trades"] < 30:
        lines += [f"> Only {s['trades']} trades. Under ~30 trades these numbers are mostly noise, "
                  "so don't change the rules based on them yet.", ""]
    for key, title in (("setup", "By setup"), ("rule_followed", "Followed the plan?")):
        groups = defaultdict(list)
        for t in trades:
            groups[t.get(key) or "(blank)"].append(t)
        lines += [f"## {title}", "", "| Group " + HEADER[0], "|---" + HEADER[1]]
        for g, ts in sorted(groups.items()):
            lines.append(f"| {g} " + fmt(summarize(ts)))
        lines.append("")
    lines += ["## Trade log", "", "| Date | Token | Setup | Size | Return | P&L | Exit reason |", "|---|---|---|---|---|---|---|"]
    for t in trades:
        lines.append(f"| {t['date']} | {t['token']} | {t.get('setup', '')} | ${float(t['size_usd']):,.2f} | "
                     f"{t['return_pct']:+.1f}% | ${t['pnl_usd']:,.2f} | {t.get('exit_reason', '')} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", default=os.path.join(ROOT, "journal", "trades.csv"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "reports"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "performance.md")
    with open(path, "w") as f:
        f.write(report(load_trades(args.journal)))
    print(path)


if __name__ == "__main__":
    main()
