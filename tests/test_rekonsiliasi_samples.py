"""Rekonsiliasi memakai file ESB asli di samples/ (tidak masuk git).

Dilewati otomatis bila samples/ belum berisi file .xlsx.
"""
from pathlib import Path

import pytest

from app.parser.esb import BILL, COGS, baca_file_esb
from app.validasi import GAGAL, LULUS, cek_footer, cek_silang

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
FILES = sorted(SAMPLES.rglob("*.xlsx"))

pytestmark = pytest.mark.skipif(not FILES, reason="samples/ belum berisi file ESB asli")


@pytest.fixture(scope="module")
def hasil():
    return {f: baca_file_esb(f) for f in FILES}


@pytest.mark.parametrize("f", FILES, ids=lambda f: f.name)
def test_file_terbaca_tanpa_galat(hasil, f):
    h = hasil[f]
    if h.jenis not in (BILL, COGS):
        pytest.skip(f"{h.jenis.nama if h.jenis else 'tidak dikenali'}: belum diolah di tahap ini")
    assert h.galat == [], [c.pesan for c in h.galat]


@pytest.mark.parametrize("f", FILES, ids=lambda f: f.name)
def test_total_sama_persis_dengan_footer(hasil, f):
    h = hasil[f]
    if h.jenis not in (BILL, COGS) or not h.bisa_dipakai:
        pytest.skip("bukan Bill/COGS atau tidak terbaca")
    c = cek_footer(h)
    assert c.status == LULUS, c.rincian


def test_bill_cocok_dengan_cogs_per_folder(hasil):
    """File Bill & COGS di folder yang sama dianggap satu periode/cabang."""
    per_folder = {}
    for f, h in hasil.items():
        if h.bisa_dipakai and h.jenis in (BILL, COGS):
            per_folder.setdefault(f.parent, {})[h.jenis.kode] = h
    pasangan = [v for v in per_folder.values() if {"bill", "cogs"} <= v.keys()]
    if not pasangan:
        pytest.skip("belum ada pasangan Bill+COGS dalam satu folder")
    for v in pasangan:
        c = cek_silang(v["bill"], v["cogs"])
        assert c.status != GAGAL, c.rincian[:20]
