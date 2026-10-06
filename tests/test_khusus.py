"""Laporan khusus cabang: tidak ada angka gabungan atau angka cabang lain di data, paket Claude, dan ekspor HTML."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import data_contoh

PERIODE = [("2026-09", "bulan"), ("2026-09", "M3"), ("2026-09", "M4"), ("2026-10", "bulan")]
JEJAK_GABUNGAN = ("semua cabang", "kedua cabang", "dua cabang", "lintas cabang", '"keduanya"')


@pytest.fixture(scope="module")
def klien(tmp_path_factory):
    d = tmp_path_factory.mktemp("khusus")
    data_contoh.isi(d / "c.duckdb", d / "tmp")
    mp = pytest.MonkeyPatch()
    mp.setenv("AMPYANG_DB", str(d / "c.duckdb"))
    from app.web import app
    yield TestClient(app)
    mp.undo()


def _angka_khas(klien, cabang, bulan, pilih):
    """Angka cabang `cabang` yang tidak boleh muncul di laporan khusus cabang lain."""
    d = klien.get(f"/api/dashboard?cabang={cabang}&bulan={bulan}&pilih={pilih}").json()
    o = d["overview"]["kartu"]
    return [o["grand_total"]["teks"], o["subtotal"]["teks"], d["kudapan"]["kartu"]["omzet"]["teks"]]


@pytest.mark.parametrize("bulan,pilih", PERIODE)
@pytest.mark.parametrize("cabang,lain", [("Rungkut", "Mawar"), ("Mawar", "Rungkut")])
def test_data_khusus_tanpa_cabang_lain(klien, cabang, lain, bulan, pilih):
    q = f"cabang={cabang}&bulan={bulan}&pilih={pilih}&lingkup=khusus"
    data = klien.get(f"/api/dashboard?{q}").json()
    assert data["lingkup"] == "khusus"
    paket = klien.get(f"/api/paket-claude?{q}").text
    html = klien.get(f"/api/ekspor?{q}").text
    isi_html = re.search(r"window\.DATA_EKSPOR = (.*?);</script>", html, re.S).group(1)
    for nama, teks in (("data", json.dumps(data, ensure_ascii=False)), ("paket", paket), ("html", isi_html)):
        assert not re.search(rf"\b{lain}\b", teks, re.I), f"{nama} menyebut {lain}"
        for j in JEJAK_GABUNGAN:
            assert j not in teks.lower(), f"{nama} memuat '{j}'"
        if cabang == "Rungkut":
            assert "Pisang Goreng Keju" not in teks, f"{nama} memuat menu khas Mawar"
        for a in _angka_khas(klien, lain, bulan, pilih):
            if a.startswith("Rp") and a != "Rp0":
                assert a not in teks, f"{nama} memuat angka {lain} {a}"


def test_kartu_gabungan_member_hilang_tapi_angka_cabang_tetap(klien):
    q = "cabang=Rungkut&bulan=2026-10&pilih=bulan"
    lengkap = klien.get(f"/api/dashboard?{q}").json()["membership"]
    khusus = klien.get(f"/api/dashboard?{q}&lingkup=khusus").json()["membership"]
    for k in ("total_member", "terverifikasi", "terverifikasi_baru", "member_baru"):
        assert k in lengkap["kartu"] and k not in khusus["kartu"]
    for k in ("member_baru_cabang", "bill_member", "omzet_member", "pernah_transaksi"):
        assert khusus["kartu"][k]["teks"] == lengkap["kartu"][k]["teks"]
    assert "dari semua member" not in khusus["kartu"]["pernah_transaksi"]["label"]
    assert all("Member baru (semua cabang)" not in r for r in khusus["harian"])


def test_kampanye_khusus_hanya_cabang_sendiri(klien):
    s = klien.get("/api/dashboard?cabang=Rungkut&bulan=2026-09&pilih=M4&lingkup=khusus").json()["sosmed"]
    k = s["kampanye"]["daftar"][0]
    assert k["cabang"] == "Rungkut"
    assert [r["Cabang"] for r in k["tambahan_bill"]] == ["Rungkut"] == [r["Cabang"] for r in k["korelasi"]]
    assert [r["Cara bagi"] for r in k["biaya_bill"]] == ["Dibebankan penuh ke Rungkut"]


def test_jendela_waktu_cabang_lain(klien):
    j = klien.get("/api/dashboard?cabang=Rungkut&bulan=2026-09&pilih=bulan&lingkup=khusus").json()["foot_traffic"]["jendela"]
    ket = {r["jendela"]: r["keterangan"] for r in j}
    assert ket.get("Subuh") == "Sabtu–Minggu (buka 06.00)"
    assert ket.get("Larut") is None  # baris tetap bila cabang ini punya bill di jam itu, tanpa keterangan


def test_narasi_khusus_terpisah(klien):
    q = {"cabang": "Mawar", "bulan": "2026-09", "pilih": "M2"}
    r = klien.post("/api/narasi/tempel", json={**q, "lingkup": "khusus", "teks": "=== promo ===\nFAKTA: Promo tercatat."}).json()
    assert r["tab"] == {"promo": {"temuan": 1, "dibuang": 0}}
    url = "/api/dashboard?cabang=Mawar&bulan=2026-09&pilih=M2"
    assert klien.get(url + "&lingkup=khusus").json()["narasi"]["tab"]["promo"]["status"] == "ada"
    assert klien.get(url).json()["narasi"]["tab"]["promo"]["status"] == "belum"


def test_lingkup_tidak_dikenal(klien):
    assert klien.get("/api/dashboard?cabang=Rungkut&bulan=2026-09&lingkup=semua").status_code == 400
