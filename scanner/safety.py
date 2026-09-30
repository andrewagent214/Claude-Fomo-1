#!/usr/bin/env python3
"""Automated contract-safety check: RugCheck (Solana) and honeypot.is (EVM).

Covers the first part of docs/RESEARCH_CHECKLIST.md automatically:
  * Solana: mint/freeze authority, unlocked LP, holder concentration (RugCheck)
  * Base / BNB / Ethereum: honeypot simulation, buy/sell tax (honeypot.is)

A FAIL drops the token from the watchlist. "unchecked" (API down, chain not
covered) does not, but you must then do that part of the checklist by hand.
A PASS is not a guarantee: these tools catch known traps, not every rug.

Usage:
    python3 scanner/safety.py solana <token_address>
    python3 scanner/safety.py base <token_address>
"""
import json
import sys
import time
import urllib.parse
import urllib.request

RUGCHECK = "https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
HONEYPOT = "https://api.honeypot.is/v2/IsHoneypot?"
# DexScreener chain id -> EVM chain id honeypot.is simulates on
EVM_CHAIN_IDS = {"ethereum": 1, "bsc": 56, "base": 8453}
BAD_EVM_RISK = ("honeypot", "very_high", "high")


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "claude-fomo-scanner/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def judge_rugcheck(report):
    """RugCheck summary -> (status, notes). Any 'danger' risk is a FAIL."""
    risks = report.get("risks") or []
    danger = [r["name"] for r in risks if r.get("level") == "danger"]
    warn = [r["name"] for r in risks if r.get("level") == "warn"]
    if report.get("rugged"):
        danger.insert(0, "marked rugged")
    if danger:
        return "FAIL", [f"RugCheck danger: {d}" for d in danger]
    return "OK", [f"RugCheck warn: {w}" for w in warn]


def judge_honeypot(report, max_tax_pct):
    """honeypot.is v2 response -> (status, notes)."""
    hp = report.get("honeypotResult") or {}
    if hp.get("isHoneypot"):
        return "FAIL", [f"honeypot: {hp.get('honeypotReason') or 'cannot sell'}"]
    if not report.get("simulationSuccess"):
        return "FAIL", ["sell could not be simulated (treat as honeypot)"]
    sim = report.get("simulationResult") or {}
    fails = [f"{side} tax {sim[k]:.0f}%" for side, k in (("buy", "buyTax"), ("sell", "sellTax"))
             if (sim.get(k) or 0) > max_tax_pct]
    risk = (report.get("summary") or {}).get("risk")
    if risk in BAD_EVM_RISK:
        fails.append(f"honeypot.is risk {risk}")
    if fails:
        return "FAIL", fails
    flags = [f.get("description") or f.get("flag") for f in (report.get("summary") or {}).get("flags") or []]
    return "OK", [f"honeypot.is: {f}" for f in flags if f]


def check(chain, token_address, max_tax_pct=10, fetch=get_json):
    """Return {"status": OK | FAIL | unchecked, "notes": [...]}. Never raises."""
    try:
        if chain == "solana":
            status, notes = judge_rugcheck(fetch(RUGCHECK.format(mint=token_address)))
            time.sleep(1)  # public API is rate limited
        elif chain in EVM_CHAIN_IDS:
            q = urllib.parse.urlencode({"address": token_address, "chainID": EVM_CHAIN_IDS[chain]})
            status, notes = judge_honeypot(fetch(HONEYPOT + q), max_tax_pct)
            time.sleep(1)
        else:
            return {"status": "unchecked", "notes": [f"no automated check for {chain}"]}
    except Exception as e:  # a down API must not block the scan; the manual checklist still applies
        return {"status": "unchecked", "notes": [f"safety API error ({type(e).__name__})"]}
    return {"status": status, "notes": notes}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    res = check(sys.argv[1], sys.argv[2])
    print(res["status"])
    for n in res["notes"]:
        print(f"  - {n}")
