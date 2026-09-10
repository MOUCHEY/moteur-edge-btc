"""
Features causales.

Regle unique et non negociable : une feature a l'index t n'utilise QUE de
l'information disponible a la cloture de la barre t. L'entree se fait a l'open
de t+1 (voir backtest.py). Toute violation ici produit un edge fantome et rien
dans le code ne le signalerait.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]

    logret = np.log(c).diff()
    f["ret_1"] = logret * 1e4                      # en bps
    for k in (4, 12, 24, 72, 168):
        f[f"ret_{k}"] = (np.log(c) - np.log(c).shift(k)) * 1e4

    for k in (24, 72, 168):
        f[f"vol_{k}"] = logret.rolling(k).std() * 1e4

    # Position du prix dans sa propre distribution recente
    for k in (24, 72, 168):
        ma = c.rolling(k).mean()
        sd = c.rolling(k).std()
        f[f"z_close_{k}"] = (c - ma) / sd.replace(0, np.nan)

    # Amplitude et vraie amplitude
    f["range_bps"] = (h - l) / c * 1e4
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    f["atr_14"] = (tr.rolling(14).mean() / c) * 1e4
    f["atr_48"] = (tr.rolling(48).mean() / c) * 1e4

    # Corps de bougie signe : proxy de pression directionnelle
    f["body_bps"] = (c - o) / c * 1e4

    # RSI de Wilder
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    f["rsi_14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))

    # --- Flux : la donnee que peu de gens exploitent sur BTC ---
    # part du volume execute a l'achat au marche (agresseur acheteur)
    vol = df["volume"].replace(0, np.nan)
    f["taker_ratio"] = df["taker_buy_base"] / vol
    f["taker_ratio_24"] = f["taker_ratio"].rolling(24).mean()
    f["taker_z_72"] = (
        (f["taker_ratio"] - f["taker_ratio"].rolling(72).mean())
        / f["taker_ratio"].rolling(72).std().replace(0, np.nan)
    )
    f["vol_rel_24"] = vol / vol.rolling(24).mean()
    f["trade_size"] = df["quote_volume"] / df["trades"].replace(0, np.nan)
    f["trade_size_z"] = (
        (f["trade_size"] - f["trade_size"].rolling(168).mean())
        / f["trade_size"].rolling(168).std().replace(0, np.nan)
    )

    # Distance aux extremes recents (cassures)
    for k in (24, 72, 168):
        f[f"dist_high_{k}"] = (c / h.rolling(k).max() - 1) * 1e4
        f[f"dist_low_{k}"] = (c / l.rolling(k).min() - 1) * 1e4

    # Calendrier — UTC, jamais l'heure locale
    f["hour"] = df["ts"].dt.hour
    f["dow"] = df["ts"].dt.dayofweek
    f["is_weekend"] = (f["dow"] >= 5).astype(int)

    return f


def assert_causal(df: pd.DataFrame, feats: pd.DataFrame, builder=None) -> None:
    """
    Test de fuite : on corrompt le futur et on verifie que les features n'en
    savent rien. Une feature qui bouge a une fuite de lookahead.

    `builder` est la fonction qui a produit `feats` (par defaut `build`). Le
    passer explicitement permet de controler un pipeline enrichi : une colonne
    presente dans `feats` mais que le builder ne reproduit pas ne peut PAS etre
    verifiee, et une feature non verifiable doit lever plutot que passer
    silencieusement — c'est tout l'interet du garde-fou.
    """
    builder = builder or build
    n = len(df)
    cut = n // 2
    tampered = df.copy()
    for col in ("open", "high", "low", "close", "volume", "taker_buy_base", "quote_volume"):
        tampered.loc[cut:, col] = tampered.loc[cut:, col] * 1.5

    f2 = builder(tampered)
    manquantes = [c for c in feats.columns if c not in f2.columns]
    if manquantes:
        raise AssertionError(
            f"features non verifiables (le builder ne les reproduit pas) : {manquantes}. "
            "Toute feature doit passer par le builder pour etre controlee.")
    a = feats.iloc[: cut - 1]
    b = f2.iloc[: cut - 1]
    leaks = []
    for col in feats.columns:
        x, y = a[col], b[col]
        both = x.notna() & y.notna()
        if both.sum() and not np.allclose(x[both], y[both], rtol=1e-9, atol=1e-12):
            leaks.append(col)
    if leaks:
        raise AssertionError(f"FUITE DE LOOKAHEAD dans : {leaks}")
