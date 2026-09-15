"""Contract/security regressions using only constructed data and YAML specs.

Run this file explicitly. It never calls a market loader or reads vault files.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from engine.expressions import SpecError, evaluate, parse
from engine.features import assert_causal, build
from engine.spec import Spec, load


def contract(**changes):
    values = dict(id="SYNTHETIC", titre="fixture", auteur="test", interval="1h",
                  entry_long="x > 0", entry_short=None, mode="horizon", horizon=3,
                  stop_atr=None, target_atr=None, atr_col="atr_48",
                  params={}, budget_declare=1)
    values.update(changes)
    return Spec(**values)


def candles(n=220, index=None):
    # Deterministic coherent bars, independent of every market data source.
    close = 100 + np.arange(n) * 0.02 + np.sin(np.arange(n) / 3)
    return pd.DataFrame({
        "ts": pd.date_range("2001-01-01", periods=n, freq="h", tz="UTC"),
        "open": close - 0.1, "close": close, "high": close + 0.5,
        "low": close - 0.5, "volume": 10 + np.arange(n) % 7,
        "trades": 5 + np.arange(n) % 3, "taker_buy_base": 5 + np.arange(n) % 4,
        "quote_volume": (10 + np.arange(n) % 7) * close,
        "other_future_column": np.arange(n, dtype=float),
    }, index=index)


class StrictExpressions(unittest.TestCase):
    def setUp(self):
        self.index = pd.Index(["first", "second", "third", "last"], name="row")
        self.feats = pd.DataFrame({"x": [-3.0, -1.0, 1.0, 4.0],
                                   "y": [1.0, 3.0, 2.0, 8.0]}, index=self.index)

    def test_pointwise_arithmetic_boolean_abs_and_index(self):
        out = evaluate("(abs(x) >= {threshold}) & ((y / 2) < 4)", self.feats,
                       {"threshold": 2})
        expected = pd.Series([True, False, False, False], index=self.index)
        pd.testing.assert_series_equal(out, expected)
        pd.testing.assert_series_equal(
            evaluate("~(x > 0) | (y == 8)", self.feats, {}),
            pd.Series([True, True, False, True], index=self.index))

    def test_chained_comparisons_are_vectorial(self):
        out = evaluate("-2 < x < 3", self.feats, {})
        self.assertEqual(out.tolist(), [False, True, True, False])

    def test_direct_scalar_parameter_names_are_supported(self):
        self.assertEqual(evaluate("x > threshold", self.feats, {"threshold": 2}).tolist(),
                         [False, False, False, True])

    def test_feature_name_template_keeps_integer_type(self):
        feats = self.feats.rename(columns={"x": "z_close_24"})
        self.assertEqual(evaluate("z_close_{window} < -{threshold}", feats,
                                  {"window": 24, "threshold": 2.0}).tolist(),
                         [True, False, False, False])

    def test_forbidden_syntax_cannot_read_future_or_execute_python(self):
        expressions = [
            "x.shift(-1) > 0", "x.mean() > 0", "x.sum() > 0", "max(x) > 0",
            "x.iloc[-1] > 0", "x[0] > 0", "x.rolling(2).mean() > 0",
            "x.__class__", "np.where(x > 0, True, False)",
            "__import__('os').getcwd()", "(lambda: x)()", "[v for v in x]",
            "x if True else y", "x > 0 and y > 0", "not (x > 0)",
            "x in y", "x is y", "(x := y)", "abs(x, axis=0) > 0",
            "abs(*x) > 0", "globals()", "f'{x}'", "x @ y", "x ^ y",
        ]
        for expr in expressions:
            with self.subTest(expr=expr), self.assertRaises(SpecError):
                evaluate(expr, self.feats, {})

    def test_templates_cannot_traverse_values_or_inject_code(self):
        for expr in ("x > {p.real}", "x > {p[0]}", "x > {p!r}",
                     "x > {p:03}", "x > {missing}", "x > {p"):
            with self.subTest(expr=expr), self.assertRaises(SpecError):
                evaluate(expr, self.feats, {"p": 1})
        for value in ("0 or __import__('os')", [1], {"x": 1}, None,
                      float("nan"), float("inf"), complex(1, 2)):
            with self.subTest(value=value), self.assertRaises(SpecError):
                evaluate("x > {p}", self.feats, {"p": value})

    def test_non_vector_non_boolean_and_unknown_names_are_rejected(self):
        for expr in ("True", "1 > 0", "x + 1", "abs(x)", "unknown > 0",
                     "x & y", "~x", "(x > 0) + 1", "x > 1e309"):
            with self.subTest(expr=expr), self.assertRaises(SpecError):
                evaluate(expr, self.feats, {})

    def test_missing_values_never_become_entries_after_negation(self):
        feats = pd.DataFrame({"x": [np.nan, np.inf, -np.inf, -1.0, 1.0]})
        for expr in ("~(x > 0)", "x != 0", "(x > 0) | True"):
            with self.subTest(expr=expr):
                self.assertEqual(evaluate(expr, feats, {}).iloc[:3].tolist(), [False] * 3)
        self.assertEqual(evaluate("~(x > 0)", feats, {}).tolist(),
                         [False, False, False, True, False])

    def test_invalid_intermediate_values_suppress_rows(self):
        feats = pd.DataFrame({"x": [0.0, 1.0, -1.0]})
        self.assertFalse(evaluate("~((x / 0) > 0)", feats, {}).any())
        self.assertEqual(evaluate("(1 / x) != 0", feats, {}).tolist(),
                         [False, True, True])
        with self.assertRaises(SpecError):
            evaluate("x > (1 / 0)", feats, {})

    def test_nullable_columns_keep_missing_mask(self):
        feats = pd.DataFrame({"x": pd.Series([pd.NA, -1, 1], dtype="Float64")})
        self.assertEqual(evaluate("~(x > 0)", feats, {}).tolist(), [False, True, False])

    def test_feature_schema_and_parameter_collision_are_rejected(self):
        for feats in (pd.DataFrame({"x": ["1", "2"]}),
                      pd.DataFrame({"x": pd.date_range("2001-01-01", periods=2)}),
                      pd.DataFrame([[1, 2]], columns=["x", "x"])):
            with self.subTest(dtypes=feats.dtypes), self.assertRaises(SpecError):
                evaluate("x > 0", feats, {})
        with self.assertRaises(SpecError):
            evaluate("x > 0", self.feats, {"x": 5})

    def test_expression_resources_are_bounded(self):
        for expr in ("x > (9 ** 999999)", "x ** y > 0",
                     "x > " + "+".join(["1"] * 300)):
            with self.subTest(expr=expr[:50]), self.assertRaises(SpecError):
                evaluate(expr, self.feats, {})

    def test_every_allowed_expression_has_prefix_invariance(self):
        expressions = ("abs(x) > 1", "(x + y * 2) > 4", "~(x >= 1)",
                       "((x ** 2) > 1) & (y % 2 == 0)", "-2 < x < 5")
        for expr in expressions:
            full = evaluate(expr, self.feats, {})
            for cut in (1, 2, 3):
                with self.subTest(expr=expr, cut=cut):
                    pd.testing.assert_series_equal(
                        full.iloc[:cut], evaluate(expr, self.feats.iloc[:cut], {}))


class ImmutableSpec(unittest.TestCase):
    def test_constructor_and_hash_use_effective_fields_without_raw(self):
        a = contract()
        self.assertEqual(len(a.hash), 64)
        self.assertEqual(a.validate(), [])
        self.assertNotEqual(a.hash, replace(a, horizon=4).hash)
        self.assertNotEqual(a.hash, replace(a, entry_long="x < 0").hash)
        self.assertEqual(a.hash, replace(a, raw={"exit": {"horizon": 999}}).hash)

    def test_all_effective_contract_changes_affect_hash(self):
        a = contract()
        changes = dict(id="different", titre="new title", auteur="other", interval="15m",
                       entry_long="x < 0", entry_short="x < -1", mode="bracket", horizon=4,
                       stop_atr=1.0, target_atr=2.0, atr_col="atr_14", params={"p": [1]},
                       budget_declare=2, notes="new note")
        for key, value in changes.items():
            with self.subTest(field=key):
                self.assertNotEqual(a.hash, replace(a, **{key: value}).hash)

    def test_deep_freeze_breaks_links_with_mutable_callers(self):
        params = {"p": [1, 2]}
        raw = {"nested": {"values": [10, 20]}}
        sp = contract(params=params, budget_declare=2, raw=raw)
        before = sp.hash
        params["p"].append(3)
        raw["nested"]["values"].append(30)
        self.assertEqual(sp.params["p"], (1, 2))
        self.assertEqual(sp.raw["nested"]["values"], (10, 20))
        self.assertEqual(sp.hash, before)
        with self.assertRaises(FrozenInstanceError):
            sp.horizon = 8
        with self.assertRaises(TypeError):
            sp.params["p"] = (3,)
        with self.assertRaises(TypeError):
            sp.raw["nested"]["values"] = (0,)
        with self.assertRaises(TypeError):
            sp.grid()[0]["p"] = 3

    def test_export_is_detached_and_canonical_order_is_stable(self):
        sp = contract(params={"b": [2], "a": [1]})
        other = contract(params={"a": [1], "b": [2]})
        self.assertEqual(sp.hash, other.hash)
        exported = sp.to_dict()
        exported["params"]["a"].append(4)
        exported["horizon"] = 9
        self.assertEqual(sp.params["a"], (1,))
        self.assertEqual(sp.horizon, 3)
        self.assertEqual(sp.hash, other.hash)

    def test_actual_parameters_must_match_every_declared_value_and_type(self):
        sp = contract(params={"window": [24, 72], "threshold": [1.5, 2.0]}, budget_declare=4)
        for params in sp.grid():
            self.assertEqual(sp.validate_params(params), [])
        for params in ({}, {"window": 24}, {"window": 24, "threshold": 1.5, "extra": 0},
                       {"window": 24.0, "threshold": 1.5}, {"window": 99, "threshold": 1.5},
                       {"window": 24, "threshold": np.nan}, {"window": "24", "threshold": 1.5}):
            with self.subTest(params=params):
                self.assertTrue(sp.validate_params(params))
        self.assertTrue(contract(params={"p": [1]}).validate_params({"p": True}))

    def test_horizon_is_positive_integer_in_both_exit_modes(self):
        for mode in ("horizon", "bracket"):
            for value in (0, -1, True, 1.5, "3", None, np.nan, np.inf):
                with self.subTest(mode=mode, value=value):
                    sp = contract(mode=mode, horizon=value, stop_atr=1.0, target_atr=2.0)
                    self.assertTrue(any("horizon" in err for err in sp.validate()))

    def test_bracket_distances_must_be_finite_positive_numbers(self):
        for name in ("stop_atr", "target_atr"):
            for value in (None, 0, -1, True, "1", np.nan, np.inf):
                with self.subTest(name=name, value=value):
                    values = {"mode": "bracket", "stop_atr": 1.0, "target_atr": 2.0}
                    values[name] = value
                    self.assertTrue(any(name in err for err in contract(**values).validate()))
        self.assertEqual(contract(mode="bracket", stop_atr=1.0, target_atr=2.0).validate(), [])

    def test_empty_non_scalar_duplicate_or_nonfinite_grids_are_rejected(self):
        for params in ({"p": []}, {"p": "text"}, {"p": [np.nan]}, {"p": [np.inf]},
                       {"p": [[1]]}, {"p": ["1"]}, {"p": [1, 1]}):
            with self.subTest(params=params):
                self.assertTrue(contract(params=params, budget_declare=5).validate())

    def test_budget_and_free_parameter_limits_remain_enforced(self):
        self.assertTrue(any("budget declare" in err for err in
                            contract(params={"p": [1, 2]}, budget_declare=1).validate()))
        self.assertTrue(any("parametres libres" in err for err in
                            contract(params={k: [1] for k in "abcd"}).validate()))
        for value in (0, -1, True, 1.5, np.inf, "3"):
            with self.subTest(value=value):
                self.assertTrue(contract(budget_declare=value).validate())

    def test_expressions_are_validated_before_execution(self):
        for expr in ("x.shift(-1) > 0", "x.mean() > 0", "(x > 0) and (y > 0)"):
            with self.subTest(expr=expr):
                self.assertTrue(contract(entry_long=expr).validate())
        self.assertTrue(contract(entry_long="x > {missing}").validate())

    def test_yaml_horizon_and_budget_are_not_silently_truncated(self):
        for field, value in (("horizon", "1.9"), ("horizon", "true"), ("budget", "1.9")):
            content = "id: T\nsignal:\n  entry_long: x > 0\nexit:\n  horizon: "
            content += value if field == "horizon" else "3"
            content += "\nbudget_essais: " + (value if field == "budget" else "1") + "\n"
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "spec.yaml"
                p.write_text(content)
                self.assertTrue(load(p).validate())

    def test_existing_yaml_specs_are_read_without_any_market_access(self):
        root = Path(__file__).resolve().parents[1]
        calibration = load(root / "experiments/EXP-0000-calibration/spec.yaml")
        self.assertEqual(calibration.validate(), [])
        self.assertEqual(len(calibration.grid()), 9)
        for params in calibration.grid():
            parse(calibration.entry_long, params)
            parse(calibration.entry_short, params)
        template = load(root / "experiments/TEMPLATE/spec.yaml")
        self.assertIn("aucune condition d'entree", template.validate())


class PrefixCausality(unittest.TestCase):
    def test_causal_builder_passes_on_nonstandard_indices(self):
        indices = (pd.Index([f"bar-{i}" for i in range(220)], name="bar"),
                   pd.RangeIndex(start=400, stop=840, step=2, name="offset"),
                   pd.date_range("1999-12-01", periods=220, freq="h", name="clock"))
        for index in indices:
            with self.subTest(index_type=type(index).__name__):
                df = candles(index=index)
                assert_causal(df, build(df))

    def test_shift_one_leak_is_detected_at_last_prefix_row_even_if_only_nan_differs(self):
        df = candles(20)
        def leaking(d):
            return pd.DataFrame({"next": d["close"].shift(-1)}, index=d.index)
        with self.assertRaises(AssertionError):
            assert_causal(df, leaking(df), leaking, cuts=[10])

    def test_future_columns_outside_old_price_allowlist_are_checked(self):
        df = candles(20)
        for column in ("trades", "other_future_column"):
            def leaking(d):
                return pd.DataFrame({"next": d[column].shift(-1)}, index=d.index)
            with self.subTest(column=column), self.assertRaises(AssertionError):
                assert_causal(df, leaking(df), leaking)

    def test_future_timestamps_are_checked(self):
        df = candles(20)
        def leaking(d):
            return pd.DataFrame({"next_hour": d["ts"].dt.hour.shift(-1)}, index=d.index)
        with self.assertRaises(AssertionError):
            assert_causal(df, leaking(df), leaking)

    def test_future_aggregate_and_backfill_are_detected(self):
        df = candles(20)
        def aggregate(d):
            return pd.DataFrame({"future": d["close"].mean()}, index=d.index)
        with self.assertRaises(AssertionError):
            assert_causal(df, aggregate(df), aggregate)
        def backfilled(d):
            return pd.DataFrame({"future": d["close"].rolling(3).mean().bfill()}, index=d.index)
        with self.assertRaises(AssertionError):
            assert_causal(df, backfilled(df), backfilled)

    def test_builder_must_reproduce_columns_dtype_and_index(self):
        df = candles(20, index=pd.Index([f"row-{i}" for i in range(20)]))
        def plain(d):
            return pd.DataFrame({"x": d["close"]}, index=d.index)
        feats = plain(df)
        for broken in (feats.assign(extra=1), feats.rename(columns={"x": "other"}),
                       feats.reset_index(drop=True), feats.astype("float32")):
            with self.subTest(columns=broken.columns), self.assertRaises(AssertionError):
                assert_causal(df, broken, plain)

    def test_nan_structure_cannot_be_ignored(self):
        df = candles(20)
        def plain(d):
            return pd.DataFrame({"x": d["close"]}, index=d.index)
        feats = plain(df)
        feats.loc[2, "x"] = np.nan
        with self.assertRaises(AssertionError):
            assert_causal(df, feats, plain)

    def test_multiple_default_cuts_are_positional_and_include_boundary(self):
        df = candles(20, index=pd.Index([f"r{i}" for i in range(20)]))
        sizes = []
        def plain(d):
            sizes.append(len(d))
            return pd.DataFrame({"x": d["close"]}, index=d.index)
        assert_causal(df, plain(df), plain)
        self.assertTrue({1, 5, 10, 15, 19}.issubset(sizes))

    def test_too_short_data_or_invalid_cuts_cannot_claim_verification(self):
        for n in (0, 1):
            df = candles(n)
            with self.subTest(n=n), self.assertRaises(AssertionError):
                assert_causal(df, pd.DataFrame(index=df.index), lambda d: pd.DataFrame(index=d.index))
        df = candles(20)
        for cuts in ([], [0], [20], [True], [1.5]):
            with self.subTest(cuts=cuts), self.assertRaises(AssertionError):
                assert_causal(df, build(df), cuts=cuts)


if __name__ == "__main__":
    unittest.main()
