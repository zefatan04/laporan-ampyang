from datetime import date
from decimal import Decimal

import pandas as pd

from app.parser.esb import baca_file_esb
from app.validasi import (GAGAL, LULUS, PERINGATAN, TIDAK_BISA, cek_cabang_periode, cek_duplikat,
                          cek_footer, cek_kelengkapan, cek_salah_input, cek_silang, cek_tanpa_hpp,
                          cek_terbaca, nilai_hari_parsial, tandai_salah_input_cogs, validasi_unggahan)
from tests.fixtures.buat_esb import FOOTER_BILL, bill, buat_bill, buat_cogs, footer_dari, item

AWAL, AKHIR = date(2026, 9, 1), date(2026, 9, 7)
T = [date(2026, 9, d) for d in range(1, 8)]


def _pasangan(tmp_path, bills=None, items=None, cogs_kw=None, **kw):
    bills = bills or [bill("S1", T[0], sub=50000), bill("S2", T[1], sub=30000)]
    items = items or [item("S1", T[0], "Nasi Goreng", 2, 25000, 18000),
                      item("S2", T[1], "Kopi Susu", 2, 15000, 8000, kat="BEVERAGE", detail="KOPI")]
    b = baca_file_esb(buat_bill(tmp_path / "b.xlsx", bills, **kw))
    c = baca_file_esb(buat_cogs(tmp_path / "c.xlsx", items, **(cogs_kw or kw)))
    return b, c


def test_cabang_periode_cocok(tmp_path):
    b, _ = _pasangan(tmp_path)
    assert cek_cabang_periode(b, AWAL, AKHIR).status == LULUS
    assert cek_cabang_periode(b, AWAL, AKHIR, ["Rungkut"]).status == LULUS


def test_cabang_salah(tmp_path):
    b, _ = _pasangan(tmp_path)
    assert cek_cabang_periode(b, AWAL, AKHIR, ["Mawar"]).status == GAGAL


def test_baris_cabang_di_luar_metadata(tmp_path):
    b, _ = _pasangan(tmp_path, bills=[bill("S1", T[0]), bill("S2", T[0], cabang="Mawar")])
    c = cek_cabang_periode(b, AWAL, AKHIR)
    assert c.status == GAGAL and any(r["Hasil"] == "ada cabang di luar metadata" for r in c.rincian)


def test_periode_salah(tmp_path):
    b, _ = _pasangan(tmp_path)
    assert cek_cabang_periode(b, AWAL, date(2026, 9, 6)).status == GAGAL


def test_non_sales_dicatat(tmp_path):
    b, _ = _pasangan(tmp_path, bills=[bill("S1", T[0]), bill("S2", T[0], tipe="Non Sales")])
    c = cek_terbaca(b)
    assert c.status == PERINGATAN and "Non Sales" in c.rincian[0]["Catatan"]


def test_footer_cocok_dan_tidak(tmp_path):
    b, _ = _pasangan(tmp_path)
    assert cek_footer(b).status == LULUS
    baris = [bill("S1", T[0], sub=50000)]
    f = footer_dari(baris, FOOTER_BILL)
    f["Subtotal"] += 2      # selisih Rp2: di luar toleransi
    f["Grand Total"] += 1   # selisih Rp1: masih dalam toleransi
    c = cek_footer(baca_file_esb(buat_bill(tmp_path / "x.xlsx", baris, footer=f)))
    assert c.status == GAGAL
    hasil = {r["Kolom"]: r["Hasil"] for r in c.rincian}
    assert hasil["Subtotal"] == "TIDAK COCOK"
    assert hasil["Grand Total"] == "cocok"


def test_footer_cogs_tidak_bisa(tmp_path):
    _, c = _pasangan(tmp_path)
    assert cek_footer(c).status == TIDAK_BISA


def test_silang_cocok(tmp_path):
    b, c = _pasangan(tmp_path)
    assert cek_silang(b, c).status == LULUS


def test_silang_tidak_cocok_menyebut_bill(tmp_path):
    b, c = _pasangan(tmp_path, items=[item("S1", T[0], "Nasi Goreng", 2, 25000, 18000),
                                      item("S3", T[1], "Kopi Susu", 1, 15000, 8000)])
    cek = cek_silang(b, c)
    assert cek.status == GAGAL
    nomor = {r.get("Sales Number") for r in cek.rincian}
    assert {"S2", "S3"} <= nomor


def test_silang_periode_beda_dirinci_per_tanggal(tmp_path):
    # Kasus nyata Okt 2026: Bill 28/9-4/10, COGS 27/9-3/10.
    bills = [bill("S1", T[1], sub=50000), bill("S2", T[2], sub=30000)]
    items = [item("S0", T[0], "Teh", 1, 10000, 2000), item("S1", T[1], "Nasi", 2, 25000, 9000)]
    b, c = _pasangan(tmp_path, bills=bills, items=items, awal=T[1], akhir=T[2],
                     cogs_kw={"awal": T[0], "akhir": T[1]})
    cek = cek_silang(b, c)
    assert cek.status == GAGAL
    assert "Periode Bill dan COGS berbeda" in cek.ringkasan
    hal = {r.get("Hal"): r for r in cek.rincian}
    assert hal["Periode export"]["Selisih"].startswith("BERBEDA")
    bersama = next(r for k, r in hal.items() if k and k.startswith("Hanya tanggal"))
    assert bersama["Selisih"] == "Rp0"
    assert not any("Sales Number" in r for r in cek.rincian)  # S0/S2 sudah dijelaskan oleh periode


def test_silang_tanpa_cogs():
    assert cek_silang(None, None).status == TIDAK_BISA


def test_duplikat_sales_number(tmp_path):
    b, _ = _pasangan(tmp_path, bills=[bill("S1", T[0]), bill("S1", T[1])])
    assert cek_duplikat(b, AWAL, AKHIR).status == GAGAL


def test_tumpang_tindih_periode(tmp_path):
    b, _ = _pasangan(tmp_path)
    tersimpan = [{"cabang": "Rungkut", "jenis": "bill", "awal": date(2026, 8, 25), "akhir": date(2026, 9, 1)},
                 {"cabang": "Mawar", "jenis": "bill", "awal": AWAL, "akhir": AKHIR}]
    c = cek_duplikat(b, AWAL, AKHIR, tersimpan)
    assert c.status == GAGAL
    assert len([r for r in c.rincian if r["Jenis"] == "Periode tumpang tindih"]) == 1


def test_kelengkapan_hari_per_cabang(tmp_path):
    b, _ = _pasangan(tmp_path, bills=[bill("S1", T[0]), bill("S2", T[1]), bill("S3", T[0], cabang="Mawar")],
                     cabang=["Mawar", "Rungkut"])
    c = cek_kelengkapan(b, AWAL, AKHIR)
    assert c.status == PERINGATAN
    assert len([r for r in c.rincian if r["Cabang"] == "Rungkut" and "tanpa transaksi" in r["Status"]]) == 5
    assert len([r for r in c.rincian if r["Cabang"] == "Mawar" and "tanpa transaksi" in r["Status"]]) == 6


def test_hari_parsial_karena_bill_sedikit():
    # Selasa 1 & 8 Sep: 40 bill. Selasa 15 Sep (terakhir): 10 bill -> < 50% x 40.
    per_hari = {date(2026, 9, 1): 40, date(2026, 9, 8): 40, date(2026, 9, 15): 10}
    jam = {t: "20:50" for t in per_hari}
    p = nilai_hari_parsial(per_hari, jam, "Rungkut")
    assert p["tanggal"] == date(2026, 9, 15)
    assert len(p["alasan"]) == 1


def test_hari_parsial_karena_jam():
    per_hari = {date(2026, 9, 1): 40, date(2026, 9, 8): 40}
    # Rungkut tutup 21:00, bill terakhir 13:00 -> 8 jam sebelum tutup.
    p = nilai_hari_parsial(per_hari, {date(2026, 9, 1): "20:50", date(2026, 9, 8): "13:00"}, "Rungkut")
    assert p is not None and "13:00" in p["alasan"][0]


def test_hari_lengkap_tidak_parsial():
    per_hari = {date(2026, 9, 1): 40, date(2026, 9, 8): 38}
    assert nilai_hari_parsial(per_hari, {t: "20:45" for t in per_hari}, "Rungkut") is None


def test_salah_input_cogs():
    df = pd.DataFrame([
        {"price": Decimal(10000), "qty": Decimal(2), "cogs_total": Decimal(30001)},  # 15.000,5/unit > 15.000
        {"price": Decimal(10000), "qty": Decimal(2), "cogs_total": Decimal(30000)},  # tepat 1,5x: tidak
        {"price": Decimal(0), "qty": Decimal(1), "cogs_total": Decimal(9000)},       # item gratis: tidak
        {"price": Decimal(10000), "qty": Decimal(0), "cogs_total": Decimal(9000)},   # qty 0: tidak dinilai
    ])
    assert tandai_salah_input_cogs(df).tolist() == [True, False, False, False]


def test_cek_salah_input_dan_tanpa_hpp(tmp_path):
    _, c = _pasangan(tmp_path, items=[
        item("S1", T[0], "Nasi Goreng", 1, 25000, 90000),
        item("S1", T[0], "Es Teh", 1, 25000, 0, kat="BEVERAGE", detail="TEH"),
        item("S2", T[1], "Kerupuk", 1, 0, 1000),
        item("S2", T[1], "Kopi", 1, 30000, 9000),
    ])
    s = cek_salah_input(c)
    assert s.status == PERINGATAN and s.rincian[0]["Menu"] == "Nasi Goreng"
    t = cek_tanpa_hpp(c)
    assert t.status == PERINGATAN and [r["Menu"] for r in t.rincian] == ["Es Teh"]


def test_validasi_gabungan_bersih(tmp_path):
    b, c = _pasangan(tmp_path)
    lap = validasi_unggahan([b, c], AWAL, AKHIR)
    assert not lap.butuh_konfirmasi and not lap.terblokir
    assert all(x.status in (LULUS, PERINGATAN, TIDAK_BISA) for x in lap.cek)


def test_validasi_butuh_konfirmasi_bila_silang_gagal(tmp_path):
    b, c = _pasangan(tmp_path, items=[item("S1", T[0], "Nasi Goreng", 2, 25000, 18000)])
    lap = validasi_unggahan([b, c], AWAL, AKHIR)
    assert lap.butuh_konfirmasi and not lap.terblokir


def test_validasi_cogs_tidak_ada_memblokir(tmp_path):
    b, _ = _pasangan(tmp_path)
    assert validasi_unggahan([b], AWAL, AKHIR).terblokir
