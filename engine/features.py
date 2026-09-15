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


def assert_causal(df: pd.DataFrame, feats: pd.DataFrame, builder=None, *, cuts=None) -> None:
    """Check prefix invariance, including the last available row at each cut.

    Every column and timestamp in the future is absent from the prefix passed
    to the builder. Index/column structure, dtypes and the missing-value mask
    must match as well as finite values. Several positional cuts are checked;
    this diagnostic is not a mathematical proof for every possible dataset.
    """
    builder = builder or build
    if not isinstance(df, pd.DataFrame) or not isinstance(feats, pd.DataFrame):
        raise AssertionError("causalite : DataFrame attendus")
    n = len(df)
    if n < 2:
        raise AssertionError("causalite non verifiable avec moins de deux lignes")
    if not df.columns.is_unique or not feats.columns.is_unique:
        raise AssertionError("causalite : colonnes dupliquees interdites")
    try:
        pd.testing.assert_index_equal(feats.index, df.index, exact=True, check_names=True)
    except AssertionError as exc:
        raise AssertionError("causalite : index des features non aligne") from exc

    def compare(expected, actual, label):
        if not isinstance(actual, pd.DataFrame):
            raise AssertionError(f"causalite : builder sans DataFrame ({label})")
        try:
            pd.testing.assert_frame_equal(
                expected, actual, check_dtype=True, check_index_type=True,
                check_column_type=True, check_names=True, check_exact=False,
                rtol=1e-9, atol=1e-12,
            )
        except AssertionError as exc:
            raise AssertionError(
                f"FUITE DE LOOKAHEAD ou features non reproductibles ({label}) : {exc}"
            ) from exc

    # First verify that the declared builder actually produced every feature.
    compare(feats, builder(df.copy(deep=True)), "reproduction complete")
    if cuts is None:
        selected = sorted({1, n // 4, n // 2, (3 * n) // 4, n - 1} - {0})
    else:
        try:
            selected = list(cuts)
        except TypeError as exc:
            raise AssertionError("causalite : coupes positionnelles attendues") from exc
        if not selected or any(type(cut) is not int or not 1 <= cut < n for cut in selected):
            raise AssertionError("causalite : chaque coupe doit etre un entier entre 1 et n-1")
        selected = sorted(set(selected))
    for cut in selected:
        prefix = df.iloc[:cut].copy(deep=True)
        compare(feats.iloc[:cut], builder(prefix), f"prefixe de {cut} lignes")
