"""Tes fungsi hitung dashboard dengan data kecil yang hasilnya dihitung manual.

Skenario Rungkut, minggu 28 Sep – 4 Okt 2026 (pajak 10%, tanpa service):
  B1 Sen 08:30 DINE IN   Nasi 2×40.000 + Teh 1×20.000        sub 100.000  GT 110.000  (F&B)
  B2 Sen 12:15 TAKE AWAY Sewa Raket 1×50.000                 sub  50.000  GT  55.000  (non-F&B)
  B8 Sen 13:00 Non Sales Teh 1×10.000                        sub  10.000  GT  11.000  (dikeluarkan)
  B3 Sel 18:00 DINE IN   Mie 1×30.000 + Raket 1×30.000       sub  60.000  GT  66.000  (campuran)
  Rab        tutup (tercakup unggahan, 0 bill)
  B4 Kam 19:30 DINE IN   Paket Catering 10×20.000            sub 200.000  GT 220.000  (F&B, 10 porsi)
  B5 Jum 10:00 DINE IN   WFA 1×29.000 + Nasi Rp0 + Teh Rp0   sub  29.000  GT  31.900  (F&B, 1 porsi)
  B6 Sab 06:30 ESB ORDER Nasi 1×40.000                       sub  40.000  GT  44.000  (F&B)
  B7 Min 21:30 GOFOOD    Kopi 1×30.000                       sub  30.000  GT  33.000  (F&B, 0 porsi)
"""
import math
from datetime import date
from decimal import Decimal

import pytest

from app import db
from app.hitung import dashboard, foot_traffic, overview
from app.hitung.data import muat
from app.hitung.kategori import kelompok, suhu
from app.hitung.minggu import bulan_penuh, label_tanggal, minggu_bulan, ringkas_tanggal
from app.parser.esb import baca_file_esb
from app.pengaturan_bawaan import KATEGORI, SUHU_PER_MENU
from app.validasi import validasi_unggahan
from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item

SEN, SEL, RAB, KAM, JUM, SAB, MIN = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30),
                                     date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4)]
NASI = {"kat": "FOOD", "detail": "BUBUR & NASI"}
TEH = {"kat": "BEVERAGE", "detail": "TEH"}
RAKET = {"kat": "AKSESORIS", "detail": "AKSESORIS BADMINTON"}


def _simpan(con, tmp_path, bills, items, awal, akhir, nama):
    fs = [baca_file_esb(buat_bill(tmp_path / f"{nama}b.xlsx", bills, awal=awal, akhir=akhir)),
          baca_file_esb(buat_cogs(tmp_path / f"{nama}c.xlsx", items, awal=awal, akhir=akhir))]
    lap = validasi_unggahan(fs, awal, akhir)
    assert not lap.terblokir and not lap.butuh_konfirmasi, [(c.nama, c.ringkasan) for c in lap.cek if c.status == "gagal"]
    db.simpan_unggahan(con, fs, lap, awal, akhir)


@pytest.fixture
def con(tmp_path):
    with db.koneksi(tmp_path / "h.duckdb") as c:
        bills = [
            bill("B1", SEN, "08:30:00", 100000), bill("B2", SEN, "12:15:00", 50000, vp="TAKE AWAY"),
            bill("B8", SEN, "13:00:00", 10000, tipe="Non Sales"),
            bill("B3", SEL, "18:00:00", 60000), bill("B4", KAM, "19:30:00", 200000),
            bill("B5", JUM, "10:00:00", 29000), bill("B6", SAB, "06:30:00", 40000, vp="ESB ORDER"),
            bill("B7", MIN, "21:30:00", 30000, vp="GOFOOD"),
        ]
        items = [
            item("B1", SEN, "Nasi Goreng", 2, 40000, 30000, **NASI), item("B1", SEN, "Teh Tarik Dingin", 1, 20000, 4000, **TEH),
            item("B2", SEN, "SEWA RAKET", 1, 50000, 0, **RAKET),
            item("B8", SEN, "Teh Tarik Dingin", 1, 10000, 4000, tipe="Non Sales", **TEH),
            item("B3", SEL, "Mie Goreng", 1, 30000, 10000, kat="FOOD", detail="MIE"),
            item("B3", SEL, "SEWA RAKET", 1, 30000, 0, **RAKET),
            item("B4", KAM, "Paket Catering", 10, 20000, 0, kat="FOOD", detail="SPESIAL MENU"),
            item("B5", JUM, "COMBO MEAL WFA SET C", 1, 29000, 0, kat="FOOD PROMO", detail="COMBO MEAL WFA"),
            item("B5", JUM, "Nasi Goreng", 1, 0, 15000, **NASI), item("B5", JUM, "Teh Tarik Dingin", 1, 0, 4000, **TEH),
            item("B6", SAB, "Nasi Goreng", 1, 40000, 15000, **NASI),
            item("B7", MIN, "Kopi Ampyang", 1, 30000, 5000, kat="BEVERAGE", detail="KOPI"),
        ]
        _simpan(c, tmp_path, bills, items, SEN, MIN, "cur")
        # Minggu sebelumnya, hanya 3 hari (parsial): Sen 21 – Rab 23 Sep.
        p = [date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)]
        _simpan(c, tmp_path,
                [bill("P1", p[0], "20:30:00", 100000), bill("P2", p[1], "20:30:00", 20000), bill("P3", p[2], "20:30:00", 40000)],
                [item("P1", p[0], "Nasi Goreng", 2, 50000, 30000, **NASI), item("P2", p[1], "Teh", 1, 20000, 4000, **TEH),
                 item("P3", p[2], "Nasi Goreng", 1, 40000, 15000, **NASI)], p[0], p[2], "prev")
        yield c


# ---------------------------------------------------------------- minggu & kategori

def test_minggu_oktober_2026():
    m = minggu_bulan(2026, 10)
    assert [(x.kode, x.awal, x.akhir) for x in m] == [
        ("M1", date(2026, 10, 5), date(2026, 10, 11)), ("M2", date(2026, 10, 12), date(2026, 10, 18)),
        ("M3", date(2026, 10, 19), date(2026, 10, 25)), ("M4", date(2026, 10, 26), date(2026, 11, 1))]
    assert m[3].label == "M4 · 26 Okt–1 Nov"
    assert bulan_penuh(2026, 10).awal == date(2026, 10, 1)


def test_minggu_lima_dan_label():
    m = minggu_bulan(2026, 6)  # Juni 2026: Senin 1, 8, 15, 22, 29
    assert [x.kode for x in m] == ["M1", "M2", "M3", "M4", "M5"]
    assert m[0].label == "M1 · 1–7 Jun"
    assert label_tanggal(date(2026, 11, 1), date(2026, 11, 1)) == "1 Nov"
    assert ringkas_tanggal([date(2026, 10, d) for d in (1, 2, 3, 5)]) == "1–3 Okt, 5 Okt"


@pytest.mark.parametrize("kat, detail, hasil", [
    ("FOOD", "BUBUR & NASI", "makanan_utama"), ("FOOD ", "MIE", "makanan_utama"),
    ("FOOD", "KUDAPAN", "kudapan"), ("FOOD", "TOAST", "toast"), ("FOOD PROMO", "COMBO MEAL WFA", "paket"),
    ("BEVERAGE", "TEH", "minuman"), ("SHOWCASE", "SHOWCASE", "minuman_kemasan"), ("ADD ON ", "ADD ON", "addon"),
    ("ZUPER FOOD", "ZUPER FOOD", "zuper_food"), ("JASA", "SEWA MEJA MAHJONG", "non_fnb"),
    ("AKSESORIS", "AKSESORIS BADMINTON", "non_fnb"), ("MERCHANDISE", "KAOS", "lainnya"),
])
def test_kelompok(kat, detail, hasil):
    assert kelompok(kat, detail, KATEGORI) == hasil


def test_suhu():
    assert suhu("Teh Tarik Dingin", SUHU_PER_MENU) == "dingin"
    assert suhu("Kopi O Panas", SUHU_PER_MENU) == "panas"
    assert suhu("Es Kopi Susu", SUHU_PER_MENU) == "dingin"
    assert suhu("Juice Jeruk", SUHU_PER_MENU) == "dingin"  # keputusan user 6 Okt 2026
    assert suhu("Soda Gembira", SUHU_PER_MENU) == "dingin"
    assert suhu("Wedang Jahe", SUHU_PER_MENU) == "panas"
    assert suhu("Lemon Tea", SUHU_PER_MENU) == "tidak_diketahui"


# ---------------------------------------------------------------- overview

def test_cakupan_hari(con):
    d = muat(con, "Rungkut", SEN, MIN)
    assert d.lengkap and d.tutup == [RAB] and len(d.hari_buka) == 6
    assert len(d.bill) == 7 and len(d.bill_semua) == 8


def test_kartu_overview(con):
    d = muat(con, "Rungkut", SEN, MIN)
    r = overview.ringkas(d)
    k = overview.kartu(d, r)
    assert Decimal(k["grand_total"]["nilai"]) == Decimal("559900")
    assert Decimal(k["subtotal"]["nilai"]) == Decimal("509000")
    assert k["jumlah_bill"]["teks"] == "7"
    # Bill F&B: B1, B4, B5, B6, B7 -> 438.900 / 5
    assert Decimal(k["rata_bill_fnb"]["nilai"]) == Decimal("87780")
    keluar = {x["alasan"][:24]: x["jumlah"] for x in k["rata_bill_fnb"]["asal"]["dikeluarkan"]}
    assert keluar == {"Sales Type bukan 'Sales'": 1, "Bill berisi item non-F&B": 1, "Bill campuran F&B + non-": 1}
    # 559.900 / 6 hari buka (Rabu tutup)
    assert k["omzet_per_hari_buka"]["teks"] == "Rp93.317"
    assert k["hari_terbaik"]["label"] == "Kamis 1 Okt" and k["hari_terbaik"]["teks"] == "Rp220.000"
    assert k["hari_terlemah"]["label"] == "Jumat 2 Okt" and k["hari_terlemah"]["teks"] == "Rp31.900"
    assert k["omzet_non_fnb"]["teks"] == "Rp80.000"  # 50.000 + 30.000, basis Subtotal


def test_rekonsiliasi_dan_harian(con):
    d = muat(con, "Rungkut", SEN, MIN)
    r = overview.rekonsiliasi(d)
    assert r["grand_total"] == "Rp559.900" and r["selisih_nol"]
    h = overview.harian(d, {"2026-10-01": "Libur uji"})
    assert [x["status"] for x in h] == ["buka", "buka", "tutup", "buka", "buka", "buka", "buka"]
    assert h[2]["grand_total"] == "0" and h[3]["libur"] == "Libur uji"


def test_tidak_ada_data_bukan_nol(con):
    d = muat(con, "Mawar", SEN, MIN)
    k = overview.kartu(d, overview.ringkas(d))
    assert k["grand_total"]["status"] == "tidak_diketahui"
    assert k["grand_total"]["teks"].startswith("Tidak diketahui — belum ada Bill + COGS Report Mawar")


def test_banding_per_hari_karena_minggu_lalu_parsial(con):
    d = muat(con, "Rungkut", SEN, MIN)
    p = muat(con, "Rungkut", date(2026, 9, 21), date(2026, 9, 27))
    assert not p.lengkap and len(p.hari_buka) == 3
    b = overview.banding(d, overview.ringkas(d), p, overview.ringkas(p), "uji")
    assert b["per_hari"]
    baris = {x["metrik"]: x for x in b["baris"]}
    # 559.900/6 = 93.316,67 vs 176.000/3 = 58.666,67
    assert baris["Grand Total per hari buka"]["sekarang"] == "Rp93.317"
    assert baris["Grand Total per hari buka"]["sebelumnya"] == "Rp58.667"
    assert baris["Grand Total per hari buka"]["selisih"]["arah"] == "naik"
    assert baris["Bill per hari buka"]["sekarang"] == "1,2"

    dek = b["dekomposisi"]
    o1, o0 = 438900 / 6, 176000 / 3
    n1, n0 = 5 / 6, 1.0
    a1, a0 = o1 / n1, o0 / n0
    kn = (o1 - o0) * math.log(n1 / n0) / math.log(o1 / o0)
    ka = (o1 - o0) * math.log(a1 / a0) / math.log(o1 / o0)
    rp = lambda v: ("+" if v > 0 else "−") + f"Rp{round(abs(v)):,}".replace(",", ".")
    assert dek["dari_jumlah_bill"]["teks"] == rp(kn)
    assert dek["dari_rata_bill"]["teks"] == rp(ka)
    assert abs((kn + ka) - (o1 - o0)) < 1e-6


def test_banding_tanpa_data_sebelumnya(con):
    d = muat(con, "Rungkut", date(2026, 9, 21), date(2026, 9, 27))
    p = muat(con, "Rungkut", date(2026, 9, 14), date(2026, 9, 20))
    b = overview.banding(d, overview.ringkas(d), p, overview.ringkas(p), "uji")
    assert not b["tersedia"] and "belum ada data" in b["alasan"]


# ---------------------------------------------------------------- foot traffic

def test_foot_traffic(con):
    f = foot_traffic.hitung(muat(con, "Rungkut", SEN, MIN))
    k = f["kartu"]
    assert k["bill_per_hari"]["teks"] == "1,2"            # 7 / 6
    assert k["orang_makan_per_hari"]["teks"] == "2,5"     # (2+1+10+1+1) / 6, porsi Rp0 di paket ikut
    assert k["porsi_per_bill"]["teks"] == "2,1"           # 15 / 7
    assert {r["porsi"]: r["bill"] for r in f["rombongan"]} == {"0": 2, "1": 3, "2": 1, "3": 0, "4+": 1}
    assert any("≥10 porsi" in c for c in f["catatan_rombongan"])
    j = {r["jendela"]: r for r in f["jendela"]}
    assert (j["Pagi"]["bill_hari_kerja"], j["Pagi"]["per_hari_kerja"]) == (2, "0,5")  # 4 hari kerja buka
    assert (j["Subuh"]["bill_akhir_pekan"], j["Larut"]["bill_akhir_pekan"]) == (1, 1)
    assert j["Malam"]["bill_hari_kerja"] == 2
    assert {r["hari"]: r["bill"] for r in f["per_hari"]}["Rabu"] == 0
    assert {r["channel"]: r["bill"] for r in f["channel"]} == {"DINE IN": 4, "TAKE AWAY": 1, "ESB ORDER": 1, "GOFOOD": 1}


# ---------------------------------------------------------------- dashboard utuh

def test_dashboard_bulanan_jembatan(con):
    h = dashboard.hitung(con, "Rungkut", 2026, 9, "bulan")
    assert [t["kode"] for t in h["tombol"]] == ["M1", "M2", "M3", "M4", "bulan"]
    kolom = {c["label"]: c for c in h["overview"]["bulanan"]["kolom"]}
    assert kolom["M4 · 28 Sep–4 Okt"]["Grand Total"] == "Rp559.900"
    assert kolom["M3 · 21–27 Sep"]["status"] == "parsial (3 hari)"
    j = {x["label"].split(" (")[0]: x for x in h["overview"]["bulanan"]["jembatan"]}
    # Σ minggu = 176.000 (M3) + 559.900 (M4); keluar 1–4 Okt = 220.000+31.900+44.000+33.000
    assert j["Σ minggu M1–M4"]["grand_total"] == "Rp735.900"
    assert j["− hari minggu ini yang jatuh di bulan lain"]["grand_total"] == "−Rp328.900"
    assert j["= Bulan Penuh"]["grand_total"] == "Rp407.000"
    assert h["overview"]["kartu"]["grand_total"]["teks"] == "Rp407.000"


def test_dashboard_mingguan(con):
    h = dashboard.hitung(con, "Rungkut", 2026, 9, "M4")
    assert h["periode"]["label"] == "M4 · 28 Sep–4 Okt" and h["periode"]["lengkap"]
    assert h["overview"]["banding"]["label"].startswith("Dibanding minggu sebelumnya")
    assert h["foot_traffic"]["banding"]["tersedia"]
    assert h["kualitas"]["baris_dikeluarkan"][0]["jumlah"] == 1
    assert not h["peringatan_merah"]
