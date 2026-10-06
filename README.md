# Laporan Ampyang

Dashboard laporan mingguan dan bulanan Kedai Ampyang (Rungkut & Mawar).
Berjalan di laptop, dibuka lewat browser di `http://localhost:8000`, tanpa
perlu internet (kecuali untuk narasi otomatis).

Prinsip utama: **angka yang salah lebih buruk daripada angka yang kosong.**
Data yang tidak ada atau tidak cocok ditampilkan sebagai "Tidak diketahui"
beserta alasannya.

> Status: tahap 9 dari 10. Sudah bisa: upload Bill Report + COGS Report,
> CSV loyalty, dan CSV Instagram Insights; laporan validasi, simpan, riwayat
> data; dashboard kedelapan tab (Overview Omzet, Makanan, Kudapan, Minuman,
> Foot Traffic, Promo, Membership, Sosmed & Campaign; mingguan M1–M5 + Bulan
> Penuh) dengan tombol "Dari mana angka ini?", panel kualitas data, dan
> Pengaturan, plus narasi temuan otomatis (Claude) yang angkanya dicek ke
> data. Ekspor HTML menyusul.

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

## Narasi otomatis (opsional)

Setiap tab punya kotak **Temuan**: 3–6 temuan yang ditulis Claude dari angka
tab itu. Untuk mengaktifkan:

1. Salin `.env.example` menjadi `.env` di folder aplikasi.
2. Isi `ANTHROPIC_API_KEY=` dengan API key dari console.anthropic.com.
3. Tutup dan jalankan ulang aplikasi.

Narasi dibuat hanya saat tombol **Buat narasi** ditekan (butuh internet,
±1 menit per tab) dan disimpan, jadi tidak dibuat ulang setiap halaman dibuka.
Kalau data periode itu berubah, narasi ditandai "data berubah" sampai dibuat
ulang. Setiap angka di narasi dicocokkan otomatis ke data; kalimat dengan
angka yang tidak ada di data dibuang dan bisa dilihat di bawah kotak Temuan.
Yang dikirim ke Claude hanya angka agregat, nama menu, dan catatan kualitas
data: tanpa nomor WA, nama pelanggan, nama kasir, atau alamat IP.

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
