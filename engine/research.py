"""Contrat commun aux commandes de recherche ; aucune porte finale ouverte."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

from .journal import digest

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "experiments" / "events"


class ResearchError(RuntimeError):
    pass


def require_is(split):
    if split != "IS":
        raise ResearchError("OOS et coffres indisponibles : validation independante non qualifiee.")


def g0_contract(sp, spec_path) -> dict:
    """Controle structurel, pas une certification du mecanisme economique."""
    path = Path(spec_path).parent / "G0.json"
    if not path.is_file():
        raise ResearchError("G0.json preenregistre requis avant toute lecture de marche.")
    contract = json.loads(path.read_text())
    if contract.get("spec_hash") != sp.hash:
        raise ResearchError("G0 ne correspond pas a la spec executee.")
    for field in ("hypothesis", "mechanism", "abandonment_rule"):
        if not isinstance(contract.get(field), str) or not contract[field].strip():
            raise ResearchError(f"G0 : {field} requis.")
    predictions = contract.get("predictions")
    if not isinstance(predictions, list) or not predictions or any(
            not isinstance(p, str) or not p.strip() for p in predictions):
        raise ResearchError("G0 : predictions falsifiables requises.")
    if type(contract.get("budget_configs")) is not int or contract["budget_configs"] != len(sp.grid()):
        raise ResearchError("G0 : budget doit correspondre exactement a la grille.")
    errors = sp.validate_params(contract.get("central_params"))
    if errors:
        raise ResearchError("G0 : configuration centrale invalide : " + "; ".join(errors))
    if type(contract.get("min_trades")) is not int or contract["min_trades"] < 100:
        raise ResearchError("G0 : min_trades entier >= 100 requis (seuil de protocole, pas preuve de puissance).")
    return contract


def provenance() -> dict:
    """Empreintes des seules sources et du protocole, jamais des donnees."""
    files = sorted((ROOT / "engine").rglob("*.py")) + [ROOT / "PROTOCOLE.md", ROOT / "requirements.txt"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in files if p.is_file()}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    versions = {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy", "PyYAML")}
    return {"commit": revision, "source_sha256": hashes,
            "source_bundle_sha256": digest(hashes), "dependencies": versions}


def gate_status():
    return {"G2": "non revue independante", "G3": "descriptif, predictions non verifiees",
            "G4": "non qualifiee", "G5": "indisponible", "G6": "indisponible",
            "G7": "indisponible"}
