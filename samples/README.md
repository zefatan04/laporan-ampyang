# Folder `samples/`

Berisi file export **asli** untuk tes rekonsiliasi. Isinya tidak pernah
masuk git (lihat `.gitignore`), karena memuat omzet dan data pelanggan.

## Susunan

Satu subfolder per periode. Satu export ESB boleh berisi dua cabang
sekaligus (dipisah dari kolom Branch). File Bill dan COGS di folder yang
sama dianggap satu pasangan dan **harus berperiode sama**.

```
samples/
  2026-09-28_2026-10-04/
    bill.xlsx      <- Sales Recapitulation Report, Sales Report Type: Bill Report
    cogs.xlsx      <- Sales Menu COGS Report, Show Menu Package: Yes
```

Nama file bebas: jenis laporan dikenali dari isinya.

CSV Instagram Insights disimpan per akun di `samples/instagram/<akun>/`
(mis. `samples/instagram/brand/Tayangan Sep 4.csv`).

## Menjalankan tes

```
python -m pytest tests/test_rekonsiliasi_samples.py -v
```

Tes memeriksa: file terbaca tanpa galat, Σ baris data Bill Report sama
persis dengan footer ESB (COGS Report tidak punya footer), periode Bill dan
COGS sama, dan Σ Total COGS = Σ Subtotal Bill per cabang per tanggal.
