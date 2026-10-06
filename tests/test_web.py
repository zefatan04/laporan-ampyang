from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item

A, B = date(2026, 9, 28), date(2026, 10, 4)


@pytest.fixture
def klien(tmp_path, monkeypatch):
    monkeypatch.setenv("AMPYANG_DB", str(tmp_path / "w.duckdb"))
    from app.web import app
    return TestClient(app)


def _file(tmp_path, items_kurang=False):
    bills = [bill("S1", A, sub=50000), bill("S2", B, sub=30000)]
    items = [item("S1", A, "Nasi", 2, 25000, 9000), item("S2", B, "Kopi", 2, 15000, 5000)]
    if items_kurang:
        items = items[:1]
    b = buat_bill(tmp_path / "b.xlsx", bills, awal=A, akhir=B)
    c = buat_cogs(tmp_path / "c.xlsx", items, awal=A, akhir=B)
    return [("files", ("bill.xlsx", b.read_bytes())), ("files", ("cogs.xlsx", c.read_bytes()))]


def test_halaman_utama(klien):
    r = klien.get("/")
    assert r.status_code == 200 and "Laporan Ampyang" in r.text


def test_alur_unggah_simpan_riwayat_hapus(tmp_path, klien):
    r = klien.post("/api/unggah", data={"awal": A.isoformat(), "akhir": B.isoformat()}, files=_file(tmp_path))
    assert r.status_code == 200, r.text
    h = r.json()
    assert not h["terblokir"] and not h["butuh_konfirmasi"]
    assert {f["kode"] for f in h["file"]} == {"bill", "cogs"}
    assert klien.post("/api/simpan", json={"token": h["token"]}).status_code == 200
    # token sekali pakai
    assert klien.post("/api/simpan", json={"token": h["token"]}).status_code == 410

    rw = klien.get("/api/riwayat").json()
    assert rw["minggu"][0]["sel"]["Rungkut|bill"]["status"] == "lengkap"

    # unggah ulang periode sama -> tumpang tindih, wajib ganti
    h2 = klien.post("/api/unggah", data={"awal": A.isoformat(), "akhir": B.isoformat()}, files=_file(tmp_path)).json()
    assert h2["tumpang_tindih"]
    assert klien.post("/api/simpan", json={"token": h2["token"]}).status_code == 409
    assert klien.post("/api/simpan", json={"token": h2["token"], "ganti": True}).status_code == 200

    uid = klien.get("/api/riwayat").json()["periode"][0]["unggahan_id"]
    assert klien.delete(f"/api/periode/{uid}/Rungkut").status_code == 200
    assert klien.get("/api/riwayat").json()["periode"] == []


def test_tidak_cocok_butuh_centang(tmp_path, klien):
    h = klien.post("/api/unggah", data={"awal": A.isoformat(), "akhir": B.isoformat()},
                   files=_file(tmp_path, items_kurang=True)).json()
    assert h["butuh_konfirmasi"]
    assert klien.post("/api/simpan", json={"token": h["token"]}).status_code == 409
    assert klien.post("/api/simpan", json={"token": h["token"], "simpan_walau_tidak_cocok": True}).status_code == 200
