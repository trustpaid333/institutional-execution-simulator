"""Run: python -m unittest -v"""
import unittest

import numpy as np

from execution_simulator import (
    Config, MarketPath, child_order_sizes, execute_order,
    generate_market_path, run_simulation,
)


class ExecutionSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config(shares=10_003, buckets=7)
        self.path = generate_market_path(self.cfg, np.random.default_rng(123))

    def test_immediate_and_twap_complete_without_overfill(self):
        for name in ("Immediate", "TWAP"):
            metrics, _ = execute_order(name, self.cfg, self.path)
            self.assertEqual(metrics["filled_shares"], self.cfg.shares)
            self.assertEqual(metrics["unfilled_shares"], 0)

    def test_twap_integer_slices_sum_to_requested_shares(self):
        q = child_order_sizes("TWAP", self.cfg, self.path)
        self.assertEqual(q.sum(), self.cfg.shares)
        self.assertTrue(np.issubdtype(q.dtype, np.integer))
        self.assertLessEqual(q.max() - q.min(), 1)

    def test_pov_never_overfills_and_obeys_participation_cap(self):
        q = child_order_sizes("POV", self.cfg, self.path)
        self.assertLessEqual(q.sum(), self.cfg.shares)
        for quantity, volume in zip(q, self.path.market_volume):
            self.assertLessEqual(quantity, int(np.floor(self.cfg.participation_rate * volume)))

    def test_zero_costs_flat_market_all_have_zero_shortfall(self):
        cfg = Config(shares=10, buckets=3, volatility_bps_per_bucket=0,
                     typical_spread_bps=0, impact_coefficient_bps=0,
                     fee_per_share=0)
        path = generate_market_path(cfg, np.random.default_rng(1))
        for name in ("Immediate", "TWAP", "POV"):
            metrics, _ = execute_order(name, cfg, path)
            self.assertAlmostEqual(metrics["implementation_shortfall_bps"], 0, places=9)

    def test_cost_components_add_to_total(self):
        for name in ("Immediate", "TWAP", "POV"):
            m, _ = execute_order(name, self.cfg, self.path)
            parts = (m["timing_cost_usd"] + m["spread_cost_usd"]
                     + m["impact_cost_usd"] + m["fees_usd"]
                     + m["opportunity_cost_usd"])
            self.assertAlmostEqual(parts, m["implementation_shortfall_usd"], places=8)

    def test_unfilled_opportunity_cost_changes_sign_for_buy_sell(self):
        path = MarketPath(mid=np.array([100.0, 101.0]),
                          spread_bps=np.zeros(2),
                          market_volume=np.zeros(2, dtype=int),
                          book_depth=np.ones(2) * 10_000)
        buy, _ = execute_order("POV", Config(side="buy", shares=10, buckets=2), path)
        sell, _ = execute_order("POV", Config(side="sell", shares=10, buckets=2), path)
        self.assertEqual(buy["unfilled_shares"], 10)
        self.assertAlmostEqual(buy["opportunity_cost_usd"], 10)
        self.assertAlmostEqual(sell["opportunity_cost_usd"], -10)

    def test_fixed_seed_reproduces_market_path(self):
        first = generate_market_path(self.cfg, np.random.default_rng(77))
        second = generate_market_path(self.cfg, np.random.default_rng(77))
        np.testing.assert_array_equal(first.mid, second.mid)
        np.testing.assert_array_equal(first.market_volume, second.market_volume)

    def test_invalid_configuration_fails(self):
        for cfg_kwargs in ({"shares": 0}, {"side": "both"}, {"participation_rate": 1.1}):
            with self.assertRaises(ValueError):
                Config(**cfg_kwargs)


if __name__ == "__main__":
    unittest.main()
