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

Laporan ESB opsional (Promotion, Sales Recapitulation Detail, Staff Sales &
Cancel, Cancel Menu Detail, Customer Data) contoh 28 Sep – 4 Okt ada di
`samples/esb-opsional/`; tesnya `tests/test_esb_opsional.py::test_sampel_asli_cocok_dengan_bill_cogs`.

CSV Instagram Insights disimpan per akun di `samples/instagram/<akun>/`
(mis. `samples/instagram/brand/Tayangan Sep 4.csv`).

## Menjalankan tes

```
python -m pytest tests/test_rekonsiliasi_samples.py -v
```

Tes memeriksa: file terbaca tanpa galat, Σ baris data Bill Report sama
persis dengan footer ESB (COGS Report tidak punya footer), periode Bill dan
COGS sama, dan Σ Total COGS = Σ Subtotal Bill per cabang per tanggal.
