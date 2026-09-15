"""Execution/metric regressions. Generated fixtures only; no market-data loader."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from engine import backtest, metrics
from engine.costs import CostModel
from engine.data import DataError
from engine.spec import Spec
from engine.validation import montecarlo


def bars(n=8):
    return pd.DataFrame({
        "ts": pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC"),
        "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
    })


def strategy(**changes):
    values = dict(id="SYNTH-EXEC", titre="fixture", auteur="tests", interval="1h",
                  entry_long="trigger > 0", entry_short=None, mode="horizon", horizon=2,
                  stop_atr=None, target_atr=None, atr_col="atr_48")
    values.update(changes)
    return Spec(**values)


def feature_frame(n=8, signal_at=0):
    signals = np.zeros(n)
    signals[signal_at] = 1
    return pd.DataFrame({"trigger": signals, "atr_48": 100.0})


def trade_frame(returns):
    n = len(returns)
    return pd.DataFrame({
        "net_bps": returns,
        "entry_ts": pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"),
        "exit_ts": pd.date_range("2020-01-02", periods=n, freq="D", tz="UTC"),
        "bars_held": 24,
    })


class ExecutionSynthetic(unittest.TestCase):
    def run_trade(self, df, spec=None, feats=None, costs=None):
        return backtest.run(df, feature_frame(len(df)) if feats is None else feats,
                            strategy() if spec is None else spec, {},
                            CostModel(0, 0, 0, 0) if costs is None else costs)

    def bracket(self, side=1, **changes):
        values = dict(mode="bracket", horizon=3, stop_atr=1.0, target_atr=2.0)
        if side == -1:
            values.update(entry_long=None, entry_short="trigger > 0")
        values.update(changes)
        return strategy(**values)

    def test_timeout_excludes_future_high_and_low_for_both_sides(self):
        for side in (1, -1):
            with self.subTest(side=side):
                df = bars()
                df.loc[2, ["high", "low"]] = [110, 90]
                tr = self.run_trade(df, self.bracket(side, horizon=1))
                self.assertEqual(len(tr), 1)
                self.assertEqual(tr.iloc[0]["reason"], "timeout")
                self.assertEqual(tr.iloc[0]["exit"], 100)
                self.assertEqual(tr.iloc[0]["gross_bps"], 0)
                self.assertEqual(tr.iloc[0]["exit_ts"], df.ts.iloc[2])

    def test_gap_stop_uses_adverse_open_for_long_and_short(self):
        for side, prices in ((1, [90, 92, 88, 90]), (-1, [110, 112, 108, 110])):
            with self.subTest(side=side):
                df = bars()
                df.loc[2, ["open", "high", "low", "close"]] = prices
                first = self.run_trade(df, self.bracket(side)).iloc[0]
                self.assertEqual(first["exit"], prices[0])
                self.assertEqual(first["reason"], "stop_gap")
                self.assertAlmostEqual(first["gross_bps"], -1000)
                self.assertEqual(first["exit_ts"], df.ts.iloc[2])

    def test_open_target_precedes_later_stop_and_awards_no_improvement(self):
        for side, prices, target in ((1, [105, 106, 90, 100], 102),
                                     (-1, [95, 110, 94, 100], 98)):
            with self.subTest(side=side):
                df = bars()
                df.loc[2, ["open", "high", "low", "close"]] = prices
                first = self.run_trade(df, self.bracket(side)).iloc[0]
                self.assertEqual(first["reason"], "target_gap")
                self.assertEqual(first["exit"], target)

    def test_ambiguous_intrabar_stop_charges_full_exit_bar(self):
        df = bars()
        df.loc[1, ["high", "low"]] = [103, 98]
        tr = self.run_trade(df, self.bracket(), costs=CostModel(0, 0, 0, 24))
        first = tr.iloc[0]
        self.assertEqual(first["reason"], "stop")
        self.assertEqual(first["exit"], 99)
        self.assertEqual(first["bars_held"], 1)
        self.assertEqual(first["exit_ts"], df.ts.iloc[2])
        self.assertEqual(first["exit_time_precision"], "bar_close_upper_bound")
        self.assertEqual(first["cost_bps"], 1)

    def test_next_close_signal_after_intrabar_exit_does_not_overlap(self):
        df = bars()
        df.loc[1, ["high", "low"]] = [103, 98]
        f = feature_frame()
        f.loc[1, "trigger"] = 1
        tr = self.run_trade(df, self.bracket(horizon=2), f)
        self.assertEqual(len(tr), 2)
        self.assertEqual(tr.iloc[0].exit_ts, tr.iloc[1].entry_ts)

    def test_time_gap_fails_before_signal_evaluation(self):
        df = bars()
        df.loc[2:, "ts"] += pd.Timedelta(hours=23)
        with patch.object(backtest, "evaluate", side_effect=AssertionError("should not run")):
            with self.assertRaisesRegex(DataError, "gap temporel"):
                self.run_trade(df)

    def test_bad_price_and_misaligned_index_fail(self):
        df = bars()
        df.loc[3, "open"] = np.nan
        with self.assertRaises(DataError):
            self.run_trade(df)
        f = feature_frame()
        f.index = f.index + 1
        with self.assertRaises(DataError):
            self.run_trade(bars(), feats=f)

    def test_incomplete_terminal_horizon_is_excluded_and_reported(self):
        for mode in ("horizon", "bracket"):
            with self.subTest(mode=mode):
                df = bars(4)
                f = feature_frame(4, signal_at=1)
                sp = strategy(horizon=2) if mode == "horizon" else self.bracket(horizon=2)
                # Even a potential immediate bracket target is not selected
                # merely because it would close before the data boundary.
                df.loc[2, "high"] = 110
                tr = self.run_trade(df, sp, f)
                self.assertTrue(tr.empty)
                self.assertEqual(tr.attrs["excluded_incomplete_horizon_signals"], 1)
                self.assertEqual(metrics.research(tr, 3600)["excluded_incomplete_horizon_signals"], 1)

    def test_complete_horizon_exits_at_required_open(self):
        df = bars(4)
        df.loc[3, ["open", "high", "low", "close"]] = 105
        tr = self.run_trade(df)
        self.assertEqual(len(tr), 1)
        self.assertEqual(tr.iloc[0]["exit"], 105)
        self.assertEqual(tr.iloc[0]["bars_held"], 2)

    def test_invalid_spec_and_extra_parameters_fail_before_evaluate(self):
        with patch.object(backtest, "evaluate", side_effect=AssertionError("should not run")):
            with self.assertRaises(backtest.SpecError):
                self.run_trade(bars(), strategy(horizon=0))
            with self.assertRaises(backtest.SpecError):
                backtest.run(bars(), feature_frame(), strategy(), {"one_sided": .5})

    def test_future_signal_is_rejected(self):
        with self.assertRaises(backtest.SpecError):
            self.run_trade(bars(), strategy(entry_long="trigger.shift(-1) > 0"))


class HypotheticalMetricsSynthetic(unittest.TestCase):
    def test_initial_loss_contributes_to_drawdown(self):
        report = metrics.deployment(trade_frame([-1000, 100]), 3600)
        self.assertAlmostEqual(report["max_drawdown"], -.0112, places=4)
        self.assertFalse(report["qualifie"])
        self.assertIn("ex post", report["hypotheses"])

    def test_ruin_is_absorbing_and_cannot_rebound(self):
        np.testing.assert_allclose(metrics.equity_path(np.array([-.1, -1.2, -2., 100.])),
                                   [1., .9, 0., 0., 0.])
        returns = [-20000., -20000.] + [-100.] * 38
        report = metrics.deployment(trade_frame(returns), 3600)
        self.assertEqual(report["max_drawdown"], -1)
        self.assertEqual(report["capital_final_normalise"], 0)
        self.assertEqual(report["cagr"], -1)
        self.assertTrue(report["ruine_observee_dans_scenario"])

    def test_no_loss_quantile_means_no_hypothetical_position_size(self):
        report = metrics.deployment(trade_frame([100.] * 30), 3600)
        self.assertFalse(report["calculable"])
        self.assertFalse(montecarlo.run(trade_frame([100.] * 30), n_sims=3)["calculable"])

    def test_montecarlo_drawdown_includes_first_loss(self):
        # Identical losses have no permutation ambiguity: the first loss must
        # count, so 20 losses of 1% draw down by 1 - .99**20, not 1 - .99**19.
        report = montecarlo.run(trade_frame([-100.] * 20), n_sims=5)
        self.assertAlmostEqual(report["dd_p95"], .99 ** 20 - 1, places=4)
        self.assertFalse(report["qualifie"])

    def test_montecarlo_ruin_cannot_rebound(self):
        report = montecarlo.run(trade_frame([-20000., -20000.] + [-100.] * 38), n_sims=10)
        self.assertEqual(report["dd_p95"], -1)
        self.assertEqual(report["rendement_median"], -1)
        self.assertEqual(report["part_scenarios_insolvables"], 1)

    def test_dsr_remains_unqualified_for_large_values(self):
        tr = trade_frame(np.linspace(90, 110, 100))
        report = metrics.deflated_sharpe(tr, 1)
        self.assertGreater(report["dsr"], .95)
        self.assertFalse(report["qualifie"])
        self.assertIsNone(report["n_essais_independants_etablis"])
        self.assertEqual(report["sr0"], 0)
        self.assertIn("pas une probabilite", report["note"])

    def test_dsr_handles_constant_returns_and_invalid_trial_counts(self):
        self.assertIsNone(metrics.deflated_sharpe(trade_frame([10.] * 30), 2)["dsr"])
        for n in (0, -1, 1.5, True):
            with self.subTest(n=n), self.assertRaises(ValueError):
                metrics.deflated_sharpe(trade_frame(np.arange(30)), n)

    def test_cost_stress_scales_funding_and_fractional_day(self):
        costs = CostModel(4, 2, 1, 24)
        self.assertEqual(costs.total(3, 3600), 10)
        self.assertEqual(costs.scaled(2).total(3, 3600), 20)
        self.assertEqual(costs.holding(.5, 3600), .5)

    def test_invalid_costs_are_rejected(self):
        for value in (-1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CostModel(funding_bps_per_day=value)


if __name__ == "__main__":
    unittest.main()
