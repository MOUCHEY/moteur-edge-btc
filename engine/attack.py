"""
Outil de red team : attaques automatisees sur une strategie figee.

    python3 -m engine.attack <spec.yaml> --params '{"fen":72,"seuil":2.0}'

Ce module ne repare rien et ne propose rien. Il produit des constats chiffres.
Chaque attaque repond a une question precise sur laquelle une strategie peut
mourir, et retourne un verdict booleen sur un critere pre-ecrit.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

from . import backtest, features, metrics, spec as spec_mod
from .costs import DEFAULT
from .data import STEP_SECONDS, data_fingerprint, load
from .journal import Session, clean, digest
from .research import EVENTS, ResearchError, g0_contract, gate_status, provenance, require_is


def concentration(trades: pd.DataFrame) -> dict:
    """
    Le PnL tient-il a une poignee de trades ?

    Un edge qui disparait en retirant 5 trades sur 800 n'est pas un edge, c'est
    une poignee d'evenements chanceux. On ne pourra pas les reproduire.
    """
    x = np.sort(trades["net_bps"].to_numpy(float))[::-1]
    n, total = len(x), trades["net_bps"].sum()
    out = {"n_trades": n, "somme_bps": round(float(total), 1)}
    for k in (1, 5, 10):
        if n > k:
            reste = total - x[:k].sum()
            out[f"sans_top_{k}"] = round(float(reste / (n - k)), 3)
    top5_share = float(x[:5].sum() / total) if total > 0 else np.nan
    out["part_pnl_du_top_5"] = round(top5_share, 3) if np.isfinite(top5_share) else None
    out["passe"] = bool(out.get("sans_top_5") is not None and out["sans_top_5"] > 0)
    out["critere"] = "l'esperance reste positive apres retrait des 5 meilleurs trades"
    return out


def par_annee(trades: pd.DataFrame) -> dict:
    """Un seul regime porte-t-il tout ? Sur BTC, 2020-2021 est le suspect n°1."""
    t = trades.copy()
    t["an"] = pd.to_datetime(t["entry_ts"], utc=True).dt.year
    g = t.groupby("an")["net_bps"].agg(["count", "mean"])
    ans = {int(a): {"n": int(r["count"]), "net_bps": round(float(r["mean"]), 2)}
           for a, r in g.iterrows()}
    pos = sum(1 for v in ans.values() if v["net_bps"] > 0)
    return {"par_annee": ans, "annees_positives": f"{pos}/{len(ans)}",
            "passe": bool(len(ans) and pos / len(ans) >= 0.6),
            "critere": ">= 60 % des annees civiles positives"}


def chevauchement(trades: pd.DataFrame) -> dict:
    """
    Les trades se recouvrent-ils ? Si oui, le t-stat est surestime : n trades
    correlés ne valent pas n observations independantes.
    """
    t = trades.sort_values("entry_ts")
    ent = pd.to_datetime(t["entry_ts"], utc=True).to_numpy()
    ex = pd.to_datetime(t["exit_ts"], utc=True).to_numpy()
    overlaps = int((ent[1:] < ex[:-1]).sum())
    x = t["net_bps"].to_numpy(float)
    n = len(x)
    # autocorrelation d'ordre 1 des rendements de trade
    ac1 = float(np.corrcoef(x[:-1], x[1:])[0, 1]) if n > 2 else np.nan
    facteur = float(np.sqrt((1 + ac1) / (1 - ac1))) if np.isfinite(ac1) and abs(ac1) < 0.95 else np.nan
    t_brut = metrics.research(trades, 3600)["t_net"]
    return {
        "trades_chevauchants": overlaps,
        "autocorr_ordre_1": round(ac1, 4) if np.isfinite(ac1) else None,
        "t_brut": round(float(t_brut), 3) if np.isfinite(t_brut) else None,
        "t_corrige_estime": round(float(t_brut / facteur), 3) if np.isfinite(facteur) and facteur > 0 else None,
        "passe": bool(overlaps == 0),
        "critere": "aucun chevauchement (le harness l'interdit deja, ceci le verifie)",
    }


def fiabilite_du_t(trades: pd.DataFrame, n_boot: int = 1000, seed: int = 3, block: int = 10) -> dict:
    """Sensibilite au bootstrap par blocs de trades, sans certification G2/G4."""
    x = trades['net_bps'].to_numpy(float)
    n = len(x)
    if n < 30 or not np.isfinite(x).all():
        return {'note': 'moins de 30 trades ou rendement non fini', 'qualified': False}
    if type(block) is not int or not 1 <= block <= n or type(n_boot) is not int or n_boot < 1:
        raise ValueError('parametres bootstrap invalides')
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        starts = rng.integers(0, n - block + 1, size=int(np.ceil(n / block)))
        sample = np.concatenate([x[j:j+block] for j in starts])[:n]
        means.append(float(sample.mean()))
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {'moyenne_bps': float(x.mean()), 'intervalle_bootstrap_descriptif': [float(lo), float(hi)],
            'seed': seed, 'block': block, 'replications': n_boot, 'bootstrap_means': means,
            'qualified': False, 'passe': False,
            'note': 'Bloc de trades, hypothese de dependance non certifiee. Ne constitue pas une porte.'}


def decalage_entree(df, feats, sp, params, session=None) -> dict:
    """
    L'attaque la plus revelatrice.

    On retarde l'entree d'une puis deux barres. Un edge structurel se degrade
    PROGRESSIVEMENT — l'information met du temps a se dissiper. Un artefact de
    calage temporel s'evapore d'un coup, ou pire, il etait deja mort et seule
    une coincidence d'alignement le maintenait en vie.
    """
    out = {}
    base = None
    for lag in (0, 1, 2):
        f = feats.shift(lag) if lag else feats
        tr = (session.evaluate(dict(params), f'attack_delay_{lag}',
                               lambda: backtest.run(df, f, sp, params))
              if session else backtest.run(df, f, sp, params))
        m = metrics.research(tr, STEP_SECONDS[sp.interval])
        out[f"lag_{lag}"] = {"n": m["n_trades"],
                             "net_bps": round(m["net_bps"], 3) if m["n_trades"] else None,
                             "t_net": round(m["t_net"], 3) if m["n_trades"] > 1 and np.isfinite(m["t_net"]) else None}
        if lag == 0:
            base = m["net_bps"]

    l1 = out["lag_1"]["net_bps"]
    if base and base > 0 and l1 is not None:
        chute = 1 - l1 / base
        out["chute_a_lag_1"] = round(float(chute), 3)
        out["passe"] = bool(chute < 0.80)
        out["critere"] = "l'edge perd moins de 80 % a une barre de retard (degradation progressive)"
    else:
        out["passe"] = False
        out["critere"] = "edge de base non positif — test non concluant"
    return out


def heures(trades: pd.DataFrame) -> dict:
    """Les trades se concentrent-ils sur des heures peu liquides ?"""
    h = pd.to_datetime(trades["entry_ts"], utc=True).dt.hour
    vc = h.value_counts(normalize=True).sort_index()
    if vc.empty:
        return {'note': 'aucun trade', 'qualified': False}
    top = vc.idxmax()
    return {"heure_dominante_utc": int(top), "part": round(float(vc.max()), 3),
            "passe": bool(vc.max() < 0.25),
            "critere": "aucune heure UTC ne concentre plus de 25 % des trades"}


ATTAQUES = ["concentration", "par_annee", "chevauchement", "fiabilite_du_t",
            "decalage_entree", "heures"]


def main() -> int:
    ap = argparse.ArgumentParser(description='Diagnostics IS sur la configuration centrale preenregistree')
    ap.add_argument('spec')
    ap.add_argument('--params')
    ap.add_argument('--split', default='IS')
    a = ap.parse_args()
    sp = spec_mod.load(a.spec)
    try:
        with Session(EVENTS, 'diagnostic_attack', sp.hash, a.split, {'provenance': provenance()}) as session:
            require_is(a.split)
            if sp.validate():
                raise ResearchError('; '.join(sp.validate()))
            g0 = g0_contract(sp, a.spec)
            params = json.loads(a.params) if a.params is not None else g0['central_params']
            if sp.validate_params(params) or params != g0['central_params']:
                raise ResearchError('Les attaques doivent conserver les parametres centraux preenregistres.')
            session.bind_contract(g0, sp.to_dict(), asdict(DEFAULT))
            df = load(sp.interval, a.split)
            session.bind_data(data_fingerprint(df))
            feats = features.build(df)
            features.assert_causal(df, feats)
            trades = session.evaluate(params, 'attack_baseline', lambda: backtest.run(df, feats, sp, params))
            attacks = {}
            if len(trades) >= 20:
                attacks = {'concentration': concentration(trades), 'par_annee': par_annee(trades),
                           'chevauchement': chevauchement(trades), 'fiabilite_du_t': fiabilite_du_t(trades),
                           'decalage_entree': decalage_entree(df, feats, sp, params, session), 'heures': heures(trades)}
                # Un seuil generique n'est pas une prediction preenregistree.
                for diagnostic in attacks.values():
                    if 'passe' in diagnostic:
                        diagnostic['condition_descriptive'] = diagnostic.pop('passe')
                    diagnostic['qualified_gate'] = False
            report = {'exp': sp.id, 'spec_hash': sp.hash, 'split': a.split, 'params': params,
                      'provenance': provenance(), 'data_sha256': data_fingerprint(df),
                      'base': metrics.research(trades, STEP_SECONDS[sp.interval]),
                      'trades': trades.assign(entry_ts=trades.entry_ts.astype(str), exit_ts=trades.exit_ts.astype(str)).to_dict('records'),
                      'attaques': attacks, 'gates': gate_status(),
                      'verdict': 'DIAGNOSTIC SEULEMENT ; revue independante non effectuee'}
            report, output = session.publish(Path(a.spec).parent / 'results', report)
            print(json.dumps(clean(report), indent=2, allow_nan=False))
            return 0 if len(trades) >= 20 else 1
    except (ResearchError, ValueError, RuntimeError) as exc:
        print(f'Diagnostic refuse/echoue : {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
