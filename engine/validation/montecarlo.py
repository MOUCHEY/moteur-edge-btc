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
from ..metrics import equity_path


def run(trades: pd.DataFrame, n_sims: int = 5000, seed: int = 99,
        risque_pct: float = 1.0) -> dict:
    x = trades["net_bps"].to_numpy(float)
    status = {"qualifie": False, "statut": "scenario_hypothetique_ex_post",
              "seed": seed, "risque_pct": risque_pct}
    if (isinstance(n_sims, (bool, np.bool_)) or not isinstance(n_sims, (int, np.integer))
            or n_sims < 1 or not np.isfinite(risque_pct) or risque_pct <= 0):
        raise ValueError("nombre de simulations ou echelle de risque invalide")
    if not np.isfinite(x).all():
        raise ValueError("rendements non finis")
    n = len(x)
    if n < 20:
        return {**status, "calculable": False, "note": "moins de 20 trades, non calculable"}

    q10 = float(np.percentile(x, 10))
    if q10 >= 0:
        return {**status, "calculable": False,
                "note": "10e centile non negatif, dimensionnement impossible"}
    perte_type = abs(q10)
    levier = (risque_pct / 100) / (perte_type / 1e4)

    rng = np.random.default_rng(seed)
    dds, finals, ruines, insolvables = np.empty(n_sims), np.empty(n_sims), 0, 0

    for i in range(n_sims):
        r = rng.permutation(x) / 1e4 * levier
        eq = equity_path(r)
        dds[i] = (eq / np.maximum.accumulate(eq) - 1).min()
        finals[i] = eq[-1] - 1
        if eq.min() <= 0.5:          # seuil descriptif, relatif au capital initial
            ruines += 1
        if (eq == 0).any():
            insolvables += 1

    return {
        **status, "calculable": True,
        "n_sims": n_sims,
        "levier": round(levier, 2),
        "dd_median": round(float(np.median(dds)), 4),
        "dd_p95": round(float(np.percentile(dds, 5)), 4),   # 5e centile = pire 5 %
        "dd_pire": round(float(dds.min()), 4),
        "rendement_median": round(float(np.median(finals)), 4),
        "part_simulations_perdantes": round(float((finals < 0).mean()), 4),
        "risque_de_ruine_50pct": round(ruines / n_sims, 4),
        "seuil_alerte_fraction_capital_initial": 0.5,
        "part_scenarios_insolvables": round(insolvables / n_sims, 4),
        "note": "ordre seul permute, dependance temporelle detruite ; dimensionnement "
                "ex post sur 10e centile de tous les rendements, sans courtier ; "
                "capital initial inclus, ruine absorbante ; aucune preuve d'edge",
    }
