"""
Chargement des donnees + decoupage IS / OOS / VAULT.

Le decoupage est FIGE (voir PROTOCOLE.md section 1). Les bornes sont ici et
nulle part ailleurs : une strategie qui veut d'autres bornes doit modifier ce
fichier, ce qui apparait dans le diff et donc dans la revue.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"

# --- Decoupage fige le 2026-09-10 -------------------------------------------
SPLITS = {
    "IS":    ("2017-08-17", "2022-12-31"),   # bac a sable, acces libre
    "OOS":   ("2023-01-01", "2025-08-31"),   # 1 ouverture par strategie
    "VAULT": ("2025-09-01", "2099-12-31"),   # 1 ouverture pour tout le projet
}

STEP_SECONDS = {"1h": 3600, "15m": 900, "5m": 300, "1d": 86400}


class DataError(RuntimeError):
    """Leve quand une donnee est douteuse. On prefere planter que mesurer faux."""


def load(interval: str = "1h", split: str | None = "IS") -> pd.DataFrame:
    """Charge la serie et applique les garde-fous. `split=None` -> tout sauf VAULT."""
    if split == "VAULT":
        if not _vault_authorised():
            raise DataError(
                "VAULT scelle. Ouverture = decision de Jeunathan (PROTOCOLE.md G6). "
                "Poser le fichier vault/OPEN_AUTHORISATION pour lever le verrou."
            )
        return _open_vault(interval)

    path = PROC / f"BTCUSDT-{interval}.csv.gz"
    if not path.exists():
        raise DataError(f"{path} absent — lancer `python3 data/fetch.py` d'abord")

    df = pd.read_csv(path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)

    _sanity(df, interval)

    if split is None:
        lo, hi = SPLITS["IS"][0], SPLITS["OOS"][1]
    else:
        if split not in SPLITS:
            raise DataError(f"split inconnu : {split}")
        if split == "VAULT" and not _vault_authorised():
            raise DataError(
                "VAULT scelle. Ouverture = decision de Jeunathan (PROTOCOLE.md G6). "
                "Poser le fichier vault/OPEN_AUTHORISATION pour lever le verrou."
            )
        lo, hi = SPLITS[split]

    m = (df["ts"] >= pd.Timestamp(lo, tz="UTC")) & (df["ts"] <= pd.Timestamp(hi, tz="UTC") + pd.Timedelta(days=1))
    out = df.loc[m].reset_index(drop=True)
    if len(out) < 500:
        raise DataError(f"split {split} : {len(out)} barres, trop peu pour mesurer")
    return out


def _open_vault(interval: str) -> pd.DataFrame:
    """Dechiffre le coffre. Journalise l'ouverture : elle est unique et definitive."""
    import io, json, subprocess
    from datetime import datetime, timezone

    seal = json.loads((ROOT / "vault" / "SEAL.json").read_text())
    key = Path(seal["clef"]).expanduser()
    if not key.exists():
        raise DataError(f"clef absente : {key}")
    enc = ROOT / "vault" / f"BTCUSDT-{interval}.csv.enc"
    r = subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
         "-pass", f"file:{key}"],
        input=enc.read_bytes(), capture_output=True, check=True)

    attendu = next(s["vault_sha256_clair"] for s in seal["series"] if s["interval"] == interval)
    got = hashlib.sha256(r.stdout).hexdigest()
    if got != attendu:
        raise DataError(f"le coffre a ete altere : {got} != {attendu}")

    log = ROOT / "vault" / "OUVERTURES.log"
    with open(log, "a") as fh:
        fh.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}  {interval}  sha={got[:16]}\n")

    df = pd.read_csv(io.BytesIO(r.stdout), parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def _vault_authorised() -> bool:
    return (ROOT / "vault" / "OPEN_AUTHORISATION").exists()


def _sanity(df: pd.DataFrame, interval: str) -> None:
    """Les erreurs qui ne levent aucune exception toutes seules."""
    if df["ts"].duplicated().any():
        raise DataError("horodatages dupliques")
    if not df["ts"].is_monotonic_increasing:
        raise DataError("horodatages non croissants")

    bad = df[(df["high"] < df["low"]) | (df["close"] > df["high"]) | (df["close"] < df["low"])]
    if len(bad):
        raise DataError(f"{len(bad)} barres OHLC incoherentes")

    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise DataError("prix nul ou negatif")

    # Un gap non signale se fait passer pour un mouvement intra-barre
    step = STEP_SECONDS[interval]
    d = df["ts"].diff().dt.total_seconds().dropna()
    gaps = int((d != step).sum())
    if gaps / len(df) > 0.02:
        raise DataError(f"{gaps} gaps ({gaps/len(df):.1%}) — serie trop trouee")
    df.attrs["gaps"] = gaps


def forward_return(df: pd.DataFrame, k: int, interval: str) -> pd.Series:
    """
    Rendement a k barres, rejete par HORODATAGE et pas par indice.

    Sans ce filtre, un trou de 6 h dans la serie se retrouve compte comme un
    mouvement de k barres et on mesure un gap en croyant mesurer un effet.
    """
    c = df["close"]
    fwd = c.shift(-k) / c - 1.0
    ecart = df["ts"].shift(-k) - df["ts"]
    attendu = pd.Timedelta(seconds=STEP_SECONDS[interval] * k)
    return fwd.where(ecart == attendu)


def data_fingerprint(interval: str) -> str:
    """Hash du manifeste : identifie sans ambiguite le jeu de donnees d'un run."""
    mf = ROOT / "data" / "MANIFEST.json"
    if not mf.exists():
        return "no-manifest"
    m = json.loads(mf.read_text())
    for s in m.get("series", []):
        if s["interval"] == interval:
            return s["sha256_canonical"][:16]
    return "unknown"
