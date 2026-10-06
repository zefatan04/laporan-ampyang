"""Parser, validasi, penyimpanan, dan tab Membership.

Skenario Rungkut 28 Sep – 4 Okt 2026 (ESB: B1 GT 110.000 Sen, B2 GT 55.000 Sen, B3 GT 220.000 Kam):
  T1 Sen 12:10 nomor A  110.000 (= B1)      kasir Puji   1 stempel
  T2 Sen 12:40 nomor A  110.000 (ganda)     kasir Puji   1 stempel  -> tanpa pasangan + dicatat ganda
  T3 Kam 19:45 nomor B  220.000 (= B3)      kasir Aisha  2 stempel
  T4 Kam 20:00 nomor C   99.000 (tak ada)   kasir Aisha  1 stempel  -> tanpa pasangan
"""
from datetime import date

import pytest

from app import db, db_loyalty
from app.hitung import membership
from app.hitung.data import muat
from app.parser.esb import baca_file_esb
from app.parser.loyalty import HARIAN, LOG, PELANGGAN, TRANSAKSI, baca_file_loyalty, sidik
from app.validasi import GAGAL, LULUS, validasi_unggahan
from app.validasi_loyalty import butuh_konfirmasi, terblokir, validasi_loyalty
from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item
from tests.fixtures.buat_loyalty import tulis

A, Z = date(2026, 9, 28), date(2026, 10, 4)
HARI = [date(2026, 9, 28 + i) if i < 3 else date(2026, 10, i - 2) for i in range(7)]
C = "Rungkut"


def _trx():
    return [
        {"Waktu": "2026-09-28 12:10:00", "Nomor WA": "081111", "Nama Member": "Ani", "Nominal Bill": "110000",
         "Stempel Didapat": "1", "Stempel Hangus": "0", "Stempel Setelahnya": "1", "Dicatat Kasir": "PUJI - Rungkut", "Cabang": C},
        {"Waktu": "2026-09-28 12:40:00", "Nomor WA": "6281111", "Nama Member": "Ani", "Nominal Bill": "110000",
         "Stempel Didapat": "1", "Stempel Hangus": "0", "Stempel Setelahnya": "2", "Dicatat Kasir": "PUJI - Rungkut", "Cabang": C},
        {"Waktu": "2026-10-01 19:45:00", "Nomor WA": "082222", "Nama Member": "Budi", "Nominal Bill": "220000",
         "Stempel Didapat": "2", "Stempel Hangus": "0", "Stempel Setelahnya": "2", "Dicatat Kasir": "AISHA - RUNGKUT", "Cabang": C},
        {"Waktu": "2026-10-01 20:00:00", "Nomor WA": "083333", "Nama Member": "Cici", "Nominal Bill": "99000",
         "Stempel Didapat": "1", "Stempel Hangus": "0", "Stempel Setelahnya": "1", "Dicatat Kasir": "AISHA - RUNGKUT", "Cabang": C},
    ]


def _harian(ubah=None):
    isi = {HARI[0]: (2, 2, 220000), HARI[3]: (2, 3, 319000)}
    hasil = []
    for t in HARI:
        b, s, o = isi.get(t, (0, 0, 0))
        hasil.append({"Tanggal": t.isoformat(), "Jumlah Bill": b, "Stempel Diberikan": s, "Omzet Tercatat": o,
                      "Klaim Dibuat": 1 if t == HARI[5] else 0, "Hadiah Diserahkan": 1 if t == HARI[5] else 0,
                      "Member Baru (semua cabang)": 2 if t == HARI[0] else 0, "Login Berhasil": 1,
                      "Member Baru (didaftarkan kasir cabang ini)": 1 if t == HARI[0] else 0, "Cabang": C})
    if ubah:
        ubah(hasil)
    return hasil


def _file_loyalty(tmp_path, harian=None, nama="L"):
    p = tmp_path
    return [
        tulis(p / f"{nama}riwayat-transaksi-rungkut-20260928-20261004.csv", "transaksi", _trx()),
        tulis(p / f"{nama}rekap-harian-rungkut-20260928-20261004.csv", "harian", harian or _harian()),
        tulis(p / f"{nama}riwayat-klaim-rungkut-20260928-20261004.csv", "klaim", [
            {"Waktu Klaim": "2026-10-03 18:00:00", "Nomor WA": "082222", "Nama Member": "Budi", "Tingkat": "3",
             "Nama Hadiah": "Es Thai Tea", "Kode": "X1", "Status": "Sudah diserahkan",
             "Waktu Diserahkan": "2026-10-03 18:01:00", "Diserahkan Kasir": "AISHA - RUNGKUT", "IP Saat Klaim": "1.2.3.4", "Cabang": C},
            {"Waktu Klaim": "2026-10-03 19:00:00", "Nomor WA": "089999", "Nama Member": "Staf", "Tingkat": "3",
             "Nama Hadiah": "Teh Tarik", "Kode": "X2", "Status": "Menunggu diambil", "Cabang": C}]),
        tulis(p / f"{nama}log-aktivitas-rungkut-20260928-20261004.csv", "log", [
            {"Waktu": "2026-09-28 11:00:00", "Kode Kejadian": "daftar", "Kejadian": "daftar", "Nama Akun": "Ani",
             "Nomor WA/Login": "6281111", "Alamat IP": "10.0.0.1", "Keterangan": "Nomor belum terverifikasi", "Cabang": C},
            {"Waktu": "2026-09-28 11:05:00", "Kode Kejadian": "pendaftaran_janggal", "Kejadian": "Pendaftaran janggal",
             "Nama Akun": "Xx", "Nomor WA/Login": "6281234", "Alamat IP": "10.0.0.1",
             "Keterangan": "Xx (081234): nama terlalu pendek", "Cabang": C},
            {"Waktu": "2026-09-28 11:06:00", "Kode Kejadian": "kasir_online", "Kejadian": "Kasir online",
             "Nama Akun": "PUJI", "Alamat IP": "10.0.0.2", "Cabang": C}]),
        tulis(p / f"{nama}rekap-pelanggan-rungkut-20261006.csv", "pelanggan", [
            {"Nomor WA": "081111", "Nama": "Ani", "Tanggal Gabung": "2026-09-28", "Status Verifikasi": "Terverifikasi",
             "Jumlah Transaksi": "2", "Total Belanja": "220000", "Kasir Pendaftar": "PUJI - Rungkut", "Cabang Pendaftaran": C, "Cabang": C},
            {"Nomor WA": "082222", "Nama": "Budi", "Tanggal Gabung": "2026-08-01", "Status Verifikasi": "Belum",
             "Jumlah Transaksi": "3", "Total Belanja": "500000", "Cabang Pendaftaran": "Tidak diketahui", "Cabang": C},
            {"Nomor WA": "083333", "Nama": "Cici", "Tanggal Gabung": "2026-09-28", "Status Verifikasi": "Belum",
             "Jumlah Transaksi": "1", "Total Belanja": "99000", "Cabang Pendaftaran": "Tidak diketahui", "Cabang": C},
            {"Nomor WA": "084444", "Nama": "Dodi", "Tanggal Gabung": "2026-07-01", "Status Verifikasi": "Belum",
             "Jumlah Transaksi": "0", "Total Belanja": "0", "Cabang Pendaftaran": "Tidak diketahui", "Cabang": C}]),
    ]


@pytest.fixture
def con(tmp_path):
    with db.koneksi(tmp_path / "l.duckdb") as c:
        bills = [bill("B1", HARI[0], "12:00:00", 100000), bill("B2", HARI[0], "13:00:00", 50000),
                 bill("B3", HARI[3], "19:30:00", 200000)]
        bills += [bill(f"X{i}", t, "20:30:00", 10000) for i, t in enumerate(HARI)]
        items = [item("B1", HARI[0], "Nasi", 1, 100000, 30000), item("B2", HARI[0], "Nasi", 1, 50000, 15000),
                 item("B3", HARI[3], "Nasi", 2, 100000, 60000)]
        items += [item(f"X{i}", t, "Teh", 1, 10000, 2000, kat="BEVERAGE", detail="TEH") for i, t in enumerate(HARI)]
        fs = [baca_file_esb(buat_bill(tmp_path / "b.xlsx", bills, awal=A, akhir=Z)),
              baca_file_esb(buat_cogs(tmp_path / "c.xlsx", items, awal=A, akhir=Z))]
        db.simpan_unggahan(c, fs, validasi_unggahan(fs, A, Z), A, Z)
        yield c


def test_sidik_nomor_dinormalkan():
    assert sidik("081234") == sidik("6281234") == sidik("81234") == sidik("+62 812-34")
    assert sidik("") is None and sidik("-") is None


def test_parser_tanpa_data_pribadi(tmp_path):
    f = _file_loyalty(tmp_path)
    t = baca_file_loyalty(f[0])
    assert t.jenis is TRANSAKSI and t.galat == [] and t.cabang == [C]
    teks = t.data.astype(str).to_string()
    assert "Ani" not in teks and "081111" not in teks
    lg = baca_file_loyalty(f[3])
    assert lg.jenis is LOG and list(lg.data["kode"]) == ["daftar", "pendaftaran_janggal"]  # kasir_online dibuang
    assert list(lg.data["keterangan"]) == ["", "nama terlalu pendek"]  # nama & nomor dibuang dari keterangan
    p = baca_file_loyalty(f[4])
    assert p.jenis is PELANGGAN and p.tanggal_snapshot == date(2026, 10, 6)
    assert "Ani" not in p.data.astype(str).to_string()


def test_tanpa_kolom_cabang_ditolak(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("﻿Tanggal,Jumlah Bill,Stempel Diberikan,Omzet Tercatat,Klaim Dibuat\n2026-09-28,1,1,1000,0\n", encoding="utf-8")
    h = baca_file_loyalty(f)
    assert h.jenis is HARIAN and any("Cabang" in c.pesan for c in h.galat)


def test_validasi_lulus_dan_klaim_staf(tmp_path):
    fs = [baca_file_loyalty(f) for f in _file_loyalty(tmp_path)]
    cek = validasi_loyalty(fs, A, Z, [])
    rek = next(c for c in cek if c.nomor == 13)
    assert rek.status == LULUS, rek.rincian
    assert any("klaim milik staf" in r["Hasil"] for r in rek.rincian)
    assert not terblokir(cek) and not butuh_konfirmasi(cek)


def test_validasi_harian_tidak_cocok(tmp_path):
    def ubah(h):
        h[0]["Omzet Tercatat"] = 999
    fs = [baca_file_loyalty(f) for f in _file_loyalty(tmp_path, _harian(ubah))]
    cek = validasi_loyalty(fs, A, Z, [])
    assert butuh_konfirmasi(cek)
    assert next(c for c in cek if c.nomor == 13).status == GAGAL


def test_validasi_periode_salah(tmp_path):
    fs = [baca_file_loyalty(f) for f in _file_loyalty(tmp_path)]
    assert terblokir(validasi_loyalty(fs, A, date(2026, 10, 3), []))


def test_simpan_tumpang_ganti_hapus(tmp_path, con):
    fs = [baca_file_loyalty(f) for f in _file_loyalty(tmp_path)]
    cek = validasi_loyalty(fs, A, Z, db_loyalty.periode_tersimpan(con))
    uid = db_loyalty.simpan(con, fs, cek, A, Z)
    assert con.execute("SELECT count(*) FROM loy_transaksi").fetchone()[0] == 4
    cek2 = validasi_loyalty(fs, A, Z, db_loyalty.periode_tersimpan(con))
    assert next(c for c in cek2 if c.nomor == 14).status == GAGAL
    with pytest.raises(db.TidakBolehDisimpan):
        db_loyalty.simpan(con, fs, cek2, A, Z)
    uid2 = db_loyalty.simpan(con, fs, cek2, A, Z, ganti=True)
    assert con.execute("SELECT count(*) FROM loy_transaksi").fetchone()[0] == 4
    assert con.execute("SELECT count(*) FROM loy_pelanggan").fetchone()[0] == 4  # potret tanggal sama diganti
    r = db.riwayat(con)
    assert r["minggu"][0]["sel"]["Rungkut|loyalty"]["status"] == "lengkap"
    assert db_loyalty.hapus_periode(con, uid2, C)
    assert con.execute("SELECT count(*) FROM loy_transaksi").fetchone()[0] == 0
    assert uid2 != uid


def test_membership(tmp_path, con):
    fs = [baca_file_loyalty(f) for f in _file_loyalty(tmp_path)]
    db_loyalty.simpan(con, fs, validasi_loyalty(fs, A, Z, []), A, Z)
    d = muat(con, C, A, Z)
    m = membership.hitung(con, d, muat(con, C, date(2026, 9, 21), date(2026, 9, 27)), "uji")
    k = m["kartu"]
    assert k["total_member"]["teks"] == "4" and k["terverifikasi"]["teks"] == "1"
    assert k["terverifikasi_baru"]["teks"] == "1" and k["terverifikasi_baru"]["label"] == "dari 2 member baru (potret)"
    assert k["pernah_transaksi"]["teks"] == "3" and k["repeat_sejak_gabung"]["teks"] == "2"
    assert k["member_baru"]["teks"] == "2" and k["member_baru_cabang"]["teks"] == "1"
    assert k["member_aktif"]["teks"] == "3" and k["repeat"]["teks"] == "1"  # nomor A 2× (081111 = 6281111)
    assert k["bill_member"]["teks"] == "4" and k["omzet_member"]["teks"] == "Rp539.000"
    # ESB: 3 + 7 bill Sales = 10; GT 110.000 + 55.000 + 220.000 + 7 × 11.000 = 462.000
    assert k["porsi_bill"]["teks"] == "40,0%" and k["porsi_omzet"]["label"] == "Rp539.000 dari Rp462.000"
    assert k["stempel"]["teks"] == "5" and k["klaim"]["teks"] == "2" and k["klaim"]["label"] == "1 sudah diserahkan"
    q = m["kualitas"]
    assert [x["Nominal"] for x in q["tanpa_esb"]] == ["Rp110.000", "Rp99.000"]
    assert q["ganda"][0]["Dicatat"] == "2×" and q["ganda"][0]["Bill ESB cocok"] == 1
    assert q["janggal"] == 1 and q["rincian"][0]["Keterangan"] == "nama terlalu pendek"
    r = m["rata_bill"]
    # bill F&B member tercocokkan: B1 (110.000), B3 (220.000) -> 165.000; non-member: B2 + 7 X -> (55.000 + 77.000) / 8
    assert r["member"]["teks"] == "Rp165.000" and r["non_member"]["teks"] == "Rp16.500" and r["sampel_kecil"]
    kasir = {x["Kasir"]: x for x in m["per_kasir"]}
    assert kasir["PUJI - Rungkut"]["Tanpa pasangan ESB"] == 1 and kasir["PUJI - Rungkut"]["Member didaftarkan"] == 1
    assert kasir["AISHA - RUNGKUT"]["Hadiah diserahkan"] == 1
    assert not m["banding"]["tersedia"]


def test_membership_tanpa_data(con):
    d = muat(con, "Mawar", A, Z)
    m = membership.hitung(con, d, d, "uji")
    assert not m["tersedia"] and "belum ada CSV loyalty" in m["alasan"]
