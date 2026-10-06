"""Penyimpanan DuckDB.

Uang disimpan sebagai DECIMAL(18,6): ESB memakai pecahan sampai 4 desimal
dan penjumlahan harus sama persis dengan footer. Penanda turunan (salah
input resep, tanpa HPP, kategori) TIDAK disimpan; dihitung saat dibaca
supaya perubahan aturan di Pengaturan langsung berlaku ke data lama.

Satu unggahan = satu pasangan Bill + COGS untuk satu periode, boleh berisi
beberapa cabang. Tabel `periode` mencatat per cabang per jenis file, dan
itulah satuan yang ditampilkan di Riwayat serta yang bisa dihapus.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pyarrow as pa

from app.parser.esb import BILL, COGS, HasilBaca
from app.validasi import NAMA_HARI, LaporanValidasi, nilai_hari_parsial

AKAR = Path(__file__).resolve().parent.parent
DESIMAL = "DECIMAL(18,6)"

KOLOM_BILL = [
    ("sales_number", "VARCHAR"), ("bill_number", "VARCHAR"), ("sales_type", "VARCHAR"),
    ("sales_date", "DATE"), ("sales_in_date", "DATE"), ("sales_in_time", "VARCHAR"),
    ("sales_out_time", "VARCHAR"), ("visit_purpose", "VARCHAR"), ("table_name", "VARCHAR"),
    ("pax_total", DESIMAL), ("subtotal", DESIMAL), ("menu_discount", DESIMAL),
    ("bill_discount", DESIMAL), ("voucher_discount", DESIMAL), ("net_sales", DESIMAL),
    ("service_charge_total", DESIMAL), ("tax_total", DESIMAL), ("vat_total", DESIMAL),
    ("delivery_cost", DESIMAL), ("order_fee", DESIMAL), ("platform_fee", DESIMAL),
    ("voucher_sales_total", DESIMAL), ("rounding_total", DESIMAL), ("grand_total", DESIMAL),
    ("promotion", "VARCHAR"), ("cashier", "VARCHAR"),
]
KOLOM_COGS = [
    ("sales_number", "VARCHAR"), ("sales_date", "DATE"), ("sales_type", "VARCHAR"),
    ("menu", "VARCHAR"), ("menu_bersih", "VARCHAR"), ("menu_code", "VARCHAR"),
    ("menu_category", "VARCHAR"), ("menu_category_detail", "VARCHAR"),
    ("qty", DESIMAL), ("price", DESIMAL), ("total", DESIMAL), ("discount_total", DESIMAL),
    ("cogs_total", DESIMAL), ("cogs_total_pct", DESIMAL), ("margin", DESIMAL),
]

SKEMA = f"""
CREATE SEQUENCE IF NOT EXISTS seq_unggahan START 1;
CREATE TABLE IF NOT EXISTS unggahan (
    id INTEGER PRIMARY KEY,
    waktu TIMESTAMP NOT NULL,
    awal DATE NOT NULL,
    akhir DATE NOT NULL,
    file_bill VARCHAR,
    file_cogs VARCHAR,
    simpan_walau_tidak_cocok BOOLEAN NOT NULL,
    validasi JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS periode (
    unggahan_id INTEGER NOT NULL,
    cabang VARCHAR NOT NULL,
    jenis VARCHAR NOT NULL,          -- 'bill' | 'cogs'
    awal DATE NOT NULL,
    akhir DATE NOT NULL,
    jumlah_baris INTEGER NOT NULL,
    hari_tutup JSON NOT NULL,        -- daftar tanggal tanpa transaksi
    hari_parsial DATE,               -- dikeluarkan dari rata-rata harian
    rekonsiliasi_gagal BOOLEAN NOT NULL,
    PRIMARY KEY (unggahan_id, cabang, jenis)
);
CREATE TABLE IF NOT EXISTS esb_bill (
    unggahan_id INTEGER NOT NULL, cabang VARCHAR NOT NULL, baris_excel INTEGER NOT NULL,
    {", ".join(f"{k} {t}" for k, t in KOLOM_BILL)}
);
CREATE TABLE IF NOT EXISTS esb_cogs (
    unggahan_id INTEGER NOT NULL, cabang VARCHAR NOT NULL, baris_excel INTEGER NOT NULL,
    {", ".join(f"{k} {t}" for k, t in KOLOM_COGS)}
);
"""


def lokasi_db() -> Path:
    return Path(os.environ.get("AMPYANG_DB", AKAR / "data" / "ampyang.duckdb"))


@contextmanager
def koneksi(path: Path | None = None):
    path = Path(path or lokasi_db())
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute(SKEMA)
        yield con
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Tulis
# ---------------------------------------------------------------------------

def _tabel_arrow(df, kolom: list[tuple[str, str]], unggahan_id: int) -> pa.Table:
    data = {
        "unggahan_id": pa.array([unggahan_id] * len(df), pa.int32()),
        "cabang": pa.array(df["cabang"].tolist(), pa.string()),
        "baris_excel": pa.array(df["baris_excel"].astype(int).tolist(), pa.int32()),
    }
    for k, t in kolom:
        nilai = [None if v is None or (isinstance(v, float) and v != v) else v for v in df[k].tolist()]
        if t == DESIMAL:
            data[k] = pa.array([None if v is None else Decimal(v) for v in nilai], pa.decimal128(18, 6))
        elif t == "DATE":
            data[k] = pa.array(nilai, pa.date32())
        else:
            data[k] = pa.array([None if v is None else str(v) for v in nilai], pa.string())
    return pa.table(data)


def periode_tersimpan(con) -> list[dict]:
    rows = con.execute("SELECT unggahan_id, cabang, jenis, awal, akhir FROM periode").fetchall()
    return [dict(zip(("unggahan_id", "cabang", "jenis", "awal", "akhir"), r)) for r in rows]


def tumpang_tindih(con, cabang: set[str], awal: date, akhir: date) -> list[dict]:
    return [p for p in periode_tersimpan(con)
            if p["cabang"] in cabang and p["awal"] <= akhir and p["akhir"] >= awal]


class TidakBolehDisimpan(Exception):
    pass


def simpan_unggahan(con, files: list[HasilBaca], laporan: LaporanValidasi, awal: date, akhir: date,
                    ganti: bool = False, simpan_walau_tidak_cocok: bool = False) -> int:
    """Simpan satu unggahan. Semua aturan penyimpanan ditegakkan di sini,
    bukan hanya di tampilan, supaya tidak ada jalan pintas lewat API."""
    if laporan.terblokir:
        raise TidakBolehDisimpan("Validasi menunjukkan file wajib tidak lengkap atau cabang/periode salah.")
    if laporan.butuh_konfirmasi and not simpan_walau_tidak_cocok:
        raise TidakBolehDisimpan("Rekonsiliasi tidak cocok. Centang 'simpan walau tidak cocok' untuk tetap menyimpan.")
    bill = next(h for h in files if h.jenis is BILL and h.bisa_dipakai)
    cogs = next(h for h in files if h.jenis is COGS and h.bisa_dipakai)
    cabang = set(bill.data["cabang"].dropna()) | set(cogs.data["cabang"].dropna())

    con.execute("BEGIN TRANSACTION")
    try:
        lama = tumpang_tindih(con, cabang, awal, akhir)
        if lama and not ganti:
            raise TidakBolehDisimpan("Periode tumpang tindih dengan data tersimpan. Pilih 'ganti' untuk menimpa.")
        for p in {(p["unggahan_id"], p["cabang"]) for p in lama}:
            _hapus(con, *p)

        uid = con.execute("SELECT nextval('seq_unggahan')").fetchone()[0]
        con.execute("INSERT INTO unggahan VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [uid, datetime.now(), awal, akhir, bill.nama_file, cogs.nama_file,
                     laporan.butuh_konfirmasi, json.dumps([asdict(c) for c in laporan.cek], default=str)])
        for h, tabel, kolom in ((bill, "esb_bill", KOLOM_BILL), (cogs, "esb_cogs", KOLOM_COGS)):
            t = _tabel_arrow(h.data, kolom, uid)
            con.register("_baru", t)
            con.execute(f"INSERT INTO {tabel} SELECT * FROM _baru")
            con.unregister("_baru")

        gagal_rekon = laporan.butuh_konfirmasi
        semua = [awal + timedelta(days=i) for i in range((akhir - awal).days + 1)]
        for c in sorted(cabang):
            d = bill.data[(bill.data["cabang"] == c) & (bill.data["sales_type"] == "Sales")]
            per_hari = d.groupby("sales_date").size().to_dict()
            tutup = [t.isoformat() for t in semua if per_hari.get(t, 0) == 0]
            parsial = nilai_hari_parsial({t: per_hari.get(t, 0) for t in semua},
                                         d.groupby("sales_date")["sales_in_time"].max().to_dict(), c)
            for h in (bill, cogs):
                n = int((h.data["cabang"] == c).sum())
                con.execute("INSERT INTO periode VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [uid, c, h.jenis.kode, awal, akhir, n, json.dumps(tutup),
                             parsial["tanggal"] if parsial else None, gagal_rekon])
        con.execute("COMMIT")
        return uid
    except Exception:
        con.execute("ROLLBACK")
        raise


def _hapus(con, unggahan_id: int, cabang: str):
    for t in ("esb_bill", "esb_cogs", "periode"):
        con.execute(f"DELETE FROM {t} WHERE unggahan_id = ? AND cabang = ?", [unggahan_id, cabang])
    sisa = con.execute("SELECT count(*) FROM periode WHERE unggahan_id = ?", [unggahan_id]).fetchone()[0]
    if sisa == 0:
        con.execute("DELETE FROM unggahan WHERE id = ?", [unggahan_id])


def hapus_periode(con, unggahan_id: int, cabang: str) -> bool:
    ada = con.execute("SELECT count(*) FROM periode WHERE unggahan_id = ? AND cabang = ?",
                      [unggahan_id, cabang]).fetchone()[0]
    if not ada:
        return False
    con.execute("BEGIN TRANSACTION")
    try:
        _hapus(con, unggahan_id, cabang)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return True


# ---------------------------------------------------------------------------
# Riwayat
# ---------------------------------------------------------------------------

HIJAU, KUNING, MERAH = "lengkap", "sebagian", "tidak_ada"


def senin(t: date) -> date:
    return t - timedelta(days=t.weekday())


def riwayat(con, cabang_semua=("Rungkut", "Mawar")) -> dict:
    """Daftar periode tersimpan + status kelengkapan per minggu (Senin–Minggu).

    Status per minggu per cabang per jenis file:
      lengkap   7 hari tercakup, rekonsiliasi cocok
      sebagian  sebagian hari tercakup, atau disimpan walau rekonsiliasi gagal
      tidak_ada tidak ada data sama sekali
    Hari tutup (tanpa transaksi) tetap dihitung tercakup: datanya ada, isinya nol.
    """
    rows = con.execute("""
        SELECT p.unggahan_id, p.cabang, p.jenis, p.awal, p.akhir, p.jumlah_baris, p.hari_tutup,
               p.hari_parsial, p.rekonsiliasi_gagal, u.waktu, u.file_bill, u.file_cogs
        FROM periode p JOIN unggahan u ON u.id = p.unggahan_id
        ORDER BY p.awal DESC, p.cabang, p.jenis
    """).fetchall()
    kunci = ("unggahan_id", "cabang", "jenis", "awal", "akhir", "jumlah_baris", "hari_tutup",
             "hari_parsial", "rekonsiliasi_gagal", "waktu", "file_bill", "file_cogs")
    periode = [dict(zip(kunci, r)) for r in rows]
    for p in periode:
        p["hari_tutup"] = json.loads(p["hari_tutup"])

    minggu = []
    if periode:
        mulai = senin(min(p["awal"] for p in periode))
        selesai = senin(max(p["akhir"] for p in periode))
        m = selesai
        while m >= mulai:
            hari = [m + timedelta(days=i) for i in range(7)]
            sel = {}
            for c in cabang_semua:
                for j in ("bill", "cogs"):
                    cocok = [p for p in periode if p["cabang"] == c and p["jenis"] == j
                             and p["awal"] <= hari[-1] and p["akhir"] >= hari[0]]
                    tercakup = {t for t in hari for p in cocok if p["awal"] <= t <= p["akhir"]}
                    if not tercakup:
                        status, ket = MERAH, "tidak ada data"
                    elif len(tercakup) < 7 or any(p["rekonsiliasi_gagal"] for p in cocok):
                        status = KUNING
                        ket = [f"{len(tercakup)}/7 hari"]
                        if any(p["rekonsiliasi_gagal"] for p in cocok):
                            ket.append("rekonsiliasi tidak cocok")
                        ket = ", ".join(ket)
                    else:
                        status, ket = HIJAU, "7/7 hari"
                    tutup = sorted({t for p in cocok for t in p["hari_tutup"]
                                    if hari[0].isoformat() <= t <= hari[-1].isoformat()})
                    if tutup:
                        ket += " · tutup: " + ", ".join(
                            f"{NAMA_HARI[date.fromisoformat(t).weekday()]} {date.fromisoformat(t):%d/%m}" for t in tutup)
                    sel[f"{c}|{j}"] = {"status": status, "keterangan": ket}
            minggu.append({"senin": m, "minggu": hari[-1], "sel": sel})
            m -= timedelta(days=7)
    return {"periode": periode, "minggu": minggu, "cabang": list(cabang_semua)}
