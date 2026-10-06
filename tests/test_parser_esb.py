from datetime import date
from decimal import Decimal

import openpyxl

from app.parser.esb import BILL, COGS, baca_file_esb, bersihkan_nama_menu
from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item

T1, T2 = date(2026, 9, 1), date(2026, 9, 2)


def test_bill_terbaca(tmp_path):
    p = buat_bill(tmp_path / "b.xlsx", [bill("S1", T1, sub=50000), bill("S2", T2, sub=30000, pax=3)])
    h = baca_file_esb(p)
    assert h.jenis is BILL
    assert h.galat == []
    assert h.baris_header == 13
    assert h.periode == (date(2026, 9, 1), date(2026, 9, 7))
    assert h.cabang == "Kedai Ampyang Rungkut"
    assert list(h.data["sales_number"]) == ["S1", "S2"]
    assert h.data["subtotal"].tolist() == [Decimal("50000.00"), Decimal("30000.00")]
    assert h.data["sales_date"].tolist() == [T1, T2]
    assert h.footer["Grand Total"] == Decimal("88000.00")
    assert h.footer["Pax Total"] == Decimal(4)
    assert h.baris_footer == 16


def test_header_pindah_baris_jadi_peringatan(tmp_path):
    p = buat_bill(tmp_path / "b.xlsx", [bill("S1", T1)], baris_header=11)
    h = baca_file_esb(p)
    assert h.galat == []
    assert h.baris_header == 11
    assert any("baris 11" in c.pesan for c in h.peringatan)


def test_cogs_nama_menu_dibersihkan(tmp_path):
    p = buat_cogs(tmp_path / "c.xlsx", [item("S1", T1, "Nasi  Goreng  Jawa ", 1, 25000, 9000)])
    h = baca_file_esb(p)
    assert h.jenis is COGS
    assert h.data["menu_bersih"].tolist() == ["Nasi Goreng Jawa"]
    assert bersihkan_nama_menu("  Es   Teh ") == "Es Teh"


def test_jenis_dikenali_dari_isi_bukan_nama(tmp_path):
    p = buat_cogs(tmp_path / "bill-report.xlsx", [item("S1", T1, "Kopi", 1, 10000, 3000)])
    assert baca_file_esb(p).jenis is COGS


def test_file_asing_ditolak(tmp_path):
    p = tmp_path / "x.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["Nama", "Alamat"])
    wb.save(p)
    h = baca_file_esb(p)
    assert h.jenis is None and h.galat


def test_kolom_wajib_hilang(tmp_path):
    p = buat_bill(tmp_path / "b.xlsx", [bill("S1", T1)])
    wb = openpyxl.load_workbook(p)
    wb.active.cell(13, 9, "Sub Total")  # kolom Subtotal diganti nama
    wb.save(p)
    h = baca_file_esb(p)
    assert h.kolom_hilang == ["Subtotal"]
    assert not h.bisa_dipakai


def test_baris_tanpa_id_di_tengah_data_dilaporkan(tmp_path):
    p = buat_bill(tmp_path / "b.xlsx", [bill("S1", T1), bill(None, T1), bill("S3", T1)])
    h = baca_file_esb(p)
    assert any(c.baris == 15 and "tanpa 'Sales Number'" in c.pesan for c in h.galat)


def test_angka_rusak_dilaporkan_bukan_dinolkan(tmp_path):
    p = buat_bill(tmp_path / "b.xlsx", [bill("S1", T1)])
    wb = openpyxl.load_workbook(p)
    wb.active.cell(14, 9, "50,000.00")  # format Amerika
    wb.save(p)
    h = baca_file_esb(p)
    assert any(c.baris == 14 and "Subtotal" in c.pesan for c in h.galat)


def test_footer_tidak_ada(tmp_path):
    p = buat_bill(tmp_path / "b.xlsx", [bill("S1", T1)], footer={})
    h = baca_file_esb(p)
    assert any("footer" in c.pesan.lower() for c in h.galat)
