#!/usr/bin/env python3
"""Contre-exemples reproductibles — revue red team de la PR #8 (173ab068).

    python3 reproduce_findings.py --root <racine du depot a la revision examinee>

Aucune donnee de marche, aucun coffre, aucune cle, aucun reseau. Chaque
verification fabrique ses observations en memoire ou dans un repertoire
temporaire. Un code de sortie 0 signifie « defauts reproduits », jamais
« moteur valide ».
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

RESULTS: list[dict] = []


def record(ident, titre, reproduit, detail):
    RESULTS.append({"id": ident, "titre": titre, "reproduit": bool(reproduit), "detail": detail})
    mark = "REPRODUIT" if reproduit else "non reproduit"
    print(f"[{mark}] {ident} — {titre}")
    for line in detail.splitlines():
        print(f"    {line}")
    print()


def candles(n, start="2019-01-01", seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    ts = pd.date_range(start, periods=n, freq="h", tz="UTC")
    high = close * (1 + abs(rng.normal(0, 0.003, n)))
    low = close * (1 - abs(rng.normal(0, 0.003, n)))
    openp = np.clip(close * (1 + rng.normal(0, 0.001, n)), low, high)
    vol = rng.uniform(10, 100, n)
    return pd.DataFrame({"ts": ts, "open": openp, "high": high, "low": low,
                         "close": close, "volume": vol,
                         "trades": rng.integers(50, 500, n),
                         "taker_buy_base": vol * rng.uniform(.3, .7, n),
                         "quote_volume": vol * close})


# ---------------------------------------------------------------- R1
def r1_substitution(mod):
    """Un parametre negatif substitue sans parentheses change le sens du contrat."""
    exprs = mod.format_expression("x > {p} ** 2", {"p": -2.0})
    feats = pd.DataFrame({"x": [0.0, 3.0, 5.0]})
    got = mod.evaluate("x > {p} ** 2", feats, {"p": -2.0}).tolist()
    attendu = (feats["x"] > (-2.0) ** 2).tolist()
    record("R1", "Substitution de parametre non parenthesee (engine/expressions.py:73)",
           got != attendu,
           f"expression apres substitution : {exprs!r}\n"
           f"Python evalue -2.0 ** 2 = {-2.0 ** 2} au lieu de (-2.0)**2 = {(-2.0)**2}\n"
           f"signal obtenu  : {got}\n"
           f"signal attendu : {attendu}")


# ---------------------------------------------------------------- R2
def r2_causal_cuts(features_mod):
    """Une fuite confinee a des lignes rares echappe aux 5 coupes par defaut."""
    periode = 7
    def coupes(n):
        return sorted({1, n // 4, n // 2, (3 * n) // 4, n - 1} - {0})

    n = next(k for k in range(80, 600)
             if all((c - 1) % periode != 3 for c in coupes(k)) and (k - 1) % periode != 3)

    df = candles(n)

    def builder(d):
        f = pd.DataFrame(index=d.index)
        futur = d["close"].shift(-1)
        masque = (np.arange(len(d)) % periode == 3)
        # Fuite uniquement sur des lignes rares : ailleurs, valeur causale.
        f["x"] = pd.Series(np.where(masque, futur.to_numpy(), d["close"].to_numpy()),
                           index=d.index)
        return f

    feats = builder(df)
    fuite_reelle = int((feats["x"].to_numpy()[:-1] == df["close"].shift(-1).to_numpy()[:-1]).sum())
    try:
        features_mod.assert_causal(df, feats, builder)
        passe = True
        erreur = ""
    except AssertionError as exc:
        passe, erreur = False, str(exc)[:120]
    record("R2", "assert_causal : fuite sur lignes rares non detectee (engine/features.py:115)",
           passe,
           f"n = {n} barres, coupes par defaut = {coupes(n)}\n"
           f"lignes reellement contaminees par close(t+1) : {fuite_reelle}\n"
           f"assert_causal a {'ACCEPTE' if passe else 'refuse'} ce builder"
           + ("" if passe else f" ({erreur})"))


# ---------------------------------------------------------------- R3
def r3_truncature(journal):
    """Supprimer des evenements non encore commites annule le gel du contrat."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "events"
        spec = {"id": "EXP-9999", "horizon": 1}
        with journal.Session(d, "discovery", "h", "IS", {}) as s:
            s.bind_contract({"hypothesis": "A", "predictions": ["p"]}, spec, {"spread_bps": 4.0})
        refus = None
        try:
            with journal.Session(d, "discovery", "h", "IS", {}) as s:
                s.bind_contract({"hypothesis": "B_modifie_apres_resultat", "predictions": ["p"]},
                                spec, {"spread_bps": 4.0})
        except journal.JournalError as exc:
            refus = str(exc)
        avant = len(list(d.glob("*.json")))
        for p in d.glob("*.json"):
            p.unlink()
        rebind = None
        try:
            with journal.Session(d, "discovery", "h", "IS", {}) as s:
                s.bind_contract({"hypothesis": "B_modifie_apres_resultat", "predictions": ["p"]},
                                spec, {"spread_bps": 4.0})
            rebind = "ACCEPTE"
        except journal.JournalError as exc:
            rebind = f"refuse ({exc})"
        chaine_ok = len(journal.read_events(d)) > 0
    record("R3", "Troncature du journal : le gel G0 redevient modifiable (engine/journal.py:187)",
           rebind == "ACCEPTE",
           f"1) gel initial du contrat A : ok ({avant} evenements)\n"
           f"2) tentative de contrat B sur le meme id : {refus}\n"
           f"3) suppression des fichiers d'evenements (jamais commites)\n"
           f"4) nouveau gel du contrat B : {rebind}\n"
           f"5) read_events sur le journal tronque : chaine valide = {chaine_ok}")


# ---------------------------------------------------------------- R4 / R5
def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True).stdout


def r4_ci_perimetre(rejouer):
    """verify_history ne couvre ni les rapports publies ni HISTORIQUE.json."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True)
        (root / "experiments" / "events").mkdir(parents=True)
        (root / "experiments" / "EXP-0001" / "results").mkdir(parents=True)
        (root / "experiments" / "ledger.json").write_text('{"total_configs": 136}\n')
        (root / "experiments" / "HISTORIQUE.json").write_text('{"declared": 136}\n')
        (root / "experiments" / "EXP-0001" / "results" / "run-a.json").write_text('{"t_net": -3.0}\n')
        # un evenement valide dans la base
        sys.path.insert(0, str(ROOT))
        from engine import journal as J
        J.append(root / "experiments" / "events", "fixture", {"i": 0})
        # Le verrou n'est pas un evenement : le depot reel l'ignore aussi.
        (root / "experiments" / "events" / ".lock").unlink(missing_ok=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True,
                       capture_output=True, env=env)
        base = _git(root, "rev-parse", "HEAD").decode().strip()

        # 1) suppression d'un rapport publie deja commite
        (root / "experiments" / "EXP-0001" / "results" / "run-a.json").unlink()
        # 2) reecriture de HISTORIQUE.json
        (root / "experiments" / "HISTORIQUE.json").write_text('{"declared": 0}\n')
        # 3) ajout puis suppression d'evenements jamais commites
        J.append(root / "experiments" / "events", "fixture", {"i": 1})
        for p in sorted((root / "experiments" / "events").glob("*.json"))[1:]:
            p.unlink()
        (root / "experiments" / "events" / ".lock").unlink(missing_ok=True)
        try:
            count = rejouer.verify_history(root, base)
            verdict = f"ACCEPTE ({count} evenement(s) de base verifies)"
            passe = True
        except rejouer.HistoryError as exc:
            verdict, passe = f"refuse ({exc})", False
    record("R4", "Perimetre CI : rapports publies et HISTORIQUE.json non couverts (ci/rejouer_local.py:49)",
           passe,
           "Depot temporaire : rapport publie supprime, HISTORIQUE.json reecrit,\n"
           "evenement post-base cree puis supprime.\n"
           f"verify_history : {verdict}")


def r5_colonnes_flux(data_mod, features_mod, run_mod):
    """Un fichier IS valide sans colonnes de flux fait planter hors des erreurs prevues."""
    df = candles(600).drop(columns=["taker_buy_base"])
    sanity = None
    try:
        data_mod._sanity(df, "1h")
        sanity = "accepte"
    except data_mod.DataError as exc:
        sanity = f"refuse ({exc})"
    try:
        features_mod.build(df)
        levee = None
    except Exception as exc:
        levee = type(exc).__name__
    attrapees = ("ResearchError", "ValueError", "RuntimeError")
    import inspect
    source = inspect.getsource(run_mod.main)
    capture = "except (ResearchError, ValueError, RuntimeError)" in source
    record("R5", "Colonne de flux absente : exception non prevue (engine/data.py:108, engine/features.py:51)",
           sanity == "accepte" and levee == "KeyError" and capture,
           f"_sanity sur un CSV sans taker_buy_base : {sanity}\n"
           f"features.build leve : {levee}\n"
           f"run.main n'attrape que {attrapees} -> remontee non geree")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="racine du depot a la revision examinee")
    ap.add_argument("--json", help="fichier de sortie")
    a = ap.parse_args()
    ROOT = Path(a.root).resolve()
    sys.path.insert(0, str(ROOT))
    from engine import expressions, features, journal, data, run as run_mod
    sys.path.insert(0, str(ROOT / "ci"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("rejouer", ROOT / "ci" / "rejouer_local.py")
    rejouer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rejouer)

    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    print(f"Revision examinee : {revision}\n")
    r1_substitution(expressions)
    r2_causal_cuts(features)
    r3_truncature(journal)
    r4_ci_perimetre(rejouer)
    r5_colonnes_flux(data, features, run_mod)

    out = {"revision": revision, "findings": RESULTS,
           "note": "code de sortie 0 = defauts reproduits, pas moteur valide"}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
    print(f"{sum(r['reproduit'] for r in RESULTS)}/{len(RESULTS)} defauts reproduits")
