from datetime import date
from decimal import Decimal

import pytest

from app.angka import (AngkaTidakValid, baca_angka, baca_jam, baca_tanggal, format_angka,
                       format_persen, format_rupiah)


@pytest.mark.parametrize("masuk, keluar", [
    ("231.973.850,00", Decimal("231973850.00")),
    ("1.500", Decimal("1500")),
    ("12,5", Decimal("12.5")),
    ("-2.000,50", Decimal("-2000.50")),
    ("(2.000,50)", Decimal("-2000.50")),
    ("Rp1.234.567", Decimal("1234567")),
    (1500, Decimal(1500)),
    (0.1 + 0.2, Decimal("0.30")),
    ("0", Decimal(0)),
])
def test_baca_angka(masuk, keluar):
    assert baca_angka(masuk) == keluar


@pytest.mark.parametrize("kosong", [None, "", "  ", "-"])
def test_baca_angka_kosong_bukan_nol(kosong):
    assert baca_angka(kosong) is None


@pytest.mark.parametrize("salah", ["1,500.00", "12.5", "abc", "1.50,00"])
def test_baca_angka_format_asing_ditolak(salah):
    with pytest.raises(AngkaTidakValid):
        baca_angka(salah)


@pytest.mark.parametrize("masuk, keluar", [
    ("01-09-2026", date(2026, 9, 1)),
    ("1/9/2026", date(2026, 9, 1)),
    ("2026-09-01", date(2026, 9, 1)),
    ("2026-09-01 13:00:00", date(2026, 9, 1)),
    ("1 Sep 2026", date(2026, 9, 1)),
    ("01 Agustus 2026", date(2026, 8, 1)),
])
def test_baca_tanggal(masuk, keluar):
    assert baca_tanggal(masuk) == keluar


def test_baca_tanggal_bulan_dulu_ditolak():
    with pytest.raises(ValueError):
        baca_tanggal("09/2026/01")


def test_baca_jam():
    assert baca_jam("07:05:59") == (7, 5)
    assert baca_jam("2026-09-01 21:30") == (21, 30)
    with pytest.raises(ValueError):
        baca_jam("25:00")


def test_format():
    assert format_rupiah(Decimal("1234567.49")) == "Rp1.234.567"
    assert format_rupiah(Decimal("-1500")) == "−Rp1.500"
    assert format_rupiah(None) == "Tidak diketahui"
    assert format_angka(Decimal("1234.5"), 1) == "1.234,5"
    assert format_persen(12.5) == "12,5%"
