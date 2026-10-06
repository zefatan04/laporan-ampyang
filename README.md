# Laporan Ampyang

Dashboard laporan mingguan dan bulanan Kedai Ampyang (Rungkut & Mawar).
Berjalan di laptop, dibuka lewat browser di `http://localhost:8000`, tanpa
perlu internet (kecuali untuk narasi otomatis).

Prinsip utama: **angka yang salah lebih buruk daripada angka yang kosong.**
Data yang tidak ada atau tidak cocok ditampilkan sebagai "Tidak diketahui"
beserta alasannya.

> Status: tahap 2 dari 10 (parser + validasi Bill Report & COGS Report).
> Halaman web belum tersedia.

## Memasang (Windows)

1. Unduh repo ini (tombol **Code → Download ZIP**), ekstrak ke mis. `Documents\laporan-ampyang`.
2. Klik dua kali `scripts\pasang.bat`. Kalau Python belum ada, file ini
   memasangnya lewat winget, lalu minta dijalankan sekali lagi.

## Mengecek file ESB (sementara, lewat terminal)

```
.venv\Scripts\python -m app.cek_file --awal 2026-09-28 --akhir 2026-10-04 bill.xlsx cogs.xlsx
```

## Tes

```
.venv\Scripts\python -m pytest
```

Tes rekonsiliasi dengan file asli memakai folder `samples/` (lihat
`samples/README.md`); dilewati otomatis bila folder itu kosong.
