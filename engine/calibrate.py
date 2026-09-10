"""
Mesure du plancher de bruit d'un balayage.

    python3 -m engine.calibrate <spec.yaml> --sims 200 --block 168

Rejoue EXACTEMENT le meme balayage sur des series synthetiques ou l'on sait
qu'il n'y a rien a trouver. Le comparateur legitime est le MAXIMUM du balayage
reel contre la distribution des MAXIMA obtenus sur du bruit — pas la valeur
d'une configuration isolee contre zero.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import backtest, features, metrics, spec as spec_mod
from .data import STEP_SECONDS, load
from .validation import synthetic


def max_t(df, sp) -> float:
    f = features.build(df)
    best = -np.inf
    for p in sp.grid():
        tr = backtest.run(df, f, sp, p)
        if len(tr) < 30:
            continue
        t = metrics.research(tr, STEP_SECONDS[sp.interval])["t_net"]
        if np.isfinite(t):
            best = max(best, t)
    return best if np.isfinite(best) else np.nan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--sims", type=int, default=200)
    ap.add_argument("--block", type=int, default=168, help="barres par bloc de bootstrap")
    ap.add_argument("--split", default="IS")
    ap.add_argument("--remove-drift", action="store_true",
                    help="null sans derive : isole la STRUCTURE de la tendance de fond")
    a = ap.parse_args()

    sp = spec_mod.load(a.spec)
    df = load(sp.interval, a.split)

    reel = max_t(df, sp)
    print(f"balayage reel : {len(sp.grid())} configs, max t = {reel:.3f}", flush=True)

    floor = synthetic.noise_floor(
        df, lambda d: max_t(d, sp), block=a.block, n_sims=a.sims,
        horizon=sp.horizon, remove_drift=a.remove_drift)
    v = synthetic.verdict(reel, floor)

    out = {
        "exp": sp.id, "spec_hash": sp.hash, "split": a.split,
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_configs": len(sp.grid()), "max_t_reel": round(float(reel), 4),
        "plancher": floor, "verdict": v,
    }
    d = Path(a.spec).parent / "results"
    d.mkdir(parents=True, exist_ok=True)
    suffix = "_nodrift" if a.remove_drift else ""
    (d / f"plancher_{a.split}{suffix}.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
