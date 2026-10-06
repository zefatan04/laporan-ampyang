"""Paket untuk Claude (jalur manual tanpa API), tempel jawaban, dan ekspor HTML mandiri."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import narasi
from tests.fixtures import data_contoh
from tests.test_narasi import _data


# ---------------------------------------------------------------- paket

def test_paket_berisi_instruksi_format_dan_semua_tab():
    p = narasi.paket(_data())
    assert "Hanya boleh menyebut angka yang ada di JSON" in p
    assert "=== overview ===" in p and "BELUM BISA DISIMPULKAN" in p
    for tab in narasi.TAB:
        assert f"### Tab `{tab}`" in p
    for terlarang in ("AISHA", "PUJI", "118.99.123.35", "rahasia rumus", "RKT-001"):
        assert terlarang not in p
    # setiap blok JSON bisa dibaca ulang
    blok = re.findall(r"```json\n(.*?)\n```", p, re.S)
    assert len(blok) == len(narasi.TAB) and all(json.loads(b) for b in blok)


# ---------------------------------------------------------------- baca jawaban

def test_baca_jawaban_toleran_format_markdown():
    teks = """Berikut hasilnya.
```
=== overview ===
- **FAKTA:** Grand Total Rp51.729.896 dari 518 bill.
2. Dugaan: rombongan akhir pekan
   lebih banyak.
BELUM BISA DISIMPULKAN: perbandingan minggu lalu, data belum ada.
SARAN: Fokuskan konten ke akhir pekan.
=== tiktok ===
FAKTA: tidak relevan.
=== promo ===
```"""
    hasil, catatan = narasi.baca_jawaban(teks)
    assert [t["jenis"] for t in hasil["overview"]] == ["fakta", "dugaan", "belum_bisa_disimpulkan", "saran"]
    assert hasil["overview"][0]["teks"] == "Grand Total Rp51.729.896 dari 518 bill."
    assert hasil["overview"][1]["teks"] == "rombongan akhir pekan lebih banyak."
    assert hasil["promo"] == [] and "tiktok" not in hasil
    assert any("tiktok" in c for c in catatan)


def test_baca_jawaban_tanpa_blok_ditolak():
    with pytest.raises(narasi.NarasiGagal):
        narasi.baca_jawaban("Grand Total naik 5%.")


def test_simpan_manual_memverifikasi_angka(tmp_path):
    from app import db
    with db.koneksi(tmp_path / "m.duckdb") as con:
        r = narasi.simpan_manual(con, _data(), """=== overview ===
FAKTA: Grand Total Rp51.729.896 dari 518 bill.
FAKTA: Omzet sebulan diperkirakan Rp210.000.000.
DUGAAN: rombongan akhir pekan lebih banyak.
SARAN: naikkan stok kudapan 20%.
=== promo ===
""")
        assert r["tab"] == {"overview": {"temuan": 2, "dibuang": 2}}
        assert any("promo" in c for c in r["catatan"])
        s = narasi.status(con, _data())["overview"]
        assert s["status"] == "ada" and s["model"] == narasi.MODEL_MANUAL
        assert [t["teks"] for t in s["temuan"]] == ["Grand Total Rp51.729.896 dari 518 bill.",
                                                    "Dugaan: rombongan akhir pekan lebih banyak."]


# ---------------------------------------------------------------- endpoint & ekspor

@pytest.fixture(scope="module")
def klien(tmp_path_factory):
    d = tmp_path_factory.mktemp("contoh")
    data_contoh.isi(d / "c.duckdb", d / "tmp")
    mp = pytest.MonkeyPatch()
    mp.setenv("AMPYANG_DB", str(d / "c.duckdb"))
    from app.web import app
    yield TestClient(app)
    mp.undo()


def test_endpoint_paket_dan_tempel(klien):
    r = klien.get("/api/paket-claude?cabang=Mawar&bulan=2026-09&pilih=M4")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "Paket-Claude-Ampyang-Mawar-2026-09-28_2026-10-04.md" in r.headers["content-disposition"]
    assert "### Tab `sosmed`" in r.text
    r = klien.post("/api/narasi/tempel", json={"cabang": "Mawar", "bulan": "2026-09", "pilih": "M4",
                                               "teks": "=== foot ===\nFAKTA: Data jendela waktu tersedia."}).json()
    assert r["tab"] == {"foot": {"temuan": 1, "dibuang": 0}}
    d = klien.get("/api/dashboard?cabang=Mawar&bulan=2026-09&pilih=M4").json()
    assert d["narasi"]["tab"]["foot"]["status"] == "ada"
    assert "galat" in klien.post("/api/narasi/tempel", json={"cabang": "Mawar", "bulan": "2026-09", "teks": "acak"}).json()


def test_ekspor_html_mandiri(klien):
    r = klien.get("/api/ekspor?cabang=Rungkut&bulan=2026-10&pilih=bulan")
    assert r.status_code == 200 and "Laporan-Ampyang-Rungkut-2026-10-01_2026-10-31.html" in r.headers["content-disposition"]
    h = r.text
    assert "/static/" not in h and "<script src" not in h and "<link" not in h  # semuanya inline
    m = re.search(r"window\.DATA_EKSPOR = (.*?);</script>", h, re.S)
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert data["cabang"] == "Rungkut" and data["narasi"]["tab"]["overview"]["status"] == "ada"
    # tidak ada penutup script di tengah data/skrip yang memotong dokumen
    assert h.count("</script>") == h.count("<script>")
