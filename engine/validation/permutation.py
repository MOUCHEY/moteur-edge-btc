"""
Permutation d'etiquettes : la CONDITION porte-t-elle de l'information ?

Null teste : « les rendements sont les memes, mais l'etiquette (heure, regime,
seuil, session) est distribuee au hasard ». Si le vrai resultat se noie dans
cette distribution, la condition ne sert a rien.

Piege central : les lignes ne sont PAS independantes. Plusieurs mesures issues
du meme jour, du meme evenement, ou de fenetres qui se chevauchent forment une
grappe. Permuter ligne a ligne casse la dependance et fabrique un null trop
etroit — le p sort minuscule et faux. On permute donc par GRAPPE.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps


def permute_labels(labels: pd.Series, clusters: pd.Series | None,
                   rng: np.random.Generator) -> np.ndarray:
    """Permute les etiquettes en gardant intacte la structure de grappes."""
    lab = labels.to_numpy()
    if clusters is None:
        return rng.permutation(lab)

    cl = clusters.to_numpy()
    if len(cl) != len(lab) or pd.isna(cl).any():
        raise ValueError("grappes alignees et sans valeurs manquantes requises")
    uniq = pd.unique(cl)
    # une etiquette par grappe : on permute les grappes entieres
    rep = {c: lab[cl == c] for c in uniq}
    if len({len(block) for block in rep.values()}) != 1:
        raise ValueError("grappes inegales : une permutation adaptee doit etre preenregistree")
    shuffled = rng.permutation(uniq)
    out = np.empty_like(lab)
    for src, dst in zip(uniq, shuffled):
        m = cl == dst
        block = rep[src]
        out[m] = block
    return out


def test(values: pd.Series, labels: pd.Series, selected, clusters: pd.Series | None = None,
         n_perm: int = 5000, seed: int = 7, stat: str = "mean") -> dict:
    """
    `values`   : rendement net par evenement, en bps — le GAIN DE CHAQUE EVENEMENT.
                 Ne jamais passer une esperance calculee avec un parametre MOYEN
                 ou un cout MEDIAN : ca detruit la variance et fausse le p.
    `selected` : valeur(s) d'etiquette qui definissent la poche testee.
    `clusters` : identifiant de grappe (ex. la date) — obligatoire si les
                 evenements se chevauchent.
    """
    sel = set(selected if isinstance(selected, (list, tuple, set)) else [selected])
    v = values.to_numpy(float)
    ok = np.isfinite(v)
    v, labels = v[ok], labels[ok]
    clusters = clusters[ok] if clusters is not None else None

    def compute(lab_arr):
        m = np.isin(lab_arr, list(sel))
        if m.sum() < 5:
            return np.nan
        x = v[m]
        if stat == "mean":
            return x.mean()
        if stat == "t":
            s = x.std(ddof=1)
            return x.mean() / (s / np.sqrt(len(x))) if s > 0 else np.nan
        raise ValueError(stat)

    reel = compute(labels.to_numpy())
    rng = np.random.default_rng(seed)
    null = np.array([compute(permute_labels(labels, clusters, rng)) for _ in range(n_perm)])
    null = null[np.isfinite(null)]

    if not np.isfinite(reel) or len(null) < 100:
        return {"p_empirique": np.nan, "raison": "echantillon insuffisant"}

    # +1 au numerateur et au denominateur : un p empirique ne vaut jamais 0
    p = (1 + (null >= reel).sum()) / (1 + len(null))
    n_clusters = int(pd.unique(clusters).size) if clusters is not None else int(len(v))

    return {
        "qualified": False,
        "passe_G4": False,
        "scope": "Sensibilite conditionnelle a une echangeabilite non certifiee ; aucune promotion de porte.",
        "reel": float(reel),
        "null_median": float(np.median(null)),
        "null_p95": float(np.percentile(null, 95)),
        "p_empirique": float(p),
        "n_permutations": int(len(null)),
        "n_evenements": int(len(v)),
        "n_grappes": n_clusters,
        "resolution_p": round(1 / (1 + len(null)), 5),
        "avertissement": (
            "p proche du seuil (0,04-0,06) : c'est le nombre de tirages qui parle "
            "autant que le marche" if 0.04 <= p <= 0.06 else
            "p tres petit sur peu de grappes : verifier que les grappes sont bien "
            "les unites independantes" if p < 0.01 and n_clusters < 300 else None
        ),
    }
