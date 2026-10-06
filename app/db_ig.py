"""Validasi dan penyimpanan data harian Instagram Insights.

Satu nilai berlaku per (akun, metrik, tanggal). File panjang dan file mingguan yang
tumpang tindih digabung tanpa dobel: nilai yang sama dilewati, nilai yang
berbeda adalah KONFLIK dan ditampilkan.

- Konflik di dalam satu unggahan (dua file metrik yang sama memberi nilai
  berbeda untuk satu tanggal) -> tidak bisa disimpan; aplikasi tidak memilih.
- Konflik dengan data tersimpan -> butuh centang "ganti"; nilai baru dipakai.

Cakupan (`ig_cakupan`) mencatat rentang tanggal yang diunggah per metrik.
Tanggal di dalam cakupan tanpa baris = "tidak tercatat" (biasanya Pengikut,
karena Instagram tidak menulis hari bernilai 0). Tanggal di luar cakupan =
"tidak diunggah".

Rentang file Pengikut tidak bisa dibaca dari isinya (hari 0 tidak ditulis),
jadi diperluas ke rentang file metrik lain akun yang sama di unggahan yang
sama yang bersinggungan dengannya (ekspor Meta Business Suite selalu
sekaligus untuk rentang yang sama).
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta

from app.db import TidakBolehDisimpan
from app.parser.instagram import AKUN, PER_KODE, HasilIG
from app.validasi import GAGAL, LULUS, PERINGATAN, Cek

SKEMA = """
CREATE SEQUENCE IF NOT EXISTS seq_unggahan_ig START 1;
CREATE TABLE IF NOT EXISTS unggahan_ig (id INTEGER PRIMARY KEY, waktu TIMESTAMP NOT NULL, akun VARCHAR NOT NULL,
    file JSON NOT NULL, validasi JSON NOT NULL);
CREATE TABLE IF NOT EXISTS ig_cakupan (unggahan_id INTEGER NOT NULL, akun VARCHAR NOT NULL, metrik VARCHAR NOT NULL,
    awal DATE NOT NULL, akhir DATE NOT NULL, file VARCHAR NOT NULL);
CREATE TABLE IF NOT EXISTS ig_nilai (unggahan_id INTEGER NOT NULL, akun VARCHAR NOT NULL, metrik VARCHAR NOT NULL,
    tanggal DATE NOT NULL, nilai BIGINT NOT NULL);
"""

# Nilai yang berlaku = dari unggahan terbaru yang memuat tanggal itu. Konflik
# hanya bisa tersimpan lewat centang "ganti", jadi unggahan terbaru = pilihan
# user. Menghapus satu unggahan mengembalikan nilai dari unggahan sebelumnya.
BERLAKU = """SELECT akun, metrik, tanggal, arg_max(nilai, unggahan_id) AS nilai
             FROM ig_nilai GROUP BY akun, metrik, tanggal"""


def pastikan(con):
    con.execute(SKEMA)


def _tgl(t: date) -> str:
    return f"{t:%d-%m-%Y}"


def cakupan_file(files: list[HasilIG]) -> list[tuple[HasilIG, date, date]]:
    """Rentang tiap file yang bisa dipakai. Pengikut diperluas (lihat docstring modul)."""
    pakai = [h for h in files if h.bisa_dipakai and h.periode]
    lain = [h.periode for h in pakai if h.metrik.kode != "pengikut"]
    hasil = []
    for h in pakai:
        a, z = h.periode
        if h.metrik.kode == "pengikut":
            for la, lz in lain:
                if la <= z and lz >= a:
                    a, z = min(a, la), max(z, lz)
        hasil.append((h, a, z))
    return hasil


def tersimpan(con, akun: str) -> dict[tuple[str, date], int]:
    pastikan(con)
    rows = con.execute(f"SELECT metrik, tanggal, nilai FROM ({BERLAKU}) WHERE akun = ?", [akun]).fetchall()
    return {(m, t): v for m, t, v in rows}


def validasi(files: list[HasilIG], akun: str | None, lama: dict[tuple[str, date], int]) -> tuple[list[Cek], dict]:
    """Cek 21–24. Mengembalikan (cek, gabungan) dengan gabungan = {(metrik, tanggal): nilai}."""
    cek = []
    # 21 terbaca
    for h in files:
        if h.galat:
            cek.append(Cek(21, "File Instagram terbaca", GAGAL, f"{len(h.galat)} masalah saat membaca file.",
                           [{"Baris": c.baris or "-", "Masalah": c.pesan} for c in h.galat[:50]], h.nama_file))
        else:
            p = h.periode
            ket = f"{h.metrik.nama}: {len(h.data)} hari" + (f", {_tgl(p[0])} – {_tgl(p[1])}" if p else "")
            cat = [{"Catatan": c.pesan} for c in h.peringatan]
            if h.metrik.kode == "pengikut":
                cat.append({"Catatan": "Instagram tidak menulis hari dengan 0 pengikut baru. Tanggal yang tidak ada di file "
                                       "ditampilkan 'tidak tercatat', bukan 0."})
            if h.metrik.kode == "jangkauan":
                cat.append({"Catatan": "Jangkauan harian tidak bisa dijumlah menjadi jangkauan mingguan (akun yang sama "
                                       "bisa terhitung di beberapa hari). Dashboard memakai rata-rata per hari."})
            cek.append(Cek(21, "File Instagram terbaca", PERINGATAN if h.peringatan else LULUS, ket + ".", cat, h.nama_file))

    # 22 akun
    if akun not in AKUN:
        cek.append(Cek(22, "Akun Instagram", GAGAL,
                       "Pilih akun Instagram (Rungkut, Mawar, atau Brand) di form unggah. Nama akun tidak ada di isi file."))
    else:
        cek.append(Cek(22, "Akun Instagram", LULUS, f"Semua file Instagram di unggahan ini disimpan sebagai akun {akun}."))

    # 23 gabung di dalam unggahan
    gabung: dict[tuple[str, date], int] = {}
    asal: dict[tuple[str, date], str] = {}
    konflik, dobel = [], 0
    for h in files:
        if not h.bisa_dipakai:
            continue
        for t, v in zip(h.data["tanggal"], h.data["nilai"]):
            k = (h.metrik.kode, t)
            if k in gabung:
                if gabung[k] != v:
                    konflik.append({"Metrik": h.metrik.nama, "Tanggal": _tgl(t), "Nilai 1": f"{gabung[k]} ({asal[k]})",
                                    "Nilai 2": f"{v} ({h.nama_file})"})
                else:
                    dobel += 1
                continue
            gabung[k], asal[k] = int(v), h.nama_file
    if konflik:
        cek.append(Cek(23, "Gabung file Instagram", GAGAL,
                       f"{len(konflik)} tanggal punya nilai berbeda di dua file metrik yang sama. Aplikasi tidak memilih "
                       "salah satu; keluarkan file yang salah lalu periksa ulang.", konflik))
    else:
        cek.append(Cek(23, "Gabung file Instagram", LULUS,
                       f"{len(gabung)} nilai harian" + (f"; {dobel} tanggal tumpang tindih bernilai sama, dipakai sekali." if dobel else ".")))

    # 24 dibanding data tersimpan
    beda = [{"Metrik": PER_KODE[m].nama, "Tanggal": _tgl(t), "Tersimpan": lama[(m, t)], "Baru": v}
            for (m, t), v in sorted(gabung.items(), key=lambda x: (x[0][1], x[0][0])) if (m, t) in lama and lama[(m, t)] != v]
    sama = sum(1 for k, v in gabung.items() if lama.get(k) == v)
    baru = sum(1 for k in gabung if k not in lama)
    if beda:
        cek.append(Cek(24, "Dibanding data Instagram tersimpan", PERINGATAN,
                       f"{len(beda)} tanggal sudah tersimpan dengan nilai lain (konflik). Instagram masih memperbarui angka "
                       "beberapa hari setelahnya, jadi ekspor yang lebih baru biasanya lebih tepat. Centang 'ganti' untuk "
                       f"memakai nilai baru. {baru} tanggal baru, {sama} sama dengan yang tersimpan.", beda))
    else:
        cek.append(Cek(24, "Dibanding data Instagram tersimpan", LULUS,
                       f"{baru} nilai harian baru, {sama} sudah tersimpan dengan nilai sama (dilewati)."))
    return cek, {"gabung": gabung, "konflik_lama": len(beda)}


def terblokir(cek: list[Cek]) -> bool:
    return any(c.status == GAGAL and c.nomor in (21, 22, 23) for c in cek)


def simpan(con, files: list[HasilIG], akun: str, cek: list[Cek], gabung: dict, ganti: bool) -> int:
    pastikan(con)
    if terblokir(cek):
        raise TidakBolehDisimpan("Validasi Instagram gagal (file tidak terbaca, akun belum dipilih, atau konflik di dalam unggahan).")
    lama = tersimpan(con, akun)
    beda = [k for k, v in gabung.items() if k in lama and lama[k] != v]
    if beda and not ganti:
        raise TidakBolehDisimpan(f"{len(beda)} nilai Instagram berbeda dengan yang tersimpan. Centang 'ganti' untuk memakai nilai baru.")
    con.execute("BEGIN TRANSACTION")
    try:
        uid = con.execute("SELECT nextval('seq_unggahan_ig')").fetchone()[0]
        from dataclasses import asdict
        con.execute("INSERT INTO unggahan_ig VALUES (?, ?, ?, ?, ?)",
                    [uid, datetime.now(), akun, json.dumps([h.nama_file for h in files if h.bisa_dipakai]),
                     json.dumps([asdict(c) for c in cek], default=str)])
        for h, a, z in cakupan_file(files):
            con.execute("INSERT INTO ig_cakupan VALUES (?, ?, ?, ?, ?, ?)", [uid, akun, h.metrik.kode, a, z, h.nama_file])
        con.executemany("INSERT INTO ig_nilai VALUES (?, ?, ?, ?, ?)",
                        [[uid, akun, m, t, v] for (m, t), v in sorted(gabung.items(), key=lambda x: (x[0][1], x[0][0]))])
        con.execute("COMMIT")
        return uid
    except Exception:
        con.execute("ROLLBACK")
        raise


def hapus_unggahan(con, uid: int) -> bool:
    """Hapus satu unggahan. Tanggal yang juga ada di unggahan lain kembali memakai nilai unggahan itu."""
    pastikan(con)
    if not con.execute("SELECT count(*) FROM unggahan_ig WHERE id = ?", [uid]).fetchone()[0]:
        return False
    con.execute("BEGIN TRANSACTION")
    try:
        for t in ("ig_nilai", "ig_cakupan"):
            con.execute(f"DELETE FROM {t} WHERE unggahan_id = ?", [uid])
        con.execute("DELETE FROM unggahan_ig WHERE id = ?", [uid])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return True


def harian(con, akun: str, awal: date, akhir: date) -> tuple[dict[str, dict[date, int]], dict[str, set[date]]]:
    """(nilai[metrik][tanggal], tanggal tercakup[metrik]) untuk satu akun."""
    pastikan(con)
    nilai: dict[str, dict[date, int]] = defaultdict(dict)
    for m, t, v in con.execute(f"SELECT metrik, tanggal, nilai FROM ({BERLAKU}) WHERE akun = ? AND tanggal BETWEEN ? AND ?",
                               [akun, awal, akhir]).fetchall():
        nilai[m][t] = int(v)
    cak: dict[str, set[date]] = defaultdict(set)
    for m, a, z in con.execute("SELECT metrik, awal, akhir FROM ig_cakupan WHERE akun = ? AND awal <= ? AND akhir >= ?",
                               [akun, akhir, awal]).fetchall():
        t = max(a, awal)
        while t <= min(z, akhir):
            cak[m].add(t)
            t += timedelta(days=1)
    for m, per in nilai.items():  # nilai selalu berarti tercakup
        cak[m] |= set(per)
    return nilai, cak


def riwayat(con) -> dict:
    pastikan(con)
    up = con.execute("""SELECT u.id, u.waktu, u.akun, u.file, min(c.awal), max(c.akhir),
                               (SELECT count(*) FROM ig_nilai h WHERE h.unggahan_id = u.id)
                        FROM unggahan_ig u LEFT JOIN ig_cakupan c ON c.unggahan_id = u.id
                        GROUP BY 1, 2, 3, 4 ORDER BY 2 DESC""").fetchall()
    unggahan = [{"unggahan_id": i, "waktu": w, "akun": a, "file": json.loads(f), "awal": aw, "akhir": ak, "nilai_ditulis": n}
                for i, w, a, f, aw, ak, n in up]
    cak = con.execute("SELECT akun, metrik, awal, akhir FROM ig_cakupan").fetchall()
    minggu = []
    if cak:
        def senin(t):
            return t - timedelta(days=t.weekday())
        m, mulai = senin(max(c[3] for c in cak)), senin(min(c[2] for c in cak))
        while m >= mulai:
            hari = [m + timedelta(days=i) for i in range(7)]
            sel = {}
            for akun in AKUN:
                per = defaultdict(set)
                for a, met, aw, ak in cak:
                    if a == akun:
                        per[met] |= {t for t in hari if aw <= t <= ak}
                n_met = sum(1 for v in per.values() if len(v) == 7)
                ada = sum(1 for v in per.values() if v)
                if not ada:
                    sel[akun] = {"status": "tidak_ada", "keterangan": "tidak ada data"}
                elif n_met == len(PER_KODE):
                    sel[akun] = {"status": "lengkap", "keterangan": "6/6 metrik, 7/7 hari"}
                else:
                    sel[akun] = {"status": "sebagian", "keterangan": f"{n_met}/6 metrik lengkap 7 hari"}
            minggu.append({"senin": m, "minggu": hari[-1], "sel": sel})
            m -= timedelta(days=7)
    return {"unggahan": unggahan, "minggu": minggu, "akun": list(AKUN)}
