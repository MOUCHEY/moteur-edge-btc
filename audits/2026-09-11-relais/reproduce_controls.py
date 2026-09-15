"""Contre-exemples de controles, exclusivement sur fixtures temporaires.

Lancer depuis n'importe quel repertoire. Aucun fichier de marche du depot,
aucun coffre, aucune clef et aucun service distant ne sont lus. Les appels
nommes IS/OOS ci-dessous portent sur un CSV fictif cree dans TemporaryDirectory.
Le script imprime un constat JSON ; il ne corrige pas les sources du moteur.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import scipy
import yaml

from engine import data, run, calibrate
from engine.validation import synthetic

BASELINE = "7454850c1328d41bf626766825833a480a5f4139"


def bars(n=1800):
    rng = np.random.default_rng(401)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    return pd.DataFrame({
        "ts": pd.date_range("2022-12-01", periods=n, freq="h", tz="UTC"),
        "open": close, "close": close, "high": close * 1.002,
        "low": close * 0.998, "volume": 10.0, "trades": 20,
        "taker_buy_base": 5.0, "quote_volume": 10 * close,
    })


def fake_backtest(df, feats, sp, params, *args, **kwargs):
    """Statistiques ordonnees par x pour isoler la logique de selection."""
    x = np.tile(np.array([-2.0, -1.0, 0.0, 1.0, 2.0]), 8) + params["x"]
    ts = pd.date_range("2000-01-01", periods=len(x), freq="2h", tz="UTC")
    return pd.DataFrame({
        "net_bps": x, "gross_bps": x + 6, "cost_bps": 6.0,
        "bars_held": 1, "entry_ts": ts,
        "exit_ts": ts + pd.Timedelta(hours=1),
    })


def main():
    findings = {}
    with tempfile.TemporaryDirectory(prefix="edge-controls-") as tmp:
        root = Path(tmp)
        proc = root / "processed"
        proc.mkdir()
        df = bars()
        df.to_csv(proc / "BTCUSDT-1h.csv.gz", index=False, compression="gzip")
        sp = root / "spec.yaml"
        sp.write_text(yaml.safe_dump({
            "id": "AUDIT-SYNTHETIC", "titre": "Fixture de controle",
            "auteur": "astra", "data": {"interval": "1h"},
            "signal": {"entry_long": "ret_1 > {x}"},
            "exit": {"mode": "horizon", "horizon": 1},
            "params": {"x": [1, 2, 3]}, "budget_essais": 3,
        }))
        led = root / "ledger.json"
        initial = {"total_configs": 136, "runs": []}
        led.write_text(json.dumps(initial))

        # Le chargeur lit uniquement le CSV fictif du repertoire temporaire.
        with patch.object(data, "PROC", proc):
            is_ts = set(data.load("1h", "IS")["ts"])
            oos_ts = set(data.load("1h", "OOS")["ts"])
            common = sorted(is_ts & oos_ts)
            findings["C01_split_overlap"] = {
                "reproduced": len(common) == 1,
                "shared_synthetic_timestamps": [str(t) for t in common],
            }

            # Les backtests sont remplaces par des tableaux de nombres fixes.
            # Les controles de split, compteur et fichiers du CLI sont reels.
            def invoke(split, no_ledger=False):
                argv = ["engine.run", str(sp), "--split", split]
                if no_ledger:
                    argv.append("--no-ledger")
                sink = io.StringIO()
                with patch.object(sys, "argv", argv), \
                     contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                    return run.main()

            with patch.object(run, "LEDGER", led), \
                 patch.object(run, "data_fingerprint", return_value="synthetic-only"), \
                 patch.object(run.backtest, "run", side_effect=fake_backtest), \
                 patch.object(run.metrics, "deployment", return_value={}), \
                 patch.object(run.montecarlo, "run", return_value={}), \
                 patch.object(run.metrics, "deflated_sharpe", return_value={"dsr": None}) as dsr:
                before = led.read_bytes()
                first = invoke("OOS", no_ledger=True)
                reports = list((root / "results").glob("OOS_*.json"))
                first_report = json.loads(reports[0].read_text())
                reports[0].write_text('{"sentinel_previous_report": true}')
                second = invoke("OOS", no_ledger=True)
                after = json.loads(reports[0].read_text())
                findings["C02_oos_without_gates_and_reselected"] = {
                    "reproduced": first == 0
                        and first_report["meilleure_config"].get("x") == 3
                        and len(first_report["balayage"]) == 3,
                    "exit_code": first, "grid_configurations_evaluated": len(first_report["balayage"]),
                    "selected_on_synthetic_oos": first_report["meilleure_config"],
                    "gate_evidence_supplied": False,
                }
                findings["C03_repeated_oos_unrecorded_overwrite"] = {
                    "reproduced": second == 0 and led.read_bytes() == before
                        and "sentinel_previous_report" not in after,
                    "second_exit_code": second,
                    "ledger_unchanged": led.read_bytes() == before,
                    "report_replaced": "sentinel_previous_report" not in after,
                    "oos_report_files_after_two_runs": len(list((root / "results").glob("OOS_*.json"))),
                }
                dsr.reset_mock()
                recorded_exit = invoke("IS")
                passed_count = dsr.call_args.args[1]
                total_after = json.loads(led.read_text())["total_configs"]
                findings["C04_dsr_before_new_trials"] = {
                    "reproduced": recorded_exit == 0 and passed_count == 136 and total_after == 139,
                    "prior_count_fixture": 136, "new_configurations": 3,
                    "count_sent_to_dsr": passed_count, "ledger_after_run": total_after,
                }
                before_failure = led.read_bytes()
                with patch.object(run, "load", side_effect=RuntimeError("synthetic_failure_before_results")):
                    try:
                        invoke("IS")
                    except RuntimeError as exc:
                        failed = str(exc) == "synthetic_failure_before_results"
                    else:
                        failed = False
                findings["C05_failure_not_recorded"] = {
                    "reproduced": failed and led.read_bytes() == before_failure,
                    "injected_failure": failed, "ledger_unchanged": led.read_bytes() == before_failure,
                }
                findings["C09_metric_injected_as_parameter"] = {
                    "reproduced": "one_sided" in first_report["meilleure_config"],
                    "declared_parameter_names": ["x"],
                    "reported_parameter_names": sorted(first_report["meilleure_config"]),
                    "cause": "p_one_sided metric is selected by the p_ parameter prefix filter.",
                }

        # Un processus a moyenne nulle peut rester previsible dans les blocs.
        predictable = bars(2400)
        ret = np.tile(np.r_[np.full(12, 0.01), np.full(12, -0.01)], 100)
        c = 100 * np.exp(np.cumsum(ret))
        predictable["close"] = c
        predictable["open"] = c
        predictable["high"] = c * 1.002
        predictable["low"] = c * 0.998
        rebuilt = synthetic.block_bootstrap(predictable, 24, np.random.default_rng(402), remove_drift=True)
        r = np.diff(np.log(rebuilt["close"].to_numpy()))
        predictive_gain = float(np.mean(np.sign(r[:-1]) * r[1:]))
        findings["C06_bootstrap_can_preserve_predictability"] = {
            "reproduced": predictive_gain > 0.005,
            "synthetic_process": "12 positive returns then 12 negative, repeated; block 24; drift removed",
            "lagged_sign_times_next_log_return_mean": predictive_gain,
            "scope": "Counterexample to a universally no-predictability null; not a market strategy test.",
        }
        floor = synthetic.noise_floor(bars(600), lambda _: 1.0, block=24, n_sims=1)
        verdict = synthetic.verdict(2.0, floor)
        findings["C07_one_simulation_can_pass_floor"] = {
            "reproduced": floor["n_sims_valides"] == 1 and verdict.get("passe") is True,
            "valid_simulations": floor["n_sims_valides"], "passes": verdict.get("passe"),
            "note": "No inference precision or valid null supplied.",
        }

        def fail(_):
            raise ValueError("synthetic_error")

        failed_floor = synthetic.noise_floor(bars(600), fail, block=24, n_sims=3)
        findings["C08_simulation_errors_not_described"] = {
            "reproduced": failed_floor["n_sims_valides"] == 0
                and not any(k in failed_floor for k in ("errors", "erreurs", "n_sims_failed")),
            "simulations_requested": 3, "valid_simulations": failed_floor["n_sims_valides"],
            "note": "Errors become NaN without a per-simulation error record.",
        }

    files = ["engine/data.py", "engine/run.py", "engine/validation/synthetic.py", "engine/metrics.py"]
    result = {
        "baseline_commit": BASELINE, "synthetic_only": True,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market_data_or_vault_read": False,
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "pandas": pd.__version__, "scipy": scipy.__version__, "pyyaml": yaml.__version__},
        "code_sha256": {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files},
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "findings": findings,
    }
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if all(v["reproduced"] for v in findings.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
