"""Journal local append-only, verifie avant chaque ajout.

Le verrou serialise les ecritures cooperatives. La chaine rend les alterations
detectables contre une revision publiee ; elle n'isole pas un utilisateur qui
peut reecrire tout le repertoire. Une tentative interrompue reste ouverte.
"""
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Mapping
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from uuid import uuid4


class JournalError(RuntimeError):
    pass


def clean(value):
    """JSON strict : valeurs non finies representees par null, jamais NaN."""
    if isinstance(value, Mapping):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "item"):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def canonical(value) -> bytes:
    return json.dumps(clean(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_events(directory: Path) -> list[dict]:
    directory = Path(directory)
    if directory.is_symlink() or directory.parent.is_symlink():
        raise JournalError("repertoire du journal symbolique interdit")
    previous = None
    events = []
    for seq, path in enumerate(sorted(directory.glob("*.json")), 1):
        if path.is_symlink():
            raise JournalError("evenement symbolique interdit")
        try:
            event = json.loads(path.read_text())
            unsigned = {k: v for k, v in event.items() if k != "sha256"}
            if (event["schema_version"] != 1 or type(event["sequence"]) is not int or event["sequence"] != seq
                    or not isinstance(event["payload"], dict) or not isinstance(event["kind"], str)
                    or event["prev_sha256"] != previous
                    or path.name != f'{seq:08d}-{event["event_id"]}.json'
                    or event["sha256"] != digest(unsigned)):
                raise ValueError("chaine ou empreinte invalide")
        except (ValueError, KeyError, TypeError) as exc:
            raise JournalError(f"journal altere au rang {seq}") from exc
        previous = event["sha256"]
        events.append(event)
    return events


def write_once(path: Path, value) -> str:
    """Publication atomique et exclusive ; refuse d'ecraser un resultat."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(clean(value), sort_keys=True, indent=2,
                      ensure_ascii=False, allow_nan=False).encode() + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.link(temporary, path)  # atomique, echoue si la destination existe
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        os.unlink(temporary)
    return hashlib.sha256(blob).hexdigest()


@contextmanager
def locked(directory: Path):
    if directory.is_symlink() or directory.parent.is_symlink() or (directory / ".lock").is_symlink():
        raise JournalError("lien symbolique interdit dans le verrou du journal")
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def append(directory: Path, kind: str, payload: dict) -> dict:
    directory = Path(directory)
    with locked(directory):
        old = read_events(directory)
        return _append_locked(directory, old, kind, payload)


def _append_locked(directory, old, kind, payload):
    event = {
        "schema_version": 1, "sequence": len(old) + 1,
        "event_id": uuid4().hex,
        "utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "prev_sha256": old[-1]["sha256"] if old else None,
        "kind": kind, "payload": clean(payload),
    }
    event["sha256"] = digest(event)
    write_once(directory / f'{event["sequence"]:08d}-{event["event_id"]}.json', event)
    return event


def summary(directory: Path) -> dict:
    events = read_events(directory)
    started, closed, measured, distinct = set(), set(), 0, set()
    for e in events:
        p = e["payload"]
        if e["kind"] == "run_started":
            started.add(p["run_id"])
        elif e["kind"] in ("run_completed", "run_failed"):
            closed.add(p["run_id"])
        elif e["kind"] == "evaluation_completed" and p["domain"] == "IS":
            measured += 1
            distinct.add(p["evaluation_identity"])
    return {
        "attempts_started": len(started), "attempts_unfinished": len(started - closed),
        "new_is_evaluations_completed": measured,
        "new_distinct_is_evaluation_identities": len(distinct),
        "historical_unique_trials": None, "independent_trials": None,
        "note": "Identites descriptives, pas un nombre d'essais independants pour le DSR.",
    }


class Session:
    def __init__(self, directory: Path, kind: str, spec_hash: str, split: str, metadata: dict):
        self.directory = Path(directory)
        self.context = {"run_id": uuid4().hex, "kind": kind,
                        "spec_hash": spec_hash, "split": split}
        self.metadata = metadata
        self.data_sha256 = None

    @property
    def run_id(self):
        return self.context["run_id"]

    def event(self, kind, **payload):
        return append(self.directory, kind, {**self.context, **payload})

    def __enter__(self):
        self.event("run_started", metadata=self.metadata)
        return self

    def bind_data(self, fingerprint):
        self.data_sha256 = fingerprint
        self.event("data_bound", data_sha256=fingerprint)

    def bind_contract(self, g0, spec, costs, **metadata):
        """Un identifiant d'experience ne peut changer de contrat apres son gel.

        Comparaison et ajout sous le meme verrou, avant tout chargement de marche.
        Une correction de moteur peut etre reevaluee sous la meme hypothese ; sa
        provenance distincte reste dans chaque mesure. Une modification de G0,
        des regles, de la grille ou des couts exige un nouvel identifiant.
        """
        snapshot = {"g0": g0, "spec": spec, "costs": costs}
        fingerprint = digest(snapshot)
        payload = {**self.context, **snapshot, **metadata,
                   "g0_sha256": digest(g0), "contract_sha256": fingerprint}
        with locked(self.directory):
            events = read_events(self.directory)
            for e in events:
                if e["kind"] == "contract_bound" and e["payload"]["spec"]["id"] == spec["id"]:
                    if e["payload"]["contract_sha256"] != fingerprint:
                        raise JournalError("Contrat deja fige : creer une nouvelle experience pour le modifier.")
            _append_locked(self.directory, events, "contract_bound", payload)

    def evaluate(self, params: dict, label: str, fn, domain="IS"):
        identity = digest({"spec": self.context["spec_hash"], "params": params,
                           "label": label, "domain": domain, "data": self.data_sha256,
                           "provenance": self.metadata.get("provenance")})
        payload = {"evaluation_id": uuid4().hex, "evaluation_identity": identity,
                   "params": params, "label": label, "domain": domain}
        self.event("evaluation_started", **payload)
        try:
            result = fn()
        except BaseException as exc:
            self.event("evaluation_failed", **payload, error_type=type(exc).__name__)
            raise
        # Les tableaux de trades sont conserves avec le resultat du run ; ici,
        # seules les petites sorties de mesure sont journalisees.
        evidence = result if isinstance(result, (dict, float, int)) else None
        self.event("evaluation_completed", **payload, evidence=evidence)
        return result

    def publish(self, directory: Path, report: dict):
        output = Path(directory) / f"{self.run_id}.json"
        report = {**report, "run_id": self.run_id,
                  "journal_snapshot": {"stage": "before_report_publication_and_run_close",
                                       **summary(self.directory)}}
        sha = write_once(output, report)
        self.event("report_published", filename=output.name, report_sha256=sha)
        return report, output

    def __exit__(self, exc_type, exc, traceback):
        self.event("run_failed" if exc_type else "run_completed",
                   error_type=exc_type.__name__ if exc_type else None)
        return False
