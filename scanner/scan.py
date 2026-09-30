#!/usr/bin/env python3
"""Screen newly-promoted and hype-keyword meme coins using public market data.

This does NOT predict price. It applies hard safety filters and a simple
momentum score so you only spend research time on tokens that pass basic
liquidity/activity checks. Every number in the report comes straight from the
API response at scan time.

Usage:
    python3 scanner/scan.py                 # live scan (needs internet)
    python3 scanner/scan.py --fixture FILE  # offline scan of saved pair data
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import chart
import safety

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.dexscreener.com"


def load_config(path=os.path.join(ROOT, "config.json")):
    with open(path) as f:
        return json.load(f)


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "claude-fomo-scanner/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def fetch_candidate_pairs(chains, keywords=()):
    """Latest token profiles + top boosted tokens + keyword searches -> trading pairs."""
    pairs = []
    for kw in keywords:
        found = get_json(f"{API}/latest/dex/search?q={urllib.parse.quote(kw)}").get("pairs") or []
        pairs.extend(p for p in found if p.get("chainId") in chains)
        time.sleep(0.25)
    tokens = {}
    for endpoint in ("/token-profiles/latest/v1", "/token-boosts/top/v1"):
        for item in get_json(API + endpoint):
            if item.get("chainId") in chains:
                tokens.setdefault(item["chainId"], set()).add(item["tokenAddress"])

    for chain, addrs in tokens.items():
        addrs = sorted(addrs)
        for i in range(0, len(addrs), 30):  # API accepts up to 30 addresses per call
            pairs.extend(get_json(f"{API}/tokens/v1/{chain}/{','.join(addrs[i:i + 30])}"))
            time.sleep(0.25)
    return pairs


def best_pair_per_token(pairs):
    """Keep the most liquid pair for each base token."""
    best = {}
    for p in pairs:
        key = (p.get("chainId"), p.get("baseToken", {}).get("address"))
        liq = (p.get("liquidity") or {}).get("usd") or 0
        if key not in best or liq > ((best[key].get("liquidity") or {}).get("usd") or 0):
            best[key] = p
    return list(best.values())


def hype_match(p, keywords):
    text = f"{p.get('baseToken', {}).get('name', '')} {p.get('baseToken', {}).get('symbol', '')}".lower()
    return [k for k in keywords if k in text]


def metrics(p, now_ms):
    txns_1h = (p.get("txns") or {}).get("h1") or {}
    buys, sells = txns_1h.get("buys", 0), txns_1h.get("sells", 0)
    liq = (p.get("liquidity") or {}).get("usd") or 0
    vol24 = (p.get("volume") or {}).get("h24") or 0
    fdv = p.get("fdv") or p.get("marketCap") or 0
    created = p.get("pairCreatedAt")
    return {
        "chain": p.get("chainId"),
        "symbol": p.get("baseToken", {}).get("symbol"),
        "name": p.get("baseToken", {}).get("name"),
        "token_address": p.get("baseToken", {}).get("address"),
        "dex": p.get("dexId"),
        "pair_address": p.get("pairAddress"),
        "url": p.get("url"),
        "price_usd": float(p.get("priceUsd") or 0),
        "liquidity_usd": liq,
        "volume_24h_usd": vol24,
        "fdv_usd": fdv,
        "age_minutes": (now_ms - created) / 60000 if created else None,
        "txns_1h": buys + sells,
        "buy_sell_ratio_1h": buys / sells if sells else float(buys > 0) * 99,
        "change_1h_pct": (p.get("priceChange") or {}).get("h1") or 0,
        "change_24h_pct": (p.get("priceChange") or {}).get("h24") or 0,
        "vol_to_liq": vol24 / liq if liq else 0,
        "fdv_to_liq": fdv / liq if liq else float("inf"),
    }


def evaluate(m, cfg):
    """Return (verdict, score, reasons). Verdict is WATCH or AVOID, never BUY."""
    f, s = cfg["filters"], cfg["scoring"]
    fails = []
    if m["liquidity_usd"] < f["min_liquidity_usd"]:
        fails.append(f"liquidity ${m['liquidity_usd']:,.0f} < ${f['min_liquidity_usd']:,}")
    if m["volume_24h_usd"] < f["min_volume_24h_usd"]:
        fails.append(f"24h volume ${m['volume_24h_usd']:,.0f} < ${f['min_volume_24h_usd']:,}")
    if m["age_minutes"] is None or m["age_minutes"] < f["min_age_minutes"]:
        fails.append("pair too new / unknown age")
    elif m["age_minutes"] > f["max_age_days"] * 1440:
        fails.append(f"older than {f['max_age_days']}d")
    if m["txns_1h"] < f["min_txns_1h"]:
        fails.append(f"only {m['txns_1h']} txns in 1h")
    if m["change_24h_pct"] > f["max_price_change_24h_pct"]:
        fails.append(f"already +{m['change_24h_pct']:.0f}% in 24h (chasing)")
    if m["fdv_to_liq"] > f["max_fdv_to_liquidity"]:
        fails.append(f"FDV/liquidity {m['fdv_to_liq']:.0f}x (thin exit)")
    if fails:
        return "AVOID", 0, fails

    score, reasons = 0, []
    if m["buy_sell_ratio_1h"] >= s["buy_sell_ratio_1h_good"]:
        score += 1
        reasons.append(f"buys/sells 1h {m['buy_sell_ratio_1h']:.2f}")
    if s["volume_to_liquidity_good"] <= m["vol_to_liq"] <= s["volume_to_liquidity_too_hot"]:
        score += 1
        reasons.append(f"vol/liq {m['vol_to_liq']:.1f}x")
    if m["change_1h_pct"] > 0:
        score += 1
        reasons.append(f"1h {m['change_1h_pct']:+.1f}%")
    if m["liquidity_usd"] >= 2 * f["min_liquidity_usd"]:
        score += 1
        reasons.append("deep liquidity")
    return "WATCH", score, reasons


def chain_label(r, cfg):
    """Chain name, with a gas warning where fees eat into a $20 trade."""
    return r["chain"] + (" ⛽" if r["chain"] in cfg.get("high_gas_chains", []) else "")


def trade_plan(m, cfg):
    """Position size and exit levels derived from config risk rules."""
    r = cfg["risk"]
    risk_usd = r["account_size_usd"] * r["max_risk_per_trade_pct"] / 100
    size = risk_usd / (r["stop_loss_pct"] / 100)
    price = m["price_usd"]
    return {
        "position_usd": round(size, 2),
        "stop_price": price * (1 - r["stop_loss_pct"] / 100),
        "lock_in_price": price * r["lock_in_trigger_multiple"],
        "floor_price": price * (1 + r["lock_in_floor_gain_pct"] / 100),
    }


HISTORY_FIELDS = ["captured_at", "chain", "token_address", "symbol", "price_usd", "fdv_usd",
                  "liquidity_usd", "volume_24h_usd", "txns_1h", "buy_sell_ratio_1h"]


def update_history(rows, path, stamp):
    """Append this scan to the history file and attach growth since first seen."""
    first = {}
    if os.path.exists(path):
        with open(path) as f:
            for h in csv.DictReader(f):
                key = (h["chain"], h["token_address"])
                if key not in first:
                    first[key] = {**h, "scans": 0}
                first[key]["scans"] += 1
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({**r, "captured_at": stamp})
    for r in rows:
        h = first.get((r["chain"], r["token_address"]))
        r["times_seen"] = (h["scans"] if h else 0) + 1
        r["first_seen"] = h["captured_at"] if h else stamp
        old_fdv = float(h["fdv_usd"]) if h and h["fdv_usd"] else 0
        r["fdv_growth_pct"] = (r["fdv_usd"] / old_fdv - 1) * 100 if old_fdv else None


def write_outputs(rows, cfg, out_dir, stamp):
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, f"scan_{stamp}.csv")
    fields = ["verdict", "score", "chain", "symbol", "price_usd", "liquidity_usd", "volume_24h_usd",
              "fdv_usd", "age_minutes", "txns_1h", "buy_sell_ratio_1h", "change_1h_pct",
              "change_24h_pct", "vol_to_liq", "fdv_to_liq", "hype", "safety", "chart_trend", "times_seen",
              "fdv_growth_pct", "token_address", "pair_address", "url", "reasons"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "reasons": "; ".join(r["reasons"]), "hype": " ".join(r["hype"])})

    watch = [r for r in rows if r["verdict"] == "WATCH"]
    md = [f"# Scan {stamp}", "",
          f"Pairs screened: **{len(rows)}** · passed filters: **{len(watch)}** · "
          f"rejected: **{len(rows) - len(watch)}**", "",
          "> WATCH = worth researching with docs/RESEARCH_CHECKLIST.md. It is not a buy signal.",
          "> Best entries: chart = PULLBACK or UPTREND. Skip EXTENDED (chasing) and DOWNTREND.",
          "> Safety OK = RugCheck / honeypot.is found no known trap. unchecked = do contract checks by hand.", "",
          "## Watchlist", ""]
    if watch:
        md += ["| Score | Token | Chain | Safety | Chart | Hype | Price | Liquidity | 24h Vol | 1h | 24h | Mcap growth (seen) "
               "| Size | Stop | 2x lock-in | Floor after lock |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in watch:
            p = trade_plan(r, cfg)
            growth = "new" if r.get("fdv_growth_pct") is None else f"{r['fdv_growth_pct']:+.0f}% ({r['times_seen']}x)"
            md.append(f"| {r['score']} | [{r['symbol']}]({r['url']}) | {chain_label(r, cfg)} | {r.get('safety', 'unchecked')} | {r.get('chart_trend', 'n/a')} | "
                      f"{' '.join(r['hype']) or '-'} | {r['price_usd']:.8g} | "
                      f"${r['liquidity_usd']:,.0f} | ${r['volume_24h_usd']:,.0f} | {r['change_1h_pct']:+.1f}% | "
                      f"{r['change_24h_pct']:+.1f}% | {growth} | ${p['position_usd']} | {p['stop_price']:.8g} | "
                      f"{p['lock_in_price']:.8g} | {p['floor_price']:.8g} |")
        if any(r["chain"] in cfg.get("high_gas_chains", []) for r in watch):
            md += ["", "> ⛽ = network fees can be several dollars per swap, a big bite out of a $20 trade. Check the fee "
                   "Fomo quotes before buying."]
        if any(r["hype"] for r in watch):
            md += ["", "> **Hype-keyword tokens:** a Trump/Elon name does NOT mean Trump or Elon is involved. "
                   "Almost all are unofficial. Only trust a contract address posted by the person's verified account."]
    else:
        md.append("Nothing passed the filters. Not trading is a valid outcome.")
    md += ["", "## Rejected (top reasons)", ""]
    for r in [r for r in rows if r["verdict"] == "AVOID"][:25]:
        md.append(f"- **{r['symbol']}** ({r['chain']}): {'; '.join(r['reasons'])}")
    md_path = os.path.join(out_dir, f"scan_{stamp}.md")
    with open(md_path, "w") as f:
        f.write("\n".join(md) + "\n")
    return csv_path, md_path


def add_chart(r, candles_fn):
    try:
        c = chart.analyze(candles_fn(r["chain"], r["pair_address"]))
    except Exception as e:  # chart data is a bonus, never block the scan
        r["chart_trend"] = f"n/a ({type(e).__name__})"
        return
    r["chart_trend"] = c["trend"]
    if c["trend"] in ("PULLBACK", "UPTREND"):
        r["score"] += 1
        r["reasons"].append(f"chart {c['trend']}")
    elif c["trend"] in ("DOWNTREND", "EXTENDED"):
        r["score"] -= 1
        r["reasons"].append(f"chart {c['trend']}: {c['note']}")


def add_safety(r, safety_fn, cfg):
    res = safety_fn(r["chain"], r["token_address"], cfg.get("safety", {}).get("max_tax_pct", 10))
    r["safety"] = res["status"]
    if res["status"] == "FAIL":
        r["verdict"], r["score"], r["reasons"] = "AVOID", 0, res["notes"]
    else:
        r["reasons"].extend(res["notes"])


def run(pairs, cfg, out_dir, now_ms=None, candles_fn=None, history_path=None, safety_fn=None):
    now_ms = now_ms or int(time.time() * 1000)
    rows = []
    for p in best_pair_per_token(pairs):
        m = metrics(p, now_ms)
        verdict, score, reasons = evaluate(m, cfg)
        hype = hype_match(p, cfg.get("hype_keywords", []))
        if hype and verdict == "WATCH":
            score += 1
            reasons.append("hype keyword")
        rows.append({**m, "verdict": verdict, "score": score, "reasons": reasons, "hype": hype})
    if safety_fn:
        for r in rows:
            if r["verdict"] == "WATCH" and r["token_address"]:
                add_safety(r, safety_fn, cfg)
    if candles_fn:
        for r in rows:
            if r["verdict"] == "WATCH" and r["pair_address"]:
                add_chart(r, candles_fn)
    rows.sort(key=lambda r: (r["verdict"] != "WATCH", -r["score"], -r["liquidity_usd"]))
    stamp = datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    if history_path:
        update_history(rows, history_path, stamp)
    return rows, write_outputs(rows, cfg, out_dir, stamp)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", help="JSON file of DexScreener pair objects (offline mode)")
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "scans"))
    ap.add_argument("--no-charts", action="store_true", help="skip GeckoTerminal chart checks")
    ap.add_argument("--no-safety", action="store_true", help="skip RugCheck / honeypot.is contract checks")
    args = ap.parse_args()
    cfg = load_config()
    if args.fixture:
        with open(args.fixture) as f:
            data = json.load(f)
        pairs, now_ms, candles_fn, history = data["pairs"], data.get("captured_at_ms"), None, None
        safety_fn = None
    else:
        pairs, now_ms = fetch_candidate_pairs(cfg["chains"], cfg.get("hype_keywords", [])), None
        candles_fn = None if args.no_charts else chart.fetch_candles
        safety_fn = None if args.no_safety else safety.check
        history = os.path.join(ROOT, "output", "history.csv")
    rows, (csv_path, md_path) = run(pairs, cfg, args.out, now_ms, candles_fn, history, safety_fn)
    print(f"Screened {len(rows)} tokens, {sum(r['verdict'] == 'WATCH' for r in rows)} on watchlist")
    print(f"  {md_path}\n  {csv_path}")


if __name__ == "__main__":
    sys.exit(main())
