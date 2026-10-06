"""Rekonsiliasi memakai file ESB asli di samples/ (tidak masuk git).

Dilewati otomatis bila samples/ belum berisi file .xlsx. File Bill & COGS
di folder yang sama dianggap satu unggahan.
"""
from pathlib import Path

import pytest

from app.parser.esb import BILL, COGS, baca_file_esb
from app.validasi import LULUS, cek_footer, cek_silang

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
FILES = sorted(SAMPLES.rglob("*.xlsx"))

pytestmark = pytest.mark.skipif(not FILES, reason="samples/ belum berisi file ESB asli")


@pytest.fixture(scope="module")
def hasil():
    return {f: baca_file_esb(f) for f in FILES}


@pytest.fixture(scope="module")
def pasangan(hasil):
    per_folder = {}
    for f, h in hasil.items():
        if h.bisa_dipakai and h.jenis in (BILL, COGS):
            per_folder.setdefault(f.parent, {})[h.jenis.kode] = h
    p = {k: v for k, v in per_folder.items() if {"bill", "cogs"} <= v.keys()}
    if not p:
        pytest.skip("belum ada pasangan Bill+COGS dalam satu folder")
    return p


@pytest.mark.parametrize("f", FILES, ids=lambda f: f"{f.parent.name}/{f.name}")
def test_file_terbaca_tanpa_galat(hasil, f):
    h = hasil[f]
    if h.jenis not in (BILL, COGS):
        pytest.skip(f"{h.jenis.nama if h.jenis else 'tidak dikenali'}: belum diolah di tahap ini")
    assert h.galat == [], [c.pesan for c in h.galat]


@pytest.mark.parametrize("f", FILES, ids=lambda f: f"{f.parent.name}/{f.name}")
def test_total_sama_persis_dengan_footer(hasil, f):
    h = hasil[f]
    if h.jenis is not BILL or not h.bisa_dipakai:
        pytest.skip("hanya Bill Report yang punya footer")
    c = cek_footer(h)
    assert c.status == LULUS, c.rincian


def test_periode_bill_dan_cogs_sama(pasangan):
    for folder, v in pasangan.items():
        assert v["bill"].periode == v["cogs"].periode, (
            f"{folder.name}: periode Bill {v['bill'].periode} ≠ COGS {v['cogs'].periode}. Export ulang COGS.")


def test_tanggal_bersama_bill_cocok_dengan_cogs(pasangan):
    """Σ Subtotal Bill = Σ Total COGS per cabang per tanggal yang ada di kedua file."""
    for folder, v in pasangan.items():
        c = cek_silang(v["bill"], v["cogs"])
        per_bill = [r for r in c.rincian if "Sales Number" in r]
        assert per_bill == [], f"{folder.name}: {per_bill[:10]}"
        if v["bill"].periode == v["cogs"].periode:
            assert c.status == LULUS, c.rincian[:20]
