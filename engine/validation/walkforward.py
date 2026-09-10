"""
Walk-forward ancre : on ne choisit jamais un parametre avec de l'information
qu'on n'aurait pas eue au moment de choisir.

Ancre (et non glissant) : la fenetre d'apprentissage part toujours du debut et
s'allonge. C'est ce que fait reellement quelqu'un qui accumule de l'historique.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def run(df: pd.DataFrame, feats: pd.DataFrame, spec, backtest_fn, metric_fn,
        n_folds: int = 6, min_train_frac: float = 0.35) -> dict:
    n = len(df)
    start = int(n * min_train_frac)
    bornes = np.linspace(start, n, n_folds + 1).astype(int)

    folds = []
    for i in range(n_folds):
        tr_end = bornes[i]
        te_end = bornes[i + 1]
        if te_end - tr_end < 50:
            continue

        # 1) choisir le meilleur parametre SUR LE TRAIN uniquement
        best, best_score = None, -np.inf
        for p in spec.grid():
            tr = backtest_fn(df.iloc[:tr_end], feats.iloc[:tr_end], spec, p)
            if len(tr) < 10:
                continue
            s = metric_fn(tr)
            if np.isfinite(s) and s > best_score:
                best, best_score = p, s

        if best is None:
            folds.append({"fold": i, "statut": "aucun parametre entrainable"})
            continue

        # 2) l'appliquer tel quel sur le segment suivant, jamais vu
        te = backtest_fn(df.iloc[tr_end:te_end], feats.iloc[tr_end:te_end], spec, best)
        score = metric_fn(te) if len(te) else np.nan
        folds.append({
            "fold": i,
            "train_barres": int(tr_end),
            "test_barres": int(te_end - tr_end),
            "params_choisis": best,
            "train_score": round(float(best_score), 3),
            "test_score": round(float(score), 3) if np.isfinite(score) else None,
            "test_trades": int(len(te)),
            "test_net_bps": round(float(te["net_bps"].mean()), 3) if len(te) else None,
        })

    valides = [f for f in folds if f.get("test_net_bps") is not None]
    positifs = [f for f in valides if f["test_net_bps"] > 0]
    # la stabilite du choix compte autant que la performance
    choix = [str(f.get("params_choisis")) for f in valides]
    stabilite = (max(choix.count(c) for c in set(choix)) / len(choix)) if choix else np.nan

    return {
        "folds": folds,
        "n_folds_valides": len(valides),
        "part_folds_positifs": round(len(positifs) / len(valides), 3) if valides else None,
        "net_bps_moyen_oos": round(float(np.mean([f["test_net_bps"] for f in valides])), 3) if valides else None,
        "stabilite_parametres": round(float(stabilite), 3) if valides else None,
        "passe_G5": bool(valides and len(positifs) / len(valides) >= 0.60),
    }
