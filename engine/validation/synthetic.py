"""Sensibilite descriptive par blocs. Ce generateur ne certifie aucun modele nul.

Le centrage ne supprime pas les dependances conditionnelles. Bonferroni peut
rester valide sans independance, sous p-valeurs elementaires valides. Les
quantiles ci-dessous ne constituent donc pas automatiquement une porte G4.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def block_bootstrap(df: pd.DataFrame, block: int, rng: np.random.Generator,
                    remove_drift: bool = False) -> pd.DataFrame:
    """
    Reconstruit une serie OHLCV synthetique par blocs de barres entieres.

    On bootstrappe des blocs d'INDICES, pas de prix : la geometrie intra-barre
    (position de open/high/low par rapport au close) et le volume suivent la
    barre d'origine. Seul l'enchainement temporel est detruit.
    """
    n = len(df)
    if type(block) is not int or not 1 <= block <= n:
        raise ValueError("block entier entre 1 et la taille de serie requis")
    c = df["close"].to_numpy(float)
    logret = np.diff(np.log(c), prepend=np.log(c[0]))
    logret[0] = 0.0

    if remove_drift:
        logret = logret - logret.mean()

    # geometrie interne de chaque barre, relative a son close
    ratio_o = df["open"].to_numpy(float) / c
    ratio_h = df["high"].to_numpy(float) / c
    ratio_l = df["low"].to_numpy(float) / c

    starts = rng.integers(0, n - block + 1, size=int(np.ceil(n / block)))
    idx = np.concatenate([np.arange(s, min(s + block, n)) for s in starts])[:n]

    new_ret = logret[idx]
    new_close = c[0] * np.exp(np.cumsum(new_ret))

    out = pd.DataFrame({
        "ts": df["ts"].to_numpy(),                # calendrier reel conserve
        "close": new_close,
        "open": new_close * ratio_o[idx],
        "high": new_close * ratio_h[idx],
        "low": new_close * ratio_l[idx],
        "volume": df["volume"].to_numpy()[idx],
        "trades": df["trades"].to_numpy()[idx],
        "taker_buy_base": df["taker_buy_base"].to_numpy()[idx],
        "quote_volume": df["quote_volume"].to_numpy()[idx] * new_close / c[idx],
    })
    # coherence OHLC apres reconstruction
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    return out


def noise_floor(df: pd.DataFrame, sweep_fn, block: int, n_sims: int = 200,
                seed: int = 12345, horizon: int | None = None,
                remove_drift: bool = False) -> dict:
    """Conserve toutes les statistiques/erreurs ; aucun seuil de passage valide."""
    if type(n_sims) is not int or n_sims < 1:
        raise ValueError("n_sims doit etre un entier positif")
    if type(block) is not int or not 1 <= block <= len(df):
        raise ValueError("taille de bloc invalide")
    rng = np.random.default_rng(seed)
    outcomes, values = [], []
    for i in range(n_sims):
        try:
            syn = block_bootstrap(df, block, rng, remove_drift=remove_drift)
            v = sweep_fn(syn)
            if v is None or not np.isfinite(v):
                raise ValueError("statistique non finie")
            values.append(float(v))
            outcomes.append({"simulation": i, "value": float(v), "error_type": None})
        except Exception as exc:
            outcomes.append({"simulation": i, "value": None, "error_type": type(exc).__name__})
    b = np.asarray(values, float)
    return {
        "n_sims_requested": n_sims, "n_sims_valides": len(values),
        "n_sims_failed": n_sims - len(values), "seed": seed,
        "block": block, "remove_drift": remove_drift,
        "p05": float(np.percentile(b, 5)) if len(b) else None,
        "median": float(np.median(b)) if len(b) else None,
        "p95": float(np.percentile(b, 95)) if len(b) else None,
        "p99": float(np.percentile(b, 99)) if len(b) else None,
        "max": float(b.max()) if len(b) else None,
        "outcomes": outcomes, "qualified_null": False,
        "avertissement": "Sensibilite descriptive. Dependances conservees ; quantiles sans garantie de faux positifs.",
    }


def verdict(reel: float, floor: dict) -> dict:
    """Aucune promotion possible a partir de cette sensibilite."""
    return {"passe": False, "qualified": False,
            "reason": "G4 indisponible : modele nul, selection et precision non qualifies.",
            "statistique_comparee": float(reel) if reel is not None and np.isfinite(reel) else None,
            "p95_descriptif": floor.get("p95")}
