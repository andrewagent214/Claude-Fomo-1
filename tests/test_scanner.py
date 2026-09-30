import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scanner"))

import chart  # noqa: E402
import evening  # noqa: E402
import positions  # noqa: E402
import safety  # noqa: E402
import scan  # noqa: E402
import stats  # noqa: E402
import watch  # noqa: E402


class ScanTest(unittest.TestCase):
    def test_filters_and_dedup(self):
        with open(os.path.join(ROOT, "tests", "fixtures", "sample_pairs.json")) as f:
            data = json.load(f)
        with tempfile.TemporaryDirectory() as d:
            rows, (csv_path, md_path) = scan.run(data["pairs"], scan.load_config(), d, data["captured_at_ms"])
            self.assertTrue(os.path.exists(csv_path) and os.path.exists(md_path))
        by_sym = {r["symbol"]: r for r in rows}
        self.assertEqual(len(rows), 5)  # duplicate GOODA pair collapsed to most liquid
        self.assertEqual(by_sym["GOODA"]["verdict"], "WATCH")
        self.assertEqual(by_sym["GOODA"]["score"], 4)
        for sym in ("THINLQ", "BABY", "PUMPED"):
            self.assertEqual(by_sym[sym]["verdict"], "AVOID", sym)
        self.assertEqual(by_sym["TRUMPCAT"]["verdict"], "WATCH")
        self.assertEqual(by_sym["TRUMPCAT"]["hype"], ["trump"])

    def test_history_growth(self):
        with open(os.path.join(ROOT, "tests", "fixtures", "sample_pairs.json")) as f:
            data = json.load(f)
        cfg = scan.load_config()
        with tempfile.TemporaryDirectory() as d:
            hist = os.path.join(d, "history.csv")
            scan.run(data["pairs"], cfg, d, data["captured_at_ms"], history_path=hist)
            later = json.loads(json.dumps(data["pairs"]))
            for p in later:
                p["fdv"] *= 2
            rows, _ = scan.run(later, cfg, d, data["captured_at_ms"] + 3600_000, history_path=hist)
        gooda = next(r for r in rows if r["symbol"] == "GOODA")
        self.assertEqual(gooda["times_seen"], 2)
        self.assertAlmostEqual(gooda["fdv_growth_pct"], 100)

    def test_position_size_matches_risk(self):
        cfg = scan.load_config()
        plan = scan.trade_plan({"price_usd": 1.0}, cfg)
        r = cfg["risk"]
        loss_at_stop = plan["position_usd"] * r["stop_loss_pct"] / 100
        self.assertAlmostEqual(loss_at_stop, r["account_size_usd"] * r["max_risk_per_trade_pct"] / 100)


def candles(closes):
    return [{"t": i, "o": c, "h": c * 1.02, "l": c * 0.98, "c": c, "v": 1000} for i, c in enumerate(closes)]


class ChartTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(chart.analyze(candles([1 + i * 0.01 for i in range(48)]))["trend"], "UPTREND")
        self.assertEqual(chart.analyze(candles([2 - i * 0.02 for i in range(48)]))["trend"], "DOWNTREND")
        self.assertEqual(chart.analyze(candles([1] * 44 + [3] * 4))["trend"], "EXTENDED")
        self.assertEqual(chart.analyze(candles([1] * 10))["trend"], "TOO NEW")


class SafetyTest(unittest.TestCase):
    def test_rugcheck(self):
        ok = {"risks": [{"name": "Low amount of LP Providers", "level": "warn"}]}
        bad = {"risks": [{"name": "Freeze Authority still enabled", "level": "danger"}]}
        self.assertEqual(safety.judge_rugcheck(ok), ("OK", ["RugCheck warn: Low amount of LP Providers"]))
        self.assertEqual(safety.judge_rugcheck(bad)[0], "FAIL")
        self.assertEqual(safety.judge_rugcheck({"rugged": True})[0], "FAIL")

    def test_honeypot(self):
        clean = {"simulationSuccess": True, "honeypotResult": {"isHoneypot": False},
                 "simulationResult": {"buyTax": 0, "sellTax": 1}, "summary": {"risk": "low", "flags": []}}
        self.assertEqual(safety.judge_honeypot(clean, 10), ("OK", []))
        self.assertEqual(safety.judge_honeypot(dict(clean, honeypotResult={"isHoneypot": True}), 10)[0], "FAIL")
        self.assertEqual(safety.judge_honeypot(dict(clean, simulationSuccess=False), 10)[0], "FAIL")
        taxed = safety.judge_honeypot(dict(clean, simulationResult={"buyTax": 0, "sellTax": 25}), 10)
        self.assertEqual(taxed, ("FAIL", ["sell tax 25%"]))
        self.assertEqual(safety.judge_honeypot(dict(clean, summary={"risk": "high"}), 10)[0], "FAIL")

    def test_check_routes_and_never_raises(self):
        urls = []

        def fetch(url):
            urls.append(url)
            raise OSError("blocked")
        safety.time.sleep, sleep = (lambda s: None), safety.time.sleep
        try:
            self.assertEqual(safety.check("base", "0xabc", fetch=fetch)["status"], "unchecked")
            self.assertEqual(safety.check("solana", "Mint1", fetch=fetch)["status"], "unchecked")
            self.assertEqual(safety.check("monad", "0xabc", fetch=fetch)["status"], "unchecked")
        finally:
            safety.time.sleep = sleep
        self.assertIn("chainID=8453", urls[0])
        self.assertIn("/tokens/Mint1/report/summary", urls[1])
        self.assertEqual(len(urls), 2)  # unsupported chain makes no call

    def test_scan_drops_failed_tokens(self):
        with open(os.path.join(ROOT, "tests", "fixtures", "sample_pairs.json")) as f:
            data = json.load(f)

        def fake(chain, addr, max_tax):
            return {"status": "OK", "notes": []}
        with tempfile.TemporaryDirectory() as d:
            rows, _ = scan.run(data["pairs"], scan.load_config(), d, data["captured_at_ms"], safety_fn=fake)
            gooda_addr = next(r for r in rows if r["symbol"] == "GOODA")["token_address"]

            def fail_gooda(chain, addr, max_tax):
                return {"status": "FAIL", "notes": ["honeypot: x"]} if addr == gooda_addr else fake(chain, addr, max_tax)
            rows, (_, md_path) = scan.run(data["pairs"], scan.load_config(), d, data["captured_at_ms"],
                                          safety_fn=fail_gooda)
            with open(md_path) as f:
                self.assertIn("honeypot: x", f.read())
        by_sym = {r["symbol"]: r for r in rows}
        self.assertEqual(by_sym["GOODA"]["verdict"], "AVOID")
        self.assertEqual(by_sym["TRUMPCAT"]["safety"], "OK")
        self.assertNotIn("safety", by_sym["THINLQ"])  # already-rejected tokens aren't checked


class ExitRuleTest(unittest.TestCase):
    risk = scan.load_config()["risk"]

    def test_initial_stop(self):
        self.assertEqual(positions.exit_status(1.0, 0.80, 1.0, self.risk)[0], "HOLD")
        self.assertEqual(positions.exit_status(1.0, 0.75, 1.0, self.risk)[0], "SELL")

    def test_floor_after_2x(self):
        action, stop, mode = positions.exit_status(1.0, 1.5, 2.0, self.risk)
        self.assertAlmostEqual(stop, 1.3)  # never below +30% once it has doubled
        self.assertEqual(action, "HOLD")
        self.assertEqual(positions.exit_status(1.0, 1.29, 2.0, self.risk)[0], "SELL")

    def test_trailing_stop_rises(self):
        action, stop, _ = positions.exit_status(1.0, 4.0, 5.0, self.risk)
        self.assertAlmostEqual(stop, 5.0 * 0.65)
        self.assertEqual(action, "HOLD")

    def test_check_updates_peak(self):
        rows = [{"token": "X", "chain": "solana", "pair_address": "p", "entry_price": "1", "size_usd": "20",
                 "peak_price": "2.2", "holders": "500/450"}]
        pair = {"priceUsd": "1.2", "txns": {"h1": {"buys": 10, "sells": 30}}, "liquidity": {"usd": 1}}
        res = positions.check(rows, scan.load_config(), lambda c, a: pair, lambda c, a: candles([1] * 5), 0)
        self.assertEqual(res[0]["action"], "SELL")  # 1.2 < 1.3 floor
        self.assertIn("holders falling 500->450", res[0]["warnings"])
        self.assertEqual(rows[0]["peak_price"], "2.2")


class AwayTest(unittest.TestCase):
    cfg = scan.load_config()

    def test_stop_crossed_while_away(self):
        # bought at 1.0 at hour 10, spiked to 2.0, dumped to 1.2 (below +30% floor), bounced to 1.4
        closes = [1.0] * 10 + [1.5, 2.0, 1.6, 1.2, 1.4] + [1.4] * 20
        rows = [{"token": "X", "chain": "solana", "pair_address": "p", "entry_price": "1", "size_usd": "20",
                 "peak_price": "1", "holders": "", "date_opened": "1970-01-01T10:00:00+00:00"}]
        pair = {"priceUsd": "1.4", "txns": {"h1": {"buys": 30, "sells": 10}}, "liquidity": {"usd": 1}}
        res = positions.check(rows, self.cfg, lambda c, a: pair,
                              lambda c, a: [dict(x, t=x["t"] * 3600) for x in candles(closes)], 0)
        self.assertEqual(res[0]["action"], "SELL")
        self.assertIn("while you were away", res[0]["warnings"][0])
        self.assertEqual(rows[0]["peak_price"], "2")

    def test_opened_ms(self):
        self.assertEqual(positions.opened_ms("1970-01-01"), 0)
        self.assertIsNone(positions.opened_ms("yesterday"))

    def test_brief_renders(self):
        held = [{"token": "X", "action": "HOLD", "gain_pct": 10, "price": 1.1, "stop": 0.75, "mode": "INITIAL STOP",
                 "trend": "UPTREND", "warnings": [], "value": 22, "size": 20}]
        acct = {"realized": -5, "cash_basis": 45, "today": 0, "halted": False, "day_halted": False}
        watch = [{"score": 5, "symbol": "NEW", "url": "u", "chain": "ethereum", "chart_trend": "PULLBACK", "hype": ["trump"],
                  "age_minutes": 120, "change_1h_pct": 3, "change_24h_pct": 40, "price_usd": 1.0}]
        text = evening.brief(self.cfg, held, acct, watch)
        self.assertIn("Nothing to sell", text)
        self.assertIn("NEW", text)
        self.assertIn("under 24h old", text)
        halted = evening.brief(self.cfg, held, dict(acct, halted=True), watch)
        self.assertIn("loss limit reached", halted)
        self.assertIn("Skipped: loss limit hit", halted)


class StatsTest(unittest.TestCase):
    def test_summary(self):
        trades = [{"pnl_usd": 20}, {"pnl_usd": -10}, {"pnl_usd": -10}, {"pnl_usd": 30}]
        s = stats.summarize(trades)
        self.assertEqual(s["win_rate_pct"], 50)
        self.assertEqual(s["net_pnl_usd"], 30)
        self.assertEqual(s["profit_factor"], 2.5)
        self.assertEqual(s["max_drawdown_usd"], 20)


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(json.dumps(scan.load_config()))
        self.cfg["alerts"]["ntfy_topic"] = "test"
        self.sent = []
        self._orig = (watch.send, watch.positions.run, watch.evening.account_status)
        watch.send = lambda topic, title, msg, *a: self.sent.append(title)
        watch.evening.account_status = lambda cfg: {"halted": False, "day_halted": False}

    def tearDown(self):
        watch.send, watch.positions.run, watch.evening.account_status = self._orig

    def hold(self, action, mode="INITIAL STOP", warnings=()):
        watch.positions.run = lambda cfg: ([{"token": "X", "action": action, "mode": mode, "gain_pct": 0,
                                             "price": 1, "stop": 1, "warnings": list(warnings)}], "")

    def test_sell_alert_repeats_every_30_min(self):
        self.hold("SELL")
        state = {}
        watch.check_once(self.cfg, state, False, now=1000)
        watch.check_once(self.cfg, state, False, now=1000 + 600)
        watch.check_once(self.cfg, state, False, now=1000 + 1800)
        self.assertEqual(self.sent, ["SELL X now", "SELL X now"])

    def test_lock_and_warning_once_then_cleared_after_sold(self):
        self.hold("HOLD", "LOCKED (reached 2x)", ["chart in downtrend"])
        state = {}
        watch.check_once(self.cfg, state, False, now=1)
        watch.check_once(self.cfg, state, False, now=2)
        self.assertEqual(self.sent, ["X hit 2x 🎯", "Warning: X"])
        watch.positions.run = lambda cfg: ([], "")
        watch.check_once(self.cfg, state, False, now=3)
        self.assertEqual(state, {})

    def test_buy_alert_filters(self):
        base = {"score": 6, "chart_trend": "PULLBACK", "chain": "solana", "token_address": "a", "symbol": "GOOD",
                "age_minutes": 600, "hype": [], "price_usd": 1.0, "url": "u"}
        ideas = list(watch.buy_alerts([base, dict(base, symbol="HOT", chart_trend="EXTENDED"),
                                       dict(base, symbol="WEAK", score=2)], self.cfg))
        self.assertEqual([i[1] for i in ideas], ["Buy idea: GOOD (solana)"])


if __name__ == "__main__":
    unittest.main()
