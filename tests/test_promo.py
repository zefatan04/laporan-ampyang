"""Tes tab Promo dengan data 9 minggu buatan (Rungkut, 1 bill per hari, pajak 10%):

  31 Agu – 27 Sep  pembanding : Nasi Goreng 1×100.000 + Kopi Promo 1×10.000  → GT 121.000/hari
  28 Sep –  4 Okt  promo      : isi tergantung skenario
   5 Okt –  1 Nov  sesudah    : sama dengan pembanding
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app import db, pengaturan
from app.hitung import promo
from app.hitung.data import muat
from app.parser.esb import baca_file_esb
from app.validasi import validasi_unggahan
from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item

NASI = {"kat": "FOOD", "detail": "BUBUR & NASI"}
KOPI = {"kat": "BEVERAGE", "detail": "KOPI"}
TEH = {"kat": "BEVERAGE", "detail": "TEH"}
AWAL_A, MULAI, SELESAI, AKHIR_S = date(2026, 8, 31), date(2026, 9, 28), date(2026, 10, 4), date(2026, 11, 1)

NORMAL = [("Nasi Goreng", 1, 100000, NASI), ("Kopi Promo", 1, 10000, KOPI)]
SKENARIO = {
    "naik": [("Nasi Goreng", 1, 100000, NASI), ("Kopi Promo", 3, 10000, KOPI)],          # GT 143.000
    "sama": NORMAL,                                                                        # GT 121.000
    "kanibal": [("Kopi Promo", 3, 10000, KOPI), ("Teh Biasa", 1, 40000, TEH)],             # GT  77.000
}


def _unggah(con, tmp_path, a, z, isi, nama, promo_tag=None):
    bills, items = [], []
    t = a
    while t <= z:
        sn = f"{nama}{t:%m%d}"
        sub = sum(q * h for _, q, h, _ in isi)
        bills.append(bill(sn, t, "20:30:00", sub, Promotion=promo_tag))
        items += [item(sn, t, m, q, h, h * q // 3, **k) for m, q, h, k in isi]
        t += timedelta(days=1)
    fs = [baca_file_esb(buat_bill(tmp_path / f"{nama}b.xlsx", bills, awal=a, akhir=z)),
          baca_file_esb(buat_cogs(tmp_path / f"{nama}c.xlsx", items, awal=a, akhir=z))]
    lap = validasi_unggahan(fs, a, z)
    assert not lap.terblokir and not lap.butuh_konfirmasi, [(c.nama, c.ringkasan) for c in lap.cek if c.status == "gagal"]
    db.simpan_unggahan(con, fs, lap, a, z)


def _bangun(tmp_path, skenario, sesudah=True):
    con_cm = db.koneksi(tmp_path / f"{skenario}.duckdb")
    con = con_cm.__enter__()
    _unggah(con, tmp_path, AWAL_A, MULAI - timedelta(days=1), NORMAL, "A")
    _unggah(con, tmp_path, MULAI, SELESAI, SKENARIO[skenario], "P", promo_tag="PROMO KOPI, PROMO KOPI")
    if sesudah:
        _unggah(con, tmp_path, SELESAI + timedelta(days=1), AKHIR_S, NORMAL, "S")
    pengaturan.simpan(con, "promo", [{"nama": "Promo Kopi", "mulai": MULAI.isoformat(), "selesai": SELESAI.isoformat(),
                                      "cabang": "keduanya", "promotion_esb": ["Promo Kopi"], "menu_promo": ["kopi promo"]}])
    return con_cm, con


@pytest.fixture
def naik(tmp_path):
    cm, con = _bangun(tmp_path, "naik")
    yield con
    cm.__exit__(None, None, None)


def _eval(con):
    return promo.evaluasi(con, "Rungkut", pengaturan.ambil(con, "promo")[0], promo._libur(con))


def test_nama_promo():
    assert promo.nama_promo("PROMO A, PROMO A") == ["PROMO A"]
    assert promo.nama_promo("DISCOUNT 10 % ,  Promo B") == ["DISCOUNT 10 %", "Promo B"]
    assert promo.nama_promo(None) == []


def test_pembanding_hari_yang_sama():
    akt = {date(2026, 9, 28): {"x": Decimal(10)}, date(2026, 9, 29): {"x": Decimal(20)}}
    pb = {date(2026, 9, 21): {"x": Decimal(4)}, date(2026, 9, 14): {"x": Decimal(6)}}  # dua Senin, tanpa Selasa
    r = promo.banding_pembanding(akt, pb, "x")
    assert r["aktual"] == 10 and r["harapan"] == 5 and r["tanpa_pembanding"] == [date(2026, 9, 29)]
    assert r["persen"] == 100


def test_menambah_omzet(naik):
    e = _eval(naik)
    assert e["kesimpulan"]["label"] == "Menambah omzet"
    b = {r["metrik"]: r for r in e["banding"]}
    # 7 hari × 143.000 vs 7 × 121.000 → +18,2%, pembanding A dan B sama
    assert b["Omzet cabang (Grand Total)"]["A"] == "Rp1.001.000 vs pembanding Rp847.000 (+18,2%)"
    assert b["Omzet cabang (Grand Total)"]["B"] == b["Omzet cabang (Grand Total)"]["A"]
    assert b["Omzet menu promo (Total)"]["A"].endswith("(+200,0%)")
    assert b["Omzet menu non-promo (Total) — tanda kanibalisasi"]["A"].endswith("(±0,0%)")
    assert e["bill_promo"]["Bill memakai promo"] == "7" and e["bill_promo"]["Total diskon"] == "Rp0"
    assert e["rata_bill"]["selama"] == "Rp143.000" and e["rata_bill"]["sebelum"] == "Rp121.000"
    assert e["setelah"]["teks"].endswith("(±0,0%)")
    assert e["sampel_a"]["Senin"] == 4
    assert any("bukan bukti sebab-akibat" in a for a in e["kesimpulan"]["alasan"])


def test_netral(tmp_path):
    cm, con = _bangun(tmp_path, "sama")
    try:
        assert _eval(con)["kesimpulan"]["label"] == "Netral"
    finally:
        cm.__exit__(None, None, None)


def test_mengurangi_dan_kanibalisasi(tmp_path):
    cm, con = _bangun(tmp_path, "kanibal")
    try:
        k = _eval(con)["kesimpulan"]
        assert k["label"] == "Mengurangi omzet"  # 77.000 vs 121.000 = −36,4%
        assert any("Tanda kanibalisasi" in a for a in k["alasan"])
    finally:
        cm.__exit__(None, None, None)


def test_tanpa_data_sesudah_pakai_a_saja(tmp_path):
    cm, con = _bangun(tmp_path, "naik", sesudah=False)
    try:
        e = _eval(con)
        assert e["kesimpulan"]["label"] == "Menambah omzet"
        assert e["banding"][0]["B"].startswith("Tidak diketahui")
        assert e["setelah"]["teks"].startswith("Tidak diketahui")
    finally:
        cm.__exit__(None, None, None)


def test_hari_libur_dikeluarkan(naik):
    pengaturan.simpan(naik, "hari_libur", [{"tanggal": "2026-09-30", "nama": "Libur uji"},
                                           {"tanggal": "2026-09-23", "nama": "Libur uji"}])
    e = _eval(naik)
    assert e["hari_dibandingkan"] == 6 and e["libur_dikeluarkan"] == ["Rabu 30 Sep"]
    assert e["sampel_a"]["Rabu"] == 3


def test_belum_bisa_disimpulkan_tanpa_pembanding(tmp_path):
    with db.koneksi(tmp_path / "x.duckdb") as con:
        _unggah(con, tmp_path, MULAI, SELESAI, SKENARIO["naik"], "P")
        pengaturan.simpan(con, "promo", [{"nama": "Promo Kopi", "mulai": MULAI.isoformat(), "selesai": SELESAI.isoformat(),
                                          "cabang": "Rungkut", "promotion_esb": [], "menu_promo": []}])
        e = _eval(con)
        assert e["kesimpulan"]["label"] == "Belum bisa disimpulkan"
        assert "butuh minimal 14" in e["kesimpulan"]["alasan"][0]
        assert e["bill_promo"] is None and "belum diisi" in e["bill_promo_alasan"]


def test_promo_esb_dan_tampil_di_tab(naik):
    pengaturan.simpan(naik, "promotion_internal", [])
    d = muat(naik, "Rungkut", MULAI, SELESAI)
    h = promo.hitung(naik, d)
    r = h["esb"]["baris"][0]
    assert r["Promotion (ESB)"] == "PROMO KOPI" and r["Bill"] == 7 and r["Jenis"] == "promo: Promo Kopi"
    assert [p["nama"] for p in h["terdaftar"]] == ["Promo Kopi"]
    # Mawar tidak punya data; promo 'keduanya' tetap dievaluasi dan jujur soal kekosongan
    dm = muat(naik, "Mawar", MULAI, SELESAI)
    hm = promo.hitung(naik, dm)
    assert hm["terdaftar"][0]["kesimpulan"]["label"] == "Belum bisa disimpulkan"


def test_paket(tmp_path):
    with db.koneksi(tmp_path / "pk.duckdb") as con:
        t1, t2 = date(2026, 9, 28), date(2026, 9, 29)
        bills = [bill("B1", t1, "20:30:00", 29000), bill("B2", t2, "20:30:00", 44000), bill("B3", t2, "20:30:00", 15000)]
        items = [
            item("B1", t1, "COMBO MEAL WFA SET C", 1, 29000, 0, kat="FOOD PROMO", detail="COMBO MEAL WFA"),
            item("B1", t1, "Tahu Walik", 1, 0, 6000, kat="FOOD", detail="KUDAPAN"),
            item("B1", t1, "Teh Tarik Dingin", 1, 0, 4000, **TEH),
            item("B2", t2, "COMBO MEAL WFA SET C", 1, 29000, 0, kat="FOOD PROMO", detail="COMBO MEAL WFA"),
            item("B2", t2, "Tahu Walik", 1, 0, 6000, kat="FOOD", detail="KUDAPAN"),
            item("B2", t2, "Teh Tarik Dingin", 1, 0, 4000, **TEH),
            item("B2", t2, "Tahu Walik", 1, 15000, 6000, kat="FOOD", detail="KUDAPAN"),   # beli item lain + harga normal
            item("B3", t2, "Teh Tarik Dingin", 1, 15000, 4000, **TEH),                    # harga normal teh
        ]
        _a, _z = t1, t2
        fs = [baca_file_esb(buat_bill(tmp_path / "pb.xlsx", bills, awal=_a, akhir=_z)),
              baca_file_esb(buat_cogs(tmp_path / "pc.xlsx", items, awal=_a, akhir=_z))]
        db.simpan_unggahan(con, fs, validasi_unggahan(fs, _a, _z), _a, _z)
        p = promo.paket(con, muat(con, "Rungkut", t1, t2))
        r = p["baris"][0]
        assert r["Terjual"] == "2" and r["Harga paket"] == "Rp29.000"
        assert r["Harga normal isi (rata-rata)"] == "Rp30.000" and r["Hemat pelanggan per paket"] == "Rp1.000"
        assert r["HPP paket (rata-rata)"] == "Rp10.000" and r["Margin per paket (rata-rata)"] == "Rp19.000"
        assert r["Margin %"] == "65,5%" and r["Bill paket + item lain"] == "50,0%"
        assert p["paket_saja"] == 1 and p["paket_saja_per_hari"] == "0,5"
        assert p["isi"][0]["Isi (item Rp0)"] == "Tahu Walik + Teh Tarik Dingin" and p["isi"][0]["Bill"] == 2
