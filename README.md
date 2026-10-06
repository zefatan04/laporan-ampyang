# Laporan Ampyang

Aplikasi laporan mingguan dan bulanan Kedai Ampyang untuk cabang **Rungkut**
dan **Mawar**. Anda mengunggah file export kasir (ESB), web loyalty, dan
Instagram, lalu aplikasi menyusun dashboard delapan tab: omzet, makanan,
kudapan, minuman, foot traffic, promo, membership, dan sosial media &
kampanye.

Aplikasi berjalan di laptop Anda sendiri dan dibuka lewat browser. Data tidak
dikirim ke mana pun dan tidak butuh internet, kecuali saat memasang pertama
kali.

Pegangan utamanya: **angka yang salah lebih buruk daripada angka yang
kosong.** Kalau sebuah angka tidak bisa dihitung dengan pasti, aplikasi
menulis "Tidak diketahui" beserta alasannya, bukan menebak.

---

## 1. Memasang (sekali saja, Windows)

1. Di halaman GitHub repo ini, tekan **Code → Download ZIP**. Ekstrak ke
   folder yang mudah ditemukan, misalnya `Documents\laporan-ampyang`.
2. Buka folder itu, masuk ke folder `scripts`, lalu klik dua kali
   **`pasang.bat`**.
   - Kalau Python belum ada, file ini memasangnya. Setelah selesai, tutup
     jendela hitamnya lalu klik dua kali `pasang.bat` **sekali lagi**.
   - Butuh internet dan beberapa menit.
3. Kalau muncul tulisan **Selesai**, pemasangan berhasil.

## 2. Membuka aplikasi (setiap kali dipakai)

1. Klik dua kali **`scripts\jalankan.bat`**.
2. Browser terbuka sendiri ke `http://localhost:8000`. Kalau tidak, buka
   alamat itu secara manual.
3. Jendela hitam harus tetap terbuka selama aplikasi dipakai. Tutup jendela
   itu untuk mematikan aplikasi.

---

## 3. Rutinitas mingguan

Satu minggu = **Senin sampai Minggu**. Lakukan setiap Senin untuk minggu yang
baru lewat.

### a. Export dari ESB (wajib)

Untuk periode Senin–Minggu yang sama persis, unduh dua laporan dalam format
**.xlsx**. Boleh memilih Rungkut dan Mawar sekaligus dalam satu export.

| Laporan | Pengaturan |
|---|---|
| Sales Recapitulation Report | Sales Report Type: **Bill Report** |
| Sales Menu COGS Report | Centang **Show Menu Package** |

Ambil export **setelah kedai tutup** hari Minggu. Export yang diambil siang
hari membuat hari terakhir terhitung "parsial".

Laporan ESB **opsional**: unggah bersama Bill dan COGS minggu yang sama
(periode sama persis, pilih Rungkut **dan** Mawar). Masing-masing dicocokkan
dengan Bill/COGS. Kalau cocok, datanya dipakai. Kalau tidak cocok, file itu
saja yang tidak disimpan, sedangkan Bill dan COGS tetap tersimpan.

| Laporan | Pengaturan | Dipakai untuk |
|---|---|---|
| Sales Recapitulation Detail Report | Sales Type: Sales, Non Sales | Metode pembayaran (tab Overview) |
| Promotion Report | Promotion Filter: Detail Bill, Promotion Type: All | Diskon per promo dan menu yang didiskon (tab Promo) |
| Staff Sales & Cancel Report | Sales Type: **Sales**, Status: all | Penjualan dan pembatalan per staf (tab Overview) |
| Cancel Menu Detail Report | Type: Cancel / Void, Status: all | Daftar item yang dibatalkan beserta alasannya (tab Overview) |
| Customer Data Report | Sales Mode: Data Customer | Pelanggan ESB ORDER (tab Membership). Nama dan email tidak dibaca; nomor telepon disimpan sebagai sidik. |

### b. Export dari web loyalty (disarankan)

Di panel pemilik web loyalty, halaman Ekspor, untuk **setiap cabang**:
Riwayat Transaksi, Riwayat Klaim, Rekap Harian, Log Aktivitas, dan Rekap
Pelanggan, dengan periode yang sama.

### c. Export Instagram (opsional)

Dari Meta Business Suite → Insights, unduh CSV per metrik: Tayangan,
Jangkauan, Interaksi, Kunjungan (profil), Klik tautan, dan Pengikut. File
mingguan dan file rentang panjang boleh dicampur; tanggal yang sama hanya
dipakai sekali.

Kalau CSV tidak bisa diunduh, salin total mingguan dari aplikasi Instagram ke
**Pengaturan → Input manual Instagram**.

### d. Unggah

1. Buka menu **Upload**.
2. Isi tanggal mulai (Senin) dan tanggal akhir (Minggu).
3. Kalau mengunggah CSV Instagram, pilih **akun Instagram**-nya (Brand,
   Rungkut, atau Mawar). Satu kali unggah = satu akun Instagram.
4. Tarik semua file ke kotak unggah (ESB, loyalty, dan Instagram boleh
   sekaligus), lalu tekan **Periksa file**.
5. Baca **laporan validasi**:
   - **Lulus** (hijau): aman.
   - **Perlu dibaca** (kuning): bisa disimpan, tapi baca catatannya.
   - **Gagal** (merah): tidak bisa disimpan. Perbaiki file sesuai pesan, lalu
     periksa ulang.
6. Tekan **Simpan**. Kalau periode itu sudah pernah diunggah, centang
   **Ganti data yang sudah tersimpan**.

Salah unggah? Buka **Riwayat data**, cari periodenya, tekan **Hapus**, lalu
unggah ulang.

---

## 4. Membaca dashboard

1. Buka menu **Dashboard**, pilih cabang dan bulan.
2. Pilih minggu (**M1, M2, …**) atau **Bulan Penuh**. Minggu ke-n adalah
   minggu yang hari Seninnya jatuh di bulan itu.
3. Pindah antar tab di baris tab.

Yang perlu diketahui saat membaca:

- **Dari mana angka ini?** di bawah setiap angka membuka rumus, file dan
  kolom sumber, filter, jumlah baris, dan baris yang dikeluarkan.
- **Tidak diketahui — [alasan]**: angka tidak bisa dihitung dengan pasti.
  Alasannya menyebut data apa yang kurang.
- **batas bawah / batas atas**: angka sebenarnya paling sedikit / paling
  banyak segitu, karena ada hari yang datanya tidak ada.
- **estimasi** dan **input manual**: angka bukan dari data harian lengkap.
- **Parsial**: minggu atau bulan yang belum lengkap 7/semua hari.
  Perbandingannya memakai rata-rata per hari buka, bukan total.
- **Kualitas data periode ini** di bagian bawah: file yang ada/tidak ada,
  hasil pencocokan total, hari tutup/parsial, dan baris yang dikeluarkan.
  Baca bagian ini sebelum mengambil kesimpulan.
- Penilaian promo dan kampanye membandingkan dengan **hari yang sama**
  (Senin dengan Senin) dari 4 minggu sebelumnya. Hasilnya perbandingan waktu,
  bukan bukti sebab-akibat.

## 5. Narasi temuan dengan Claude (tanpa API)

Di atas setiap tab ada kotak **Temuan**. Narasinya dibuat oleh Claude di
claude.ai, lalu dicek otomatis oleh aplikasi:

1. Tekan **Unduh paket untuk Claude**. Anda mendapat satu file `.md` berisi
   angka kedelapan tab periode yang sedang dibuka dan instruksi analisa.
2. Buka [claude.ai](https://claude.ai), unggah file itu ke chat (atau salin
   seluruh isinya), lalu kirim.
3. Salin **seluruh** jawaban Claude.
4. Kembali ke dashboard, tekan **Tempel jawaban Claude**, tempel, lalu tekan
   **Cek & simpan**.

Aplikasi mencocokkan setiap angka di jawaban Claude dengan data. Kalimat
yang memuat angka di luar data dibuang, dan daftarnya bisa dilihat di bawah
kotak Temuan. Narasi yang lolos diberi tanda **narasi terverifikasi**.

- "Dugaan:" = kemungkinan penjelasan, bukan fakta dari data.
- "Saran:" = usulan tindakan untuk tim marketing.
- Kalau data periode itu berubah (unggah ulang atau pengaturan diubah), kotak
  Temuan menulis "data berubah sejak narasi dibuat". Ulangi langkah 1–4.

Isi paket hanya angka agregat, nama menu, dan catatan kualitas data. Nomor
WA, nama pelanggan, nama kasir, alamat IP, dan nomor bill tidak ikut.

## 6. Mengirim laporan ke atasan

Di dashboard, tekan **Unduh HTML**. Anda mendapat **satu file** berisi
kedelapan tab periode yang sedang dibuka, termasuk grafik, kotak Temuan, dan
"Dari mana angka ini?". File itu bisa dikirim lewat WhatsApp atau email dan
dibuka di browser mana pun, juga di HP, tanpa aplikasi dan tanpa internet.

### Laporan khusus satu cabang

Centang **Laporan khusus cabang ini** di dashboard sebelum menekan **Unduh
HTML** atau **Unduh paket untuk Claude**. Isinya hanya data cabang yang
dipilih: tanpa angka gabungan semua cabang (misalnya total member web
loyalty) dan tanpa angka cabang lain (misalnya bagian cabang lain dari
kampanye bersama). Narasi untuk laporan khusus dibuat dan disimpan terpisah:
unduh paket dan tempel jawaban Claude **saat centang ini aktif**.

Nama file HTML-nya sama dengan laporan biasa, jadi periksa centangnya
sebelum mengirim.

## 7. Pengaturan

Isi sekali, lalu perbarui bila ada perubahan. Perubahan langsung berlaku ke
semua data, termasuk data lama.

| Bagian | Kapan diisi |
|---|---|
| Hari libur nasional & Ramadan | Cocokkan sekali dengan SKB 3 Menteri, lalu centang "sudah dicocokkan". Sebelum dicentang, dashboard menampilkan peringatan. |
| Target omzet | Opsional. Kosongkan bila tidak ada target. |
| Daftar promo | Setiap ada promo baru: nama, tanggal, cabang, nama promo di ESB, menu promo. |
| Kampanye iklan | Setiap ada iklan berbayar: tanggal, cabang sasaran, anggaran, akun Instagram. |
| Daftar konten | Opsional: tanggal, akun, format, topik postingan. |
| Input manual Instagram | Hanya bila CSV Instagram tidak bisa diunduh. |
| Menu baru yang dipantau | Setiap ada menu baru yang ingin dilihat penjualannya. |
| Kategori menu, minuman panas/dingin | Bila ESB menambah kategori atau menu minuman baru. |

---

## 8. Kalau ada masalah

| Masalah | Yang dilakukan |
|---|---|
| Browser menulis "tidak dapat terhubung" | Jendela hitam `jalankan.bat` mungkin tertutup. Klik dua kali lagi. |
| Validasi "Gagal" karena periode Bill dan COGS beda | Export ulang keduanya dengan tanggal yang sama persis. |
| Validasi "Gagal" karena total tidak cocok | Export ulang dari ESB. Kalau tetap gagal, kirim kedua file ke pengelola aplikasi. |
| Banyak "Tidak diketahui" | Baca alasannya. Biasanya ada file yang belum diunggah (lihat Kualitas data dan Riwayat data). |
| Hari terakhir tertulis "parsial" | Export diambil sebelum tutup. Export ulang setelah tutup lalu unggah dengan "ganti". |
| Ingin memindahkan aplikasi ke laptop lain | Pasang di laptop baru, lalu salin folder `data` dari laptop lama ke folder aplikasi di laptop baru. |

**Cadangan data**: seluruh data ada di folder `data` (file
`ampyang.duckdb`). Salin folder itu ke flashdisk/Google Drive secara
berkala. File ini berisi data omzet, jadi simpan di tempat yang aman.

---

## Untuk pengelola teknis

- Keputusan dan temuan per tahap: `KEPUTUSAN.md`. Baca sebelum mengubah rumus.
- Menjalankan tanpa script: `python run.py` (hanya mendengarkan di
  `127.0.0.1`). Variabel: `AMPYANG_DB`, `AMPYANG_PORT`, `AMPYANG_TANPA_BROWSER=1`.
- Mengecek file ESB tanpa menyimpan:
  `.venv\Scripts\python -m app.cek_file --awal 2026-09-28 --akhir 2026-10-04 bill.xlsx cogs.xlsx`
- Tes:
  ```
  .venv\Scripts\python -m pip install -r requirements-tes.txt
  .venv\Scripts\python -m playwright install chromium
  .venv\Scripts\python -m pytest
  ```
  `tests/test_browser.py` membuka semua halaman dan kedelapan tab (laptop dan
  lebar 390px) serta file HTML ekspor, dan gagal bila ada error di konsol
  browser. Tes ini dilewati bila Playwright/Chromium belum dipasang. Tes
  rekonsiliasi dengan file asli memakai folder `samples/` (lihat
  `samples/README.md`) dan dilewati bila folder itu kosong.
- Narasi lewat Claude API (opsional, saat ini tidak dipakai): isi
  `ANTHROPIC_API_KEY` di `.env` lalu jalankan ulang. Tombol **Buat lewat API**
  muncul di kotak Temuan, dengan verifikasi angka yang sama (`app/narasi.py`).
