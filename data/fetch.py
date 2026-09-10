#!/usr/bin/env python3
"""
Telechargement reproductible des donnees BTCUSDT depuis les dumps publics Binance.

Source : https://data.binance.vision/data/spot/monthly/klines/
Ces dumps sont figes et immuables : re-executer ce script a n'importe quelle date
doit produire des fichiers au hash identique (hors dernier mois partiel, exclu).

Usage :
    python3 data/fetch.py --intervals 1h 15m
"""
import argparse
import hashlib
import io
import json
import sys
import time
import ssl
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# macOS + python.org : le trousseau systeme n'est pas cable a OpenSSL,
# urlopen echoue en CERTIFICATE_VERIFY_FAILED la ou curl fonctionne.
try:
    import certifi
    SSLCTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSLCTX = ssl.create_default_context()

BASE = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOL = "BTCUSDT"
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
PROC = ROOT / "processed"

# Colonnes officielles des klines Binance
COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]

# Premier mois complet de BTCUSDT sur Binance spot
START = date(2017, 8, 1)

# Borne du coffre-fort. Retelecharger ne doit JAMAIS reecrire en clair la
# periode scellee : sans cette borne, un simple `python3 data/fetch.py` suffirait
# a rouvrir VAULT-H sans passer par la clef ni par le journal d'ouvertures.
VAULT_START = date(2025, 9, 1)


def months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch_month(interval: str, y: int, m: int) -> pd.DataFrame | None:
    name = f"{SYMBOL}-{interval}-{y:04d}-{m:02d}"
    url = f"{BASE}/{SYMBOL}/{interval}/{name}.zip"
    cache = RAW / f"{name}.zip"
    if cache.exists():
        blob = cache.read_bytes()
    else:
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=60, context=SSLCTX) as r:
                    blob = r.read()
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None  # mois pas encore publie
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        cache.write_bytes(blob)

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        inner = z.namelist()[0]
        with z.open(inner) as f:
            head = f.read(64)
        with z.open(inner) as f:
            # Depuis 2025 Binance prefixe certains CSV d'une ligne d'en-tete
            skip = 1 if head.startswith(b"open_time") else None
            df = pd.read_csv(f, header=None, names=COLS, skiprows=skip)
    return df


def canonical_csv(df: pd.DataFrame) -> bytes:
    """Serialisation canonique : le hash porte sur les VALEURS, pas sur
    l'encodage binaire. Un changement de version de gzip/pandas ne doit pas
    faire mentir le manifeste."""
    return df.to_csv(index=False, float_format="%.8f",
                     date_format="%Y-%m-%dT%H:%M:%SZ",
                     lineterminator="\n").encode()


def write_gz(blob: bytes, path: Path) -> None:
    """mtime=0 : sans ca gzip embarque l'heure de generation et le fichier
    change a chaque execution alors que les donnees sont identiques."""
    import gzip
    with open(path, "wb") as fh:
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, compresslevel=9) as gz:
            gz.write(blob)


def build(interval: str, end: date) -> dict:
    frames = []
    missing = []
    for y, m in months(START, end):
        df = fetch_month(interval, y, m)
        if df is None:
            missing.append(f"{y:04d}-{m:02d}")
            continue
        frames.append(df)
        print(f"  {interval} {y:04d}-{m:02d}  {len(df):>6d} barres", flush=True)

    full = pd.concat(frames, ignore_index=True)

    # Binance a bascule open_time des ms aux us EN COURS DE SERIE (dumps 2025+).
    # Detecter l'unite globalement ecrase toutes les dates anterieures en 1970 :
    # il faut trancher LIGNE PAR LIGNE. Un horodatage 2017-2026 vaut ~1.5e12 en
    # ms et ~1.5e15 en us ; le seuil 1e14 les separe sans ambiguite.
    ot = full["open_time"].astype("int64")
    ts = pd.Series(pd.NaT, index=full.index, dtype="datetime64[ns, UTC]")
    is_us = ot > 10**14
    if (~is_us).any():
        ts.loc[~is_us] = pd.to_datetime(ot[~is_us], unit="ms", utc=True)
    if is_us.any():
        ts.loc[is_us] = pd.to_datetime(ot[is_us], unit="us", utc=True)
    full["ts"] = ts
    if full["ts"].dt.year.min() < 2017:
        raise SystemExit("horodatage aberrant apres conversion — unite mal detectee")

    full = full[["ts", "open", "high", "low", "close", "volume", "trades",
                 "taker_buy_base", "quote_volume"]].copy()
    for c in ["open", "high", "low", "close", "volume", "taker_buy_base", "quote_volume"]:
        full[c] = pd.to_numeric(full[c], errors="coerce")
    full["trades"] = pd.to_numeric(full["trades"], errors="coerce").astype("int64")

    full = full.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)

    # Coupe au coffre-fort (voir VAULT_START ci-dessus)
    cut = pd.Timestamp(VAULT_START, tz="UTC")
    n_avant = len(full)
    full = full[full["ts"] < cut].reset_index(drop=True)
    if n_avant != len(full):
        print(f"  [coffre] {n_avant - len(full)} barres >= {VAULT_START} retirees "
              f"(scellees, voir vault/SEAL.md)", flush=True)

    out = PROC / f"{SYMBOL}-{interval}.csv.gz"
    blob = canonical_csv(full)
    write_gz(blob, out)

    step = {"1h": 3600, "15m": 900, "5m": 300, "1d": 86400}[interval]
    gaps = int(((full["ts"].diff().dt.total_seconds().dropna()) != step).sum())

    return {
        "interval": interval,
        "file": out.name,
        "sha256_canonical": hashlib.sha256(blob).hexdigest(),
        "bars": int(len(full)),
        "first": str(full["ts"].iloc[0]),
        "last": str(full["ts"].iloc[-1]),
        "gaps": gaps,
        "months_missing": missing,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--intervals", nargs="+", default=["1h", "15m"])
    a = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    # On s'arrete au dernier mois COMPLET : un mois partiel casserait la reproductibilite
    today = date.today()
    end = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

    manifest = {
        "source": BASE,
        "symbol": SYMBOL,
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "last_complete_month": f"{end.year:04d}-{end.month:02d}",
        "series": [],
    }
    for iv in a.intervals:
        print(f"== {iv} ==", flush=True)
        manifest["series"].append(build(iv, end))

    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["series"], indent=2))
