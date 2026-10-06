"""Penyimpanan data loyalty Keluarga Ampyang (terpisah dari tabel ESB).

Data berkala (transaksi, klaim, rekap harian, log) disimpan per unggahan per
cabang, dengan periode di `periode_loyalty`. Rekap Pelanggan adalah potret
(snapshot) per tanggal ekspor; potret dengan cabang dan tanggal yang sama
diganti, potret tanggal lain disimpan berdampingan.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime

import pandas as pd
import pyarrow as pa

from app.db import TidakBolehDisimpan
from app.parser.loyalty import HADIAH, HARIAN, KLAIM, LOG, PELANGGAN, PROMO, TRANSAKSI, HasilLoyalty
from app.validasi_loyalty import BERKALA, butuh_konfirmasi, cabang_file, terblokir

D = "DECIMAL(18,2)"
TABEL = {
    TRANSAKSI: ("loy_transaksi", [("waktu", "TIMESTAMP"), ("nomor", "VARCHAR"), ("nominal", D), ("stempel", "INTEGER"),
                                  ("hangus", "INTEGER"), ("stempel_setelah", "INTEGER"), ("kasir", "VARCHAR")]),
    KLAIM: ("loy_klaim", [("waktu", "TIMESTAMP"), ("nomor", "VARCHAR"), ("tingkat", "INTEGER"), ("hadiah", "VARCHAR"),
                          ("status", "VARCHAR"), ("waktu_serah", "TIMESTAMP"), ("kasir_serah", "VARCHAR")]),
    HARIAN: ("loy_harian", [("tanggal", "DATE"), ("bill", "INTEGER"), ("stempel", "INTEGER"), ("omzet", D),
                            ("klaim_dibuat", "INTEGER"), ("hadiah_diserahkan", "INTEGER"),
                            ("member_baru_semua", "INTEGER"), ("login", "INTEGER"), ("member_baru_cabang", "INTEGER")]),
    LOG: ("loy_log", [("waktu", "TIMESTAMP"), ("kode", "VARCHAR"), ("nomor", "VARCHAR"), ("ip", "VARCHAR"),
                      ("keterangan", "VARCHAR")]),
    PELANGGAN: ("loy_pelanggan", [("nomor", "VARCHAR"), ("gabung", "DATE"), ("terverifikasi", "BOOLEAN"),
                                  ("stempel_kini", "INTEGER"), ("stempel_total", "INTEGER"), ("transaksi", "INTEGER"),
                                  ("belanja", D), ("terakhir", "DATE"), ("klaim", "INTEGER"), ("klaim_diambil", "INTEGER"),
                                  ("kasir_pendaftar", "VARCHAR"), ("cabang_pendaftaran", "VARCHAR")]),
}

SKEMA = "\n".join([
    "CREATE SEQUENCE IF NOT EXISTS seq_unggahan_loyalty START 1;",
    """CREATE TABLE IF NOT EXISTS unggahan_loyalty (id INTEGER PRIMARY KEY, waktu TIMESTAMP NOT NULL,
        awal DATE NOT NULL, akhir DATE NOT NULL, file JSON NOT NULL, validasi JSON NOT NULL,
        simpan_walau_tidak_cocok BOOLEAN NOT NULL);""",
    """CREATE TABLE IF NOT EXISTS periode_loyalty (unggahan_id INTEGER NOT NULL, cabang VARCHAR NOT NULL,
        awal DATE NOT NULL, akhir DATE NOT NULL, jenis JSON NOT NULL, rekonsiliasi_gagal BOOLEAN NOT NULL,
        PRIMARY KEY (unggahan_id, cabang));""",
    "CREATE TABLE IF NOT EXISTS loy_katalog (unggahan_id INTEGER NOT NULL, cabang VARCHAR, jenis VARCHAR NOT NULL, isi JSON NOT NULL);",
] + [
    f"CREATE TABLE IF NOT EXISTS {t} (unggahan_id INTEGER NOT NULL, cabang VARCHAR NOT NULL"
    + (", snapshot DATE NOT NULL" if j is PELANGGAN else "") + ", " + ", ".join(f"{k} {v}" for k, v in kol) + ");"
    for j, (t, kol) in TABEL.items()
])


def pastikan(con):
    con.execute(SKEMA)


def periode_tersimpan(con) -> list[dict]:
    pastikan(con)
    rows = con.execute("SELECT unggahan_id, cabang, awal, akhir FROM periode_loyalty").fetchall()
    return [dict(zip(("unggahan_id", "cabang", "awal", "akhir"), r)) for r in rows]


def _arrow(df: pd.DataFrame, kol: list[tuple[str, str]], uid: int, cabang: str, snapshot: date | None) -> pa.Table:
    n = len(df)
    data = {"unggahan_id": pa.array([uid] * n, pa.int32()), "cabang": pa.array([cabang] * n, pa.string())}
    if snapshot is not None:
        data["snapshot"] = pa.array([snapshot] * n, pa.date32())
    tipe = {"TIMESTAMP": pa.timestamp("us"), "DATE": pa.date32(), "INTEGER": pa.int64(), "VARCHAR": pa.string(),
            "BOOLEAN": pa.bool_(), D: pa.decimal128(18, 2)}
    for k, t in kol:
        v = [None if (x is None or (not isinstance(x, (str, bool)) and pd.isna(x))) else x for x in df[k].tolist()] if n else []
        data[k] = pa.array(v, tipe[t])
    return pa.table(data)


def _hapus_cabang(con, uid: int, cabang: str):
    for j, (t, _) in TABEL.items():
        if j is not PELANGGAN:
            con.execute(f"DELETE FROM {t} WHERE unggahan_id = ? AND cabang = ?", [uid, cabang])
    con.execute("DELETE FROM periode_loyalty WHERE unggahan_id = ? AND cabang = ?", [uid, cabang])
    sisa = con.execute("SELECT count(*) FROM periode_loyalty WHERE unggahan_id = ?", [uid]).fetchone()[0]
    sisa += con.execute("SELECT count(*) FROM loy_pelanggan WHERE unggahan_id = ?", [uid]).fetchone()[0]
    if not sisa:
        con.execute("DELETE FROM loy_katalog WHERE unggahan_id = ?", [uid])
        con.execute("DELETE FROM unggahan_loyalty WHERE id = ?", [uid])


def hapus_periode(con, uid: int, cabang: str) -> bool:
    pastikan(con)
    if not con.execute("SELECT count(*) FROM periode_loyalty WHERE unggahan_id = ? AND cabang = ?", [uid, cabang]).fetchone()[0]:
        return False
    con.execute("BEGIN TRANSACTION")
    try:
        _hapus_cabang(con, uid, cabang)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return True


def simpan(con, files: list[HasilLoyalty], cek: list, awal: date, akhir: date,
           ganti: bool = False, simpan_walau_tidak_cocok: bool = False) -> int:
    pastikan(con)
    if terblokir(cek):
        raise TidakBolehDisimpan("Validasi loyalty menunjukkan file tidak terbaca atau cabang/periode salah.")
    konfirmasi = butuh_konfirmasi(cek)
    if konfirmasi and not simpan_walau_tidak_cocok:
        raise TidakBolehDisimpan("Rekap Harian loyalty tidak cocok dengan riwayat. Centang 'simpan walau tidak cocok'.")
    pakai = [h for h in files if h.bisa_dipakai]
    cab_berkala = sorted({c for h in pakai if h.jenis in BERKALA for c in cabang_file(h)})

    con.execute("BEGIN TRANSACTION")
    try:
        lama = [p for p in periode_tersimpan(con) if p["cabang"] in cab_berkala and p["awal"] <= akhir and p["akhir"] >= awal]
        if lama and not ganti:
            raise TidakBolehDisimpan("Periode loyalty tumpang tindih dengan data tersimpan. Pilih 'ganti'.")
        for p in lama:
            _hapus_cabang(con, p["unggahan_id"], p["cabang"])

        uid = con.execute("SELECT nextval('seq_unggahan_loyalty')").fetchone()[0]
        con.execute("INSERT INTO unggahan_loyalty VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [uid, datetime.now(), awal, akhir, json.dumps([h.nama_file for h in pakai]),
                     json.dumps([asdict(c) for c in cek], default=str), konfirmasi])
        for h in pakai:
            if h.jenis in (HADIAH, PROMO):
                con.execute("INSERT INTO loy_katalog VALUES (?, ?, ?, ?)",
                            [uid, ", ".join(h.cabang), h.jenis.kode, json.dumps(h.data.to_dict("records"))])
                continue
            tabel, kol = TABEL[h.jenis]
            for c in cabang_file(h):
                df = h.data[h.data["cabang"] == c] if len(h.data) else h.data
                snap = (h.tanggal_snapshot or akhir) if h.jenis is PELANGGAN else None
                if h.jenis is PELANGGAN:
                    con.execute("DELETE FROM loy_pelanggan WHERE cabang = ? AND snapshot = ?", [c, snap])
                if len(df):
                    con.register("_baru", _arrow(df, kol, uid, c, snap))
                    con.execute(f"INSERT INTO {tabel} SELECT * FROM _baru")
                    con.unregister("_baru")
        for c in cab_berkala:
            jenis = sorted({h.jenis.kode for h in pakai if h.jenis in BERKALA and c in cabang_file(h)})
            con.execute("INSERT INTO periode_loyalty VALUES (?, ?, ?, ?, ?, ?)", [uid, c, awal, akhir, json.dumps(jenis), konfirmasi])
        con.execute("COMMIT")
        return uid
    except Exception:
        con.execute("ROLLBACK")
        raise


def riwayat(con) -> dict:
    pastikan(con)
    rows = con.execute("""SELECT p.unggahan_id, p.cabang, p.awal, p.akhir, p.jenis, p.rekonsiliasi_gagal, u.waktu
                          FROM periode_loyalty p JOIN unggahan_loyalty u ON u.id = p.unggahan_id
                          ORDER BY p.awal DESC, p.cabang""").fetchall()
    hasil = [dict(zip(("unggahan_id", "cabang", "awal", "akhir", "jenis", "rekonsiliasi_gagal", "waktu"), r)) for r in rows]
    for h in hasil:
        h["jenis"] = json.loads(h["jenis"])
    snap = con.execute("SELECT cabang, snapshot, count(*) FROM loy_pelanggan GROUP BY 1, 2 ORDER BY 2 DESC").fetchall()
    return {"periode": hasil, "snapshot": [{"cabang": c, "tanggal": t, "member": n} for c, t, n in snap]}
