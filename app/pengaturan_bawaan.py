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
