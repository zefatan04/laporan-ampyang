"""Validasi unggahan CSV loyalty, ditampilkan bersama laporan validasi ESB.

Cek bernomor 11–15 supaya tidak tertukar dengan cek ESB 0–7:
  11 File loyalty terbaca
  12 Cabang & periode
  13 Rekonsiliasi Rekap Harian vs Riwayat Transaksi/Klaim (gagal -> butuh konfirmasi)
  14 Tumpang tindih dengan data loyalty tersimpan
  15 Kelengkapan jenis file
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import pandas as pd

from app.angka import format_rupiah
from app.parser.esb import Catatan
from app.parser.loyalty import HARIAN, KLAIM, LOG, PELANGGAN, TRANSAKSI, HasilLoyalty
from app.pengaturan_bawaan import CABANG
from app.validasi import GAGAL, LULUS, PERINGATAN, TIDAK_BISA, Cek

BERKALA = (TRANSAKSI, KLAIM, HARIAN, LOG)  # file berbasis rentang tanggal


def cabang_file(h: HasilLoyalty) -> list[str]:
    """Cabang dari isi; file kosong -> dari nama file (dicatat sebagai peringatan)."""
    if h.cabang:
        return [c for c in h.cabang if c in CABANG]
    m = re.search(r"-(rungkut|mawar)-", h.nama_file.lower())
    if not m:
        return []
    pesan = "File tanpa baris data; cabang diambil dari nama file."
    if all(c.pesan != pesan for c in h.peringatan):
        h.peringatan.append(Catatan(None, pesan))
    return [m.group(1).capitalize()]


def _tanggal(x):
    return x.date() if isinstance(x, datetime) else x


def cek_terbaca(files: list[HasilLoyalty]) -> list[Cek]:
    hasil = []
    for h in files:
        if h.galat:
            hasil.append(Cek(11, "File loyalty terbaca", GAGAL, f"{len(h.galat)} masalah saat membaca file.",
                             [{"Baris": c.baris or "-", "Masalah": c.pesan} for c in h.galat[:50]], h.nama_file))
        else:
            n = 0 if h.data is None else len(h.data)
            ket = f"{h.jenis.nama}: {n} baris" + (f", snapshot per {h.tanggal_snapshot:%d-%m-%Y}" if h.tanggal_snapshot else "")
            hasil.append(Cek(11, "File loyalty terbaca", PERINGATAN if h.peringatan else LULUS, ket + ".",
                             [{"Catatan": c.pesan} for c in h.peringatan], h.nama_file))
    return hasil


def _waktu_kolom(h: HasilLoyalty):
    return {TRANSAKSI: "waktu", KLAIM: "waktu", LOG: "waktu", HARIAN: "tanggal"}.get(h.jenis)


def cek_cabang_periode(files: list[HasilLoyalty], awal: date, akhir: date, cabang: list[str] | None) -> Cek:
    rincian, gagal = [], False
    for h in files:
        if not h.bisa_dipakai:
            continue
        cb = cabang_file(h)
        if not cb and h.jenis.kode not in ("promo_loyalty",):
            gagal = True
            rincian.append({"File": h.nama_file, "Hal": "Cabang", "Hasil": "tidak bisa ditentukan"})
        if cabang and any(c not in cabang for c in cb):
            gagal = True
            rincian.append({"File": h.nama_file, "Hal": "Cabang", "Hasil": f"{', '.join(cb)} tidak sesuai pilihan"})
        kol = _waktu_kolom(h)
        if kol and len(h.data):
            t = h.data[kol].map(_tanggal)
            luar = sorted({x for x in t if x is not None and (x < awal or x > akhir)})
            if luar:
                gagal = True
                rincian.append({"File": h.nama_file, "Hal": "Tanggal",
                                "Hasil": f"{len(luar)} tanggal di luar periode: " + ", ".join(f"{x:%d-%m-%Y}" for x in luar[:5])})
        if h.jenis is HARIAN:
            ada = set(h.data["tanggal"])
            kurang = [awal + timedelta(days=i) for i in range((akhir - awal).days + 1)
                      if awal + timedelta(days=i) not in ada]
            if kurang:
                gagal = True
                rincian.append({"File": h.nama_file, "Hal": "Tanggal", "Hasil": f"Rekap Harian tidak memuat {len(kurang)} tanggal periode"})
    return Cek(12, "Loyalty: cabang & periode", GAGAL if gagal else LULUS,
               "Cabang dan tanggal semua file loyalty sesuai periode." if not gagal else
               "Ada file loyalty yang cabang atau tanggalnya tidak sesuai.", rincian)


def _per_cabang(files: list[HasilLoyalty], jenis) -> dict[str, pd.DataFrame]:
    hasil = {}
    for h in files:
        if h.bisa_dipakai and h.jenis is jenis:
            for c in cabang_file(h):
                d = h.data[h.data["cabang"] == c] if len(h.data) else h.data
                hasil[c] = pd.concat([hasil[c], d]) if c in hasil else d
    return hasil


def cek_rekonsiliasi(files: list[HasilLoyalty]) -> Cek:
    har, trx, klm = _per_cabang(files, HARIAN), _per_cabang(files, TRANSAKSI), _per_cabang(files, KLAIM)
    if not har:
        return Cek(13, "Loyalty: Rekap Harian vs riwayat", TIDAK_BISA, "Rekap Harian tidak diunggah, tidak bisa dicocokkan.")
    rincian, gagal, catatan = [], False, []
    for c, h in sorted(har.items()):
        t = trx.get(c)
        if t is None:
            rincian.append({"Cabang": c, "Tanggal": "-", "Hal": "Riwayat Transaksi", "Rekap Harian": "-",
                            "Riwayat": "tidak diunggah", "Hasil": "tidak bisa dicek"})
        else:
            tt = t.assign(tgl=t["waktu"].map(lambda x: x.date())) if len(t) else t.assign(tgl=[])
            for _, r in h.iterrows():
                g = tt[tt["tgl"] == r["tanggal"]] if len(tt) else tt
                pasang = [("Jumlah bill", r["bill"], len(g), str),
                          ("Omzet tercatat", r["omzet"], sum(g["nominal"]) if len(g) else 0, format_rupiah),
                          ("Stempel", r["stempel"], int(sum(g["stempel"])) if len(g) else 0, str)]
                for hal, a, b, f in pasang:
                    if a != b:
                        gagal = True
                        rincian.append({"Cabang": c, "Tanggal": f"{r['tanggal']:%d-%m-%Y}", "Hal": hal,
                                        "Rekap Harian": f(a), "Riwayat": f(b), "Hasil": "TIDAK COCOK"})
        k = klm.get(c)
        if k is not None:
            kk = k.assign(tgl=k["waktu"].map(lambda x: x.date())) if len(k) else k.assign(tgl=[])
            for _, r in h.iterrows():
                n = int((kk["tgl"] == r["tanggal"]).sum()) if len(kk) else 0
                if n < r["klaim_dibuat"]:
                    gagal = True
                    rincian.append({"Cabang": c, "Tanggal": f"{r['tanggal']:%d-%m-%Y}", "Hal": "Klaim dibuat",
                                    "Rekap Harian": str(r["klaim_dibuat"]), "Riwayat": str(n), "Hasil": "TIDAK COCOK"})
                elif n > r["klaim_dibuat"]:
                    catatan.append(f"{c} {r['tanggal']:%d-%m}: riwayat klaim {n}, rekap harian {r['klaim_dibuat']} "
                                   "(selisih = klaim milik staf, yang memang tidak dihitung di Rekap Harian).")
    if catatan:
        rincian += [{"Cabang": "", "Tanggal": "", "Hal": "Catatan", "Rekap Harian": "", "Riwayat": "", "Hasil": x} for x in catatan]
    return Cek(13, "Loyalty: Rekap Harian vs riwayat", GAGAL if gagal else LULUS,
               "Rekap Harian cocok dengan Riwayat Transaksi dan Riwayat Klaim per hari." if not gagal else
               "Rekap Harian tidak cocok dengan riwayat; lihat rincian.", rincian)


def cek_tumpang(files: list[HasilLoyalty], awal: date, akhir: date, tersimpan: list[dict]) -> Cek:
    cab = {c for h in files if h.bisa_dipakai and h.jenis in BERKALA for c in cabang_file(h)}
    tump = [t for t in tersimpan if t["cabang"] in cab and t["awal"] <= akhir and t["akhir"] >= awal]
    if tump:
        return Cek(14, "Loyalty: tumpang tindih", GAGAL,
                   "Periode loyalty tumpang tindih dengan data tersimpan. Pilih 'ganti' untuk menimpa.",
                   [{"Detail": f"{t['cabang']}: {t['awal']:%d-%m-%Y} s/d {t['akhir']:%d-%m-%Y} sudah tersimpan"} for t in tump])
    return Cek(14, "Loyalty: tumpang tindih", LULUS, "Tidak ada periode loyalty yang tumpang tindih.")


def cek_kelengkapan(files: list[HasilLoyalty]) -> Cek:
    ada = {}
    for h in files:
        if h.bisa_dipakai:
            for c in cabang_file(h) or ["(semua)"]:
                ada.setdefault(c, set()).add(h.jenis.kode)
    perlu = {"transaksi", "klaim", "harian", "log", "pelanggan"}
    rincian = []
    for c, j in sorted(ada.items()):
        if c == "(semua)":
            continue
        kurang = perlu - j
        rincian.append({"Cabang": c, "Ada": ", ".join(sorted(j)), "Belum ada": ", ".join(sorted(kurang)) or "-"})
    kurang_any = any(r["Belum ada"] != "-" for r in rincian)
    return Cek(15, "Loyalty: kelengkapan file", PERINGATAN if kurang_any else LULUS,
               "Semua jenis file loyalty utama ada untuk tiap cabang." if not kurang_any else
               "Ada jenis file loyalty yang belum diunggah; angka yang membutuhkannya akan 'Tidak diketahui'.",
               rincian)


def validasi_loyalty(files: list[HasilLoyalty], awal: date, akhir: date, tersimpan: list[dict],
                     cabang: list[str] | None = None) -> list[Cek]:
    return (cek_terbaca(files) + [cek_cabang_periode(files, awal, akhir, cabang), cek_rekonsiliasi(files),
                                  cek_tumpang(files, awal, akhir, tersimpan), cek_kelengkapan(files)])


def terblokir(cek: list[Cek]) -> bool:
    return any(c.nomor in (11, 12) and c.status == GAGAL for c in cek)


def butuh_konfirmasi(cek: list[Cek]) -> bool:
    return any(c.nomor == 13 and c.status == GAGAL for c in cek)


SNAPSHOT = PELANGGAN
