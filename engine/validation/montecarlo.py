"""
Monte-Carlo sur l'ORDRE des trades.

Ce que ca teste : le drawdown observe est-il representatif, ou est-ce qu'on a eu
de la chance dans l'enchainement ? Une courbe d'equite lisse peut cacher une
distribution ou un ordre defavorable ruine le compte.

Ce que ca NE teste PAS : la validite de l'edge. Remelanger des trades garde leur
esperance intacte. Ne jamais presenter un Monte-Carlo comme une preuve d'edge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def run(trades: pd.DataFrame, n_sims: int = 5000, seed: int = 99,
        risque_pct: float = 1.0) -> dict:
    x = trades["net_bps"].to_numpy(float)
    n = len(x)
    if n < 20:
        return {"note": "moins de 20 trades, non calculable"}

    perte_type = abs(np.percentile(x, 10))
    if perte_type <= 0:
        return {"note": "aucune perte au 10e centile, dimensionnement impossible"}
    levier = (risque_pct / 100) / (perte_type / 1e4)

    rng = np.random.default_rng(seed)
    dds, finals, ruines = np.empty(n_sims), np.empty(n_sims), 0

    for i in range(n_sims):
        r = rng.permutation(x) / 1e4 * levier
        eq = np.cumprod(1 + r)
        dds[i] = (eq / np.maximum.accumulate(eq) - 1).min()
        finals[i] = eq[-1] - 1
        if eq.min() <= 0.5:          # -50 % : compte mort en pratique
            ruines += 1

    return {
        "n_sims": n_sims,
        "levier": round(levier, 2),
        "dd_median": round(float(np.median(dds)), 4),
        "dd_p95": round(float(np.percentile(dds, 5)), 4),   # 5e centile = pire 5 %
        "dd_pire": round(float(dds.min()), 4),
        "rendement_median": round(float(np.median(finals)), 4),
        "part_simulations_perdantes": round(float((finals < 0).mean()), 4),
        "risque_de_ruine_50pct": round(ruines / n_sims, 4),
        "note": "remelanger conserve l'esperance : ceci mesure le risque de sequence, pas l'edge",
    }
