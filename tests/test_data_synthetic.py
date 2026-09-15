"""Fixtures fabriquees uniquement : aucun historique ni coffre du depot."""
from __future__ import annotations

import gzip
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from ci import rejouer_local as ci
from engine import data


def fixture(n: int = 500, start: str = "2020-01-01") -> pd.DataFrame:
    return pd.DataFrame({
        "ts": pd.date_range(start, periods=n, freq="h", tz="UTC"),
        "open": np.full(n, 100.0), "high": np.full(n, 102.0),
        "low": np.full(n, 98.0), "close": np.full(n, 101.0),
        "volume": np.full(n, 10.0), "trades": np.full(n, 5),
        "taker_buy_base": np.full(n, 4.0), "quote_volume": np.full(n, 1000.0),
    })


class IsLoaderSynthetic(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proc = Path(self.temp.name) / "processed"
        (self.proc / "IS").mkdir(parents=True)
        self.path = self.proc / "IS" / "BTCUSDT-1h.csv.gz"
        patcher = patch.object(data, "PROC", self.proc)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, df: pd.DataFrame) -> tuple[bytes, bytes]:
        csv = df.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode()
        raw = gzip.compress(csv, mtime=0)
        self.path.write_bytes(raw)
        return raw, csv

    def test_forbidden_splits_refuse_before_any_io(self):
        with (patch.object(Path, "read_bytes", side_effect=AssertionError("lecture interdite")),
              patch.object(Path, "read_text", side_effect=AssertionError("lecture interdite")),
              patch.object(Path, "exists", side_effect=AssertionError("consultation interdite")),
              patch.object(Path, "is_file", side_effect=AssertionError("consultation interdite")),
              patch.object(Path, "is_symlink", side_effect=AssertionError("consultation interdite")),
              patch("builtins.open", side_effect=AssertionError("ouverture interdite")),
              patch("subprocess.run", side_effect=AssertionError("processus interdit"))):
            for split in ("OOS", "VAULT", "VAULT-F", None, "inconnu"):
                with self.subTest(split=split), self.assertRaises(data.DataError):
                    data.load("1h", split)
            with self.assertRaises(data.DataError):
                data._open_vault("1h")
            self.assertFalse(data._vault_authorised())

    def test_old_mixed_location_is_never_used(self):
        (self.proc / "BTCUSDT-1h.csv.gz").write_bytes(b"ancienne source interdite")
        with (patch.object(Path, "read_bytes", side_effect=AssertionError("ancien fichier lu")),
              self.assertRaisesRegex(data.DataError, "physiquement isole absent")):
            data.load()

    def test_fingerprint_is_of_exact_loaded_bytes_without_second_read(self):
        raw, csv = self.write(fixture())
        original_read = Path.read_bytes
        reads = []
        def read(path):
            reads.append(path)
            return original_read(path)
        with patch.object(Path, "read_bytes", read):
            loaded = data.load()
        self.assertEqual(reads, [self.path])
        self.assertEqual(data.data_fingerprint(loaded), hashlib.sha256(raw).hexdigest())
        self.assertEqual(loaded.attrs["csv_sha256"], hashlib.sha256(csv).hexdigest())
        self.path.write_bytes(b"remplacement apres le chargement")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("seconde lecture")):
            self.assertEqual(data.data_fingerprint(loaded), hashlib.sha256(raw).hexdigest())
        self.assertEqual(loaded.attrs["split"], "IS")
        self.assertEqual(loaded.attrs["data_bytes"], len(raw))

    def test_source_change_has_a_different_fingerprint(self):
        df = fixture()
        self.write(df)
        first = data.data_fingerprint(data.load())
        df.loc[0, "close"] = 100.5
        self.write(df)
        self.assertNotEqual(first, data.data_fingerprint(data.load()))

    def test_fingerprint_rejects_manifest_style_or_missing_provenance(self):
        for value in ("1h", fixture()):
            with self.subTest(kind=type(value).__name__), self.assertRaises(data.DataError):
                data.data_fingerprint(value)

    def test_every_row_must_be_inside_is_no_silent_filter(self):
        for start in ("2017-08-16", str(pd.Timestamp("2023-01-01") - pd.Timedelta(hours=499))):
            self.write(fixture(start=start))
            with self.subTest(start=start), self.assertRaisesRegex(data.DataError, "hors IS"):
                data.load()

    def test_unknown_interval_refuses_before_io(self):
        with (patch.object(Path, "is_symlink", side_effect=AssertionError("consultation interdite")),
              self.assertRaises(data.DataError)):
            data.load("../../arbitraire")

    def test_unordered_file_is_rejected_not_sorted(self):
        df = fixture().iloc[::-1]
        self.write(df)
        with self.assertRaisesRegex(data.DataError, "non croissants"):
            data.load()

    def test_naive_timestamp_is_not_assumed_utc(self):
        df = fixture()
        df["ts"] = df["ts"].dt.tz_localize(None).astype(str)
        self.write(df)
        with self.assertRaisesRegex(data.DataError, "fuseau explicite"):
            data.load()

    def test_short_or_corrupt_is_file_refuses(self):
        self.write(fixture(n=499))
        with self.assertRaisesRegex(data.DataError, "minimum requis"):
            data.load()
        self.path.write_bytes(b"pas un gzip")
        with self.assertRaises(data.DataError):
            data.load()

    def test_symlink_source_is_not_read(self):
        target = self.proc / "BTCUSDT-1h.csv.gz"
        target.write_bytes(b"source interdite")
        self.path.symlink_to(target)
        with (patch.object(Path, "read_bytes", side_effect=AssertionError("cible lue")),
              self.assertRaisesRegex(data.DataError, "lien symbolique")):
            data.load()

    def test_half_open_windows_do_not_share_the_boundary(self):
        for left, right, boundary in (("IS", "OOS", "2023-01-01"), ("OOS", "VAULT", "2025-09-01")):
            ts = pd.Series(pd.date_range(pd.Timestamp(boundary, tz="UTC") - pd.Timedelta(hours=1), periods=3, freq="h"))
            a, b = data._window_mask(ts, left), data._window_mask(ts, right)
            self.assertEqual(a.tolist(), [True, False, False])
            self.assertEqual(b.tolist(), [False, True, True])
            self.assertFalse((a & b).any())


class SanitySynthetic(unittest.TestCase):
    def test_finite_prices_and_volumes_are_required(self):
        for column in ("open", "high", "low", "close", "volume", "trades", "taker_buy_base", "quote_volume"):
            for value in (float("nan"), float("inf"), -float("inf")):
                df = fixture(n=3)
                df[column] = df[column].astype(float)
                df.loc[0, column] = value
                with self.subTest(column=column, value=value), self.assertRaises(data.DataError):
                    data._sanity(df, "1h")

    def test_open_and_close_both_have_to_lie_inside_high_low(self):
        for column, value in (("open", 103), ("open", 97), ("close", 103), ("close", 97), ("high", 90)):
            df = fixture(n=3)
            df.loc[0, column] = value
            with self.subTest(column=column, value=value), self.assertRaises(data.DataError):
                data._sanity(df, "1h")

    def test_negative_volumes_excess_taker_and_fractional_trades_refuse(self):
        for column, value in (("volume", -1), ("quote_volume", -1), ("taker_buy_base", -1), ("trades", -1), ("taker_buy_base", 11), ("trades", 1.5)):
            df = fixture(n=3)
            df[column] = df[column].astype(float)
            df.loc[0, column] = value
            with self.subTest(column=column, value=value), self.assertRaises(data.DataError):
                data._sanity(df, "1h")

    def test_empty_missing_nonnumeric_and_zero_price_refuse(self):
        cases = [fixture(n=0), fixture(n=3).drop(columns="volume")]
        text = fixture(n=3)
        text["volume"] = ["inconnu"] * 3
        cases.append(text)
        zero = fixture(n=3)
        zero.loc[0, "low"] = 0
        cases.append(zero)
        for i, df in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(data.DataError):
                data._sanity(df, "1h")

    def test_nat_naive_duplicates_gaps_and_nanosecond_misalignment_refuse(self):
        cases = []
        nat = fixture(n=3)
        nat.loc[0, "ts"] = pd.NaT
        cases.append(nat)
        naive = fixture(n=3)
        naive["ts"] = naive["ts"].dt.tz_localize(None)
        cases.append(naive)
        dup = fixture(n=3)
        dup.loc[1, "ts"] = dup.loc[0, "ts"]
        cases.append(dup)
        cases.append(fixture(n=4).drop(index=1))
        shifted = fixture(n=3)
        shifted["ts"] += pd.Timedelta(nanoseconds=1)
        cases.append(shifted)
        for i, df in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(data.DataError):
                data._sanity(df, "1h")

    def test_valid_zero_activity_bar_is_allowed(self):
        df = fixture(n=3)
        for c in ("volume", "trades", "taker_buy_base", "quote_volume"):
            df.loc[0, c] = 0
        data._sanity(df, "1h")
        self.assertEqual(df.attrs["gaps"], 0)

    def test_forward_return_refuses_wrong_horizon_and_masks_gaps(self):
        df = fixture(n=4)
        df["close"] = [100, 101, 102, 103]
        gap = df.drop(index=1).reset_index(drop=True)
        self.assertTrue(pd.isna(data.forward_return(gap, 1, "1h").iloc[0]))
        self.assertAlmostEqual(data.forward_return(gap, 1, "1h").iloc[1], 103 / 102 - 1)
        for k in (0, -1, True, 1.5):
            with self.subTest(k=k), self.assertRaises(data.DataError):
                data.forward_return(df, k, "1h")


class HistoryGateSynthetic(unittest.TestCase):
    """Snapshots Git simules et fichiers temporaires ; aucun commit ni reseau."""
    BASE = "a" * 40
    EVENT = "experiments/events/00000001-fixture.json"
    LEDGER = "experiments/ledger.json"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "experiments" / "events").mkdir(parents=True)
        self.snapshot = {self.LEDGER: b'{"total_configs": 12}\n', self.EVENT: b'{"fixture": "historique"}\n'}
        for path, payload in self.snapshot.items():
            (self.root / path).write_bytes(payload)

    def git(self, root, *args):
        self.assertEqual(root, self.root)
        if args == ("cat-file", "-t", self.BASE):
            return b"commit\n"
        if args[:3] == ("ls-tree", "-r", "--name-only"):
            return self.EVENT.encode() + b"\0"
        if args[0] == "show":
            path = args[1].split(":", 1)[1]
            if path not in self.snapshot:
                raise ci.HistoryError("element absent de la base")
            return self.snapshot[path]
        raise AssertionError(args)

    def test_append_preserves_all_base_bytes(self):
        (self.root / "experiments/events/00000002-fixture.json").write_bytes(b'{"nouveau": true}\n')
        with patch.object(ci, "_git", self.git):
            self.assertEqual(ci.verify_history(self.root, self.BASE), 1)

    def test_changed_ledger_is_rejected_even_if_count_increases(self):
        (self.root / self.LEDGER).write_bytes(b'{"total_configs": 999}\n')
        with patch.object(ci, "_git", self.git), self.assertRaises(ci.HistoryError):
            ci.verify_history(self.root, self.BASE)

    def test_changed_or_deleted_event_refuses_without_counter_change(self):
        for change in ("modify", "delete"):
            event = self.root / self.EVENT
            if change == "modify":
                event.write_bytes(b'{"fixture": "reecrite"}\n')
            else:
                event.unlink()
            with self.subTest(change=change), patch.object(ci, "_git", self.git), self.assertRaises(ci.HistoryError):
                ci.verify_history(self.root, self.BASE)

    def test_absent_or_null_base_never_falls_back(self):
        for base in (None, "", "HEAD~1", "0" * 40, "a" * 7):
            with (self.subTest(base=base), patch.object(ci, "_git", side_effect=AssertionError("Git ne doit pas etre appele")),
                  self.assertRaises(ci.HistoryError)):
                ci.verify_history(self.root, base)

    def test_missing_git_ancestor_is_failure(self):
        with patch.object(ci, "_git", side_effect=ci.HistoryError("base absente")), self.assertRaises(ci.HistoryError):
            ci.verify_history(self.root, self.BASE)

    def test_historical_ledger_absent_from_base_is_failure(self):
        del self.snapshot[self.LEDGER]
        with patch.object(ci, "_git", self.git), self.assertRaises(ci.HistoryError):
            ci.verify_history(self.root, self.BASE)


if __name__ == "__main__":
    unittest.main()
