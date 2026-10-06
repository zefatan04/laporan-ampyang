from datetime import date
from decimal import Decimal

import pandas as pd

from app.parser.esb import baca_file_esb
from app.validasi import (GAGAL, LULUS, PERINGATAN, TIDAK_BISA, cek_cabang_periode, cek_duplikat,
                          cek_footer, cek_kelengkapan, cek_salah_input, cek_silang, cek_tanpa_hpp,
                          nilai_hari_parsial, tandai_salah_input_cogs, validasi_unggahan)
from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item

AWAL, AKHIR = date(2026, 9, 1), date(2026, 9, 7)
T = [date(2026, 9, d) for d in range(1, 8)]


def _pasangan(tmp_path, bills=None, items=None, **kw):
    bills = bills or [bill("S1", T[0], sub=50000), bill("S2", T[1], sub=30000)]
    items = items or [item("S1", T[0], "Nasi Goreng", 2, 25000, 18000),
                      item("S2", T[1], "Kopi Susu", 2, 15000, 8000, kat="BEVERAGE", detail="KOPI")]
    b = baca_file_esb(buat_bill(tmp_path / "b.xlsx", bills, **kw))
    c = baca_file_esb(buat_cogs(tmp_path / "c.xlsx", items, **kw))
    return b, c


def test_cabang_periode_cocok(tmp_path):
    b, _ = _pasangan(tmp_path)
    assert cek_cabang_periode(b, "Rungkut", AWAL, AKHIR).status == LULUS


def test_cabang_salah(tmp_path):
    b, _ = _pasangan(tmp_path)
    assert cek_cabang_periode(b, "Mawar", AWAL, AKHIR).status == GAGAL


def test_periode_salah(tmp_path):
    b, _ = _pasangan(tmp_path)
    assert cek_cabang_periode(b, "Rungkut", AWAL, date(2026, 9, 6)).status == GAGAL


def test_footer_cocok_dan_tidak(tmp_path):
    b, _ = _pasangan(tmp_path)
    assert cek_footer(b).status == LULUS
    salah = baca_file_esb(buat_bill(tmp_path / "x.xlsx", [bill("S1", T[0], sub=50000)],
                                    footer={"Pax Total": 1, "Subtotal": Decimal("50002"),
                                            "Menu Discount": 0, "Bill Discount": 0,
                                            "Voucher Discount": 0, "Tax Total": 5000,
                                            "Grand Total": Decimal("55001")}))
    c = cek_footer(salah)
    assert c.status == GAGAL
    hasil = {r["Kolom"]: r["Hasil"] for r in c.rincian}
    assert hasil["Subtotal"] == "TIDAK COCOK"      # selisih Rp2
    assert hasil["Grand Total"] == "cocok"         # selisih Rp1 masih dalam toleransi


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


def test_silang_tanpa_cogs():
    assert cek_silang(None, None).status == TIDAK_BISA


def test_duplikat_sales_number(tmp_path):
    b, _ = _pasangan(tmp_path, bills=[bill("S1", T[0]), bill("S1", T[1])])
    assert cek_duplikat(b, "Rungkut", AWAL, AKHIR).status == GAGAL


def test_tumpang_tindih_periode(tmp_path):
    b, _ = _pasangan(tmp_path)
    tersimpan = [{"cabang": "Rungkut", "jenis": "bill", "awal": date(2026, 8, 25), "akhir": date(2026, 9, 1)},
                 {"cabang": "Mawar", "jenis": "bill", "awal": AWAL, "akhir": AKHIR}]
    c = cek_duplikat(b, "Rungkut", AWAL, AKHIR, tersimpan)
    assert c.status == GAGAL
    assert len([r for r in c.rincian if r["Jenis"] == "Periode tumpang tindih"]) == 1


def test_kelengkapan_hari_kosong(tmp_path):
    b, _ = _pasangan(tmp_path)
    c = cek_kelengkapan(b, "Rungkut", AWAL, AKHIR)
    assert c.status == PERINGATAN
    assert len([r for r in c.rincian if "tanpa transaksi" in r["Status"]]) == 5


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
    lap = validasi_unggahan([b, c], "Rungkut", AWAL, AKHIR)
    status = {(x.nomor, x.file): x.status for x in lap.cek}
    assert not lap.butuh_konfirmasi and not lap.terblokir
    assert all(v in (LULUS, PERINGATAN) for v in status.values())


def test_validasi_butuh_konfirmasi_bila_silang_gagal(tmp_path):
    b, c = _pasangan(tmp_path, items=[item("S1", T[0], "Nasi Goreng", 2, 25000, 18000)])
    lap = validasi_unggahan([b, c], "Rungkut", AWAL, AKHIR)
    assert lap.butuh_konfirmasi and not lap.terblokir


def test_validasi_cogs_tidak_ada_memblokir(tmp_path):
    b, _ = _pasangan(tmp_path)
    lap = validasi_unggahan([b], "Rungkut", AWAL, AKHIR)
    assert lap.terblokir
