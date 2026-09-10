"""
Harness d'execution. Point d'entree unique du depot.

    python3 -m engine.run experiments/EXP-0001/spec.yaml --split IS

Tout chiffre publie dans ce depot doit etre reproductible par cette commande.
Chaque execution incremente le compteur d'essais global : le budget est une
ressource et il se depense, y compris sur les experiences ratees.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest, features, metrics, spec as spec_mod
from .costs import DEFAULT
from .data import ROOT, STEP_SECONDS, data_fingerprint, load
from .validation import montecarlo, walkforward

LEDGER = ROOT / "experiments" / "ledger.json"


# ------------------------------------------------------------------ compteur
def bump_ledger(exp_id: str, spec_hash: str, n_configs: int, split: str) -> dict:
    led = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"total_configs": 0, "runs": []}
    led["total_configs"] += n_configs
    led["runs"].append({
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "exp": exp_id, "spec_hash": spec_hash, "configs": n_configs, "split": split,
    })
    if split == "OOS":
        led.setdefault("oos_ouvertures", []).append({"exp": exp_id, "hash": spec_hash})
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(led, indent=2) + "\n")
    return led


# ------------------------------------------------------------------ analyses
def sweep(df, feats, sp, costs=DEFAULT) -> pd.DataFrame:
    """Balaye la grille. Retourne une ligne par configuration."""
    rows = []
    for p in sp.grid():
        tr = backtest.run(df, feats, sp, p, costs)
        m = metrics.research(tr, STEP_SECONDS[sp.interval])
        rows.append({**{f"p_{k}": v for k, v in p.items()}, **m})
    return pd.DataFrame(rows)


def famille(sw: pd.DataFrame) -> dict:
    """
    Test d'ensemble. La question n'est pas « le meilleur est-il bon ? » mais
    « la famille entiere penche-t-elle du bon cote ? ». Une cellule brillante
    entouree de voisins negatifs est du bruit, quel que soit son t-stat.
    """
    from scipy import stats as sps
    t = sw["t_net"].dropna()
    if len(t) < 3:
        return {"note": "moins de 3 configurations, test d'ensemble non applicable",
                "mediane_t": float(t.median()) if len(t) else None}
    w = sps.wilcoxon(t, alternative="greater") if (t != 0).any() else None
    pos = float((t > 0).mean())
    return {
        "n_configs": int(len(t)),
        "mediane_t": round(float(t.median()), 3),
        "part_configs_positives": round(pos, 3),
        "wilcoxon_p": round(float(w.pvalue), 4) if w is not None else None,
        "passe_G1_famille": bool(t.median() > 0),
        "voisinage_G3": bool(pos >= 0.75),
    }


def moities(df, feats, sp, best_p) -> dict:
    """Un edge reel n'apparait pas dans une seule moitie de l'echantillon."""
    n = len(df)
    out = {}
    for nom, sl in (("premiere", slice(0, n // 2)), ("seconde", slice(n // 2, n))):
        tr = backtest.run(df.iloc[sl], feats.iloc[sl], sp, best_p)
        m = metrics.research(tr, STEP_SECONDS[sp.interval])
        out[nom] = {"n_trades": m["n_trades"], "net_bps": round(m["net_bps"], 3) if m["n_trades"] else None,
                    "t_net": round(m["t_net"], 3) if m["n_trades"] > 1 and np.isfinite(m["t_net"]) else None}
    a, b = out["premiere"]["net_bps"], out["seconde"]["net_bps"]
    out["passe_G3"] = bool(a is not None and b is not None and a > 0 and b > 0)
    return out


def sensibilite_couts(df, feats, sp, best_p) -> dict:
    out = {}
    for f in (1.0, 1.5, 2.0):
        tr = backtest.run(df, feats, sp, best_p, DEFAULT.scaled(f))
        m = metrics.research(tr, STEP_SECONDS[sp.interval])
        out[f"x{f}"] = {"net_bps": round(m["net_bps"], 3) if m["n_trades"] else None,
                        "t_net": round(m["t_net"], 3) if m["n_trades"] > 1 and np.isfinite(m["t_net"]) else None}
    out["passe_G3"] = bool(out["x2.0"]["net_bps"] is not None and out["x2.0"]["net_bps"] > 0)
    return out


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Harness moteur EDGE RENTABLE / BTC")
    ap.add_argument("spec")
    ap.add_argument("--split", default="IS", choices=["IS", "OOS", "VAULT"])
    ap.add_argument("--no-ledger", action="store_true", help="diagnostic seul, ne compte pas au budget")
    ap.add_argument("--walkforward", action="store_true")
    a = ap.parse_args()

    sp = spec_mod.load(a.spec)
    errs = sp.validate()
    if errs:
        print("SPEC REFUSEE :", file=sys.stderr)
        for e in errs:
            print("  -", e, file=sys.stderr)
        return 2

    if a.split in ("OOS", "VAULT"):
        print(f"!! Ouverture {a.split} — irreversible (PROTOCOLE.md G5/G6).", file=sys.stderr)

    df = load(sp.interval, a.split)
    feats = features.build(df)
    features.assert_causal(df, feats)          # plante si fuite de lookahead

    sw = sweep(df, feats, sp)
    fam = famille(sw)

    valides = sw.dropna(subset=["t_net"])
    if len(valides) == 0:
        print("aucune configuration n'a produit de trades exploitables", file=sys.stderr)
        best_p, best_row = {}, None
    else:
        best_row = valides.loc[valides["t_net"].idxmax()]
        best_p = {c[2:]: best_row[c] for c in sw.columns if c.startswith("p_")}

    report = {
        "exp": sp.id, "titre": sp.titre, "auteur": sp.auteur,
        "spec_hash": sp.hash, "split": a.split, "interval": sp.interval,
        "data_fingerprint": data_fingerprint(sp.interval),
        "barres": int(len(df)),
        "periode": [str(df["ts"].iloc[0]), str(df["ts"].iloc[-1])],
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "couts_bps_aller_retour": DEFAULT.round_trip(),
        "n_configs": len(sp.grid()),
        "budget_declare": sp.budget_declare,
        "balayage": json.loads(sw.to_json(orient="records")),
        "test_de_famille": fam,
    }

    if best_row is not None:
        tr = backtest.run(df, feats, sp, best_p)
        led_total = json.loads(LEDGER.read_text())["total_configs"] if LEDGER.exists() else len(sp.grid())
        report.update({
            "meilleure_config": {k: (v.item() if hasattr(v, "item") else v) for k, v in best_p.items()},
            "recherche": {k: (round(v, 4) if isinstance(v, float) and np.isfinite(v) else v)
                          for k, v in metrics.research(tr, STEP_SECONDS[sp.interval]).items()},
            "deploiement": metrics.deployment(tr, STEP_SECONDS[sp.interval]),
            "deflated_sharpe": metrics.deflated_sharpe(tr, max(led_total, len(sp.grid()))),
            "moities_temporelles": moities(df, feats, sp, best_p),
            "sensibilite_couts": sensibilite_couts(df, feats, sp, best_p),
            "monte_carlo": montecarlo.run(tr),
        })
        if a.walkforward:
            report["walk_forward"] = walkforward.run(
                df, feats, sp, backtest.run,
                lambda t: metrics.research(t, STEP_SECONDS[sp.interval])["t_net"])

    if not a.no_ledger:
        led = bump_ledger(sp.id, sp.hash, len(sp.grid()), a.split)
        report["budget_projet_apres_run"] = led["total_configs"]

    outdir = Path(a.spec).parent / "results"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{a.split}_{sp.hash}.json"
    out.write_text(json.dumps(report, indent=2, default=str) + "\n")

    print(json.dumps({k: report[k] for k in report if k != "balayage"}, indent=2, default=str))
    print(f"\n-> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
