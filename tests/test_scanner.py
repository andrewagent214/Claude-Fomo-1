import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scanner"))

import chart  # noqa: E402
import positions  # noqa: E402
import scan  # noqa: E402
import stats  # noqa: E402


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


class StatsTest(unittest.TestCase):
    def test_summary(self):
        trades = [{"pnl_usd": 20}, {"pnl_usd": -10}, {"pnl_usd": -10}, {"pnl_usd": 30}]
        s = stats.summarize(trades)
        self.assertEqual(s["win_rate_pct"], 50)
        self.assertEqual(s["net_pnl_usd"], 30)
        self.assertEqual(s["profit_factor"], 2.5)
        self.assertEqual(s["max_drawdown_usd"], 20)


if __name__ == "__main__":
    unittest.main()
