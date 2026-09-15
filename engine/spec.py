"""Immutable strategy contract, independent of its original YAML dictionary."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from .expressions import SpecError, parse, scalar

MODES = frozenset({"horizon", "bracket"})
INTERVALS = frozenset({"1h", "15m"})


def _freeze(value):
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise SpecError("les cles de la spec doivent etre des chaines")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise SpecError(f"valeur de spec non prise en charge : {type(value).__name__}")


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _positive(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


@dataclass(frozen=True, slots=True)
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
    params: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    budget_declare: int = 1
    notes: str = ""
    raw: Mapping = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self):
        # Defensive copies break every mutable link with the caller/YAML object.
        for item in fields(self):
            object.__setattr__(self, item.name, _freeze(getattr(self, item.name)))

    def to_dict(self) -> dict:
        """Detached JSON-safe effective contract, also used for its fingerprint."""
        return {item.name: _plain(getattr(self, item.name))
                for item in fields(self) if item.name != "raw"}

    @property
    def hash(self) -> str:
        """Full SHA-256 of all effective fields; raw is provenance, not authority."""
        try:
            blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise SpecError("spec non canonisable") from exc
        return hashlib.sha256(blob).hexdigest()

    def grid(self) -> tuple[Mapping, ...]:
        """Immutable configurations, not an estimate of independent trials."""
        if not isinstance(self.params, Mapping):
            raise SpecError("params doit etre un mapping de grilles")
        if not self.params:
            return (MappingProxyType({}),)
        keys = sorted(self.params)
        if any(not isinstance(self.params[k], tuple) or not self.params[k] for k in keys):
            raise SpecError("chaque grille de parametre doit etre non vide")
        return tuple(MappingProxyType(dict(zip(keys, combo)))
                     for combo in itertools.product(*(self.params[k] for k in keys)))

    def validate_params(self, params: Mapping) -> list[str]:
        """The actual execution must select exactly one declared configuration."""
        if not isinstance(params, Mapping) or not isinstance(self.params, Mapping):
            return ["parametres : mapping attendu"]
        if set(params) != set(self.params):
            return ["parametres reels : cles exactement identiques a la grille requises"]
        errs = []
        for key, value in params.items():
            try:
                clean = scalar(value)
            except SpecError:
                errs.append(f"parametre {key} : scalaire fini requis")
                continue
            values = self.params[key]
            if not isinstance(values, tuple) or not any(
                type(clean) is type(option) and clean == option for option in values
            ):
                errs.append(f"parametre {key} hors de la grille declaree (valeur et type)")
        return errs

    def validate(self) -> list[str]:
        errs = []
        for name in ("id", "titre", "auteur", "notes", "atr_col"):
            if not isinstance(getattr(self, name), str):
                errs.append(f"{name} doit etre une chaine")
        if not isinstance(self.id, str) or not self.id.strip():
            errs.append("id requis")
        if not isinstance(self.interval, str) or self.interval not in INTERVALS:
            errs.append(f"intervalle inconnu : {self.interval}")
        if not isinstance(self.mode, str) or self.mode not in MODES:
            errs.append(f"mode inconnu : {self.mode}")
        if type(self.horizon) is not int or self.horizon < 1:
            errs.append("horizon doit etre un entier >= 1, dans tous les modes")
        if type(self.budget_declare) is not int or self.budget_declare < 1:
            errs.append("budget declare doit etre un entier >= 1")
        for name in ("stop_atr", "target_atr"):
            value = getattr(self, name)
            if (self.mode == "bracket" or value is not None) and not _positive(value):
                errs.append(f"{name} doit etre strictement positif et fini")
        if self.mode == "bracket" and (not isinstance(self.atr_col, str) or not self.atr_col.strip()):
            errs.append("mode bracket : atr_col requis")
        if not (self.entry_long or self.entry_short):
            errs.append("aucune condition d'entree")
        for expr in (self.entry_long, self.entry_short):
            if expr is not None and (not isinstance(expr, str) or not expr.strip()):
                errs.append("condition d'entree : expression non vide ou null attendue")
        if not isinstance(self.params, Mapping):
            return errs + ["params doit etre un mapping de grilles"]
        if len(self.params) > 3:
            errs.append(f"{len(self.params)} parametres libres — le protocole en autorise 3 (G1)")
        count = 1
        good_grid = True
        for name, values in self.params.items():
            if not isinstance(values, tuple) or not values:
                errs.append(f"grille {name} vide ou invalide")
                good_grid = False
                continue
            count *= len(values)
            seen = set()
            for value in values:
                try:
                    clean = scalar(value)
                    marker = (type(clean).__name__, clean)
                    if marker in seen:
                        errs.append(f"grille {name} : valeur dupliquee")
                    seen.add(marker)
                except SpecError:
                    errs.append(f"grille {name} : scalaires finis uniquement")
                    good_grid = False
        if type(self.budget_declare) is int and count > self.budget_declare:
            errs.append(f"grille de {count} configs > budget declare {self.budget_declare} (G0)")
        # Avoid materializing an invalid/oversized Cartesian grid during validation.
        if good_grid and not errs:
            for params in self.grid():
                for expr in (self.entry_long, self.entry_short):
                    if expr is not None:
                        try:
                            parse(expr, params)
                        except SpecError as exc:
                            errs.append(str(exc))
            errs = list(dict.fromkeys(errs))
        return errs


def load(path: str | Path) -> Spec:
    """Load without coercing malformed numbers; validate() reports contract errors."""
    try:
        d = yaml.safe_load(Path(path).read_text())
    except yaml.YAMLError as exc:
        raise SpecError("YAML invalide") from exc
    if not isinstance(d, dict):
        raise SpecError("la spec YAML doit etre un mapping")
    sections = {}
    for name in ("exit", "signal", "data"):
        sections[name] = d.get(name, {})
        if not isinstance(sections[name], dict):
            raise SpecError(f"section {name} : mapping attendu")
    ex, sig = sections["exit"], sections["signal"]
    return Spec(
        id=d.get("id", ""), titre=d.get("titre", ""), auteur=d.get("auteur", "?"),
        interval=sections["data"].get("interval", "1h"),
        entry_long=sig.get("entry_long"), entry_short=sig.get("entry_short"),
        mode=ex.get("mode", "horizon"), horizon=ex.get("horizon", 1),
        stop_atr=ex.get("stop_atr"), target_atr=ex.get("target_atr"),
        atr_col=ex.get("atr_col", "atr_48"), params=d.get("params", {}),
        budget_declare=d.get("budget_essais", 1), notes=d.get("notes", ""), raw=d,
    )
