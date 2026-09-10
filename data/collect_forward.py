#!/usr/bin/env python3
"""
Collecte du coffre FUTUR (VAULT-F).

Les seules observations dont l'independance ne repose sur la parole de personne
sont celles qui n'existaient pas au moment du gel. Ce script recupere les barres
posterieures a la date de gel et les chiffre immediatement, sans jamais les
ecrire en clair sur le disque.

    python3 data/collect_forward.py

A lancer periodiquement (hebdomadaire suffit). Chaque barre collectee est
horodatee : un candidat gele le jour J ne peut etre juge que sur les barres
posterieures a J, et le harness le verifie.
"""
import gzip
import hashlib
import json
import ssl
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    import certifi
    SSLCTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSLCTX = ssl.create_default_context()

ROOT = Path(__file__).resolve().parent
VAULT = ROOT.parent / "vault"
KEYFILE = Path.home() / ".moteur-edge-btc" / "vault.key"
FREEZE = "2026-09-10"
API = "https://api.binance.com/api/v3/klines"
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]


def fetch(interval: str, start_ms: int) -> pd.DataFrame:
    rows, cur = [], start_ms
    while True:
        url = f"{API}?symbol=BTCUSDT&interval={interval}&startTime={cur}&limit=1000"
        with urllib.request.urlopen(url, timeout=60, context=SSLCTX) as r:
            batch = json.loads(r.read())
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        cur = batch[-1][6] + 1
    if not rows:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame(rows, columns=COLS)
    ot = df["open_time"].astype("int64")
    df["ts"] = pd.to_datetime(ot, unit="us" if ot.max() > 10**14 else "ms", utc=True)
    for c in ["open", "high", "low", "close", "volume", "taker_buy_base", "quote_volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["trades"] = pd.to_numeric(df["trades"], errors="coerce").astype("int64")
    return df[["ts", "open", "high", "low", "close", "volume", "trades",
               "taker_buy_base", "quote_volume"]]


def main() -> int:
    if not KEYFILE.exists():
        print(f"clef absente : {KEYFILE} — lancer data/seal_vault.py d'abord")
        return 1

    freeze_ms = int(pd.Timestamp(FREEZE, tz="UTC").timestamp() * 1000)
    state_path = VAULT / "FORWARD.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"series": {}}

    for interval in ("1h", "15m"):
        df = fetch(interval, freeze_ms)
        # ne garder que les barres CLOSES : une barre en cours n'est pas une observation
        now = pd.Timestamp.now(tz="UTC")
        step = pd.Timedelta(hours=1) if interval == "1h" else pd.Timedelta(minutes=15)
        df = df[df["ts"] + step <= now]
        if df.empty:
            print(f"  {interval}: aucune barre close depuis le gel")
            continue

        blob = df.to_csv(index=False, float_format="%.8f",
                         date_format="%Y-%m-%dT%H:%M:%SZ", lineterminator="\n").encode()
        enc = VAULT / f"FORWARD-{interval}.csv.enc"
        p = subprocess.run(
            ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
             "-salt", "-pass", f"file:{KEYFILE}"],
            input=blob, capture_output=True, check=True)
        enc.write_bytes(p.stdout)

        state["series"][interval] = {
            "bars": int(len(df)),
            "first": str(df["ts"].iloc[0]), "last": str(df["ts"].iloc[-1]),
            "sha256_clair": hashlib.sha256(blob).hexdigest(),
            "sha256_chiffre": hashlib.sha256(p.stdout).hexdigest(),
            "maj_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"  {interval}: {len(df)} barres depuis le gel -> {enc.name}")

    state["freeze_date"] = FREEZE
    state["note"] = ("VAULT-F : observations posterieures au gel, seules reellement "
                     "inedites. Chiffrees des la collecte, jamais ecrites en clair.")
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"-> {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
