#!/usr/bin/env python3
"""Watch your coins and the market, and push buy/sell alerts to your phone.

Fomo has no limit or stop orders, so this is your stop-loss: leave it running
on a computer that stays on, and your phone buzzes when it's time to act.

Alerts go through ntfy.sh (free, no account):
  1. Install the "ntfy" app on your phone (iOS / Android).
  2. Run this once. It creates a private topic name, saves it in config.json,
     and prints it.
  3. In the ntfy app, tap + and subscribe to that topic name.

You get:
  * SELL now: a coin hit its stop (any time of day, urgent, repeats every 30 min
    until you sell and remove it from journal/positions.csv)
  * 2x reached: your stop moved up to the +30% floor
  * Warning: hype fading (downtrend, sellers > buyers, holders falling)
  * Buy idea: a strong candidate and you have an open slot (only between the
    buy_alert_hours_pt in config.json, so no 3am buy ideas)

Usage:
    python3 scanner/watch.py           # keep running
    python3 scanner/watch.py --once    # one check, then exit
    python3 scanner/watch.py --test    # send a test alert
"""
import argparse
import json
import os
import secrets
import sys
import time
import urllib.request
from datetime import datetime

import chart
import evening
import positions
import safety
import scan

STATE = os.path.join(scan.ROOT, "output", "alert_state.json")
CONFIG = os.path.join(scan.ROOT, "config.json")


def ensure_topic(cfg):
    topic = cfg["alerts"].get("ntfy_topic")
    if not topic:
        topic = f"fomo-{secrets.token_hex(6)}"  # random: anyone who knows the name can read it
        cfg["alerts"]["ntfy_topic"] = topic
        with open(CONFIG, "w") as f:
            f.write(json.dumps(cfg, indent=2) + "\n")
        print(f"Created alert topic '{topic}' and saved it to config.json. Subscribe to it in the ntfy app.")
    return topic


PRIORITY = {"default": 3, "high": 4, "urgent": 5}


def send(topic, title, message, priority="default", tags="", url=None):
    print(f"[{datetime.now():%H:%M}] {title}: {message}")
    body = {"topic": topic, "title": title, "message": message, "priority": PRIORITY[priority],
            "tags": [t for t in tags.split(",") if t]}
    if url:
        body["click"] = url
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15).close()
    except Exception as e:
        print(f"   !! alert not delivered ({e})", file=sys.stderr)


def position_alerts(results, state):
    """Yield (key, title, message, priority, tags) for position changes not already alerted."""
    for x in results:
        t = x["token"]
        if x["action"] == "SELL":
            yield (f"{t}:sell", f"SELL {t} now",
                   f"{x['gain_pct']:+.0f}% · price {x['price']:.6g} hit stop {x['stop']:.6g}. "
                   f"{'; '.join(x['warnings'])}".strip(), "urgent", "rotating_light")
        elif x["mode"].startswith("LOCKED"):
            yield (f"{t}:locked", f"{t} hit 2x 🎯",
                   f"Now {x['gain_pct']:+.0f}%. Stop raised to {x['stop']:.6g} (+30% floor). Holding is fine; "
                   "you'll get a SELL alert if it falls back.", "high", "tada")
        for w in x["warnings"]:
            if "while you were away" not in w:
                yield (f"{t}:warn:{w.split(' (')[0]}", f"Warning: {t}",
                       f"{w}. Now {x['gain_pct']:+.0f}%. Consider selling early.", "default", "warning")


def buy_alerts(watch, cfg):
    a = cfg["alerts"]
    for w in watch:
        if w["score"] < a["min_buy_score"] or w.get("chart_trend") not in ("PULLBACK", "UPTREND"):
            continue
        p = scan.trade_plan(w, cfg)
        age_h = (w["age_minutes"] or 0) / 60
        yield (f"buy:{w['chain']}:{w['token_address']}", f"Buy idea: {w['symbol']} ({scan.chain_label(w, cfg)})",
               f"Score {w['score']}, chart {w['chart_trend']}, {age_h:.0f}h old"
               f"{', hype: ' + ' '.join(w['hype']) if w['hype'] else ''}, safety {w.get('safety', 'unchecked')}. "
               f"Price {w['price_usd']:.6g}. "
               f"Buy ${p['position_usd']:.0f}, stop {p['stop_price']:.6g}. Run the research checklist first.",
               "high", "moneybag", w["url"])


def check_once(cfg, state, do_scan, now=None):
    now = now or time.time()
    topic = cfg["alerts"]["ntfy_topic"]
    held, _ = positions.run(cfg)
    fresh = []
    for key, title, msg, prio, tags in position_alerts(held, state):
        repeat = key.endswith(":sell") and now - state.get(key, now) >= 1800  # nag every 30 min until sold
        if key not in state or repeat:
            fresh.append((key, title, msg, prio, tags, None))
    if do_scan:
        hour = datetime.fromtimestamp(now, evening.PT).hour
        lo, hi = cfg["alerts"]["buy_alert_hours_pt"]
        acct = evening.account_status(cfg)
        slots = cfg["risk"]["max_open_positions"] - sum(x["action"] == "HOLD" for x in held)
        if lo <= hour < hi and slots > 0 and not (acct["halted"] or acct["day_halted"]):
            pairs = scan.fetch_candidate_pairs(cfg["chains"], cfg.get("hype_keywords", []))
            rows, _ = scan.run(pairs, cfg, os.path.join(scan.ROOT, "output", "scans"), candles_fn=chart.fetch_candles,
                               safety_fn=safety.check,
                               history_path=os.path.join(scan.ROOT, "output", "history.csv"))
            ideas = [a for a in buy_alerts([r for r in rows if r["verdict"] == "WATCH"], cfg)
                     if now - state.get(a[0], 0) > 86400][:slots]  # same coin at most once a day
            fresh += ideas
    for key, title, msg, prio, tags, url in fresh:
        send(topic, title, msg, prio, tags, url)
        state[key] = now
    # forget alerts for coins you no longer hold, so a re-buy alerts again
    held_names = {x["token"] for x in held}
    for key in [k for k in state if not k.startswith("buy:") and k.split(":")[0] not in held_names]:
        del state[key]
    return fresh


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(state, f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()
    cfg = scan.load_config()
    topic = ensure_topic(cfg)
    if args.test:
        send(topic, "Fomo alerts working ✅", "You'll get SELL, 2x, warning and buy-idea alerts here.", "high", "white_check_mark")
        return
    a = cfg["alerts"]
    last_scan = 0.0
    while True:
        do_scan = time.time() - last_scan >= a["scan_minutes"] * 60
        state = load_state()
        try:
            check_once(cfg, state, do_scan)
            if do_scan:
                last_scan = time.time()
        except Exception as e:  # network hiccups shouldn't kill the watcher
            print(f"[{datetime.now():%H:%M}] check failed: {e}", file=sys.stderr)
        save_state(state)
        if args.once:
            return
        cfg = scan.load_config()  # pick up edits to config / positions without restarting
        time.sleep(a["check_positions_minutes"] * 60)


if __name__ == "__main__":
    sys.exit(main())
