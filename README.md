# Laporan Ampyang

Dashboard laporan mingguan dan bulanan Kedai Ampyang (Rungkut & Mawar).
Berjalan di laptop, dibuka lewat browser di `http://localhost:8000`, tanpa
perlu internet (kecuali untuk narasi otomatis).

Prinsip utama: **angka yang salah lebih buruk daripada angka yang kosong.**
Data yang tidak ada atau tidak cocok ditampilkan sebagai "Tidak diketahui"
beserta alasannya.

> Status: tahap 8 dari 10. Sudah bisa: upload Bill Report + COGS Report,
> CSV loyalty, dan CSV Instagram Insights; laporan validasi, simpan, riwayat
> data; dashboard kedelapan tab (Overview Omzet, Makanan, Kudapan, Minuman,
> Foot Traffic, Promo, Membership, Sosmed & Campaign; mingguan M1–M5 + Bulan
> Penuh) dengan tombol "Dari mana angka ini?", panel kualitas data, dan
> Pengaturan. Narasi otomatis dan ekspor HTML menyusul.

## Memasang (Windows)

1. Unduh repo ini (tombol **Code → Download ZIP**), ekstrak ke mis. `Documents\laporan-ampyang`.
2. Klik dua kali `scripts\pasang.bat`. Kalau Python belum ada, file ini
   memasangnya lewat winget, lalu minta dijalankan sekali lagi.

## Menjalankan

Klik dua kali `scripts\jalankan.bat`. Browser terbuka ke `http://localhost:8000`.
Tutup jendela hitam untuk mematikan aplikasi. Data tersimpan di `data\ampyang.duckdb`.

### Export dari ESB yang dibutuhkan (setiap minggu, Senin–Minggu)

1. **Sales Recapitulation Report** → Sales Report Type: *Bill Report*.
2. **Sales Menu COGS Report** → *Show Menu Package* dicentang.

Keduanya dengan periode yang **sama persis**. Boleh memilih dua cabang
sekaligus dalam satu export.

### Export dari web loyalty (setiap minggu, periode sama)

Dari halaman Ekspor di panel pemilik, per cabang (buka subdomain cabangnya):
Riwayat Transaksi, Riwayat Klaim, Rekap Harian, Log Aktivitas, dan Rekap
Pelanggan. Semua CSV boleh diunggah sekaligus bersama file ESB.

### Export Instagram (opsional)

Dari Meta Business Suite → Insights, unduh CSV per metrik: Tayangan,
Jangkauan, Interaksi, Kunjungan (profil), Klik tautan, Pengikut. File
mingguan dan file rentang panjang boleh dicampur; tanggal yang sama hanya
dipakai sekali. Saat upload, pilih **akun Instagram** (Brand/Rungkut/Mawar),
karena nama akun tidak ada di isi file. Bila CSV tidak bisa diunduh, isi
total mingguan di Pengaturan → Input manual Instagram.

Kampanye iklan (tanggal, cabang sasaran, anggaran, akun) diisi di
Pengaturan → Kampanye iklan.

## Mengecek file ESB lewat terminal (tanpa menyimpan)

```
.venv\Scripts\python -m app.cek_file --awal 2026-09-28 --akhir 2026-10-04 bill.xlsx cogs.xlsx
```

## Tes

```
.venv\Scripts\python -m pytest
```

Tes rekonsiliasi dengan file asli memakai folder `samples/` (lihat
`samples/README.md`); dilewati otomatis bila folder itu kosong.
