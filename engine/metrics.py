"""
Metriques de RECHERCHE et metriques de DEPLOIEMENT.

Ces deux familles repondent a deux questions differentes et les confondre est
l'erreur la plus couteuse de ce genre de projet :
  - recherche   : « existe-t-il un edge ? »        -> t-stat, net_bps, DSR
  - deploiement : « peut-on en vivre ? »           -> Sharpe annualise, DD, CAGR
Un edge de 8 bps/trade parait derisoire et peut donner un Sharpe de 1,2 si
l'exposition est courte. Toujours convertir avant de juger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

GAMMA = 0.5772156649015329  # Euler-Mascheroni
YEAR_SECONDS = 365.25 * 86400


# ---------------------------------------------------------------- recherche
def research(trades: pd.DataFrame, bar_seconds: int) -> dict:
    if trades is None or len(trades) == 0:
        return {"n_trades": 0, "t_net": np.nan, "net_bps": np.nan}

    x = trades["net_bps"].to_numpy(float)
    n = len(x)
    sd = x.std(ddof=1) if n > 1 else np.nan
    t = x.mean() / (sd / np.sqrt(n)) if n > 1 and sd > 0 else np.nan

    wins, losses = x[x > 0], x[x < 0]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf

    return {
        "n_trades": n,
        "net_bps": float(x.mean()),
        "gross_bps": float(trades["gross_bps"].mean()),
        "cost_bps": float(trades["cost_bps"].mean()),
        "sd_bps": float(sd) if np.isfinite(sd) else np.nan,
        "t_net": float(t) if np.isfinite(t) else np.nan,
        "p_one_sided": float(1 - sps.t.cdf(t, df=n - 1)) if np.isfinite(t) else np.nan,
        "win_rate": float((x > 0).mean()),
        "profit_factor": float(pf),
        "sharpe_per_trade": float(x.mean() / sd) if np.isfinite(sd) and sd > 0 else np.nan,
        # marge reelle : surcout par trade qui annulerait l'esperance
        "slippage_de_mort_bps": float(x.mean()),
        "median_bars_held": float(trades["bars_held"].median()),
        "skew": float(sps.skew(x)) if n > 2 else np.nan,
        "kurtosis": float(sps.kurtosis(x, fisher=False)) if n > 3 else np.nan,
    }


def deflated_sharpe(trades: pd.DataFrame, n_essais: int, sr_variance: float | None = None) -> dict:
    """
    Deflated Sharpe Ratio — Bailey & Lopez de Prado (2014).

    `n_essais` doit etre le nombre d'essais du PROJET ENTIER, pas de la seule
    experience. C'est le seul parametre qu'on controle, et le sous-declarer est
    la facon la plus simple de se mentir.
    """
    x = trades["net_bps"].to_numpy(float)
    n = len(x)
    if n < 20:
        return {"dsr": np.nan, "sr0": np.nan, "note": "moins de 20 trades, non calculable"}

    sr = x.mean() / x.std(ddof=1)
    g3 = sps.skew(x)
    g4 = sps.kurtosis(x, fisher=False)

    # Variance des SR entre essais : a defaut d'observation, approximation standard
    v = sr_variance if sr_variance is not None else (1.0 / n)

    N = max(int(n_essais), 2)
    z1 = sps.norm.ppf(1 - 1.0 / N)
    z2 = sps.norm.ppf(1 - 1.0 / (N * np.e))
    sr0 = np.sqrt(v) * ((1 - GAMMA) * z1 + GAMMA * z2)

    denom = 1 - g3 * sr + (g4 - 1) / 4.0 * sr**2
    if denom <= 0:
        return {"dsr": np.nan, "sr0": float(sr0), "note": "denominateur non positif"}

    dsr = sps.norm.cdf((sr - sr0) * np.sqrt(n - 1) / np.sqrt(denom))
    return {"dsr": float(dsr), "sr": float(sr), "sr0": float(sr0), "n_essais": N,
            "note": "DSR = P(le SR observe soit reel compte tenu du nombre d'essais)"}


# -------------------------------------------------------------- deploiement
def deployment(trades: pd.DataFrame, bar_seconds: int, risque_pct: float = 1.0,
               equite: float = 10_000.0) -> dict:
    """Convertit un edge de recherche en ce qu'on vivrait reellement."""
    if len(trades) < 2:
        return {}

    x = trades["net_bps"].to_numpy(float)
    t0 = pd.Timestamp(trades["entry_ts"].iloc[0])
    t1 = pd.Timestamp(trades["exit_ts"].iloc[-1])
    span_years = max((t1 - t0).total_seconds() / YEAR_SECONDS, 1e-9)

    trades_par_an = len(trades) / span_years
    heures_exposees = trades["bars_held"].sum() * bar_seconds / 3600.0
    part_du_temps = trades["bars_held"].sum() * bar_seconds / (span_years * YEAR_SECONDS)

    # Dimensionnement sur le 10e centile des pertes, ni la moyenne ni le pire
    perte_type = abs(np.percentile(x, 10))
    notionnelle = equite * (risque_pct / 100) / (perte_type / 1e4) if perte_type > 0 else np.nan

    # Equity a taille fixe en risque : chaque trade rapporte net_bps * levier
    levier = (risque_pct / 100) / (perte_type / 1e4) if perte_type > 0 else 0.0
    r = x / 1e4 * levier
    eq = np.cumprod(1 + r)
    dd = eq / np.maximum.accumulate(eq) - 1
    max_dd = float(dd.min())

    cagr = float(eq[-1] ** (1 / span_years) - 1) if eq[-1] > 0 else -1.0
    sharpe_ann = float(r.mean() / r.std(ddof=1) * np.sqrt(trades_par_an)) if r.std(ddof=1) > 0 else np.nan

    # Plus longue serie de pertes
    perdant = (x < 0).astype(int)
    serie, best = 0, 0
    for v in perdant:
        serie = serie + 1 if v else 0
        best = max(best, serie)

    return {
        "annees": round(span_years, 2),
        "trades_par_an": round(trades_par_an, 1),
        "heures_exposees_par_an": round(heures_exposees / span_years, 1),
        "part_du_temps_expose": round(part_du_temps, 4),
        "levier_notionnel": round(levier, 2),
        "notionnelle_par_trade": round(notionnelle, 0) if np.isfinite(notionnelle) else None,
        "cagr": round(cagr, 4),
        "sharpe_annualise": round(sharpe_ann, 3) if np.isfinite(sharpe_ann) else None,
        "max_drawdown": round(max_dd, 4),
        "pertes_consecutives_max": int(best),
        "hypotheses": f"risque {risque_pct}%/trade, equite {equite:.0f}, "
                      f"dimensionnement sur le 10e centile des pertes",
    }


def stouffer(t_stats: list[float]) -> dict:
    """Agrege des t-stats independants. Sert a la replication multi-actifs."""
    t = np.asarray([v for v in t_stats if np.isfinite(v)], float)
    if len(t) == 0:
        return {"z": np.nan, "p": np.nan, "k": 0}
    z = t.sum() / np.sqrt(len(t))
    return {"z": float(z), "p": float(1 - sps.norm.cdf(z)), "k": int(len(t))}
