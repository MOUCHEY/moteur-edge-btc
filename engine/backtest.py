"""
Backtest deterministe.

Conventions, toutes pessimistes par choix :
  - signal evalue a la CLOTURE de t, entree a l'OPEN de t+1 (jamais au close de t)
  - une seule position a la fois ; un signal pendant une position est ignore
  - mode bracket : si stop ET target sont touches dans la meme barre, on compte
    le STOP. Sans cette convention, un backtest de bracket est un generateur
    d'optimisme : les barres ambigues sont frequentes et toujours resolues en
    faveur de la strategie.
  - couts appliques a chaque trade, jamais retranches apres coup
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .costs import DEFAULT, CostModel
from .data import STEP_SECONDS


class SpecError(RuntimeError):
    pass


SAFE = {"abs": abs, "np": np, "min": min, "max": max, "True": True, "False": False}


def evaluate(expr: str, feats: pd.DataFrame, params: dict) -> pd.Series:
    """Evalue une expression de signal dans un namespace restreint."""
    try:
        formatted = expr.format(**params)
    except KeyError as e:
        raise SpecError(f"parametre {e} absent pour l'expression : {expr}")
    ns = {**SAFE, **{c: feats[c] for c in feats.columns}}
    try:
        out = eval(formatted, {"__builtins__": {}}, ns)  # noqa: S307 — namespace clos
    except Exception as e:
        raise SpecError(f"expression invalide « {formatted} » : {e}")
    if not isinstance(out, pd.Series):
        raise SpecError(f"l'expression doit produire une Series, pas {type(out)}")
    return out.fillna(False).astype(bool)


def run(df: pd.DataFrame, feats: pd.DataFrame, spec, params: dict | None = None,
        costs: CostModel = DEFAULT) -> pd.DataFrame:
    """Retourne un DataFrame de trades. Une ligne = un trade ferme."""
    params = params or {}
    bar_s = STEP_SECONDS[spec.interval]

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
    atr = feats[spec.atr_col].to_numpy(float) if spec.mode == "bracket" else None

    n = len(df)
    trades = []
    i = 0
    while i < n - 1:
        side = 1 if L[i] else (-1 if S[i] else 0)
        if side == 0:
            i += 1
            continue

        entry_i = i + 1                      # entree a l'open de la barre suivante
        entry_p = o[entry_i]
        if not np.isfinite(entry_p):
            i += 1
            continue

        if spec.mode == "horizon":
            exit_i = min(entry_i + spec.horizon, n - 1)
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
            cap = entry_i + max(spec.horizon, 1)
            exit_i, exit_p, reason = min(cap, n - 1), o[min(cap, n - 1)], "timeout"
            for j in range(entry_i, min(cap, n - 1) + 1):
                hit_stop = lo[j] <= stop_p if side == 1 else hi[j] >= stop_p
                hit_targ = hi[j] >= targ_p if side == 1 else lo[j] <= targ_p
                if hit_stop:                 # priorite au stop : convention pessimiste
                    exit_i, exit_p, reason = j, stop_p, "stop"
                    break
                if hit_targ:
                    exit_i, exit_p, reason = j, targ_p, "target"
                    break

        held = exit_i - entry_i
        gross = side * (exit_p / entry_p - 1.0) * 1e4
        cost = costs.total(held, bar_s)
        trades.append({
            "entry_ts": ts[entry_i], "exit_ts": ts[exit_i],
            "side": side, "entry": entry_p, "exit": exit_p,
            "bars_held": held, "gross_bps": gross,
            "cost_bps": cost, "net_bps": gross - cost, "reason": reason,
        })
        i = exit_i          # pas de positions superposees

    cols = ["entry_ts", "exit_ts", "side", "entry", "exit", "bars_held",
            "gross_bps", "cost_bps", "net_bps", "reason"]
    return pd.DataFrame(trades, columns=cols)
