#!/usr/bin/env python3
"""Controles locaux partages avec GitHub, sans donnees de marche ni coffre.

    python3 ci/rejouer_local.py --base <sha-complet-de-la-base>
    python3 ci/rejouer_local.py --tests-only

Le mode complet exige une base Git explicite. Le second mode n'atteste que les
mecanismes synthetiques : il ne valide pas la conservation de l'historique.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unittest
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class HistoryError(RuntimeError):
    """Un historique absent ou modifie bloque le controle."""


def _git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HistoryError("Base Git ou historique indisponible ; controle refuse.") from exc


def _local_bytes(root: Path, relative: str) -> bytes:
    """Lit seulement un fichier du journal ; refuse les liens symboliques."""
    parts = PurePosixPath(relative).parts
    path = root
    for part in parts:
        path /= part
        if path.is_symlink():
            raise HistoryError(f"Lien symbolique interdit dans l'historique : {relative}")
    if not path.is_file():
        raise HistoryError(f"Element historique supprime ou absent : {relative}")
    return path.read_bytes()


def verify_history(root: Path, base: str | None) -> int:
    """Preserve octet pour octet le ledger herite et chaque evenement de la base.

    Aucun repli sur HEAD~1, aucune base implicite, aucune initialisation silencieuse.
    Les nouveaux evenements sont valides separement par engine.journal.read_events.
    """
    if (not isinstance(base, str) or not re.fullmatch(r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?", base)
            or set(base) == {"0"}):
        raise HistoryError("Une base Git complete et non nulle est obligatoire.")
    if _git(root, "cat-file", "-t", base).strip() != b"commit":
        raise HistoryError("La base Git n'est pas un commit.")
    ledger = "experiments/ledger.json"
    previous = _git(root, "show", f"{base}:{ledger}")
    if _local_bytes(root, ledger) != previous:
        raise HistoryError("Le ledger historique doit rester identique octet pour octet.")

    raw = _git(root, "ls-tree", "-r", "--name-only", "-z", base, "--", "experiments/events")
    paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    for relative in paths:
        parts = PurePosixPath(relative).parts
        if (len(parts) != 3 or parts[:2] != ("experiments", "events")
                or not parts[2].endswith(".json")):
            raise HistoryError("Element historique inattendu dans experiments/events.")
        if _local_bytes(root, relative) != _git(root, "show", f"{base}:{relative}"):
            raise HistoryError(f"Evenement historique modifie : {relative}")
    return len(paths)


def run_synthetic_tests(root: Path) -> bool:
    suite = unittest.defaultTestLoader.discover(
        str(root / "tests"), pattern="test_*_synthetic.py")
    if suite.countTestCases() == 0:
        raise HistoryError("Aucun test synthetique trouve ; qualification refusee.")
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--base", help="SHA complet de la base PR ou du push avant modification")
    mode.add_argument("--tests-only", action="store_true", help="tests synthetiques seuls, historique non qualifie")
    args = parser.parse_args(argv)
    try:
        if args.tests_only:
            print("Mode tests synthetiques uniquement : historique non verifie.", flush=True)
        else:
            count = verify_history(ROOT, args.base)
            from engine.journal import read_events
            events = read_events(ROOT / "experiments" / "events")
            print(f"Historique conserve : ledger et {count} evenement(s) de base ; {len(events)} evenement(s) valides.", flush=True)
        return 0 if run_synthetic_tests(ROOT) else 1
    except (HistoryError, OSError, ValueError, ImportError, RuntimeError) as exc:
        print(f"REFUS : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
