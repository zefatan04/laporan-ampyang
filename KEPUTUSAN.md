# Keputusan yang sudah disepakati

Jawaban atas pertanyaan klarifikasi (6 Okt 2026). Kode mengikuti daftar ini;
kalau ada yang berubah, perbarui di sini dulu.

| # | Hal | Keputusan |
|---|---|---|
| 1 | Lokasi | Repo terpisah dari web loyalty (`laporan-ampyang`). |
| 2 | Format ESB | `.xlsx`. File asli untuk tes ditaruh di `samples/` (tidak masuk git). |
| 3 | Cabang di CSV loyalty | Web loyalty akan menambah kolom `Cabang` di ekspor. File lama tanpa kolom itu: user memilih cabang saat unggah. Mode "Semua Cabang" → "cabang tidak diketahui", tidak dibagi rata. |
| 4 | Jendela waktu | Subuh 06:00–06:59 (hanya ada di Rungkut Sabtu–Minggu), Pagi 07–10, Siang 11–13, Sore 14–16, Malam 17–20, Larut 21:00–22:59 (hanya Mawar). Batas jam inklusif sampai :59. Jendela yang hanya berlaku di cabang/hari tertentu diberi keterangan di dashboard, dan perbandingan antar cabang tidak memakai jendela itu. |
| 5 | Hari parsial | User berusaha tidak mengunggah hari parsial. Deteksi tetap ada sebagai pengaman: tanggal terakhir, bill < 50% median hari yang sama, atau bill terakhir > 2 jam sebelum tutup. |
| 6 | Bulan Penuh vs Minggu | Tabel bulanan diberi baris "hari di luar minggu bulan ini (±)" agar selisihnya terlihat. |
| 7 | Porsi paket | Item makanan Rp0 di paket dihitung sebagai porsi untuk perkiraan orang makan & ukuran rombongan; tetap keluar dari qty penjualan reguler. |
| 8 | Member repeat | ≥2 transaksi di dalam periode. Angka ≥2 transaksi sejak gabung ditampilkan terpisah. |
| 9 | Hari libur | Daftar libur nasional + Ramadan bawaan, bisa diedit. Cuti bersama dianggap hari operasional biasa (asumsi). |
| 10 | Panas/dingin | Dari kata kunci nama menu, bisa diedit; tanpa kata kunci → "tidak diketahui". |
| 11 | Pemasangan | Windows. `scripts/pasang.bat` memasang Python (winget) dan paket. |
| 12 | Claude API | Hanya angka agregat dan nama menu yang dikirim; tanpa nomor WA/nama pelanggan. |

## Data sosial media bersifat opsional (6 Okt 2026)

Akun Instagram sedang tidak bisa diakses, jadi seluruh pengolahan sosmed
harus bisa berjalan tanpa data Instagram.

| Kondisi | Perilaku |
|---|---|
| Tidak ada data IG | Tab 8 tetap tampil. Metrik IG: "Tidak diketahui — data Instagram periode ini tidak diunggah". Bagian kampanye yang hanya butuh ESB + form kampanye (tambahan bill vs pembanding, biaya iklan per bill tambahan) tetap dihitung. Panel kualitas data mencatat "Instagram: tidak ada". Narasi diberi tahu data IG tidak ada dan tidak boleh menyimpulkan apa pun soal sosmed. |
| Input manual mingguan | Form total mingguan per akun (tayangan, jangkauan, interaksi, kunjungan profil, klik tautan, pengikut baru), disalin dari aplikasi/Meta Business Suite. Setiap angka berlabel "input manual". Analisa yang butuh data harian (deteksi tanggal iklan, korelasi klik vs bill harian, grafik harian) tidak dihitung: "butuh data harian". |
| CSV harian menyusul | Saat akses pulih, file panjang bisa diunggah untuk mengisi celah. Digabung tanpa dobel (satu nilai per tanggal). Bila ada input manual untuk minggu yang sama, data harian dipakai dan selisihnya terhadap input manual ditampilkan. |
| Export Meta Ads Manager | Tetap opsional dan terpisah dari akses akun IG. |
