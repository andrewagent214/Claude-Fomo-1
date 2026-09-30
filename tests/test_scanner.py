import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scanner"))

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
        self.assertEqual(len(rows), 4)  # duplicate GOODA pair collapsed to most liquid
        self.assertEqual(by_sym["GOODA"]["verdict"], "WATCH")
        self.assertEqual(by_sym["GOODA"]["score"], 4)
        for sym in ("THINLQ", "BABY", "PUMPED"):
            self.assertEqual(by_sym[sym]["verdict"], "AVOID", sym)

    def test_position_size_matches_risk(self):
        cfg = scan.load_config()
        plan = scan.trade_plan({"price_usd": 1.0}, cfg)
        r = cfg["risk"]
        loss_at_stop = plan["position_usd"] * r["stop_loss_pct"] / 100
        self.assertAlmostEqual(loss_at_stop, r["account_size_usd"] * r["max_risk_per_trade_pct"] / 100)


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
