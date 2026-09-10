#!/usr/bin/env python3
"""
Scelle le coffre-fort.

Separation PHYSIQUE, pas seulement logique : les fichiers publies dans le depot
ne contiennent que IS + OOS. La periode VAULT est extraite, chiffree, et sa
version en clair supprimee.

La passphrase est generee par openssl et ecrite directement dans un fichier hors
depot. Elle ne transite ni par la sortie standard, ni par un argument de ligne
de commande, ni par le contexte de l'agent qui lance ce script : personne ne la
lit en la generant. C'est ce qui rend le verrou opposable meme a Claude.
"""
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "processed"
VAULT = ROOT.parent / "vault"
KEYDIR = Path.home() / ".moteur-edge-btc"
KEYFILE = KEYDIR / "vault.key"

VAULT_START = "2025-09-01"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    VAULT.mkdir(parents=True, exist_ok=True)
    KEYDIR.mkdir(parents=True, exist_ok=True, mode=0o700)

    if not KEYFILE.exists():
        # 32 octets aleatoires -> base64, ecrits SANS jamais passer par stdout
        with open(KEYFILE, "wb") as fh:
            subprocess.run(["openssl", "rand", "-base64", "32"], stdout=fh, check=True)
        KEYFILE.chmod(0o600)
        print(f"clef generee : {KEYFILE} (jamais affichee)")
    else:
        print(f"clef existante reutilisee : {KEYFILE}")

    seal = {"vault_start": VAULT_START, "series": [],
            "clef": str(KEYFILE),
            "note": "la clef n'est pas versionnee et n'a jamais ete affichee"}

    for f in sorted(PROC.glob("BTCUSDT-*.csv.gz")):
        interval = f.stem.replace("BTCUSDT-", "").replace(".csv", "")
        df = pd.read_csv(f, parse_dates=["ts"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)

        cut = pd.Timestamp(VAULT_START, tz="UTC")
        public, secret = df[df["ts"] < cut], df[df["ts"] >= cut]
        if len(secret) == 0:
            print(f"  {interval}: rien a sceller")
            continue

        def canon(d):
            return d.to_csv(index=False, float_format="%.8f",
                            date_format="%Y-%m-%dT%H:%M:%SZ", lineterminator="\n").encode()

        # 1) reecrire la partie publique
        pub_blob = canon(public)
        with open(f, "wb") as fh:
            with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, compresslevel=9) as gz:
                gz.write(pub_blob)

        # 2) chiffrer la partie scellee
        sec_blob = canon(secret)
        enc = VAULT / f"BTCUSDT-{interval}.csv.enc"
        p = subprocess.run(
            ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
             "-salt", "-pass", f"file:{KEYFILE}"],
            input=sec_blob, capture_output=True, check=True)
        enc.write_bytes(p.stdout)

        seal["series"].append({
            "interval": interval,
            "public_bars": len(public), "public_last": str(public["ts"].iloc[-1]),
            "public_sha256": sha(pub_blob),
            "vault_bars": len(secret),
            "vault_first": str(secret["ts"].iloc[0]), "vault_last": str(secret["ts"].iloc[-1]),
            "vault_sha256_clair": sha(sec_blob),      # temoin d'integrite
            "vault_sha256_chiffre": sha(p.stdout),
            "fichier_chiffre": enc.name,
        })
        print(f"  {interval}: {len(public)} publiques / {len(secret)} scellees")

    (VAULT / "SEAL.json").write_text(json.dumps(seal, indent=2) + "\n")
    print("-> vault/SEAL.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
