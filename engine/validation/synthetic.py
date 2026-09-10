"""
Plancher de bruit par rejeu du MEME balayage sur donnees synthetiques.

Pourquoi : avec N configurations qui partagent les memes donnees, le seuil
theorique de tests multiples (Bonferroni, sqrt(2 ln N)) est inapplicable — les
essais ne sont pas independants. On mesure donc le plancher au lieu de le
postuler : on refait exactement la meme recherche sur des series ou l'on SAIT
qu'il n'y a rien, et on regarde ce que la recherche y trouve quand meme.

Deux pieges qui invalident silencieusement ce test :
  1. Une friction exprimee en valeur ABSOLUE sur des series dont le niveau de
     prix derive librement. Ici tout est en bps (relatif) : neutralise.
  2. Des blocs PLUS LONGS que l'horizon de la strategie. Le bloc preserve alors
     une partie de la structure qu'on teste. Le sens du biais NE SE DEVINE PAS :
     si la structure preservee est defavorable a la strategie, le plancher
     s'abaisse et le test devient trop permissif ; si elle lui est favorable, il
     s'eleve et le test devient trop conservateur. Mesure sur EXP-0000 (retour a
     la moyenne sur BTC, structure de fond defavorable) : block=168 -> p95=0,60 ;
     block=24 -> p95=1,67. Toujours declarer la taille de blocs, et en publier
     au moins deux.
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
    c = df["close"].to_numpy(float)
    logret = np.diff(np.log(c), prepend=np.log(c[0]))
    logret[0] = 0.0

    if remove_drift:
        logret = logret - logret.mean()

    # geometrie interne de chaque barre, relative a son close
    ratio_o = df["open"].to_numpy(float) / c
    ratio_h = df["high"].to_numpy(float) / c
    ratio_l = df["low"].to_numpy(float) / c

    starts = rng.integers(0, max(n - block, 1), size=int(np.ceil(n / block)))
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
        "quote_volume": df["quote_volume"].to_numpy()[idx],
    })
    # coherence OHLC apres reconstruction
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    return out


def noise_floor(df: pd.DataFrame, sweep_fn, block: int, n_sims: int = 200,
                seed: int = 12345, horizon: int | None = None,
                remove_drift: bool = False) -> dict:
    """
    `sweep_fn(df_synthetique) -> meilleure statistique du balayage`.

    On compare la statistique REELLE a la distribution des MEILLEURES
    statistiques obtenues sur du bruit. Le bon comparateur est le maximum du
    balayage, pas la valeur d'une configuration isolee.
    """
    warn = None
    if horizon is not None and block > horizon:
        warn = (f"block={block} > horizon={horizon} : les blocs conservent une partie "
                f"de la structure testee. Le SENS du biais depend du signe de la "
                f"relation entre cette structure et la strategie, et ne se devine pas : "
                f"mesure sur EXP-0000, block=168 donne un plancher PLUS BAS (p95=0,60) "
                f"que block=24 (p95=1,67), donc un test plus PERMISSIF — l'inverse de "
                f"l'attente courante. Declarer la taille de blocs avec tout resultat, "
                f"et en publier au moins deux.")

    rng = np.random.default_rng(seed)
    best = []
    for _ in range(n_sims):
        syn = block_bootstrap(df, block, rng, remove_drift=remove_drift)
        try:
            v = sweep_fn(syn)
        except Exception:
            v = np.nan
        if v is not None and np.isfinite(v):
            best.append(float(v))

    b = np.asarray(best, float)
    return {
        "n_sims_valides": int(len(b)),
        "block": block,
        "remove_drift": remove_drift,
        "p05": float(np.percentile(b, 5)) if len(b) else np.nan,
        "median": float(np.median(b)) if len(b) else np.nan,
        "p95": float(np.percentile(b, 95)) if len(b) else np.nan,
        "p99": float(np.percentile(b, 99)) if len(b) else np.nan,
        "max": float(b.max()) if len(b) else np.nan,
        "avertissement": warn,
    }


def verdict(reel: float, floor: dict) -> dict:
    """Le resultat reel bat-il le plancher ? Un plancher > reel est un signal d'alarme."""
    if not np.isfinite(floor.get("p95", np.nan)):
        return {"passe": False, "raison": "plancher non calculable"}
    if floor["median"] > reel:
        # Deux causes possibles, a ne pas confondre :
        #  (a) defaut d'outil (friction absolue, blocs trop longs, bug de cout)
        #  (b) la strategie est REELLEMENT perdante, et le bruit — ou la structure
        #      exploitable a ete detruite — est simplement neutre.
        # Le discriminant : si le reel est franchement negatif, c'est (b).
        cause = ("la strategie est authentiquement perdante (le bruit, lui, est neutre)"
                 if reel < floor["p05"] else
                 "suspecter un defaut d'outil : friction absolue, blocs trop longs, cout mal applique")
        return {"passe": False, "reel": reel, "median_bruit": floor["median"],
                "raison": f"le bruit fait mieux que le reel en mediane — {cause}"}
    return {
        "passe": bool(reel > floor["p95"]),
        "reel": reel, "p95_bruit": floor["p95"],
        "marge": reel - floor["p95"],
        "raison": "reel > 95e centile du bruit" if reel > floor["p95"]
                  else "le hasard produit aussi bien avec le meme balayage",
    }
