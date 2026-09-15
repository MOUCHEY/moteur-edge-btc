"""
Statistiques descriptives et scenarios de dimensionnement hypothetiques.

Ces calculs ne qualifient ni un avantage de marche ni une execution reelle.
Les statistiques par trade supposent des dependances qui restent a examiner.
Les scenarios de capital utilisent un dimensionnement ex post, non deployable
tel quel, et une periode bornee aux trades observes (pas toute la campagne).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

GAMMA = 0.5772156649015329  # Euler-Mascheroni
YEAR_SECONDS = 365.25 * 86400


# ---------------------------------------------------------------- recherche
def research(trades: pd.DataFrame, bar_seconds: int) -> dict:
    context = {"qualifie": False, "statut": "descriptif_conditionnel",
               "excluded_incomplete_horizon_signals": int(
                   trades.attrs.get("excluded_incomplete_horizon_signals", 0))
               if trades is not None else 0}
    if trades is None or len(trades) == 0:
        return {**context, "n_trades": 0, "t_net": np.nan, "net_bps": np.nan}

    x = trades["net_bps"].to_numpy(float)
    if not np.isfinite(x).all():
        raise ValueError("rendements non finis")
    n = len(x)
    sd = x.std(ddof=1) if n > 1 else np.nan
    t = x.mean() / (sd / np.sqrt(n)) if n > 1 and sd > 0 else np.nan

    wins, losses = x[x > 0], x[x < 0]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf

    return {
        **context,
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
        # Surcout uniforme annulant la moyenne observee, pas une marge prouvee.
        "slippage_de_mort_bps": float(x.mean()),
        "median_bars_held": float(trades["bars_held"].median()),
        "skew": float(sps.skew(x)) if n > 2 else np.nan,
        "kurtosis": float(sps.kurtosis(x, fisher=False)) if n > 3 else np.nan,
    }


def deflated_sharpe(trades: pd.DataFrame, n_essais: int, sr_variance: float | None = None) -> dict:
    """
    Diagnostic selon la formule DSR, jamais une probabilite d'edge reel.

    Le compteur total du projet n'etablit pas le nombre d'essais independants.
    Le calcul ci-dessous utilise ce total comme hypothese provisoire ; la
    variance inter-essais est une approximation 1/n si elle n'est pas fournie.
    Meme une valeur proche de 1 ne qualifie aucune porte.
    """
    x = trades["net_bps"].to_numpy(float)
    n = len(x)
    base = {"qualifie": False, "statut": "diagnostic_non_calibre",
            "n_essais": n_essais, "n_essais_independants_etablis": None,
            "variance_source": "fournie_non_validee" if sr_variance is not None else "approximation_1_sur_n",
            "note": "CDF sous hypotheses de moments, dependance et selection non etablies ; pas une probabilite d'edge reel"}
    if (isinstance(n_essais, (bool, np.bool_)) or not isinstance(n_essais, (int, np.integer))
            or n_essais < 1):
        raise ValueError("nombre total d'essais entier positif requis")
    if not np.isfinite(x).all():
        raise ValueError("rendements non finis")
    if sr_variance is not None and (not np.isfinite(sr_variance) or sr_variance < 0):
        raise ValueError("variance inter-essais finie positive ou nulle requise")
    if n < 20:
        return {**base, "dsr": None, "sr0": None, "erreur": "moins de 20 trades"}
    if x.std(ddof=1) <= 0:
        return {**base, "dsr": None, "sr0": None, "erreur": "variance des trades nulle"}

    sr = x.mean() / x.std(ddof=1)
    g3 = sps.skew(x)
    g4 = sps.kurtosis(x, fisher=False)

    # Variance des SR entre essais : a defaut d'observation, approximation standard
    v = sr_variance if sr_variance is not None else (1.0 / n)

    N = int(n_essais)
    if N == 1:
        sr0 = 0.0
    else:
        z1 = sps.norm.isf(1.0 / N)
        z2 = sps.norm.isf(1.0 / (N * np.e))
        sr0 = np.sqrt(v) * ((1 - GAMMA) * z1 + GAMMA * z2)

    denom = 1 - g3 * sr + (g4 - 1) / 4.0 * sr**2
    if denom <= 0:
        return {**base, "dsr": None, "sr0": float(sr0), "erreur": "denominateur non positif"}

    dsr = sps.norm.cdf((sr - sr0) * np.sqrt(n - 1) / np.sqrt(denom))
    return {**base, "dsr": float(dsr), "sr": float(sr), "sr0": float(sr0)}


def equity_path(returns: np.ndarray) -> np.ndarray:
    """Capital normalise, incluant 1 au depart, ruine absorbante a zero.

    Ce scenario cesse toute exposition apres insolvabilite. Il ne modele pas
    un solde debiteur ni une liquidation de courtier.
    """
    r = np.asarray(returns, dtype=float)
    if r.ndim != 1 or not np.isfinite(r).all():
        raise ValueError("rendements finis a une dimension requis")
    try:
        with np.errstate(over="raise", invalid="raise"):
            # A nonpositive capital multiplier becomes zero permanently;
            # two returns below -100% must never create a positive rebound.
            return np.concatenate(([1.0], np.cumprod(np.maximum(1 + r, 0.0))))
    except FloatingPointError as exc:
        raise ValueError("capital non fini dans le scenario") from exc


# -------------------------------------------------------------- deploiement
def deployment(trades: pd.DataFrame, bar_seconds: int, risque_pct: float = 1.0,
               equite: float = 10_000.0) -> dict:
    """Scenario ex post conditionnel, sans simulation de marge ni de courtier."""
    status = {"qualifie": False, "statut": "scenario_hypothetique_ex_post"}
    if len(trades) < 2:
        return {**status, "calculable": False, "note": "moins de deux trades"}
    if (not np.isfinite(risque_pct) or risque_pct <= 0
            or not np.isfinite(equite) or equite <= 0 or bar_seconds <= 0):
        raise ValueError("hypotheses de risque/capital/intervalle invalides")

    x = trades["net_bps"].to_numpy(float)
    if not np.isfinite(x).all():
        raise ValueError("rendements non finis")
    t0 = pd.Timestamp(trades["entry_ts"].iloc[0])
    t1 = pd.Timestamp(trades["exit_ts"].iloc[-1])
    span_years = (t1 - t0).total_seconds() / YEAR_SECONDS
    if not np.isfinite(span_years) or span_years <= 0:
        raise ValueError("periode de scenario non positive")

    trades_par_an = len(trades) / span_years
    heures_exposees = trades["bars_held"].sum() * bar_seconds / 3600.0
    part_du_temps = trades["bars_held"].sum() * bar_seconds / (span_years * YEAR_SECONDS)

    # Quantile de TOUS les rendements observes ; ex post, pas un budget de risque.
    q10 = float(np.percentile(x, 10))
    if q10 >= 0:
        return {**status, "calculable": False,
                "note": "10e centile non negatif : dimensionnement de perte non defini"}
    perte_type = abs(q10)
    notionnelle = equite * (risque_pct / 100) / (perte_type / 1e4) if perte_type > 0 else np.nan

    # Equity a taille fixe en risque : chaque trade rapporte net_bps * levier
    levier = (risque_pct / 100) / (perte_type / 1e4) if perte_type > 0 else 0.0
    r = x / 1e4 * levier
    eq = equity_path(r)
    dd = eq / np.maximum.accumulate(eq) - 1
    max_dd = float(dd.min())
    ruined_at = np.flatnonzero(eq == 0)
    active_n = int(ruined_at[0]) if len(ruined_at) else len(x)
    active_trades = trades.iloc[:active_n]
    trades_par_an = active_n / span_years
    heures_exposees = active_trades["bars_held"].sum() * bar_seconds / 3600.0
    part_du_temps = heures_exposees * 3600 / (span_years * YEAR_SECONDS)

    exponent = np.log(eq[-1]) / span_years if eq[-1] > 0 else None
    cagr = (-1.0 if exponent is None else
            float(np.expm1(exponent)) if exponent < np.log(np.finfo(float).max) else None)
    sharpe_ann = (float(r.mean() / r.std(ddof=1) * np.sqrt(trades_par_an))
                  if not len(ruined_at) and r.std(ddof=1) > 0 else np.nan)

    # Plus longue serie de pertes
    perdant = (x[:active_n] < 0).astype(int)
    serie, best = 0, 0
    for v in perdant:
        serie = serie + 1 if v else 0
        best = max(best, serie)

    return {
        **status, "calculable": True,
        "annees": round(span_years, 2),
        "trades_par_an": round(trades_par_an, 1),
        "heures_exposees_par_an": round(heures_exposees / span_years, 1),
        "part_du_temps_expose": round(part_du_temps, 4),
        "levier_notionnel": round(levier, 2),
        "notionnelle_par_trade": round(notionnelle, 0) if np.isfinite(notionnelle) else None,
        "cagr": round(cagr, 4) if cagr is not None else None,
        "sharpe_annualise": round(sharpe_ann, 3) if np.isfinite(sharpe_ann) else None,
        "max_drawdown": round(max_dd, 4),
        "capital_final_normalise": float(eq[-1]),
        "ruine_observee_dans_scenario": bool((eq == 0).any()),
        "n_trades_simules_avant_arret": active_n,
        "pertes_consecutives_max": int(best),
        "hypotheses": f"scenario ex post : echelle {risque_pct}% pour la perte du 10e centile "
                      f"de tous les rendements, capital initial {equite:.0f}; "
                      "periode des trades actifs, dependance non corrigee, "
                      "ruine absorbante, ni marge ni liquidation de courtier; "
                      "temps/portage intrabar majores a la cloture",
    }


def stouffer(t_stats: list[float]) -> dict:
    """Diagnostic sous hypothese d'independance, non etablie par cet appel."""
    t = np.asarray([v for v in t_stats if np.isfinite(v)], float)
    if len(t) == 0:
        return {"z": np.nan, "p": np.nan, "k": 0, "qualifie": False}
    z = t.sum() / np.sqrt(len(t))
    return {"z": float(z), "p": float(sps.norm.sf(z)), "k": int(len(t)),
            "qualifie": False, "note": "independance et approximation normale non etablies"}
