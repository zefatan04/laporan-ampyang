"""Nilai bawaan yang nanti bisa diubah dari halaman Pengaturan."""

CABANG = ("Rungkut", "Mawar")

# Jam operasional dipakai untuk menilai hari parsial dan memberi keterangan
# jendela waktu. Indeks 0 = Senin ... 6 = Minggu. (buka, tutup) dalam jam.
JAM_OPERASIONAL = {
    "Rungkut": {0: (7, 21), 1: (7, 21), 2: (7, 21), 3: (7, 21), 4: (7, 21),
                5: (6, 21), 6: (6, 21)},
    "Mawar": {h: (8, 23) for h in range(7)},
}

# Hari parsial: hanya tanggal terakhir di file yang dinilai. Ditandai bila
# jumlah bill < AMBANG_BILL x median hari yang sama dalam seminggu, ATAU
# bill terakhir masuk lebih dari AMBANG_JAM jam sebelum jam tutup.
PARSIAL_AMBANG_BILL = 0.5
PARSIAL_AMBANG_JAM = 2

# Toleransi rekonsiliasi.
TOLERANSI_RUPIAH = 1
TOLERANSI_QTY = 0

# Salah input resep: HPP per unit > FAKTOR x harga jual.
FAKTOR_SALAH_INPUT_COGS = 1.5

# ---------------------------------------------------------------------------
# Kategori menu (bisa diubah di Pengaturan). Dicocokkan setelah teks
# dibersihkan dari spasi berlebih dan dijadikan huruf besar.
# ---------------------------------------------------------------------------
KATEGORI = {
    # Kategori ESB yang bukan makanan/minuman. Tetap masuk Grand Total,
    # dikeluarkan dari rata-rata bill (keputusan 6 Okt 2026: rata-rata bill F&B saja).
    "non_fnb_kategori": ["JASA", "AKSESORIS"],
    "makanan_kategori": ["FOOD", "FOOD PROMO"],
    "kudapan_detail": ["KUDAPAN"],
    "toast_detail": ["TOAST"],
    "paket_detail": ["COMBO MEAL WFA"],
    "minuman_kategori": ["BEVERAGE"],
    "minuman_kemasan_kategori": ["SHOWCASE"],
    "addon_kategori": ["ADD ON"],
    "zuper_food_kategori": ["ZUPER FOOD"],
}

NAMA_KELOMPOK = {
    "makanan_utama": "Makanan utama",
    "kudapan": "Kudapan",
    "toast": "Toast",
    "paket": "Paket (SKU paket)",
    "minuman": "Minuman",
    "minuman_kemasan": "Minuman kemasan (showcase)",
    "addon": "Add-on & kemasan",
    "zuper_food": "Zuper Food",
    "non_fnb": "Non-F&B (jasa & aksesoris)",
    "lainnya": "Belum dipetakan",
}

# Panas/dingin dari nama menu (regex, tanpa membedakan huruf besar-kecil).
SUHU_KATA_PANAS = r"\b(panas|hot)\b"
SUHU_KATA_DINGIN = r"\b(dingin|ice|iced|es)\b"
# Minuman tanpa kata kunci. Keputusan 6 Okt 2026: semuanya dianggap panas
# (asumsi user, bisa diubah per menu di Pengaturan).
SUHU_PER_MENU = {n: "panas" for n in [
    "Juice Jeruk", "Juice Alpukat", "Juice Jambu", "Juice Semangka", "Juice Melon",
    "NATA DE ALEOVERA", "Kencur Mix Berry", "Soda Gembira", "ALANG TIMUN", "Wedang Jahe",
    "KUNYIT ASAM LYCHEE", "Kopi Jahe", "ROSELLA GINGER LIME", "KULIT MANGGIS MIX TELANG TEA",
    "Kopi Butter", "Kopi Ampyang", "Susu Ampyang (Susu + Jahe)",
]}

# Jendela waktu dari Sales In Time; jam akhir inklusif sampai :59.
# `berlaku` = keterangan kapan jendela itu bisa terisi; jendela dengan
# keterangan tidak dipakai untuk membandingkan antar cabang.
JENDELA_WAKTU = [
    {"nama": "Subuh", "dari": 6, "sampai": 6, "berlaku": "hanya Rungkut, Sabtu–Minggu (buka 06.00)"},
    {"nama": "Pagi", "dari": 7, "sampai": 10, "berlaku": None},
    {"nama": "Siang", "dari": 11, "sampai": 13, "berlaku": None},
    {"nama": "Sore", "dari": 14, "sampai": 16, "berlaku": None},
    {"nama": "Malam", "dari": 17, "sampai": 20, "berlaku": None},
    {"nama": "Larut", "dari": 21, "sampai": 22, "berlaku": "hanya Mawar (tutup 23.00)"},
]

# Bill dengan porsi makanan utama sebanyak ini atau lebih ditandai
# kemungkinan katering/pesanan besar di rincian ukuran rombongan.
AMBANG_PORSI_KATERING = 10

# Hari libur nasional 2026. ISI AWAL, BELUM DIVERIFIKASI terhadap SKB 3
# Menteri: dashboard menampilkan peringatan sampai user menandainya benar
# di Pengaturan. Cuti bersama sengaja tidak dimasukkan (dianggap hari
# operasional biasa, keputusan 6 Okt 2026).
HARI_LIBUR = [
    ("2026-01-01", "Tahun Baru Masehi"), ("2026-01-16", "Isra Mikraj"),
    ("2026-02-17", "Tahun Baru Imlek"), ("2026-03-19", "Hari Suci Nyepi"),
    ("2026-03-20", "Idul Fitri"), ("2026-03-21", "Idul Fitri"),
    ("2026-04-03", "Wafat Yesus Kristus"), ("2026-04-05", "Paskah"),
    ("2026-05-01", "Hari Buruh"), ("2026-05-14", "Kenaikan Yesus Kristus"),
    ("2026-05-27", "Idul Adha"), ("2026-05-31", "Waisak"), ("2026-06-01", "Hari Lahir Pancasila"),
    ("2026-06-16", "Tahun Baru Islam"), ("2026-08-17", "Hari Kemerdekaan"),
    ("2026-08-25", "Maulid Nabi"), ("2026-12-25", "Natal"),
]
RAMADAN = [("2026-02-18", "2026-03-19")]
