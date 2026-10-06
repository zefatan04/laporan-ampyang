"""Tes parser Instagram, penggabungan tanpa dobel, kartu metrik, dan evaluasi kampanye.

Data ESB buatan (Rungkut):
  31 Agu – 27 Sep  pembanding : 1 bill per hari
  28 Sep –  4 Okt  kampanye   : 2, 3, 4, 2, 3, 4, 2 bill (tambahan 1, 2, 3, 1, 2, 3, 1 = 13 bill)
Klik tautan Brand selama kampanye = 10 × tambahan bill, jadi korelasinya 1.
"""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, db_ig, pengaturan
from app.hitung import sosmed
from app.hitung.data import muat
from app.parser.esb import baca_file_esb
from app.parser.instagram import baca_file_ig, teks_ig
from app.validasi import GAGAL, PERINGATAN, validasi_unggahan
from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item
from tests.fixtures.buat_ig import buat_ig

AWAL_A, MULAI, SELESAI = date(2026, 8, 31), date(2026, 9, 28), date(2026, 10, 4)
SAMPEL = Path(__file__).resolve().parents[1] / "samples" / "instagram" / "brand"


def _hari(a, z):
    return [a + timedelta(days=i) for i in range((z - a).days + 1)]


def _ig(tmp_path, nama, judul, nilai):
    return baca_file_ig(buat_ig(tmp_path / f"{nama}.csv", judul, nilai))


# ---------------------------------------------------------------- parser

def test_parser_format_asli(tmp_path):
    h = _ig(tmp_path, "t", "Tayangan", {date(2026, 9, 21): 385, date(2026, 9, 22): 1168})
    assert h.bisa_dipakai and h.metrik.kode == "tayangan"
    assert h.periode == (date(2026, 9, 21), date(2026, 9, 22))
    assert h.data["nilai"].tolist() == [385, 1168]


@pytest.mark.parametrize("judul,kode", [("Pengikut Instagram", "pengikut"), ("Klik tautan Instagram", "klik"),
                                        ("Interaksi konten", "interaksi"), ("Kunjungan Profil Instagram", "kunjungan"),
                                        ("Jangkauan", "jangkauan")])
def test_parser_kenali_judul(tmp_path, judul, kode):
    assert _ig(tmp_path, kode, judul, {date(2026, 9, 21): 1}).metrik.kode == kode


def test_parser_tolak_yang_tidak_dikenal(tmp_path):
    assert _ig(tmp_path, "a", "Penayangan Reels", {date(2026, 9, 21): 1}).galat  # judul baru: berhenti, jangan tebak
    assert baca_file_ig(buat_ig(tmp_path / "b.csv", "Tayangan", {date(2026, 9, 21): 1}, header=("Tanggal", "Iklan"))).galat
    assert baca_file_ig(buat_ig(tmp_path / "c.csv", "Tayangan", {date(2026, 9, 21): 1}, akhiran_waktu="T13:00:00")).galat
    assert _ig(tmp_path, "d", "Tayangan", {date(2026, 9, 21): "1.5"}).galat
    (tmp_path / "e.csv").write_text("sep=,\n\"Tayangan\"\n", encoding="utf-8")
    assert teks_ig((tmp_path / "e.csv").read_bytes()) is None
    assert baca_file_ig(tmp_path / "e.csv").galat


@pytest.mark.skipif(not SAMPEL.exists(), reason="file asli tidak ada (tidak masuk git)")
def test_sampel_asli_akun_brand():
    fs = [baca_file_ig(p) for p in sorted(SAMPEL.glob("*.csv"))]
    assert fs and all(h.bisa_dipakai for h in fs)
    pengikut = [h for h in fs if h.metrik.kode == "pengikut"]
    assert any(len(h.data) < 7 for h in pengikut)  # hari 0 pengikut memang tidak ditulis
    cak = {h.nama_file: (a, z) for h, a, z in db_ig.cakupan_file(fs)}
    for h in pengikut:
        a, z = cak[h.nama_file]
        assert (z - a).days == 6 and a.weekday() == 0


# ---------------------------------------------------------------- gabung & simpan

@pytest.fixture
def con(tmp_path):
    with db.koneksi(tmp_path / "s.duckdb") as c:
        yield c


def test_gabung_tanpa_dobel_dan_konflik(tmp_path, con):
    t = date(2026, 9, 21)
    panjang = _ig(tmp_path, "p", "Tayangan", {t + timedelta(days=i): 100 + i for i in range(14)})
    minggu = _ig(tmp_path, "m", "Tayangan", {t + timedelta(days=i): 100 + i for i in range(7)})
    cek, info = db_ig.validasi([panjang, minggu], "Brand", {})
    assert not db_ig.terblokir(cek) and len(info["gabung"]) == 14
    db_ig.simpan(con, [panjang, minggu], "Brand", cek, info["gabung"], False)

    # konflik di dalam satu unggahan -> tidak bisa disimpan
    salah = _ig(tmp_path, "s", "Tayangan", {t: 999})
    cek, _ = db_ig.validasi([minggu, salah], "Brand", {})
    assert db_ig.terblokir(cek) and any(c.nomor == 23 and c.status == GAGAL for c in cek)

    # konflik dengan data tersimpan -> butuh 'ganti'; nilai baru menang; hapus mengembalikan nilai lama
    cek, info = db_ig.validasi([salah], "Brand", db_ig.tersimpan(con, "Brand"))
    assert any(c.nomor == 24 and c.status == PERINGATAN for c in cek) and info["konflik_lama"] == 1
    with pytest.raises(db.TidakBolehDisimpan):
        db_ig.simpan(con, [salah], "Brand", cek, info["gabung"], False)
    uid = db_ig.simpan(con, [salah], "Brand", cek, info["gabung"], True)
    assert db_ig.tersimpan(con, "Brand")[("tayangan", t)] == 999
    assert db_ig.hapus_unggahan(con, uid)
    assert db_ig.tersimpan(con, "Brand")[("tayangan", t)] == 100


def test_akun_wajib_dipilih(tmp_path):
    cek, _ = db_ig.validasi([_ig(tmp_path, "t", "Tayangan", {date(2026, 9, 21): 1})], None, {})
    assert db_ig.terblokir(cek)


def test_pengikut_hari_kosong_tidak_tercatat_bukan_nol(tmp_path, con):
    senin = date(2026, 9, 21)
    fs = [_ig(tmp_path, "t", "Tayangan", {senin + timedelta(days=i): 10 for i in range(7)}),
          _ig(tmp_path, "j", "Jangkauan", {senin + timedelta(days=i): 100 + 100 * i for i in range(7)}),
          _ig(tmp_path, "p", "Pengikut Instagram", {senin + timedelta(days=1): 2, senin + timedelta(days=3): 1})]
    cek, info = db_ig.validasi(fs, "Brand", {})
    db_ig.simpan(con, fs, "Brand", cek, info["gabung"], False)
    x = sosmed.DataIG(con, "Brand", senin, senin + timedelta(days=6), [senin])
    k = {m: sosmed.kartu_metrik(x, m) for m in ("tayangan", "jangkauan", "pengikut", "klik")}
    assert k["tayangan"]["n"]["teks"] == "70" and k["tayangan"]["lengkap"]
    assert k["pengikut"]["n"]["teks"] == "3 (batas bawah)"
    assert "5 hari tidak tercatat" in k["pengikut"]["n"]["peringatan"][0]
    assert k["jangkauan"]["n"]["teks"] == "400" and "rata-rata" in k["jangkauan"]["judul"].lower()
    assert k["klik"]["n"]["status"] == "tidak_diketahui"
    harian = sosmed._harian_akun(x, {}, [])
    assert harian[0]["pengikut"] is None and harian[0]["pengikut_status"] == "tidak tercatat"


def test_input_manual_berlabel_dan_tidak_menjumlah_jangkauan(con):
    pengaturan.simpan(con, "ig_manual", pengaturan.periksa("ig_manual", [
        {"akun": "Rungkut", "senin": "2026-09-07", "nilai": {"tayangan": "500", "jangkauan": "300"}},
        {"akun": "Rungkut", "senin": "2026-09-14", "nilai": {"tayangan": "700", "jangkauan": "400"}}]))
    minggu = sosmed.DataIG(con, "Rungkut", date(2026, 9, 7), date(2026, 9, 13), [date(2026, 9, 7)])
    k = sosmed.kartu_metrik(minggu, "tayangan")
    assert k["n"]["teks"] == "500" and k["n"]["label"] == "input manual"
    bulan = sosmed.DataIG(con, "Rungkut", date(2026, 9, 1), date(2026, 9, 30),
                          [date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28)])
    assert sosmed.kartu_metrik(bulan, "tayangan")["n"]["teks"] == "1.200 (batas bawah)"
    assert sosmed.kartu_metrik(bulan, "jangkauan")["n"]["status"] == "tidak_diketahui"
    with pytest.raises(ValueError):
        pengaturan.periksa("ig_manual", [{"akun": "Rungkut", "senin": "2026-09-08", "nilai": {"tayangan": "1"}}])
    with pytest.raises(ValueError):
        pengaturan.periksa("ig_manual", [{"akun": "Rungkut", "senin": "2026-09-07", "nilai": {"tayangan": "1.000"}}])


# ---------------------------------------------------------------- kampanye

def _unggah_esb(con, tmp_path, a, z, bill_per_hari, nama):
    bills, items = [], []
    for i, t in enumerate(_hari(a, z)):
        for j in range(bill_per_hari(i)):
            sn = f"{nama}{t:%m%d}{j}"
            # jam malam supaya hari tidak dianggap parsial
            bills.append(bill(sn, t, "20:30:00", 50000))
            items.append(item(sn, t, "Nasi Goreng", 1, 50000, 15000))
    fs = [baca_file_esb(buat_bill(tmp_path / f"{nama}b.xlsx", bills, awal=a, akhir=z)),
          baca_file_esb(buat_cogs(tmp_path / f"{nama}c.xlsx", items, awal=a, akhir=z))]
    lap = validasi_unggahan(fs, a, z)
    assert not lap.terblokir and not lap.butuh_konfirmasi, [(c.nama, c.ringkasan) for c in lap.cek if c.status == "gagal"]
    db.simpan_unggahan(con, fs, lap, a, z)


POLA = [2, 3, 4, 2, 3, 4, 2]


@pytest.fixture
def kampanye(tmp_path, con):
    _unggah_esb(con, tmp_path, AWAL_A, MULAI - timedelta(days=1), lambda i: 1, "A")
    _unggah_esb(con, tmp_path, MULAI, SELESAI, lambda i: POLA[i], "K")
    klik = {t: 0 for t in _hari(MULAI - timedelta(days=28), SELESAI + timedelta(days=3))}
    for i, t in enumerate(_hari(MULAI, SELESAI)):
        klik[t] = 10 * (POLA[i] - 1)
    klik[SELESAI + timedelta(days=1)] = 5  # iklan masih jalan sehari sesudah tanggal isian
    fs = [_ig(tmp_path, "k", "Klik tautan Instagram", klik),
          _ig(tmp_path, "j", "Jangkauan", {t: 1000 for t in klik}),
          _ig(tmp_path, "p", "Pengikut Instagram", {MULAI: 7})]
    cek, info = db_ig.validasi(fs, "Brand", {})
    db_ig.simpan(con, fs, "Brand", cek, info["gabung"], False)
    pengaturan.simpan(con, "hari_libur", [])
    pengaturan.simpan(con, "kampanye", pengaturan.periksa("kampanye", [
        {"nama": "Iklan Okt", "cabang": "keduanya", "akun": "Brand", "mulai": MULAI.isoformat(),
         "selesai": SELESAI.isoformat(), "anggaran": "650000"}]))
    return con


def test_evaluasi_kampanye(kampanye):
    con = kampanye
    k = pengaturan.ambil(con, "kampanye")[0]
    e = sosmed.evaluasi_kampanye(con, k, [k], set())

    # tanggal iklan terdeteksi vs isian
    assert not e["deteksi"]["cocok"] and "5 Okt" in e["deteksi"]["peringatan"][0]

    # tambahan bill Rungkut = 13; Mawar tidak ada data
    rk = next(r for r in e["tambahan_bill"] if r["Cabang"] == "Rungkut")
    assert rk["Tambahan bill vs pembanding"].startswith("13,0 bill") and rk["Hari dibandingkan"] == "7/7"
    mw = next(r for r in e["tambahan_bill"] if r["Cabang"] == "Mawar")
    assert mw["Tambahan bill vs pembanding"].startswith("Tidak diketahui")

    # biaya per bill tambahan: 650.000 / 13 = 50.000; gabungan diberi label batas bawah
    biaya = {r["Cara bagi"]: r["Biaya iklan per bill tambahan"] for r in e["biaya_bill"]}
    assert biaya["Dibebankan penuh ke Rungkut"] == "Rp50.000"
    gab = next(v for c, v in biaya.items() if c.startswith("Dibagi"))
    assert gab.startswith("Rp50.000") and "batas bawah" in gab
    assert e["batas_bawah"]

    # korelasi klik vs tambahan bill = 1
    kr = next(r for r in e["korelasi"] if r["Cabang"] == "Rungkut")["Korelasi"]
    assert kr.startswith("r = 1,00 dari 7 hari")

    # biaya per klik: 650.000 / 130 klik = 5.000
    b = {x["judul"]: x["n"] for x in e["biaya_ig"]}
    assert b["Biaya per klik tautan"]["teks"] == "Rp5.000"
    assert b["Biaya per 1.000 jangkauan"]["teks"] == "Rp92.857"  # 650.000 / 7.000 × 1.000
    assert b["Biaya per pengikut baru"]["teks"].endswith("(batas atas)")


def test_kampanye_tanpa_data_ig_tetap_menghitung_bill(tmp_path, con):
    _unggah_esb(con, tmp_path, AWAL_A, MULAI - timedelta(days=1), lambda i: 1, "A")
    _unggah_esb(con, tmp_path, MULAI, SELESAI, lambda i: POLA[i], "K")
    pengaturan.simpan(con, "hari_libur", [])
    k = pengaturan.periksa("kampanye", [{"nama": "X", "cabang": "Rungkut", "akun": "Rungkut", "mulai": MULAI.isoformat(),
                                         "selesai": SELESAI.isoformat(), "anggaran": "650000"}])[0]
    e = sosmed.evaluasi_kampanye(con, k, [k], set())
    assert not e["deteksi"]["tersedia"] and not e["metrik_ig"]["tersedia"]
    assert all(x["n"]["status"] == "tidak_diketahui" for x in e["biaya_ig"])
    assert e["biaya_bill"][0]["Biaya iklan per bill tambahan"] == "Rp50.000"
    assert not e["batas_bawah"]


def test_pengaturan_kampanye_ditolak_bila_salah():
    dasar = {"nama": "X", "cabang": "Rungkut", "akun": "Brand", "mulai": "2026-09-01", "selesai": "2026-09-07"}
    assert pengaturan.periksa("kampanye", [{**dasar, "anggaran": ""}])[0]["anggaran"] == ""
    for salah in ({"anggaran": "1.500.000"}, {"cabang": "Semua"}, {"akun": "TikTok"}, {"selesai": "2026-08-01"}):
        with pytest.raises(ValueError):
            pengaturan.periksa("kampanye", [{**dasar, "anggaran": "1", **salah}])


# ---------------------------------------------------------------- web

def test_unggah_ig_lewat_web(tmp_path, monkeypatch):
    monkeypatch.setenv("AMPYANG_DB", str(tmp_path / "w.duckdb"))
    from app.web import app
    klien = TestClient(app)
    p = buat_ig(tmp_path / "Tayangan.csv", "Tayangan", {date(2026, 9, 21): 5, date(2026, 9, 22): 6})
    form = {"awal": "2026-09-21", "akhir": "2026-09-27"}
    files = [("files", ("Tayangan.csv", p.read_bytes()))]
    h = klien.post("/api/unggah", data=form, files=files).json()
    assert h["terblokir"]  # akun belum dipilih
    h = klien.post("/api/unggah", data={**form, "akun": "Brand"}, files=files).json()
    assert not h["terblokir"] and h["file"][0]["jenis"] == "Instagram · Tayangan"
    assert klien.post("/api/simpan", json={"token": h["token"]}).status_code == 200
    r = klien.get("/api/riwayat").json()["instagram"]
    assert r["unggahan"][0]["akun"] == "Brand" and r["unggahan"][0]["nilai_ditulis"] == 2
    d = klien.get("/api/dashboard?cabang=Mawar&bulan=2026-09&pilih=M3").json()
    brand = next(a for a in d["sosmed"]["akun"] if a["akun"] == "Brand")
    assert brand["kartu"][0]["n"]["teks"] == "11 (batas bawah)"
    assert klien.delete(f"/api/instagram/{r['unggahan'][0]['unggahan_id']}").status_code == 200
