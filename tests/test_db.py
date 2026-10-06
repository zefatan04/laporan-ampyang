from datetime import date

import pytest

from app import db
from app.parser.esb import baca_file_esb
from app.validasi import validasi_unggahan
from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item

A, B = date(2026, 9, 28), date(2026, 10, 4)
T = [date(2026, 9, 28 + i) if i < 3 else date(2026, 10, i - 2) for i in range(7)]


@pytest.fixture
def con(tmp_path):
    with db.koneksi(tmp_path / "t.duckdb") as c:
        yield c


def _unggahan(tmp_path, bills, items, awal=A, akhir=B, cabang="Rungkut", nama="x"):
    fs = [baca_file_esb(buat_bill(tmp_path / f"{nama}b.xlsx", bills, cabang=cabang, awal=awal, akhir=akhir)),
          baca_file_esb(buat_cogs(tmp_path / f"{nama}c.xlsx", items, cabang=cabang, awal=awal, akhir=akhir))]
    return fs, validasi_unggahan(fs, awal, akhir)


def _seminggu(cabang="Rungkut", awalan="R"):
    bills = [bill(f"{awalan}{i}", t, sub=10000 * (i + 1), cabang=cabang, sc=3) for i, t in enumerate(T)]
    items = [item(f"{awalan}{i}", t, "Nasi", 1, 10000 * (i + 1), 4000, cabang=cabang) for i, t in enumerate(T)]
    return bills, items


def test_simpan_dan_jumlah_tepat(tmp_path, con):
    fs, lap = _unggahan(tmp_path, *_seminggu())
    uid = db.simpan_unggahan(con, fs, lap, A, B)
    sub, gt = con.execute("SELECT sum(subtotal), sum(grand_total) FROM esb_bill").fetchone()
    assert sub == 280000                     # 10.000 + ... + 70.000
    assert gt == fs[0].footer["Grand Total"]  # sama persis dengan footer, tanpa pembulatan
    assert con.execute("SELECT count(*) FROM esb_cogs WHERE unggahan_id = ?", [uid]).fetchone()[0] == 7
    r = db.riwayat(con)
    assert r["minggu"][0]["sel"]["Rungkut|bill"]["status"] == db.HIJAU
    assert r["minggu"][0]["sel"]["Mawar|bill"]["status"] == db.MERAH


def test_dua_cabang_satu_file(tmp_path, con):
    rb, ri = _seminggu("Rungkut", "R")
    mb, mi = _seminggu("Mawar", "M")
    fs, lap = _unggahan(tmp_path, rb + mb, ri + mi, cabang=["Mawar", "Rungkut"])
    uid = db.simpan_unggahan(con, fs, lap, A, B)
    per = con.execute("SELECT cabang, jenis FROM periode WHERE unggahan_id = ? ORDER BY 1, 2", [uid]).fetchall()
    assert per == [("Mawar", "bill"), ("Mawar", "cogs"), ("Rungkut", "bill"), ("Rungkut", "cogs")]
    assert db.hapus_periode(con, uid, "Mawar")
    assert con.execute("SELECT DISTINCT cabang FROM esb_bill").fetchall() == [("Rungkut",)]
    assert con.execute("SELECT count(*) FROM unggahan").fetchone()[0] == 1  # Rungkut masih ada


def test_hapus_cabang_terakhir_menghapus_unggahan(tmp_path, con):
    fs, lap = _unggahan(tmp_path, *_seminggu())
    uid = db.simpan_unggahan(con, fs, lap, A, B)
    db.hapus_periode(con, uid, "Rungkut")
    assert con.execute("SELECT count(*) FROM unggahan").fetchone()[0] == 0
    assert not db.hapus_periode(con, uid, "Rungkut")


def test_tumpang_tindih_ditolak_kecuali_ganti(tmp_path, con):
    fs, lap = _unggahan(tmp_path, *_seminggu())
    db.simpan_unggahan(con, fs, lap, A, B)
    with pytest.raises(db.TidakBolehDisimpan):
        db.simpan_unggahan(con, fs, lap, A, B)
    db.simpan_unggahan(con, fs, lap, A, B, ganti=True)
    assert con.execute("SELECT count(*) FROM esb_bill").fetchone()[0] == 7


def test_tidak_cocok_butuh_centang(tmp_path, con):
    bills, items = _seminggu()
    fs, lap = _unggahan(tmp_path, bills, items[:-1])
    assert lap.butuh_konfirmasi
    with pytest.raises(db.TidakBolehDisimpan):
        db.simpan_unggahan(con, fs, lap, A, B)
    db.simpan_unggahan(con, fs, lap, A, B, simpan_walau_tidak_cocok=True)
    r = db.riwayat(con)
    sel = r["minggu"][0]["sel"]["Rungkut|bill"]
    assert sel["status"] == db.KUNING and "rekonsiliasi" in sel["keterangan"]


def test_terblokir_tidak_bisa_disimpan(tmp_path, con):
    fs, lap = _unggahan(tmp_path, *_seminggu())
    lap2 = validasi_unggahan(fs, A, B, cabang=["Mawar"])
    with pytest.raises(db.TidakBolehDisimpan):
        db.simpan_unggahan(con, fs, lap2, A, B, ganti=True, simpan_walau_tidak_cocok=True)


def test_riwayat_minggu_sebagian_dan_hari_tutup(tmp_path, con):
    bills, items = _seminggu()
    # Data hanya Rabu-Minggu, dan Jumat tutup.
    awal = T[2]
    keep = [i for i in range(2, 7) if i != 4]
    fs, lap = _unggahan(tmp_path, [bills[i] for i in keep], [items[i] for i in keep], awal=awal)
    db.simpan_unggahan(con, fs, lap, awal, B)
    sel = db.riwayat(con)["minggu"][0]["sel"]["Rungkut|bill"]
    assert sel["status"] == db.KUNING
    assert sel["keterangan"].startswith("5/7 hari") and "Jumat 02/10" in sel["keterangan"]
