"""Pembuat CSV loyalty tiruan dengan header persis seperti ekspor asli (UTF-8 BOM)."""

import csv
from pathlib import Path

HEADER = {
    "transaksi": ["Waktu", "Nomor WA", "Nama Member", "Nominal Bill", "Stempel Didapat", "Stempel Hangus",
                  "Stempel Setelahnya", "Dicatat Kasir", "Catatan Pesanan", "Cabang"],
    "klaim": ["Waktu Klaim", "Nomor WA", "Nama Member", "Tingkat", "Nama Hadiah", "Kode", "Status", "Waktu Diserahkan",
              "Diserahkan Kasir", "IP Saat Klaim", "Cabang"],
    "harian": ["Tanggal", "Jumlah Bill", "Stempel Diberikan", "Omzet Tercatat", "Klaim Dibuat", "Hadiah Diserahkan",
               "Member Baru (semua cabang)", "Login Berhasil", "Member Baru (didaftarkan kasir cabang ini)", "Cabang"],
    "pelanggan": ["Nomor WA", "Nama", "Tanggal Gabung", "Status Verifikasi", "Stempel Sekarang", "Stempel Seumur Hidup",
                  "Jumlah Transaksi", "Total Belanja", "Rata-rata Belanja", "Belanja Terakhir", "Jumlah Klaim",
                  "Klaim Diambil", "Menu Favorit", "Alergi", "Kasir Pendaftar", "Cabang Pendaftaran", "Cabang"],
    "log": ["Waktu", "Kode Kejadian", "Kejadian", "Nama Akun", "Nomor WA/Login", "Alamat IP", "Keterangan", "Cabang"],
}


def tulis(path, jenis, baris) -> Path:
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER[jenis])
        for r in baris:
            w.writerow([r.get(k, "-") for k in HEADER[jenis]])
    return path
