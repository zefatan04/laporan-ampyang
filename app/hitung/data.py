"""Mengambil data satu cabang untuk satu rentang tanggal, beserta cakupannya.

Membedakan tiga keadaan hari, yang tidak boleh tertukar:
  tidak ada data  : belum ada unggahan yang mencakup tanggal itu
  tutup           : tercakup unggahan, tetapi 0 bill Sales
  parsial         : ditandai parsial saat unggah; dikeluarkan dari rata-rata harian
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from app import pengaturan
from app.hitung.kategori import tambah_kelompok
from app.validasi import tandai_salah_input_cogs, tandai_tanpa_hpp


@dataclass
class DataRentang:
    cabang: str
    awal: date
    akhir: date
    bill_semua: pd.DataFrame          # termasuk Non Sales
    bill: pd.DataFrame                # Sales saja
    cogs: pd.DataFrame                # Sales saja, + kelompok, salah_input, tanpa_hpp
    tercakup: list[date]              # bill DAN cogs tersedia
    tutup: list[date]
    parsial: list[date]
    rekon_gagal: list[dict] = field(default_factory=list)  # unggahan yang disimpan walau tidak cocok
    unggahan: list[int] = field(default_factory=list)

    @property
    def hari(self) -> list[date]:
        return [self.awal + timedelta(days=i) for i in range((self.akhir - self.awal).days + 1)]

    @property
    def tanpa_data(self) -> list[date]:
        t = set(self.tercakup)
        return [h for h in self.hari if h not in t]

    @property
    def hari_buka(self) -> list[date]:
        keluar = set(self.tutup) | set(self.parsial)
        return [h for h in self.tercakup if h not in keluar]

    @property
    def ada_data(self) -> bool:
        return bool(self.tercakup)

    @property
    def lengkap(self) -> bool:
        return len(self.tercakup) == len(self.hari)


def _df(con, sql: str, params: list) -> pd.DataFrame:
    # Lewat Arrow supaya DECIMAL tetap Decimal (bukan float) di pandas.
    return con.execute(sql, params).to_arrow_table().to_pandas()


def muat(con, cabang: str, awal: date, akhir: date) -> DataRentang:
    per = con.execute("""
        SELECT unggahan_id, jenis, awal, akhir, hari_parsial, rekonsiliasi_gagal
        FROM periode WHERE cabang = ? AND awal <= ? AND akhir >= ?""", [cabang, akhir, awal]).fetchall()
    hari = [awal + timedelta(days=i) for i in range((akhir - awal).days + 1)]
    cakup = {j: {h for h in hari for p in per if p[1] == j and p[2] <= h <= p[3]} for j in ("bill", "cogs")}
    tercakup = sorted(cakup["bill"] & cakup["cogs"])
    parsial = sorted({p[4] for p in per if p[4] is not None and awal <= p[4] <= akhir})
    rekon_gagal = [{"unggahan_id": p[0], "awal": p[2], "akhir": p[3]} for p in per if p[5] and p[1] == "bill"]

    bill_semua = _df(con, "SELECT * FROM esb_bill WHERE cabang = ? AND sales_date BETWEEN ? AND ?",
                     [cabang, awal, akhir])
    cogs = _df(con, "SELECT * FROM esb_cogs WHERE cabang = ? AND sales_date BETWEEN ? AND ? AND sales_type = 'Sales'",
               [cabang, awal, akhir])
    for df in (bill_semua, cogs):
        df["sales_date"] = pd.to_datetime(df["sales_date"]).dt.date if len(df) else df["sales_date"]
    # Hanya hari yang tercakup kedua file yang dipakai, supaya Bill dan COGS
    # selalu membicarakan hari yang sama.
    t = set(tercakup)
    bill_semua = bill_semua[bill_semua["sales_date"].isin(t)].reset_index(drop=True)
    cogs = cogs[cogs["sales_date"].isin(t)].reset_index(drop=True)
    bill = bill_semua[bill_semua["sales_type"] == "Sales"].reset_index(drop=True)

    cogs = tambah_kelompok(cogs, pengaturan.ambil(con, "kategori"))
    cogs["salah_input"] = pd.Series(tandai_salah_input_cogs(cogs).values if len(cogs) else [], index=cogs.index, dtype=bool)
    cogs["tanpa_hpp"] = pd.Series(tandai_tanpa_hpp(cogs).values if len(cogs) else [], index=cogs.index, dtype=bool)

    per_hari = bill.groupby("sales_date").size().to_dict() if len(bill) else {}
    tutup = [h for h in tercakup if per_hari.get(h, 0) == 0]
    return DataRentang(cabang, awal, akhir, bill_semua, bill, cogs, tercakup, tutup, parsial,
                       rekon_gagal, sorted({p[0] for p in per}))
