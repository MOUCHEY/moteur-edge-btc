"""
Spec de strategie : le contrat entre Astra et le harness.

Une spec est un fichier YAML fige. Elle se hashe. La modifier apres avoir vu
ses resultats produit un hash different, donc une nouvelle experience, qui
consomme du budget (PROTOCOLE.md section 4).
"""
from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MODES = {"horizon", "bracket"}


@dataclass
class Spec:
    id: str
    titre: str
    auteur: str
    interval: str
    entry_long: str | None
    entry_short: str | None
    mode: str
    horizon: int
    stop_atr: float | None
    target_atr: float | None
    atr_col: str
    params: dict[str, list[Any]] = field(default_factory=dict)
    budget_declare: int = 1
    notes: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def hash(self) -> str:
        blob = yaml.safe_dump(self.raw, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]

    def grid(self) -> list[dict[str, Any]]:
        """Produit cartesien des parametres. C'est ce nombre qui compte au DSR."""
        if not self.params:
            return [{}]
        keys = sorted(self.params)
        return [dict(zip(keys, combo)) for combo in itertools.product(*(self.params[k] for k in keys))]

    def validate(self) -> list[str]:
        errs = []
        if self.mode not in MODES:
            errs.append(f"mode inconnu : {self.mode}")
        if not (self.entry_long or self.entry_short):
            errs.append("aucune condition d'entree")
        if self.mode == "horizon" and self.horizon < 1:
            errs.append("horizon doit valoir >= 1")
        if self.mode == "bracket" and not (self.stop_atr and self.target_atr):
            errs.append("mode bracket : stop_atr et target_atr requis")
        if len(self.params) > 3:
            errs.append(f"{len(self.params)} parametres libres — le protocole en autorise 3 (G1)")
        n = len(self.grid())
        if n > self.budget_declare:
            errs.append(f"grille de {n} configs > budget declare {self.budget_declare} (G0)")
        for expr in (self.entry_long, self.entry_short):
            if expr and (" and " in expr or " or " in expr):
                errs.append("utiliser & et | (operateurs vectoriels), pas 'and'/'or'")
        return errs


def load(path: str | Path) -> Spec:
    d = yaml.safe_load(Path(path).read_text())
    ex = d.get("exit", {})
    sig = d.get("signal", {})
    return Spec(
        id=d["id"],
        titre=d.get("titre", ""),
        auteur=d.get("auteur", "?"),
        interval=d.get("data", {}).get("interval", "1h"),
        entry_long=sig.get("entry_long"),
        entry_short=sig.get("entry_short"),
        mode=ex.get("mode", "horizon"),
        horizon=int(ex.get("horizon", 1)),
        stop_atr=ex.get("stop_atr"),
        target_atr=ex.get("target_atr"),
        atr_col=ex.get("atr_col", "atr_48"),
        params={k: list(v) for k, v in (d.get("params") or {}).items()},
        budget_declare=int(d.get("budget_essais", 1)),
        notes=d.get("notes", ""),
        raw=d,
    )
