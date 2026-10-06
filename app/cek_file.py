"""Cek file ESB dari terminal, tanpa menyimpan apa pun.

    python -m app.cek_file --cabang Rungkut --awal 2026-09-01 --akhir 2026-09-07 bill.xlsx cogs.xlsx
"""

import argparse
from datetime import date

from app.parser.esb import baca_file_esb
from app.validasi import validasi_unggahan

IKON = {"lulus": "[LULUS]", "gagal": "[GAGAL]", "peringatan": "[PERINGATAN]", "tidak_bisa": "[TIDAK BISA]"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cabang", required=True, choices=["Rungkut", "Mawar"])
    ap.add_argument("--awal", required=True, type=date.fromisoformat)
    ap.add_argument("--akhir", required=True, type=date.fromisoformat)
    ap.add_argument("--rincian", type=int, default=15, help="maks. baris rincian per cek")
    ap.add_argument("file", nargs="+")
    a = ap.parse_args(argv)

    files = [baca_file_esb(f) for f in a.file]
    lap = validasi_unggahan(files, a.cabang, a.awal, a.akhir)
    for c in lap.cek:
        asal = f"  ({c.file})" if c.file else ""
        print(f"\n{IKON[c.status]} {c.nomor}. {c.nama}{asal}\n    {c.ringkasan}")
        for r in c.rincian[: a.rincian]:
            print("      - " + " · ".join(f"{k}: {v}" for k, v in r.items()))
        if len(c.rincian) > a.rincian:
            print(f"      … dan {len(c.rincian) - a.rincian} baris lagi")
    print()
    if lap.terblokir:
        print("HASIL: tidak bisa disimpan (file wajib tidak ada/tidak terbaca, atau cabang/periode salah).")
    elif lap.butuh_konfirmasi:
        print("HASIL: boleh disimpan hanya dengan centang 'simpan walau tidak cocok'.")
    else:
        print("HASIL: siap disimpan.")


if __name__ == "__main__":
    main()
