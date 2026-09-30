#!/usr/bin/env python3
"""Read a token's hourly chart and label the trend.

Uses free GeckoTerminal OHLCV candles. The goal is "buy low, sell high":
enter on pullbacks inside an uptrend, not on vertical candles, and treat a
broken trend as a warning to exit.

Usage:
    python3 scanner/chart.py solana <pair_address>
"""
import json
import sys
import time
import urllib.request

GT = "https://api.geckoterminal.com/api/v2/networks/{net}/pools/{pool}/ohlcv/hour?aggregate=1&limit=72"
NETWORKS = {"solana": "solana", "base": "base", "ethereum": "eth", "bsc": "bsc"}


def fetch_candles(chain, pair_address):
    """Return candles oldest->newest as dicts with o/h/l/c/v."""
    url = GT.format(net=NETWORKS.get(chain, chain), pool=pair_address)
    req = urllib.request.Request(url, headers={"User-Agent": "claude-fomo-scanner/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.load(resp)["data"]["attributes"]["ohlcv_list"]
    time.sleep(2)  # free API allows ~30 calls/min
    return [{"t": r[0], "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]} for r in sorted(rows)]


def ema(values, n):
    k, out = 2 / (n + 1), values[0]
    for v in values[1:]:
        out = v * k + out * (1 - k)
    return out


def analyze(candles):
    """Label the trend from hourly candles. Needs at least 24 candles."""
    if len(candles) < 24:
        return {"trend": "TOO NEW", "note": f"only {len(candles)}h of chart history"}
    closes = [c["c"] for c in candles]
    last = closes[-1]
    ema20 = ema(closes, 20)
    recent = candles[-24:]
    lows = [min(c["l"] for c in recent[i:i + 8]) for i in (0, 8, 16)]
    higher_lows = lows[0] < lows[1] < lows[2]
    high = max(c["h"] for c in candles)
    drawdown = (1 - last / high) * 100
    # Bounce-back: how much of the deepest dip after the high has been recovered.
    hi_idx = max(range(len(candles)), key=lambda i: candles[i]["h"])
    after = candles[hi_idx:]
    dip = min(c["l"] for c in after)
    recovered = (last - dip) / (high - dip) * 100 if high > dip else 100.0
    vol_now = sum(c["v"] for c in candles[-6:])
    vol_prev = sum(c["v"] for c in candles[-12:-6]) or 1

    if last > ema20 * 1.5:
        trend, note = "EXTENDED", "far above average: wait for a pullback, don't chase"
    elif last > ema20 and higher_lows:
        trend, note = "UPTREND", "higher lows and above average"
    elif higher_lows and drawdown < 30:
        trend, note = "PULLBACK", "dip inside an uptrend: best entry zone if hype holds"
    elif last < ema20 and not higher_lows:
        trend, note = "DOWNTREND", "lower lows and below average: avoid, or exit if holding"
    else:
        trend, note = "CHOP", "no clear direction"
    return {
        "trend": trend,
        "note": note,
        "price_vs_ema20_pct": (last / ema20 - 1) * 100,
        "higher_lows": higher_lows,
        "drawdown_from_high_pct": drawdown,
        "recovered_from_dip_pct": recovered,
        "volume_6h_vs_prev_6h": vol_now / vol_prev,
        "hours_of_data": len(candles),
    }


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    for k, v in analyze(fetch_candles(sys.argv[1], sys.argv[2])).items():
        print(f"{k:>24}: {v:.2f}" if isinstance(v, float) else f"{k:>24}: {v}")


if __name__ == "__main__":
    main()
