"""
Backtest deterministe.

Conventions de simulation, a distinguer d'une execution observee :
  - signal evalue a la CLOTURE de t, entree a l'OPEN de t+1 (jamais au close de t)
  - une seule position a la fois ; un signal pendant une position est ignore
  - mode bracket : si stop ET target sont touches dans la meme barre, on compte
    le STOP. Sans cette convention, un backtest de bracket est un generateur
    d'optimisme : les barres ambigues sont frequentes et toujours resolues en
    faveur de la strategie.
  - couts appliques a chaque trade, jamais retranches apres coup
  - le timeout a l'open exclut le high/low de sa barre
  - stop traverse a l'open : execution a cet open, pas au prix du stop
  - sortie intrabar : horodatage/portage a la cloture, borne superieure faute de ticks
  - serie temporelle discontinue refusee ; horizon terminal incomplet exclu et compte
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .costs import DEFAULT, CostModel
from .data import STEP_SECONDS, DataError
from .expressions import SpecError, evaluate


def _validate_bars(df: pd.DataFrame, feats: pd.DataFrame, bar_seconds: int) -> None:
    """Reject malformed chronology before any signal or simulated trade."""
    if not df.index.is_unique or not df.index.equals(feats.index):
        raise DataError("index des prix/features non unique ou non aligne")
    required = {"ts", "open", "high", "low", "close"}
    if not required.issubset(df.columns):
        raise DataError("colonnes OHLC/ts manquantes")
    ts = df["ts"]
    if not isinstance(ts.dtype, pd.DatetimeTZDtype) or ts.dt.tz is None:
        raise DataError("horodatages avec fuseau requis")
    if ts.isna().any() or not ts.is_monotonic_increasing or ts.duplicated().any():
        raise DataError("horodatages invalides, non croissants ou dupliques")
    if not ts.diff().iloc[1:].eq(pd.Timedelta(seconds=bar_seconds)).all():
        raise DataError("gap temporel : simulation refusee avant toute entree")
    prices = df[["open", "high", "low", "close"]].to_numpy(float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise DataError("prix non fini, nul ou negatif")
    if ((df["high"] < df[["open", "close", "low"]].max(axis=1)).any()
            or (df["low"] > df[["open", "close", "high"]].min(axis=1)).any()):
        raise DataError("OHLC incoherents")


def run(df: pd.DataFrame, feats: pd.DataFrame, spec, params: dict | None = None,
        costs: CostModel = DEFAULT) -> pd.DataFrame:
    """Retourne un DataFrame de trades. Une ligne = un trade ferme."""
    errors = spec.validate()
    if errors:
        raise SpecError("spec refusee : " + "; ".join(errors))
    params = {} if params is None else dict(params)
    param_errors = spec.validate_params(params)
    if param_errors:
        raise SpecError("parametres refuses : " + "; ".join(param_errors))
    if params not in spec.grid():
        raise SpecError("parametres absents de la grille figee")
    if spec.interval not in STEP_SECONDS:
        raise SpecError("intervalle inconnu")
    bar_s = STEP_SECONDS[spec.interval]
    _validate_bars(df, feats, bar_s)

    long_sig = evaluate(spec.entry_long, feats, params) if spec.entry_long else pd.Series(False, index=df.index)
    short_sig = evaluate(spec.entry_short, feats, params) if spec.entry_short else pd.Series(False, index=df.index)

    if (long_sig & short_sig).any():
        n = int((long_sig & short_sig).sum())
        raise SpecError(f"{n} barres avec signal long ET short simultane — spec ambigue")

    o = df["open"].to_numpy(float)
    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    ts = df["ts"].to_numpy()
    L = long_sig.to_numpy()
    S = short_sig.to_numpy()
    if spec.mode == "bracket" and spec.atr_col not in feats:
        raise SpecError("feature ATR absente")
    atr = feats[spec.atr_col].to_numpy(float) if spec.mode == "bracket" else None

    n = len(df)
    trades = []
    eligible_stop = max(0, n - spec.horizon - 1)
    excluded_incomplete = int(np.count_nonzero(L[eligible_stop:] | S[eligible_stop:]))
    i = 0
    while i < eligible_stop:
        side = 1 if L[i] else (-1 if S[i] else 0)
        if side == 0:
            i += 1
            continue

        entry_i = i + 1                      # entree a l'open de la barre suivante
        cap = entry_i + spec.horizon
        if cap >= n:
            # Do not select terminal brackets by whether they happened to hit
            # early. Require a complete maximum holding horizon before entry.
            break
        entry_p = o[entry_i]
        intrabar = False

        if spec.mode == "horizon":
            exit_i = cap
            exit_p = o[exit_i]
            reason = "horizon"
        else:
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                i += 1
                continue
            stop_d = entry_p * (a * spec.stop_atr) / 1e4
            targ_d = entry_p * (a * spec.target_atr) / 1e4
            stop_p = entry_p - side * stop_d
            targ_p = entry_p + side * targ_d
            if not np.isfinite([stop_p, targ_p]).all() or min(stop_p, targ_p) <= 0:
                raise SpecError("niveaux bracket non finis ou non positifs")
            exit_i, exit_p, reason = cap, o[cap], "timeout"
            for j in range(entry_i, cap):
                gap_stop = o[j] <= stop_p if side == 1 else o[j] >= stop_p
                gap_target = o[j] >= targ_p if side == 1 else o[j] <= targ_p
                if gap_stop:
                    exit_i, exit_p, reason = j, o[j], "stop_gap"
                    break
                if gap_target:
                    # Limit target: do not award positive price improvement.
                    exit_i, exit_p, reason = j, targ_p, "target_gap"
                    break
                hit_stop = lo[j] <= stop_p if side == 1 else hi[j] >= stop_p
                hit_targ = hi[j] >= targ_p if side == 1 else lo[j] <= targ_p
                if hit_stop:                 # priorite au stop : convention pessimiste
                    exit_i, exit_p, reason = j, stop_p, "stop"
                    intrabar = True
                    break
                if hit_targ:
                    exit_i, exit_p, reason = j, targ_p, "target"
                    intrabar = True
                    break

        exit_clock_i = exit_i + int(intrabar)
        held = exit_clock_i - entry_i
        gross = side * (exit_p / entry_p - 1.0) * 1e4
        cost = costs.total(held, bar_s)
        trades.append({
            "entry_ts": ts[entry_i], "exit_ts": ts[exit_clock_i],
            "side": side, "entry": entry_p, "exit": exit_p,
            "bars_held": held, "gross_bps": gross,
            "cost_bps": cost, "net_bps": gross - cost, "reason": reason,
            "exit_time_precision": "bar_close_upper_bound" if intrabar else "open",
        })
        i = exit_i          # pas de positions superposees

    cols = ["entry_ts", "exit_ts", "side", "entry", "exit", "bars_held",
            "gross_bps", "cost_bps", "net_bps", "reason", "exit_time_precision"]
    result = pd.DataFrame(trades, columns=cols)
    result.attrs["excluded_incomplete_horizon_signals"] = excluded_incomplete
    result.attrs["terminal_policy"] = "require_full_horizon_before_entry"
    result.attrs["intrabar_timing"] = "bar_close_upper_bound_for_time_and_funding"
    return result
