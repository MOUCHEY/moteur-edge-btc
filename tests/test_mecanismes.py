"""
Tests des MECANISMES qui imposent le protocole.

Ce fichier ne teste aucune strategie et ne mesure aucune rentabilite. Il verifie
que les regles du protocole sont mecaniquement appliquees par le code, et pas
seulement ecrites dans un document que personne ne relit.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import backtest, features, metrics, spec as spec_mod  # noqa: E402
from engine.costs import CostModel  # noqa: E402
from engine.data import ROOT, SPLITS, DataError, forward_return, load  # noqa: E402
from engine.validation import permutation, synthetic  # noqa: E402


def synth(n=600, seed=0):
    """Serie OHLC jouet, sans structure exploitable."""
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    ts = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "ts": ts, "close": c, "open": c * (1 + rng.normal(0, 0.001, n)),
        "high": c * (1 + abs(rng.normal(0, 0.003, n))),
        "low": c * (1 - abs(rng.normal(0, 0.003, n))),
        "volume": rng.uniform(10, 100, n), "trades": rng.integers(50, 500, n),
        "taker_buy_base": rng.uniform(5, 50, n), "quote_volume": rng.uniform(1e3, 1e4, n),
    })


class Causalite(unittest.TestCase):
    """G-fatale n°1 : aucune feature ne doit voir le futur."""

    def test_aucune_fuite_sur_donnees_reelles(self):
        df = load("1h", "IS").iloc[:8000]
        features.assert_causal(df, features.build(df))

    def test_le_detecteur_attrape_une_vraie_fuite(self):
        """Un test qui ne peut pas echouer ne prouve rien : on lui donne une fuite."""
        def builder_tricheur(d):
            f = features.build(d)
            f["TRICHE"] = d["close"].shift(-5)       # regarde 5 barres en avant
            return f

        df = synth()
        with self.assertRaises(AssertionError):
            features.assert_causal(df, builder_tricheur(df), builder=builder_tricheur)

    def test_une_feature_non_reproductible_est_refusee(self):
        """Une colonne que le builder ne reproduit pas ne peut pas etre controlee."""
        df = synth()
        f = features.build(df)
        f["AJOUTEE_AILLEURS"] = 1.0
        with self.assertRaises(AssertionError):
            features.assert_causal(df, f)

    def test_forward_return_rejette_les_gaps(self):
        df = synth(200)
        df = pd.concat([df.iloc[:100], df.iloc[150:]], ignore_index=True)  # trou
        fr = forward_return(df, 4, "1h")
        self.assertTrue(fr.iloc[96:100].isna().all(),
                        "un gap doit produire NaN, pas un faux rendement")


class Execution(unittest.TestCase):
    """Le harness impose le calage temporel, la strategie ne peut pas y echapper."""

    def _spec(self, **kw):
        d = {"id": "T", "titre": "t", "auteur": "test", "data": {"interval": "1h"},
             "signal": {"entry_long": "ret_1 > -1e9"}, "exit": {"mode": "horizon", "horizon": 3},
             "budget_essais": 1}
        d.update(kw)
        p = Path(ROOT) / "tests" / "_tmp.yaml"
        import yaml
        p.write_text(yaml.safe_dump(d))
        s = spec_mod.load(p)
        p.unlink()
        return s

    def test_entree_a_l_open_de_la_barre_suivante(self):
        df = synth(300)
        f = features.build(df)
        tr = backtest.run(df, f, self._spec(), {}, CostModel(0, 0, 0, 0))
        self.assertGreater(len(tr), 0)
        first = tr.iloc[0]
        i = int(np.where(df["ts"].to_numpy() == first["entry_ts"])[0][0])
        self.assertAlmostEqual(first["entry"], df["open"].iloc[i], places=10,
                               msg="l'entree doit se faire a l'OPEN de la barre d'entree")

    def test_pas_de_positions_superposees(self):
        df = synth(300)
        tr = backtest.run(df, features.build(df), self._spec(), {}, CostModel(0, 0, 0, 0))
        ent = pd.to_datetime(tr["entry_ts"], utc=True).to_numpy()
        ex = pd.to_datetime(tr["exit_ts"], utc=True).to_numpy()
        self.assertTrue((ent[1:] >= ex[:-1]).all(), "aucun trade ne doit chevaucher le precedent")

    def test_bracket_donne_priorite_au_stop(self):
        """Convention pessimiste : barre ambigue -> stop. Sans ca, optimisme systematique."""
        n = 20
        ts = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
        df = pd.DataFrame({
            "ts": ts, "open": 100.0, "close": 100.0,
            "high": [100.0] * 5 + [130.0] * (n - 5),     # touche la cible
            "low": [100.0] * 5 + [70.0] * (n - 5),       # ET le stop, meme barre
            "volume": 10.0, "trades": 10, "taker_buy_base": 5.0, "quote_volume": 1e3,
        })
        f = features.build(df)
        f["atr_48"] = 500.0
        sp = self._spec(exit={"mode": "bracket", "horizon": 10, "stop_atr": 1.0,
                              "target_atr": 2.0, "atr_col": "atr_48"})
        tr = backtest.run(df, f, sp, {}, CostModel(0, 0, 0, 0))
        touche = tr[tr["reason"].isin(["stop", "target"])]
        self.assertGreater(len(touche), 0)
        self.assertTrue((touche["reason"] == "stop").all(),
                        "barre ou stop et cible sont touches : le stop doit gagner")

    def test_les_couts_sont_retranches(self):
        df = synth(300)
        f = features.build(df)
        sp = self._spec()
        gratuit = backtest.run(df, f, sp, {}, CostModel(0, 0, 0, 0))
        cher = backtest.run(df, f, sp, {}, CostModel(10, 5, 0, 0))
        self.assertAlmostEqual(cher["net_bps"].mean(), gratuit["net_bps"].mean() - 15, places=6)


class ReglesDeSpec(unittest.TestCase):
    """G0/G1 : la spec est refusee mecaniquement, pas par relecture humaine."""

    def _mk(self, **kw):
        d = {"id": "T", "titre": "t", "auteur": "a", "data": {"interval": "1h"},
             "signal": {"entry_long": "ret_1 > 0"}, "exit": {"mode": "horizon", "horizon": 3},
             "budget_essais": 1}
        d.update(kw)
        import yaml
        p = Path(ROOT) / "tests" / "_tmp2.yaml"
        p.write_text(yaml.safe_dump(d))
        s = spec_mod.load(p)
        p.unlink()
        return s

    def test_refuse_plus_de_trois_parametres(self):
        s = self._mk(params={"a": [1], "b": [2], "c": [3], "d": [4]}, budget_essais=99)
        self.assertTrue(any("parametres libres" in e for e in s.validate()))

    def test_refuse_une_grille_plus_large_que_le_budget(self):
        s = self._mk(params={"a": [1, 2, 3], "b": [1, 2]}, budget_essais=2)  # 6 > 2
        self.assertTrue(any("budget declare" in e for e in s.validate()))

    def test_refuse_and_or_python(self):
        s = self._mk(signal={"entry_long": "(ret_1 > 0) and (rsi_14 < 50)"})
        self.assertTrue(any("& et |" in e for e in s.validate()))

    def test_le_hash_change_si_la_spec_change(self):
        a = self._mk(params={"x": [1, 2]}, budget_essais=2)
        b = self._mk(params={"x": [1, 2, 3]}, budget_essais=3)
        self.assertNotEqual(a.hash, b.hash,
                            "elargir une grille doit produire une nouvelle experience")

    def test_signal_long_et_short_simultane_est_refuse(self):
        df = synth(300)
        s = self._mk(signal={"entry_long": "ret_1 > -1e9", "entry_short": "ret_1 > -1e9"})
        with self.assertRaises(backtest.SpecError):
            backtest.run(df, features.build(df), s, {})


class CoffreFort(unittest.TestCase):
    """G6 : le verrou doit resister a un acces ordinaire."""

    def test_le_vault_refuse_de_s_ouvrir_sans_autorisation(self):
        if (ROOT / "vault" / "OPEN_AUTHORISATION").exists():
            self.skipTest("autorisation posee — verrou volontairement leve")
        with self.assertRaises(DataError):
            load("1h", "VAULT")

    def test_les_donnees_publiees_ne_contiennent_pas_le_coffre(self):
        seal = json.loads((ROOT / "vault" / "SEAL.json").read_text())
        cut = pd.Timestamp(seal["vault_start"], tz="UTC")
        for iv in ("1h", "15m"):
            df = load(iv, None)
            self.assertLess(df["ts"].max(), cut,
                            f"{iv} : des barres du coffre sont dans les fichiers publies")

    def test_les_splits_ne_se_recouvrent_pas(self):
        is_fin = pd.Timestamp(SPLITS["IS"][1], tz="UTC")
        oos_deb = pd.Timestamp(SPLITS["OOS"][0], tz="UTC")
        vault_deb = pd.Timestamp(SPLITS["VAULT"][0], tz="UTC")
        self.assertLessEqual(is_fin, oos_deb)
        self.assertLessEqual(pd.Timestamp(SPLITS["OOS"][1], tz="UTC"), vault_deb)

    def test_la_clef_n_est_pas_dans_le_depot(self):
        seal = json.loads((ROOT / "vault" / "SEAL.json").read_text())
        self.assertFalse(str(Path(seal["clef"])).startswith(str(ROOT)),
                         "la clef du coffre ne doit jamais vivre dans le depot")


class IntegriteDesDonnees(unittest.TestCase):
    def test_le_hash_des_donnees_correspond_au_manifeste(self):
        """
        Detecte toute alteration silencieuse des fichiers de donnees.

        Le hash porte sur les OCTETS decompresses, jamais sur une re-serialisation
        pandas : `quote_volume` atteint ~2e8 avec 8 decimales, soit 17 chiffres
        significatifs, au-dela de ce que float64 restitue exactement. Mesure sur
        ce jeu : 315 lignes sur 70 359 ne font pas un round-trip fidele. Un test
        qui re-serialise echouerait donc sur des donnees parfaitement intactes.
        """
        import gzip
        import hashlib
        mf = json.loads((ROOT / "data" / "MANIFEST.json").read_text())
        for s in mf["series"]:
            path = ROOT / "data" / "processed" / s["file"]
            blob = gzip.decompress(path.read_bytes())
            self.assertEqual(hashlib.sha256(blob).hexdigest(), s["sha256_canonical"],
                             f"{s['file']} a ete modifie depuis le manifeste")

    def test_seal_et_manifeste_concordent(self):
        """
        SEAL.json et MANIFEST.json decrivent les memes fichiers publics. Ils ont
        diverge une fois, parce que le scellement re-serialisait via pandas quand
        fetch.py ecrivait depuis la source. Deux verites sur le meme fichier, et
        aucune alarme : ce test est l'alarme.
        """
        seal = json.loads((ROOT / "vault" / "SEAL.json").read_text())
        mf = json.loads((ROOT / "data" / "MANIFEST.json").read_text())
        for s in seal["series"]:
            m = next(x for x in mf["series"] if x["interval"] == s["interval"])
            self.assertEqual(s["public_sha256"], m["sha256_canonical"],
                             f"{s['interval']} : SEAL et MANIFEST divergent")

    def test_fetch_ne_reecrit_pas_le_coffre_en_clair(self):
        """Retelecharger ne doit pas rouvrir le coffre sans clef ni journal."""
        import re
        src = (ROOT / "data" / "fetch.py").read_text()
        self.assertIn("VAULT_START", src)
        self.assertRegex(src, r'full\["ts"\]\s*<\s*cut',
                         "fetch.py doit couper la serie avant la borne du coffre")
        seal = json.loads((ROOT / "vault" / "SEAL.json").read_text())
        cut = pd.Timestamp(seal["vault_start"], tz="UTC")
        m = re.search(r"VAULT_START = date\((\d+), (\d+), (\d+)\)", src)
        self.assertIsNotNone(m)
        y, mo, d = (int(g) for g in m.groups())
        self.assertEqual(pd.Timestamp(f"{y:04d}-{mo:02d}-{d:02d}", tz="UTC"), cut,
                         "la borne de fetch.py et celle du scellement doivent coincider")

    def test_pas_d_ohlc_incoherent(self):
        for iv in ("1h", "15m"):
            df = load(iv, None)
            self.assertTrue((df["high"] >= df["low"]).all())
            self.assertTrue((df["close"] <= df["high"]).all())
            self.assertTrue((df["close"] >= df["low"]).all())


class GardeFousCI(unittest.TestCase):
    """
    Un garde-fou de CI doit ECHOUER quand il ne peut pas verifier, pas passer.

    Constate le 13/09/2026 : sur GitHub (clone a 1 commit par defaut), le controle
    du compteur ne voyait aucun historique, affichait « pas d'etat precedent » et
    passait au vert — y compris avec un compteur remis a zero. Ces tests rejouent
    l'etape EXACTE du workflow dans des clones, pour qu'elle ne puisse plus
    redevenir decorative sans que la suite le signale.
    """

    WORKFLOW = ROOT / ".github" / "workflows" / "protocole.yml"

    def _steps(self):
        import yaml
        return yaml.safe_load(self.WORKFLOW.read_text())["jobs"]["mecanismes"]["steps"]

    def _etape_compteur(self):
        return next(s["run"] for s in self._steps() if s.get("name", "").startswith("Le compteur"))

    def _clone(self, depth=None):
        import shutil
        import subprocess
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="edge-ci-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        cmd = ["git", "clone", "-q"] + (["--depth", str(depth)] if depth else [])
        subprocess.run(cmd + [f"file://{ROOT}", str(tmp / "r")], check=True, capture_output=True)
        return tmp / "r"

    def _lancer(self, depot):
        import subprocess
        return subprocess.run(["bash", "-c", self._etape_compteur()], cwd=depot,
                              capture_output=True, text=True)

    def test_le_checkout_recupere_tout_l_historique(self):
        co = next(s for s in self._steps() if str(s.get("uses", "")).startswith("actions/checkout"))
        self.assertEqual((co.get("with") or {}).get("fetch-depth"), 0,
                         "sans fetch-depth: 0, le controle du compteur est aveugle sur GitHub")

    def test_un_clone_superficiel_fait_echouer_le_controle(self):
        r = self._lancer(self._clone(depth=1))
        self.assertNotEqual(r.returncode, 0, "un controle aveugle ne doit pas passer : " + r.stdout)

    def test_un_compteur_remis_a_zero_fait_echouer_le_controle(self):
        depot = self._clone()
        p = depot / "experiments" / "ledger.json"
        led = json.loads(p.read_text())
        led["total_configs"] = 0
        p.write_text(json.dumps(led))
        r = self._lancer(depot)
        self.assertNotEqual(r.returncode, 0, "une baisse du compteur doit etre refusee : " + r.stdout)

    def test_un_compteur_intact_passe(self):
        r = self._lancer(self._clone())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Statistique(unittest.TestCase):
    def test_p_empirique_n_est_jamais_nul(self):
        """Un p de 0 est impossible : la correction +1 doit etre appliquee."""
        rng = np.random.default_rng(1)
        v = pd.Series(rng.normal(0, 1, 500))
        lab = pd.Series(rng.integers(0, 4, 500))
        r = permutation.test(v, lab, 0, n_perm=200)
        self.assertGreater(r["p_empirique"], 0.0)

    def test_permutation_ne_trouve_rien_dans_du_bruit(self):
        """Garde-fou : si ce test trouve un effet, l'outil est casse."""
        rng = np.random.default_rng(2)
        v = pd.Series(rng.normal(0, 1, 2000))
        lab = pd.Series(rng.integers(0, 6, 2000))
        r = permutation.test(v, lab, 0, n_perm=500)
        self.assertGreater(r["p_empirique"], 0.01)

    def test_le_deflated_sharpe_baisse_quand_les_essais_montent(self):
        rng = np.random.default_rng(3)
        tr = pd.DataFrame({"net_bps": rng.normal(3, 30, 400)})
        peu = metrics.deflated_sharpe(tr, 1)["dsr"]
        beaucoup = metrics.deflated_sharpe(tr, 5000)["dsr"]
        self.assertGreater(peu, beaucoup,
                           "chercher plus doit rendre la barre plus haute")

    def test_bootstrap_de_blocs_conserve_la_longueur_et_la_coherence(self):
        df = synth(500)
        rng = np.random.default_rng(4)
        s = synthetic.block_bootstrap(df, 24, rng)
        self.assertEqual(len(s), len(df))
        self.assertTrue((s["high"] >= s["low"]).all())
        self.assertTrue((s["high"] >= s["close"]).all())

    def test_le_plancher_avertit_si_les_blocs_sont_trop_longs(self):
        df = synth(400)
        r = synthetic.noise_floor(df, lambda d: 1.0, block=100, n_sims=3, horizon=5)
        self.assertIsNotNone(r["avertissement"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
