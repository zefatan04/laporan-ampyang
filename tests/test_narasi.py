"""Tes narasi: muatan (privasi), ekstraksi & verifikasi angka, simpan/kedaluwarsa, galat model.

Claude API tidak dipanggil di tes; klien diganti tiruan.
"""
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import db, narasi


def _nilai(teks, status="pasti", label=None):
    return {"nilai": "1", "teks": teks, "jenis": "angka", "status": status, "alasan": None,
            "asal": {"rumus": "rahasia rumus", "sumber": ["Bill Report"], "filter": [], "baris": 5, "dikeluarkan": [], "catatan": []},
            "peringatan": [], **({"label": label} if label else {})}


def _data(gt="Rp51.729.896"):
    tab = {"kartu": {"grand_total": _nilai(gt), "jumlah_bill": _nilai("518"), "rata": _nilai("Rp99.865", label="F&B saja"),
                     "target": _nilai("Tidak diketahui — belum diisi", "tidak_diketahui")},
           "banding": {"baris": [{"metrik": "Bill", "selisih": {"teks": "+12", "persen": "+2,4%", "arah": "naik"}}]},
           "bill_selisih": [{"Sales Number": "RKT-001", "Selisih": "Rp1"}]}
    member = {"per_kasir": [{"Kasir": "AISHA - RUNGKUT", "Transaksi member": 26}],
              "kualitas": {"rincian": [{"IP": "118.99.123.35", "Tanda": "beruntun"}],
                           "tanpa_esb": [{"Waktu": "28-09 15:01", "Kasir": "PUJI", "Nominal": "Rp592.900"}] * 6,
                           "ganda": [{"Kasir": "PUJI"}]},
              "kartu": {"member_baru": _nilai("54")}}
    kosong = {"tersedia": False, "alasan": "belum ada"}
    return {"cabang": "Rungkut", "periode": {"label": "M4 · 28 Sep–4 Okt", "awal": "2026-09-28", "akhir": "2026-10-04"},
            "peringatan_merah": False,
            "kualitas": {"file": [{"file": "Bill Report (wajib)", "status": "ada", "keterangan": "7/7 hari"}], "hari": [],
                         "baris_dikeluarkan": [], "hari_libur_terverifikasi": False, "tanpa_hpp": {"daftar": []}},
            "overview": tab, "membership": member, "foot_traffic": kosong, "makanan": kosong, "kudapan": kosong,
            "minuman": kosong, "promo": kosong, "sosmed": kosong}


# ---------------------------------------------------------------- muatan

def test_muatan_tanpa_asal_dan_data_orang():
    d = _data()
    s = json.dumps([narasi.muatan(d, t) for t in narasi.TAB], ensure_ascii=False)
    for terlarang in ("rahasia rumus", "AISHA", "PUJI", "118.99.123.35", "RKT-001", "15:01"):
        assert terlarang not in s
    m = narasi.muatan(d, "membership")["isi_tab"]
    assert m["kualitas"]["jumlah_tanpa_esb"] == 6 and m["kualitas"]["jumlah_ganda"] == 1
    o = narasi.muatan(d, "overview")["isi_tab"]["kartu"]
    assert o["rata"] == {"teks": "Rp99.865", "keterangan": "F&B saja"}
    assert o["target"]["status"] == "tidak_diketahui"


def test_versi_berubah_bila_data_berubah():
    assert narasi.versi(narasi.muatan(_data(), "overview")) != narasi.versi(narasi.muatan(_data("Rp1"), "overview"))
    assert narasi.versi(narasi.muatan(_data(), "overview")) == narasi.versi(narasi.muatan(_data(), "overview"))


# ---------------------------------------------------------------- angka

@pytest.mark.parametrize("teks,nilai", [
    ("omzet Rp51.729.896", Decimal(51729896)), ("naik 2,4%", Decimal("2.4")), ("518 bill", Decimal(518)),
    ("sekitar Rp11,2 juta", Decimal(11200000)), ("turun −5,2 persen", Decimal("5.2")), ("Rp 592.900", Decimal(592900)),
])
def test_angka_di_teks(teks, nilai):
    assert [abs(v) for v, _, _ in narasi.angka_di_teks(teks)] == [nilai]


def test_angka_label_tidak_dihitung():
    assert narasi.angka_di_teks("minggu M4 dan kode A1") == []


def test_verifikasi_buang_angka_hitungan_sendiri():
    m = narasi.muatan(_data(), "overview")
    temuan = [
        {"teks": "Grand Total minggu ini Rp51.729.896 dari 518 bill. Rata-rata bill F&B Rp99.865.", "jenis": "fakta"},
        {"teks": "Bill naik 2,4% dibanding minggu lalu. Kalau begini terus, sebulan bisa Rp206.919.584.", "jenis": "fakta"},
        {"teks": "Omzet harian sekitar Rp7.389.985.", "jenis": "fakta"},  # dihitung model sendiri
        {"teks": "Omzet sekitar Rp51,7 juta; target belum bisa disimpulkan.", "jenis": "belum_bisa_disimpulkan"},
    ]
    bersih, dibuang = narasi.verifikasi(temuan, m)
    assert [t["teks"] for t in bersih] == [
        "Grand Total minggu ini Rp51.729.896 dari 518 bill. Rata-rata bill F&B Rp99.865.",
        "Bill naik 2,4% dibanding minggu lalu.",
        "Omzet sekitar Rp51,7 juta. Target belum bisa disimpulkan.",
    ]
    assert {d["kalimat"] for d in dibuang} == {"Kalau begini terus, sebulan bisa Rp206.919.584.", "Omzet harian sekitar Rp7.389.985."}


def test_dugaan_selalu_berlabel():
    bersih, _ = narasi.verifikasi([{"teks": "Rombongan kantor mungkin datang lebih sering.", "jenis": "dugaan"}], {})
    assert bersih[0]["teks"] == "Dugaan: rombongan kantor mungkin datang lebih sering."


def test_verifikasi_toleransi_pembulatan_ketat():
    m = {"x": "21,6%"}
    assert narasi.verifikasi([{"teks": "Porsi 22%.", "jenis": "fakta"}], m)[0]  # dibulatkan ke 0 desimal: masih cocok
    assert not narasi.verifikasi([{"teks": "Porsi 21,9%.", "jenis": "fakta"}], m)[0]


# ---------------------------------------------------------------- panggil & simpan

class KlienTiruan:
    def __init__(self, temuan=None, stop="end_turn"):
        self.temuan, self.stop, self.kw = temuan, stop, None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.kw = kw
        teks = json.dumps({"temuan": self.temuan or []})
        return SimpleNamespace(stop_reason=self.stop, model=kw["model"], content=[SimpleNamespace(type="text", text=teks)])


@pytest.fixture
def con(tmp_path):
    with db.koneksi(tmp_path / "n.duckdb") as c:
        yield c


def test_buat_simpan_dan_kedaluwarsa(con):
    k = KlienTiruan([{"teks": "Grand Total Rp51.729.896 dari 518 bill.", "jenis": "fakta"},
                     {"teks": "Dugaan: rombongan akhir pekan lebih banyak.", "jenis": "dugaan"},
                     {"teks": "Rata-rata bill naik 13%.", "jenis": "fakta"}])
    h = narasi.buat(con, _data(), "overview", klien=k)
    assert h["status"] == "ada" and [t["jenis"] for t in h["temuan"]] == ["fakta", "dugaan"]
    assert h["dibuang"] == [{"kalimat": "Rata-rata bill naik 13%.", "angka_tidak_ditemukan": ["13%"]}]
    assert k.kw["model"] == "claude-opus-5-5" and k.kw["fallbacks"] == "default"
    assert "AISHA" not in json.dumps(k.kw["messages"], ensure_ascii=False)
    s = narasi.status(con, _data())
    assert s["overview"]["status"] == "ada" and s["promo"]["status"] == "belum"
    assert narasi.status(con, _data("Rp1"))["overview"]["status"] == "kedaluwarsa"


def test_penolakan_dan_format_salah(con):
    with pytest.raises(narasi.NarasiGagal):
        narasi.buat(con, _data(), "overview", klien=KlienTiruan(stop="refusal"))
    k = KlienTiruan()
    k.beta.messages.create = lambda **kw: SimpleNamespace(stop_reason="end_turn", model="x",
                                                          content=[SimpleNamespace(type="text", text="bukan json")])
    with pytest.raises(narasi.NarasiGagal):
        narasi.buat(con, _data(), "overview", klien=k)


def test_tanpa_api_key(con, monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not narasi.aktif()
    with pytest.raises(narasi.NarasiGagal, match="tidak aktif"):
        narasi.buat(con, _data(), "overview")
    monkeypatch.setenv("AMPYANG_DB", str(tmp_path / "w.duckdb"))
    from fastapi.testclient import TestClient
    from app.web import app
    klien = TestClient(app)
    d = klien.get("/api/dashboard?cabang=Rungkut&bulan=2026-10&pilih=bulan").json()
    assert d["narasi"]["aktif"] is False and d["narasi"]["tab"]["overview"]["status"] == "belum"
    r = klien.post("/api/narasi", json={"cabang": "Rungkut", "bulan": "2026-10", "tab": "overview"})
    assert r.status_code == 200 and "tidak aktif" in r.json()["galat"]
