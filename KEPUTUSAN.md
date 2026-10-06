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

## Temuan dari export ESB asli (28 Sep – 4 Okt 2026)

- Satu export berisi **dua cabang** sekaligus (metadata `Branch` berisi
  daftar, kolom `Branch` per baris). Parser memecah per cabang; unggahan
  tidak lagi wajib satu cabang.
- Metadata `Sales Type: Sales, Non Sales`. Baris Non Sales ikut footer,
  dikeluarkan dari analisa.
- Bill Report: footer satu baris tanpa label, angka teks format Indonesia
  di bawah kolomnya. `VAT Total` dan `DPP` tidak ditotal di footer.
  Ada `Service Charge Total` (Rungkut ±3%, Mawar 0) dan `Rounding Total`:
  rekonsiliasi omzet = Subtotal − diskon + service charge + pajak + pembulatan.
- **Sales Menu COGS Report tidak punya footer.** Kebenarannya dicek lewat
  Σ Total COGS = Σ Subtotal Bill per cabang per tanggal (terbukti: 6 hari,
  861 bill, selisih Rp0).
- Nilai uang berpecahan sampai 4 desimal; dibaca sampai 6 desimal, dibulatkan
  hanya di tampilan.
- Teks kategori diakhiri spasi (`'TEH '`, `'ADD ON '`); dibersihkan.
- Kolom `Customer Name` dan `Additional Info` berisi nama pelanggan; tidak dibaca.

## Kategori, rata-rata bill, suhu, akun IG (6 Okt 2026)

| Hal | Keputusan |
|---|---|
| SHOWCASE | Sub-kelompok "minuman kemasan" di tab Minuman; tidak ikut panas/dingin & attach rate utama. |
| ADD ON | Kelompok "Add-on & kemasan", tidak masuk tab Makanan/Minuman. |
| ZUPER FOOD | Kelompok sendiri, tidak dicampur makanan utama Ampyang (juga tidak dihitung porsi orang makan). |
| JASA, AKSESORIS | Non-F&B. Tetap di Grand Total; omzetnya ditampilkan terpisah di Overview (basis Subtotal). |
| Rata-rata bill | **F&B saja.** Bill berisi item non-F&B saja dan bill campuran dikeluarkan (Grand Total bill campuran tidak bisa dipisah tanpa estimasi); jumlahnya ditampilkan di "Dari mana angka ini?". |
| Panas/dingin | Dari 17 minuman tanpa kata kunci: jus (Jeruk, Alpukat, Jambu, Semangka, Melon) dan Soda Gembira **dingin**, 11 lainnya **panas** (asumsi user), bisa diubah per menu di Pengaturan. |
| Akun Instagram | CSV di folder `Sosmed` = akun **Brand**. |

Temuan tambahan dari data: anak paket WFA (Rp0) berisi kudapan + minuman,
bukan makanan utama. "Paket Catering" tercatat FOOD / SPESIAL MENU dengan
qty puluhan per bill: ikut dihitung porsi, dan bill ≥10 porsi disebut
terpisah di rincian ukuran rombongan.

Hari libur 2026 di Pengaturan adalah isi awal yang **belum diverifikasi**;
dashboard menampilkan peringatan sampai user mencentang "sudah dicocokkan".

## Tab Makanan, Kudapan, Minuman (tahap 5)

- **Discount Total di COGS Report** terbukti = diskon menu + diskon bill
  yang dialokasikan ESB ke tiap item (Rungkut M4: Rp576.700 = 118.600 +
  458.100). Kolom Margin ESB = Total − Discount Total − COGS Total.
- Omzet menu = Total (kotor, = basis Subtotal). Omzet bersih = Total −
  Discount Total. **Margin = omzet bersih − COGS**, hanya baris Price > 0,
  COGS > 0, bukan salah input.
- **Attach rate** (definisi dipilih Claude, bisa diubah bila perlu):
  bill yang memuat item kelompok itu ÷ **bill F&B** (bill yang memuat
  minimal satu item makanan/minuman; bill sewa raket/mahjong saja tidak
  dihitung). Dua versi: berbayar saja (utama) dan termasuk item paket Rp0.
  Kudapan: dengan dan tanpa toast. Minuman: tanpa dan dengan minuman kemasan.
- **Minuman per bill** = Σ qty minuman (BEVERAGE) ÷ bill F&B.
- **Harga** per menu per periode = modus Price baris berbayar; bila seri,
  diambil yang tertinggi.
- **Menu baru** = terjual di periode ini dan tidak pernah terjual berbayar
  di semua data tersimpan sebelumnya (cabang yang sama). **Menu hilang** =
  terjual di periode sebelumnya, tidak di periode ini.
- Menu baru yang dipantau bisa didaftarkan di Pengaturan (nama, tanggal
  mulai, tab); penjualannya dihitung sejak tanggal mulai.
- Cek silang: Σ omzet semua kelompok = Σ Subtotal Bill (Sales), selisih Rp0
  untuk kedua cabang minggu 28 Sep – 4 Okt.

## HPP terlalu rendah & attach rate (7 Okt 2026)

- Baris dengan HPP/unit **< 5% harga jual** (dan COGS > 0) ditandai "HPP
  terlalu rendah" dan dikeluarkan dari margin, sama seperti HPP terlalu
  tinggi (> 1,5×). Contoh nyata: Juice Jambu HPP Rp21–32 per gelas untuk
  harga Rp18.900; Teh O Panas HPP Rp286–388 untuk harga Rp13.000.
- Definisi attach rate (pembagi = bill F&B) **dikonfirmasi user**.

## Tab Promo (tahap 6)

- Promo didaftarkan di Pengaturan: nama, mulai, selesai, cabang
  (Rungkut/Mawar/keduanya), nama di kolom Promotion ESB, menu promo.
- **Pembanding A** = rata-rata hari yang sama dalam seminggu dari 4 minggu
  sebelum promo. **Pembanding B** = 4 minggu sebelum + 4 minggu sesudah
  (bila ada datanya). Hari libur/Ramadan, tutup, parsial, dan tanpa data
  tidak dipakai, baik sebagai pembanding maupun sebagai hari promo yang dinilai.
- **Kesimpulan** memakai omzet cabang (Grand Total) di hari promo vs
  pembanding, sisi **pesimis** dari A/B. Ambang netral ±5% (Pengaturan).
  Menambah: pesimis > +5%. Mengurangi: optimis < −5%. Netral: keduanya di
  dalam ±5%. Selain itu, atau pembanding A < 14 hari buka, atau < 50% hari
  promo punya pembanding: **Belum bisa disimpulkan** dengan alasan.
- Tanda kanibalisasi: menu promo naik sementara omzet menu non-promo turun
  lebih dari ambang.
- Kolom Promotion ESB yang dianggap **internal** (tidak dinilai): bawaan
  "Discount Karyawan 10 %" dan "Discount BOD"; bisa diubah di Pengaturan.
- Total diskon per promo hanya dari bill yang memakai satu promo; bill
  dengan beberapa promo dihitung terpisah.
- "Menu kena diskon menu" hanya dari bill yang diskonnya murni diskon menu,
  karena Discount Total di COGS juga berisi alokasi diskon bill.
- **Paket**: HPP = Σ COGS item pendamping Rp0 di bill yang sama; harga
  normal isi = modus harga jual berbayar item itu di semua data cabang ini;
  rincian hanya dari bill berisi tepat 1 paket. Harga normal item yang tidak
  pernah dijual berbayar di cabang itu = tidak diketahui (tidak dipinjam dari
  cabang lain).
- Promotion Report, Staff Sales & Cancel, dan Cancel Menu Detail belum
  diolah; semua angka promo saat ini dari kolom Promotion di Bill Report.

## Loyalty & tab Membership (tahap 7)

- "Discount Karyawan 10 %" dan "Discount BOD" = diskon internal (dikonfirmasi user).
- CSV loyalty dibaca dari isinya (header), UTF-8 BOM, kolom `Cabang` wajib
  (sudah ada sejak perbaikan ekspor web loyalty). File kosong: cabang dari nama file.
- Upload ESB dan loyalty disatukan: .xlsx = ESB, .csv = dikenali dari isi.
  Unggahan boleh hanya loyalty; cek ESB hanya berjalan bila ada file ESB.
- **Privasi**: nomor WA tidak disimpan, hanya sidik SHA-256 (nomor
  dinormalkan ke 08xx). Nama member, catatan pesanan, alergi, menu favorit,
  IP member, dan nama/nomor di keterangan log tidak disimpan.
- **Nominal Bill loyalty = Grand Total ESB** (terbukti: 49 dari 54
  transaksi 28 Sep – 4 Okt cocok persis; tidak ada yang cocok ke Subtotal).
- Setiap transaksi member dicocokkan ke satu bill ESB (cabang & tanggal
  sama, GT selisih ≤ Rp1, jam masuk terdekat sebelumnya). Yang tidak punya
  pasangan dan yang tercatat ganda (member, tanggal, nominal sama) tampil di
  bagian kualitas.
- Validasi loyalty: Rekap Harian = Riwayat Transaksi per hari (bill,
  omzet, stempel). Riwayat Klaim boleh lebih banyak dari Rekap Harian
  (klaim staf tidak dihitung di Rekap Harian).
- Total member/terverifikasi/pernah transaksi dari potret Rekap Pelanggan
  (tanggal potret = tanggal di nama file); dipakai potret terdekat ≥ akhir
  periode, kalau tidak ada potret terakhir dengan catatan.
- Member baru = Σ "Member Baru (semua cabang)" Rekap Harian (lintas
  cabang); per cabang = "didaftarkan kasir cabang ini".
- Rata-rata bill member vs non-member = bill F&B ESB (Grand Total) yang
  tercocokkan vs sisanya; sampel < 10 bill diberi tanda.

Temuan data asli (Rungkut, 28 Sep – 4 Okt): 6 transaksi member tanpa
pasangan bill ESB, termasuk 1 nominal Rp592.900 yang dicatat 2× (14:37
dan 15:01) untuk member yang sama padahal di ESB hanya ada 1 bill; 5 lainnya
dicatat AISHA pukul 15:20–15:24 pada hari yang sama dengan tanda
pendaftaran beruntun di log Mawar.
