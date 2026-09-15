"""Reproduce engine audit findings using generated fixtures only.

Run from any directory: python3 path/to/reproduce_engine.py
The script prints JSON. It never calls load(), run.main(), attack.main(), or
calibration, and does not read market data or write a result file. Bytecode
generation is disabled so imported repository modules do not create files.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import platform
import sys

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd
import scipy

from engine import backtest, features, metrics, spec
from engine.costs import CostModel
from engine.data import _sanity

AUDITED_COMMIT = "7454850c1328d41bf626766825833a480a5f4139"
AUDITED_SOURCES = (
    "engine/backtest.py", "engine/features.py", "engine/metrics.py",
    "engine/spec.py", "engine/run.py", "engine/attack.py", "engine/data.py",
    "engine/costs.py", "tests/test_mecanismes.py", "requirements.txt",
)


def frame(n=600):
    """Seeded toy prices; no claim about real market performance."""
    rng = np.random.default_rng(22)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    return pd.DataFrame({
        "ts": pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC"),
        "open": prices, "close": prices,
        "high": prices * 1.001, "low": prices * 0.999,
        "volume": 100.0, "trades": 100, "taker_buy_base": 50.0,
        "quote_volume": 10000.0,
    })


def strategy(**changes):
    """Build a Spec with matching raw fields, without reading a YAML file."""
    values = dict(
        id="AUDIT-SYNTH", titre="audit", auteur="audit", interval="1h",
        entry_long="trigger > 0", entry_short=None, mode="horizon", horizon=1,
        stop_atr=None, target_atr=None, atr_col="atr_48",
    )
    values.update(changes)
    raw = {
        "id": values["id"], "titre": values["titre"], "auteur": values["auteur"],
        "data": {"interval": values["interval"]},
        "signal": {"entry_long": values["entry_long"], "entry_short": values["entry_short"]},
        "exit": {name: values[name] for name in (
            "mode", "horizon", "stop_atr", "target_atr", "atr_col")},
        "budget_essais": 1,
    }
    return spec.Spec(**values, raw=raw)


def probe_future_signal():
    df = frame()
    f = features.build(df)
    features.assert_causal(df, f)
    sp = strategy(entry_long="ret_1.shift(-2) > 0")
    tr = backtest.run(df, f, sp, {}, CostModel(0, 0, 0, 0))
    return {
        "spec_errors": sp.validate(), "trades": len(tr),
        "min_net_bps": float(tr.net_bps.min()) if len(tr) else None,
        "fraction_positive": float((tr.net_bps > 0).mean()) if len(tr) else None,
        "fixture_note": "open=close; zero costs isolate the causal defect",
    }


def probe_future_feature():
    def leaking_builder(d):
        f = features.build(d)
        f["leak_one_bar"] = d["close"].shift(-1)
        return f

    df = frame()
    features.assert_causal(df, leaking_builder(df), builder=leaking_builder)
    return {"detector_accepted": True, "injected_feature": "close.shift(-1)",
            "bars": len(df), "corruption_cut": len(df) // 2}


def bracket_fixture():
    d = frame(6)
    d[["open", "close", "high", "low"]] = 100.0
    d.loc[2, "high"] = 103.0
    f = pd.DataFrame({"trigger": [1, 0, 0, 0, 0, 0], "atr_48": 100.0})
    return d, f


def probe_timeout():
    d, f = bracket_fixture()
    sp = strategy(mode="bracket", horizon=1, stop_atr=1.0, target_atr=2.0)
    tr = backtest.run(d, f, sp, {}, CostModel(0, 0, 0, 0))
    return {"trade": tr.iloc[0].to_dict(), "timeout_open": 100.0,
            "timeout_bar_high": 103.0}


def probe_gap_stop():
    d, f = bracket_fixture()
    d.loc[2, ["open", "close", "high", "low"]] = [90.0, 90.0, 92.0, 88.0]
    sp = strategy(mode="bracket", horizon=3, stop_atr=1.0, target_atr=2.0)
    tr = backtest.run(d, f, sp, {}, CostModel(0, 0, 0, 0))
    return {"trade": tr.iloc[0].to_dict(), "gap_bar_open": 90.0,
            "gap_bar_high": 92.0, "gap_bar_low": 88.0}


def probe_gap_cost():
    d = frame(100)
    d.loc[2:, "ts"] += pd.Timedelta(hours=23)
    _sanity(d, "1h")
    f = pd.DataFrame({"trigger": [1] + [0] * 99})
    tr = backtest.run(d, f, strategy(), {}, CostModel(0, 0, 0, 24.0))
    return {
        "elapsed_hours": (tr.exit_ts.iloc[0] - tr.entry_ts.iloc[0]).total_seconds() / 3600,
        "bars_held": int(tr.bars_held.iloc[0]),
        "cost_bps": float(tr.cost_bps.iloc[0]),
        "expected_funding_bps_for_elapsed_time": 24.0,
    }


def probe_spec_hash():
    sp = strategy()
    old_hash = sp.hash
    sp.horizon = 200
    return {
        "same_hash": old_hash == sp.hash, "horizon": sp.horizon,
        "raw_horizon": sp.raw["exit"]["horizon"],
    }


def probe_negative_bracket():
    return {"stop_atr": -1.0, "target_atr": -2.0, "spec_errors": strategy(
        mode="bracket", stop_atr=-1.0, target_atr=-2.0).validate()}


def probe_initial_drawdown():
    d = pd.DataFrame({
        "entry_ts": pd.date_range("2020-01-01", periods=2, freq="D"),
        "exit_ts": pd.date_range("2020-01-02", periods=2, freq="D"),
        "net_bps": [-1000.0, 100.0], "bars_held": [24, 24],
    })
    # Independent calculation including the initial equity peak, using the
    # engine's documented sizing formula solely to isolate its drawdown error.
    x = d["net_bps"].to_numpy(float)
    leverage = 0.01 / (abs(np.percentile(x, 10)) / 1e4)
    equity = np.concatenate(([1.0], np.cumprod(1 + x / 1e4 * leverage)))
    expected_dd = float((equity / np.maximum.accumulate(equity) - 1).min())
    return {"reported": metrics.deployment(d, 3600),
            "drawdown_with_initial_equity": expected_dd}


PROBES = (
    ("E01", "future_signal_accepted", probe_future_signal,
     "Future signal accepted; every generated trade has positive net return.",
     lambda r: r["spec_errors"] == [] and r["trades"] > 0
     and r["fraction_positive"] == 1.0 and r["min_net_bps"] > 0),
    ("E02", "one_bar_future_feature_passes_causality_check", probe_future_feature,
     "The detector accepts the explicitly injected next-close feature.",
     lambda r: r["detector_accepted"] is True),
    ("E03", "future_high_on_timeout_bar_used", probe_timeout,
     "The target at 102 replaces the scheduled timeout open at 100.",
     lambda r: r["trade"]["reason"] == "target" and r["trade"]["exit"] == 102.0
     and r["trade"]["bars_held"] == 1 and r["timeout_open"] == 100.0),
    ("E04", "gap_stop_filled_above_available_market", probe_gap_stop,
     "The stop fills at 99 although the gap bar high is only 92.",
     lambda r: r["trade"]["reason"] == "stop" and r["trade"]["exit"] == 99.0
     and r["trade"]["exit"] > r["gap_bar_high"]),
    ("E05", "gap_trade_accepted_and_undercharged", probe_gap_cost,
     "24 elapsed hours count as one hour and incur 1 bp instead of 24 bps funding.",
     lambda r: r["elapsed_hours"] == 24.0 and r["bars_held"] == 1
     and r["cost_bps"] == 1.0 and r["expected_funding_bps_for_elapsed_time"] == 24.0),
    ("E06", "runtime_spec_mutation_changes_no_hash", probe_spec_hash,
     "Changing the live horizon from 1 to 200 leaves the hash unchanged.",
     lambda r: r["same_hash"] is True and r["horizon"] == 200 and r["raw_horizon"] == 1),
    ("E07", "negative_bracket_distances_accepted", probe_negative_bracket,
     "Negative stop and target distances produce no validation error.",
     lambda r: r["spec_errors"] == []),
    ("E08", "initial_loss_missing_from_drawdown", probe_initial_drawdown,
     "Reported drawdown is zero, while including initial equity gives a loss.",
     lambda r: r["reported"]["max_drawdown"] == 0.0
     and r["drawdown_with_initial_equity"] < -0.01),
)


def json_safe(value):
    """Keep output valid JSON even if a future implementation returns NaN."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def main():
    results = {}
    for finding_id, key, probe, expected, reproduced in PROBES:
        result = {"finding_id": finding_id, "expected_defect": expected,
                  "reproduced": False}
        try:
            evidence = probe()
            result["observed"] = evidence
            result["reproduced"] = bool(reproduced(evidence))
        except Exception as exc:
            # Record a failed reproduction and continue; do not suppress it as
            # success or print tracebacks containing local absolute paths.
            result["exception_type"] = type(exc).__name__
        results[key] = result

    source_hashes = {
        path: hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()
        for path in AUDITED_SOURCES
    }
    all_reproduced = all(result["reproduced"] for result in results.values())

    report = {
        "audited_commit": AUDITED_COMMIT,
        "executed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "generated fixtures only; no historical data or strategy validation",
        "source_sha256": source_hashes,
        "reproducer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "scipy": scipy.__version__,
        },
        "results": results,
        "all_expected_defects_reproduced": all_reproduced,
        "exit_code": 0 if all_reproduced else 1,
    }
    print(json.dumps(json_safe(report), indent=2, allow_nan=False))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
