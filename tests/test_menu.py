"""Tes tab Makanan/Kudapan/Minuman. Hasil dihitung manual (lihat komentar).

Minggu lalu (21–27 Sep, lengkap: hari tanpa bill = tutup):
  Q1 Sen 21: Nasi Goreng 2×40.000 (HPP 30.000) · Teh Manis Dingin 1×15.000 (3.000) · Resoles 1×12.000 (5.000)
  Q2 Sel 22: Mie Ayam 1×30.000 (10.000) · Kopi O Panas 1×10.000 (2.000)
Minggu ini (28 Sep – 4 Okt):
  C1 Sen: Nasi Goreng 1×42.000 diskon 4.200 (HPP 15.000) · Teh Manis Dingin 2×15.000 (6.000)
  C2 Sel: Nasi Goreng 1×42.000 (HPP 100.000 → salah input) · Lemon Squash 1×18.000 (HPP 0)
  C3 Rab: COMBO WFA 1×29.000 + Resoles Rp0 (5.000) + Teh Manis Dingin Rp0 (3.000)
  C4 Kam: Sewa Raket 1×50.000 (non-F&B)
  C5 Jum: Pisang Goreng 2×10.000 (6.000) · Kopi O Panas 1×10.000 (2.000)
"""
from datetime import date
from decimal import Decimal

import pytest

from app import db, pengaturan
from app.hitung import menu
from app.hitung.data import muat
from app.parser.esb import baca_file_esb
from app.validasi import validasi_unggahan
from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item

D = lambda m, h: date(2026, m, h)
NASI = {"kat": "FOOD", "detail": "BUBUR & NASI"}
MIE = {"kat": "FOOD", "detail": "MIE"}
KUD = {"kat": "FOOD", "detail": "KUDAPAN"}
TEH = {"kat": "BEVERAGE", "detail": "TEH"}
KOPI = {"kat": "BEVERAGE", "detail": "KOPI"}
J = "20:30:00"


def _simpan(con, tmp_path, bills, items, awal, akhir, nama):
    fs = [baca_file_esb(buat_bill(tmp_path / f"{nama}b.xlsx", bills, awal=awal, akhir=akhir)),
          baca_file_esb(buat_cogs(tmp_path / f"{nama}c.xlsx", items, awal=awal, akhir=akhir))]
    lap = validasi_unggahan(fs, awal, akhir)
    assert not lap.terblokir and not lap.butuh_konfirmasi
    db.simpan_unggahan(con, fs, lap, awal, akhir)


@pytest.fixture
def con(tmp_path):
    with db.koneksi(tmp_path / "m.duckdb") as c:
        _simpan(c, tmp_path,
                [bill("Q1", D(9, 21), J, 107000), bill("Q2", D(9, 22), J, 40000)],
                [item("Q1", D(9, 21), "Nasi Goreng", 2, 40000, 30000, **NASI),
                 item("Q1", D(9, 21), "Teh Manis Dingin", 1, 15000, 3000, **TEH),
                 item("Q1", D(9, 21), "Resoles", 1, 12000, 5000, **KUD),
                 item("Q2", D(9, 22), "Mie Ayam", 1, 30000, 10000, **MIE),
                 item("Q2", D(9, 22), "Kopi O Panas", 1, 10000, 2000, **KOPI)],
                D(9, 21), D(9, 27), "p")
        _simpan(c, tmp_path,
                [bill("C1", D(9, 28), J, 72000, disk=4200), bill("C2", D(9, 29), J, 60000),
                 bill("C3", D(9, 30), J, 29000), bill("C4", D(10, 1), J, 50000), bill("C5", D(10, 2), J, 30000)],
                [item("C1", D(9, 28), "Nasi Goreng", 1, 42000, 15000, **NASI, **{"Discount Total": Decimal(4200)}),
                 item("C1", D(9, 28), "Teh Manis Dingin", 2, 15000, 6000, **TEH),
                 item("C2", D(9, 29), "Nasi Goreng", 1, 42000, 100000, **NASI),
                 item("C2", D(9, 29), "Lemon Squash", 1, 18000, 0, kat="BEVERAGE", detail="NUSANTARA"),
                 item("C3", D(9, 30), "COMBO MEAL WFA SET C", 1, 29000, 0, kat="FOOD PROMO", detail="COMBO MEAL WFA"),
                 item("C3", D(9, 30), "Resoles", 1, 0, 5000, **KUD),
                 item("C3", D(9, 30), "Teh Manis Dingin", 1, 0, 3000, **TEH),
                 item("C4", D(10, 1), "SEWA RAKET", 1, 50000, 0, kat="AKSESORIS", detail="AKSESORIS BADMINTON"),
                 item("C5", D(10, 2), "Pisang Goreng", 2, 10000, 6000, **KUD),
                 item("C5", D(10, 2), "Kopi O Panas", 1, 10000, 2000, **KOPI)],
                D(9, 28), D(10, 4), "c")
        yield c


def _hitung(con, tab):
    d, dp = muat(con, "Rungkut", D(9, 28), D(10, 4)), muat(con, "Rungkut", D(9, 21), D(9, 27))
    assert d.lengkap and dp.lengkap
    return menu.hitung(con, tab, d, dp, "uji")


def test_makanan(con):
    t = _hitung(con, "makanan")
    k = t["kartu"]
    assert k["omzet"]["teks"] == "Rp84.000" and k["omzet_bersih"]["teks"] == "Rp79.800" and k["qty"]["teks"] == "2"
    # Hanya C1 layak margin: (37.800 − 15.000) / 37.800 = 60,3%; cakupan 37.800 / 79.800 = 47,4%
    assert k["margin"]["teks"] == "60,3%" and k["margin"]["label"] == "mencakup 47,4% omzet"
    keluar = {x["alasan"]: x["jumlah"] for x in k["margin"]["asal"]["dikeluarkan"]}
    assert keluar == {"Salah input resep": 1}
    nasi = t["menu"][0]
    assert nasi["Menu"] == "Nasi Goreng" and nasi["Harga (modus)"] == "Rp42.000" and nasi["Margin %"] == "60,3%"
    assert "1 dari 2 baris" in nasi["Catatan"] and "salah input" in nasi["Catatan"]
    assert t["harga"]["baris"] == [{"Menu": "Nasi Goreng", "Harga sebelumnya": "Rp40.000",
                                    "Harga sekarang": "Rp42.000", "Selisih": "+Rp2.000"}]
    assert t["naik_turun"]["naik"][0]["Menu"] == "Nasi Goreng" and t["naik_turun"]["naik"][0]["Selisih omzet"] == "+Rp4.000"
    assert [r["Menu"] for r in t["baru_hilang"]["hilang"]["baris"]] == ["Mie Ayam"]
    assert t["baru_hilang"]["baru"]["baris"] == []


def test_kudapan_attach_dan_biaya_gratis(con):
    t = _hitung(con, "kudapan")
    assert t["kartu"]["omzet"]["teks"] == "Rp20.000" and t["kartu"]["margin"]["teks"] == "70,0%"
    assert t["kartu"]["biaya_gratis"]["teks"] == "Rp5.000" and t["kartu"]["biaya_gratis"]["label"] == "1 item gratis"
    a = t["attach"][0]
    # Basis bill F&B = C1, C2, C3, C5 (C4 hanya raket). Berbayar: C5. Termasuk paket: C3, C5.
    assert a["basis"] == 4 and a["berbayar"]["teks"] == "25,0%" and a["termasuk_paket"]["teks"] == "50,0%"
    assert [r["Menu"] for r in t["baru_hilang"]["baru"]["baris"]] == ["Pisang Goreng"]
    assert [r["Menu"] for r in t["baru_hilang"]["hilang"]["baris"]] == ["Resoles"]  # terjual berbayar minggu lalu saja


def test_minuman(con):
    t = _hitung(con, "minuman")
    k = t["kartu"]
    assert k["omzet"]["teks"] == "Rp58.000" and k["qty"]["teks"] == "4"
    assert k["margin"]["teks"] == "80,0%" and k["margin"]["label"] == "mencakup 69,0% omzet"
    assert k["omzet_tanpa_hpp"]["teks"] == "Rp18.000"
    assert k["biaya_gratis"]["teks"] == "Rp3.000"
    assert k["minuman_per_bill"]["teks"] == "1,0" and k["minuman_per_bill"]["label"] == "termasuk paket: 1,3"
    a = t["attach"][0]
    assert a["berbayar"]["teks"] == "75,0%" and a["termasuk_paket"]["teks"] == "100,0%"
    suhu = {r["Suhu"]: r["Porsi qty"] for r in t["suhu"]}
    assert suhu == {"Dingin": "50,0%", "Panas": "25,0%", "Tidak diketahui": "25,0%"}
    assert t["suhu_tidak_diketahui"] == ["Lemon Squash"]
    lemon = next(r for r in t["menu"] if r["Menu"] == "Lemon Squash")
    assert lemon["Margin"] == "Tidak diketahui — tanpa data HPP"
    b = {r["metrik"]: r for r in t["banding"]["baris"]}
    assert b["Omzet minuman"]["sebelumnya"] == "Rp25.000" and b["Omzet minuman"]["sekarang"] == "Rp58.000"


def test_menu_baru_dari_pengaturan(con):
    pengaturan.simpan(con, "menu_baru", [{"nama": "Pisang Goreng", "mulai": "2026-09-30", "tab": "kudapan"},
                                         {"nama": "Bakwan", "mulai": "2026-09-30", "tab": "kudapan"}])
    t = _hitung(con, "kudapan")
    r = {x["Menu"]: x for x in t["menu_baru_pengaturan"]}
    assert r["Pisang Goreng"]["Qty berbayar"] == "2" and r["Pisang Goreng"]["Omzet"] == "Rp20.000"
    assert "belum terjual" in r["Bakwan"]["Catatan"]


def test_tanpa_data(con):
    d, dp = muat(con, "Mawar", D(9, 28), D(10, 4)), muat(con, "Mawar", D(9, 21), D(9, 27))
    t = menu.hitung(con, "makanan", d, dp, "uji")
    assert not t["tersedia"] and t["kartu"]["omzet"]["status"] == "tidak_diketahui"
