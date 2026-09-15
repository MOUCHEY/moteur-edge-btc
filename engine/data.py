"""Chargement IS uniquement ; OOS et coffres restent indisponibles.

Le gardien isole n'est pas qualifie. Aucun fichier d'autorisation local ne leve
cette interdiction. Les fichiers historiques melant IS et OOS ne sont jamais
utilises par ce chargeur.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"

# Bornes [debut inclus, fin exclue]. Ces metadonnees n'ouvrent aucun acces.
SPLITS = {
    "IS": ("2017-08-17", "2023-01-01"),
    "OOS": ("2023-01-01", "2025-09-01"),
    "VAULT": ("2025-09-01", "2100-01-01"),
}
STEP_SECONDS = {"1h": 3600, "15m": 900, "5m": 300, "1d": 86400}
MIN_BARS = 500


class DataError(RuntimeError):
    """Une donnee douteuse ou un acces indisponible bloque le chargement."""


def _window_mask(timestamps: pd.Series, split: str) -> pd.Series:
    """Calcul pur des bornes semi-ouvertes ; ne charge aucune donnee."""
    if split not in SPLITS:
        raise DataError(f"split inconnu : {split}")
    lo, hi = (pd.Timestamp(s, tz="UTC") for s in SPLITS[split])
    return (timestamps >= lo) & (timestamps < hi)


def load(interval: str = "1h", split: str | None = "IS") -> pd.DataFrame:
    """Lit une seule fois les octets d'un fichier physiquement reserve a IS.

    Le fichier entier doit etre dans IS : aucune ligne hors bornes n'est filtree
    silencieusement. Aucune preparation des donnees historiques n'est effectuee.
    """
    # Refuser AVANT toute consultation de chemin, manifeste ou autorisation.
    if split != "IS":
        raise DataError("Acces indisponible : seul IS est chargeable ; OOS, VAULT et split=None sont bloques.")
    if interval not in STEP_SECONDS:
        raise DataError(f"intervalle inconnu : {interval}")

    directory = PROC / "IS"
    path = directory / f"BTCUSDT-{interval}.csv.gz"
    if PROC.is_symlink() or directory.is_symlink() or path.is_symlink():
        raise DataError("Un fichier IS ou son repertoire ne peut pas etre un lien symbolique.")
    if not path.is_file():
        raise DataError("Jeu IS physiquement isole absent. Les anciens fichiers IS/OOS ne sont pas admis.")
    try:
        raw = path.read_bytes()
        csv_bytes = gzip.decompress(raw)
        df = pd.read_csv(io.BytesIO(csv_bytes))
    except (OSError, EOFError, ValueError, zlib.error, pd.errors.ParserError) as exc:
        raise DataError("Fichier IS illisible ou CSV compresse invalide.") from exc
    if "ts" not in df.columns:
        raise DataError("Colonne ts absente.")
    # Une heure sans fuseau ne devient pas implicitement UTC.
    time_text = df["ts"].astype("string")
    if not time_text.str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True, na=False).all():
        raise DataError("Chaque horodatage doit avoir un fuseau explicite.")
    try:
        df["ts"] = pd.to_datetime(time_text, utc=True, errors="raise", format="ISO8601")
    except (ValueError, TypeError) as exc:
        raise DataError("Horodatages ISO-8601 invalides.") from exc
    # Ne pas trier : un ordre source incorrect doit etre signale.
    _sanity(df, interval)
    if not _window_mask(df["ts"], "IS").all():
        raise DataError("Le fichier reserve a IS contient au moins une ligne hors IS.")
    if len(df) < MIN_BARS:
        raise DataError(f"split IS : {len(df)} barres, minimum requis {MIN_BARS}")
    df.attrs.update({
        "data_sha256": hashlib.sha256(raw).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "data_bytes": len(raw),
        "data_path": str(path),
        "interval": interval,
        "split": "IS",
    })
    return df


def _open_vault(interval: str) -> pd.DataFrame:
    """Indisponible meme en appel direct : aucun dechiffrement ni journal local."""
    raise DataError("Coffre indisponible : gardien isole et validation prospective non qualifies.")


def _vault_authorised() -> bool:
    """Compatibilite sans aucun acces au systeme de fichiers."""
    return False


def _sanity(df: pd.DataFrame, interval: str) -> None:
    """Exige des observations finies, coherentes, ordonnees et continues."""
    if interval not in STEP_SECONDS:
        raise DataError(f"intervalle inconnu : {interval}")
    required = {"ts", "open", "high", "low", "close", "volume"}
    if required - set(df.columns):
        raise DataError(f"Colonnes absentes : {sorted(required - set(df.columns))}")
    if df.empty:
        raise DataError("Serie vide.")
    ts = df["ts"]
    if not isinstance(ts.dtype, pd.DatetimeTZDtype) or ts.isna().any():
        raise DataError("Horodatages manquants ou sans fuseau.")
    if ts.duplicated().any() or not ts.is_monotonic_increasing:
        raise DataError("Horodatages dupliques ou non croissants.")

    numeric = ["open", "high", "low", "close", "volume"]
    numeric += [c for c in ("trades", "taker_buy_base", "quote_volume") if c in df.columns]
    for c in numeric:
        if not pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c]):
            raise DataError(f"Colonne non numerique : {c}")
        if not np.isfinite(df[c].to_numpy(dtype=float, na_value=np.nan)).all():
            raise DataError(f"Valeur non finie dans {c}")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise DataError("Prix nul ou negatif.")
    bad = ((df["high"] < df["low"])
           | (df["open"] > df["high"]) | (df["open"] < df["low"])
           | (df["close"] > df["high"]) | (df["close"] < df["low"]))
    if bad.any():
        raise DataError("Barres OHLC incoherentes, open compris.")
    for c in ("volume", "quote_volume", "taker_buy_base", "trades"):
        if c in df.columns and (df[c] < 0).any():
            raise DataError(f"Valeur negative dans {c}")
    if "taker_buy_base" in df.columns and (df["taker_buy_base"] > df["volume"]).any():
        raise DataError("Volume acheteur superieur au volume total.")
    if "trades" in df.columns and (df["trades"] % 1 != 0).any():
        raise DataError("Nombre de trades non entier.")

    step = STEP_SECONDS[interval]
    utc = ts.dt.tz_convert("UTC")
    if (utc != utc.dt.floor(f"{step}s")).any():
        raise DataError("Horodatages non alignes sur l'intervalle.")
    if (utc.diff().iloc[1:] != pd.Timedelta(seconds=step)).any():
        raise DataError("Serie discontinue : un trou exige une qualification explicite.")
    df.attrs["gaps"] = 0


def forward_return(df: pd.DataFrame, k: int, interval: str) -> pd.Series:
    """Rendement a k barres, rejete si l'ecart temporel ne correspond pas."""
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0 or interval not in STEP_SECONDS:
        raise DataError("Horizon ou intervalle invalide.")
    fwd = df["close"].shift(-k) / df["close"] - 1.0
    ecart = df["ts"].shift(-k) - df["ts"]
    attendu = pd.Timedelta(seconds=STEP_SECONDS[interval] * k)
    return fwd.where(ecart == attendu)


def data_fingerprint(df: pd.DataFrame) -> str:
    """Empreinte complete des octets lus pour CE chargement, sans nouvelle lecture.

    Cette empreinte identifie la source avant transformation du DataFrame ; elle
    ne remplace pas l'empreinte du code ni celle de la specification.
    """
    if not isinstance(df, pd.DataFrame):
        raise DataError("data_fingerprint exige le DataFrame issu du chargement.")
    digest = df.attrs.get("data_sha256")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)):
        raise DataError("Empreinte du chargement absente ou invalide.")
    return digest
