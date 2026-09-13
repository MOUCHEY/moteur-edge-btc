#!/usr/bin/env python3
"""
Rejoue en local, une par une, les etapes du workflow GitHub Actions.

    python3 ci/rejouer_local.py

Sert quand la CI distante ne peut pas s'executer. Les commandes sont lues DANS le
fichier du workflow, pas recopiees ici : ce qui passe en local est exactement ce
que GitHub aurait lance, et les deux ne peuvent pas diverger.
"""
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "protocole.yml"


def main() -> int:
    d = yaml.safe_load(WORKFLOW.read_text())
    echecs = 0
    for s in d["jobs"]["mecanismes"]["steps"]:
        run, nom = s.get("run"), s.get("name", s.get("uses", ""))
        if not run or "pip install" in run:
            continue                     # checkout, setup-python, dependances
        r = subprocess.run(["bash", "-c", run], cwd=ROOT, capture_output=True, text=True)
        sortie = (r.stdout + r.stderr).strip().splitlines()
        ok = r.returncode == 0
        print(f"{'OK' if ok else 'KO'}  {nom}")
        for ligne in (sortie[-3:] if ok else sortie[-15:]):
            print(f"      {ligne}")
        echecs += not ok
    print(f"\n{'toutes les etapes passent' if not echecs else f'{echecs} etape(s) en echec'}")
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())
