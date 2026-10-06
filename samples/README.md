# Folder `samples/`

Berisi file export **asli** untuk tes rekonsiliasi. Isinya tidak pernah
masuk git (lihat `.gitignore`), karena memuat omzet dan data pelanggan.

## Susunan

Satu subfolder per cabang per periode. File Bill dan COGS di folder yang
sama dianggap satu pasangan dan dicocokkan satu sama lain.

```
samples/
  2026-09-01_2026-09-07_Rungkut/
    bill.xlsx      <- Sales Recapitulation Report, tipe Bill Report
    cogs.xlsx      <- Sales Menu COGS Report (centang Show Menu Package)
  2026-09-01_2026-09-07_Mawar/
    bill.xlsx
    cogs.xlsx
```

Nama file bebas: jenis laporan dikenali dari isinya.

## Menjalankan tes

```
python -m pytest tests/test_rekonsiliasi_samples.py -v
```

Tes memeriksa tiga hal: file terbaca tanpa galat, Σ baris data sama persis
dengan footer ESB, dan Σ Total COGS sama dengan Σ Subtotal Bill.
