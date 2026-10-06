"""Laporan ESB opsional: Promotion, Sales Recapitulation Detail, Staff Sales & Cancel,
Cancel Menu Detail, Customer Data.

Data buatan, periode 28 Sep – 29 Sep 2026:
  R1  Rungkut 28 Sep  DINE IN    Nasi 2×50.000, diskon menu 10.000 "PROMO MENU"   bayar QRIS BCA   staf Aisha
  R2  Rungkut 29 Sep  ESB ORDER  Kopi 2×20.000                                    bayar QRIS (ESB ORDER)
  M1  Mawar   28 Sep  TAKE AWAY  Teh 2×15.000                                     bayar MEMBER DEPOSIT (10.000),CASH (23.000)
Pembatalan: Rungkut 28 Sep, Aisha membatalkan Es Teh 15.000.
"""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app import db, narasi
from app.hitung import dashboard, esb_opsional
from app.parser.esb import baca_file_esb
from app.validasi import LULUS, PERINGATAN, validasi_unggahan
from tests.fixtures.buat_esb import _tulis, bill, buat_bill, buat_cogs, footer_dari, item

A, Z = date(2026, 9, 28), date(2026, 9, 29)
SAMPEL = Path(__file__).resolve().parents[1] / "samples"

K_PROMO = ["Branch", "Sales Date", "Promotion Type", "Promotion Name", "Sales Number", "Original Price", "Special Price",
           "Member Code", "Member Name", "Menu Name", "Qty", "Discount Total", "Voucher Discount", "Bill Total"]
K_RECAP = ["Sales Number", "Bill Number", "Sales Type", "Sales Date", "Branch", "Visit Purpose", "Customer Name",
           "Payment Method", "Menu", "Order Mode", "Qty", "Subtotal", "Total", "Waiter"]
K_STAFF = ["User", "Branch", "Sales Qty", "Sales Total", "Cancel Qty", "Cancel Total", "Void Qty", "Void Total",
           "Remove Qty", "Remove Total"]
K_CANCEL = ["Sales Number", "Branch", "Menu", "Menu Code", "Menu Category", "Menu Category Detail", "Order By", "Order Time",
            "Cancel / Void By", "Cancel / Void Time", "Cancel / Void", "Cancel Notes", "Qty", "Subtotal", "Service Charge",
            "Tax", "Total"]
K_CUST = ["Order ID", "Sales Type", "Sales Number", "Full Name", "Email", "Phone Number"]
KD = ["Rungkut", "Mawar"]


def _bill_cogs(tmp):
    bills = [bill("R1", A, "12:00:00", 100000, disk=10000, Promotion="PROMO MENU, PROMO MENU"),
             bill("R2", Z, "20:30:00", 40000, vp="ESB ORDER"),
             bill("M1", A, "20:30:00", 30000, vp="TAKE AWAY", cabang="Mawar"),
             bill("M2", Z, "20:30:00", 30000, vp="TAKE AWAY", cabang="Mawar")]
    items = [item("R1", A, "Nasi", 2, 50000, 30000), item("R2", Z, "Kopi", 2, 20000, 8000, kat="BEVERAGE", detail="KOPI"),
             item("M1", A, "Teh", 2, 15000, 4000, kat="BEVERAGE", detail="TEH", cabang="Mawar"),
             item("M2", Z, "Teh", 2, 15000, 4000, kat="BEVERAGE", detail="TEH", cabang="Mawar")]
    items[0]["Discount Total"] = Decimal(10000)
    return [buat_bill(tmp / "b.xlsx", bills, cabang=KD, awal=A, akhir=Z), buat_cogs(tmp / "c.xlsx", items, cabang=KD, awal=A, akhir=Z)]


def _promo(tmp, ubah=None, cabang=("Rungkut",)):
    rows = [{"Branch": "Kedai Ampyang - Rungkut", "Sales Date": "2026-09-28 00:00:00", "Promotion Type": "MENU DISCOUNT(RP)",
             "Promotion Name": "PROMO MENU", "Sales Number": "R1", "Member Name": "Pelanggan Rahasia", "Menu Name": "Nasi",
             "Qty": 2.0, "Discount Total": 10000.0, "Voucher Discount": 0.0, "Bill Total": 99000.0}]
    footer = footer_dari(rows, ["Qty", "Discount Total", "Voucher Discount", "Bill Total"])
    if ubah:
        ubah(rows, footer)
    return _tulis(tmp / "promo.xlsx", "Promotion Report", K_PROMO, rows, footer, list(cabang), A, Z)


def _recap(tmp):
    rows = [{"Sales Number": "R1", "Bill Number": "B1", "Sales Type": "Sales", "Sales Date": "2026-09-28 00:00:00",
             "Branch": "Kedai Ampyang - Rungkut", "Visit Purpose": "DINE IN", "Customer Name": "Pelanggan Recap",
             "Payment Method": "QRIS BCA", "Menu": "Nasi", "Order Mode": "POS", "Qty": 2, "Subtotal": 100000.0, "Waiter": "Aisha"},
            {"Sales Number": "R2", "Bill Number": "B2", "Sales Type": "Sales", "Sales Date": "2026-09-29 00:00:00",
             "Branch": "Kedai Ampyang - Rungkut", "Visit Purpose": "ESB ORDER", "Payment Method": "QRIS (ESB ORDER)",
             "Menu": "Kopi", "Order Mode": "EZO QS", "Qty": 2, "Subtotal": 40000.0, "Waiter": "-"},
            {"Sales Number": "M1", "Bill Number": "B3", "Sales Type": "Sales", "Sales Date": "2026-09-28 00:00:00",
             "Branch": "Kedai Ampyang - Mawar", "Visit Purpose": "TAKE AWAY", "Payment Method": "MEMBER DEPOSIT (10.000),CASH (23.000)",
             "Menu": "Teh", "Order Mode": "POS", "Qty": 2, "Subtotal": 30000.0, "Waiter": "Budi"},
            {"Sales Number": "M2", "Bill Number": "B4", "Sales Type": "Sales", "Sales Date": "2026-09-29 00:00:00",
             "Branch": "Kedai Ampyang - Mawar", "Visit Purpose": "TAKE AWAY", "Payment Method": "CASH",
             "Menu": "Teh", "Order Mode": "POS", "Qty": 2, "Subtotal": 30000.0, "Waiter": "Budi"}]
    return _tulis(tmp / "recap.xlsx", "Sales Recapitulation Detail", K_RECAP, rows, None, KD, A, Z, baris_header=11,
                  label_bawah=[("Rounding Total", "0"), ("Platform Fee Total", None)])


def _staff(tmp, total_aisha=100000.0):
    rows = [{"User": "Aisha", "Branch": "Kedai Ampyang - Rungkut", "Sales Qty": 2, "Sales Total": total_aisha, "Cancel Qty": 0,
             "Cancel Total": 0, "Void Qty": 0, "Void Total": 0, "Remove Qty": 1, "Remove Total": 5000},
            {"User": "Aisha", "Branch": "Kedai Ampyang - Rungkut", "Sales Qty": 0, "Sales Total": 0, "Cancel Qty": 1,
             "Cancel Total": 15000, "Void Qty": 0, "Void Total": 0, "Remove Qty": 0, "Remove Total": 0},
            {"User": "-", "Branch": "Kedai Ampyang - Rungkut", "Sales Qty": 2, "Sales Total": 40000, "Cancel Qty": 0,
             "Cancel Total": 0, "Void Qty": 0, "Void Total": 0, "Remove Qty": 0, "Remove Total": 0},
            {"User": "Budi", "Branch": "Kedai Ampyang - Mawar", "Sales Qty": 4, "Sales Total": 60000, "Cancel Qty": 0,
             "Cancel Total": 0, "Void Qty": 0, "Void Total": 0, "Remove Qty": 0, "Remove Total": 0}]
    return _tulis(tmp / "staff.xlsx", "Staff Sales & Cancel Report", K_STAFF, rows, None, KD, A, Z, baris_header=12, sales_type="Sales")


def _cancel(tmp):
    rows = [{"Sales Number": "R9", "Branch": "Kedai Ampyang - Rungkut", "Menu": "Es Teh", "Menu Category": "BEVERAGE",
             "Menu Category Detail": "TEH", "Order By": "Aisha", "Order Time": "2026-09-28 17:16:15", "Cancel / Void By": "Aisha",
             "Cancel / Void Time": "2026-09-28 17:27:46", "Cancel / Void": "Cancel", "Cancel Notes": "SALAH INPUT - kasus Bu Rahasia",
             "Qty": 1, "Subtotal": 15000, "Total": 16500}]
    return _tulis(tmp / "cancel.xlsx", "Cancel Menu Detail Report", K_CANCEL, rows, None, KD, A, Z, baris_header=12)


def _customer(tmp, tambah=None):
    rows = [{"Order ID": "O1", "Sales Type": "Dine In (Quick service)", "Sales Number": "R2", "Full Name": "Nama Rahasia",
             "Email": "rahasia@contoh.id", "Phone Number": "081234567890"},
            {"Order ID": "O2", "Sales Type": "Dine In (Quick service)", "Sales Number": "LAMA1", "Full Name": "Lama",
             "Email": "-", "Phone Number": "081111"},
            {"Order ID": "O3", "Sales Type": "Dine In (Quick service)", "Sales Number": None, "Full Name": "Tanpa Nomor",
             "Email": "-", "Phone Number": "-"}] + (tambah or [])
    return _tulis(tmp / "cust.xlsx", "Customer Data Report", K_CUST, rows, None, KD, date(2026, 10, 1), date(2026, 10, 6), baris_header=10)


def _semua(tmp):
    return _bill_cogs(tmp) + [_promo(tmp), _recap(tmp), _staff(tmp), _cancel(tmp), _customer(tmp)]


def _lap(paths):
    fs = [baca_file_esb(p) for p in paths]
    return fs, validasi_unggahan(fs, A, Z)


def _cek(lap, nomor):
    return next(c for c in lap.cek if c.nomor == nomor)


# ---------------------------------------------------------------- parser & privasi

def test_parser_kelima_laporan_dan_tanpa_data_pribadi(tmp_path):
    fs = [baca_file_esb(p) for p in _semua(tmp_path)[2:]]
    assert [h.jenis.kode for h in fs] == ["promotion", "recap_detail", "staff", "cancel", "customer"]
    assert all(not h.galat for h in fs), [(h.nama_file, h.galat) for h in fs]
    teks = json.dumps([h.data.astype(str).to_dict("records") for h in fs])
    # Catatan pembatalan sengaja disimpan (ditampilkan di aplikasi, tidak dikirim ke Claude).
    for rahasia in ("Pelanggan Rahasia", "Nama Rahasia", "rahasia@contoh.id", "081234567890", "Pelanggan Recap"):
        assert rahasia not in teks
    cust = fs[4]
    assert len(cust.data) == 2 and cust.data["telp"].iloc[0] != "081234567890"
    assert fs[1].footer_label == {"Rounding Total": "0", "Platform Fee Total": None}


def test_pesan_galat_customer_tidak_menampilkan_isi_baris(tmp_path):
    p = _customer(tmp_path, tambah=[{"Order ID": "O9", "Sales Type": None, "Sales Number": "X", "Full Name": "Budi Rahasia",
                                     "Email": "budi@rahasia.id", "Phone Number": "0899"}, {"Order ID": "O10", "Sales Type": "Dine In"}])
    h = baca_file_esb(p)
    teks = " ".join(c.pesan for c in h.galat + h.peringatan)
    assert h.galat and "Budi Rahasia" not in teks and "budi@rahasia.id" not in teks and "data pribadi" in teks


# ---------------------------------------------------------------- validasi

def test_semua_cocok_disimpan_dan_tidak_menghalangi(tmp_path):
    fs, lap = _lap(_semua(tmp_path))
    assert not lap.terblokir and not lap.butuh_konfirmasi
    assert _cek(lap, 30).status == PERINGATAN  # Mawar tidak ada di Promotion Report
    assert all(_cek(lap, n).status == LULUS for n in (31, 32, 33)), [(_cek(lap, n).ringkasan) for n in (31, 32, 33)]
    s = lap.opsional.simpan
    assert set(s["promotion"]) == {"Rungkut"} and set(s["recap_detail"]) == set(s["staff"]) == {"Rungkut", "Mawar"}
    assert set(s["cancel"]) == {"Rungkut", "Mawar"} and len(s["cancel"]["Mawar"]) == 0
    assert len(s["customer"]["Rungkut"]) == 1 and len(s["customer"]["Mawar"]) == 0


def test_tidak_cocok_tidak_disimpan(tmp_path):
    p = _bill_cogs(tmp_path) + [_staff(tmp_path, total_aisha=99000.0),
                                _promo(tmp_path, ubah=lambda rows, f: f.update({"Discount Total": Decimal(1)}))]
    _, lap = _lap(p)
    assert not lap.terblokir
    assert set(lap.opsional.simpan["staff"]) == {"Mawar"}  # dicocokkan per cabang: Rungkut beda, Mawar cocok
    assert "promotion" not in lap.opsional.simpan
    assert _cek(lap, 32).status == PERINGATAN and _cek(lap, 30).status == PERINGATAN
    # pembatalan tanpa Staff Report yang cocok tetap disimpan, dengan catatan tidak bisa dicek silang
    _, lap = _lap(_bill_cogs(tmp_path) + [_cancel(tmp_path)])
    assert "Rungkut" in lap.opsional.simpan["cancel"]


def test_promo_beda_diskon_dengan_bill_report(tmp_path):
    def ubah(rows, footer):
        rows[0]["Discount Total"] = 9000.0
        footer["Discount Total"] = Decimal(9000)
    _, lap = _lap(_bill_cogs(tmp_path) + [_promo(tmp_path, ubah=ubah)])
    assert "promotion" not in lap.opsional.simpan
    assert any("tidak cocok" in r["Hasil"] for r in _cek(lap, 30).rincian)


def test_laporan_opsional_rusak_tidak_menghalangi(tmp_path):
    rusak = _tulis(tmp_path / "staff-rusak.xlsx", "Staff", ["User", "Sales Qty", "Cancel Qty", "Void Qty"],
                   [{"User": "Aisha", "Sales Qty": "abc", "Cancel Qty": 0, "Void Qty": 0}], None, KD, A, Z, baris_header=12)
    fs, lap = _lap(_bill_cogs(tmp_path) + [rusak])
    assert not lap.terblokir
    assert any(c.nomor == 0 and c.file == "staff-rusak.xlsx" and c.status == PERINGATAN for c in lap.cek)


# ---------------------------------------------------------------- dashboard

@pytest.fixture
def con(tmp_path):
    fs, lap = _lap(_semua(tmp_path))
    with db.koneksi(tmp_path / "o.duckdb") as c:
        db.simpan_unggahan(c, fs, lap, A, Z)
        yield c


def test_bagian_dashboard(con):
    d = dashboard.hitung(con, "Rungkut", 2026, 9, "M4")  # 28 Sep – 4 Okt; data 28–29 Sep
    o = d["overview"]
    assert [r["Metode bayar"] for r in o["metode_bayar"]["baris"]] == ["QRIS BCA", "QRIS (ESB ORDER)"]
    assert o["metode_bayar"]["cakupan"].startswith("dari 2 dari 7 hari")
    # Staff Report 28–29 Sep ada di dalam minggu ini
    staf = {r["Staf pencatat pesanan"]: r for r in o["staf"]["baris"]}
    assert staf["Aisha"]["Cancel"] == "1 item · Rp15.000" and "(ESB ORDER, tanpa staf)" in staf
    assert o["pembatalan"]["baris"][0]["Dibatalkan oleh"] == "Aisha"
    rp = d["promo"]["rincian_esb"]["baris"][0]
    assert rp["Promo (Promotion Report)"] == "PROMO MENU" and rp["Menu yang didiskon (qty)"] == "Nasi (2)"
    pel = {r["Hal"]: r["Nilai"] for r in d["membership"]["customer_data_esb"]["kartu"]}
    assert pel["Bill ESB ORDER di periode ini"] == "1" and pel["Nomor telepon unik"] == "1"
    m = dashboard.hitung(con, "Mawar", 2026, 9, "M4")
    assert m["overview"]["metode_bayar"]["baris"][0]["Metode bayar"] in ("CASH", "Kombinasi: MEMBER DEPOSIT + CASH")
    assert not m["promo"]["rincian_esb"]["tersedia"]
    ku = {f["file"]: f["status"] for f in m["kualitas"]["file"]}
    assert ku["Promotion Report (opsional)"] == "tidak ada" and ku["Staff Sales & Cancel Report (opsional)"] == "ada"


def test_staf_tidak_dipecah_lintas_periode(con):
    # Bulan Penuh Oktober: export 28–29 Sep tidak masuk; Sep bulan: masuk (di dalam September)
    assert not dashboard.hitung(con, "Rungkut", 2026, 10, "bulan")["overview"]["staf"]["tersedia"]
    assert dashboard.hitung(con, "Rungkut", 2026, 9, "bulan")["overview"]["staf"]["tersedia"]


def test_paket_claude_tanpa_nama_staf_dan_catatan(con):
    d = dashboard.hitung(con, "Rungkut", 2026, 9, "M4")
    d["narasi"] = {"aktif": False, "tab": {}}
    p = narasi.paket(d)
    assert "Aisha" not in p and "Bu Rahasia" not in p
    assert "QRIS BCA" in p  # metode bayar tetap ikut


def test_metode_bayar_kombinasi():
    assert esb_opsional.metode_bayar_bersih("MEMBER DEPOSIT (200.000),QRIS BCA (441.022)") == "Kombinasi: MEMBER DEPOSIT + QRIS BCA"
    assert esb_opsional.metode_bayar_bersih("QRIS (ESB ORDER)") == "QRIS (ESB ORDER)"


# ---------------------------------------------------------------- file asli

@pytest.mark.skipif(not (SAMPEL / "esb-opsional").exists(), reason="file asli tidak ada (tidak masuk git)")
def test_sampel_asli_cocok_dengan_bill_cogs():
    utama = sorted((SAMPEL / "2026-09-28_2026-10-04").glob("*.xlsx"))
    ops = sorted((SAMPEL / "esb-opsional").glob("*.xlsx"))
    fs = [baca_file_esb(p) for p in utama + ops]
    lap = validasi_unggahan(fs, date(2026, 9, 28), date(2026, 10, 4))
    assert not lap.terblokir
    s = lap.opsional.simpan
    assert set(s["promotion"]) == {"Rungkut"}  # export Promotion Report asli tidak memuat Mawar
    assert set(s["recap_detail"]) == set(s["staff"]) == set(s["cancel"]) == {"Rungkut", "Mawar"}
    assert len(s["customer"]["Rungkut"]) == 103
