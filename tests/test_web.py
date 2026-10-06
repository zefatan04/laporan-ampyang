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


def test_pengaturan_simpan_dan_tolak(klien):
    s = klien.get("/api/pengaturan").json()
    assert s["hari_libur_terverifikasi"] is False and s["target_omzet"] == {}
    assert klien.put("/api/pengaturan/target_omzet", json={"nilai": {"Rungkut|2026-10": 250000000}}).status_code == 200
    assert klien.get("/api/pengaturan").json()["target_omzet"] == {"Rungkut|2026-10": 250000000}
    assert klien.put("/api/pengaturan/target_omzet", json={"nilai": {"Darmo|2026-10": 1}}).status_code == 400
    assert klien.put("/api/pengaturan/suhu_per_menu", json={"nilai": {"Juice Jeruk": "hangat"}}).status_code == 400
    assert klien.put("/api/pengaturan/hari_libur", json={"nilai": [{"tanggal": "2026-13-01", "nama": "x"}]}).status_code == 400
    assert klien.put("/api/pengaturan/tidak_ada", json={"nilai": 1}).status_code == 404


def test_dashboard_api(tmp_path, klien):
    h = klien.post("/api/unggah", data={"awal": A.isoformat(), "akhir": B.isoformat()}, files=_file(tmp_path)).json()
    klien.post("/api/simpan", json={"token": h["token"]})
    assert klien.get("/api/dashboard/bulan").json()["bulan"] == ["2026-09", "2026-10"]
    d = klien.get("/api/dashboard", params={"cabang": "Rungkut", "bulan": "2026-09", "pilih": "M4"}).json()
    assert d["overview"]["kartu"]["grand_total"]["teks"] == "Rp88.000"
    assert klien.get("/api/dashboard", params={"cabang": "Darmo", "bulan": "2026-09"}).status_code == 400
    assert klien.get("/api/dashboard", params={"cabang": "Rungkut", "bulan": "2026-13"}).status_code == 400


def test_pengaturan_promo(klien):
    ok = {"nama": "Serbuk Hemat", "mulai": "2026-09-15", "selesai": "2026-10-15", "cabang": "keduanya",
          "promotion_esb": ["PROMO  MEMBERSHIP SERBUK HEMAT "], "menu_promo": []}
    assert klien.put("/api/pengaturan/promo", json={"nilai": [ok]}).status_code == 200
    assert klien.get("/api/pengaturan").json()["promo"][0]["promotion_esb"] == ["PROMO MEMBERSHIP SERBUK HEMAT"]
    assert klien.put("/api/pengaturan/promo", json={"nilai": [{**ok, "selesai": "2026-09-01"}]}).status_code == 400
    assert klien.put("/api/pengaturan/promo", json={"nilai": [{**ok, "cabang": "Darmo"}]}).status_code == 400
    assert klien.put("/api/pengaturan/ambang_netral_persen", json={"nilai": 80}).status_code == 400
