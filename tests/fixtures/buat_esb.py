"""Pembuat file ESB tiruan untuk tes.

Bentuknya meniru ciri export ESB yang sudah diketahui: metadata di atas,
header di baris 13, data, lalu footer berisi total sebagai teks berformat
Indonesia. Begitu file asli tersedia di samples/, bentuk tiruan ini
dicocokkan ulang dengan aslinya.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl

KOLOM_BILL = ["Sales Number", "Bill Number", "Sales Date", "Sales In Time", "Sales Out Time",
              "Visit Purpose", "Table", "Pax Total", "Subtotal", "Menu Discount", "Bill Discount",
              "Voucher Discount", "Tax Total", "Grand Total", "Promotion", "Cashier"]
KOLOM_COGS = ["Sales Number", "Sales Date", "Menu", "Menu Category", "Menu Category Detail",
              "Qty", "Price", "Total", "Discount Total", "COGS Total", "COGS Total (%)", "Margin"]


def rp_id(n) -> str:
    """Decimal -> '231.973.850,00'."""
    d = Decimal(n).quantize(Decimal("0.01"))
    bulat, _, sen = f"{abs(d):f}".partition(".")
    return ("-" if d < 0 else "") + f"{int(bulat):,}".replace(",", ".") + "," + sen


def _tulis(path: Path, judul: str, kolom: list[str], baris: list[dict], footer: dict,
           cabang: str, awal: date, akhir: date, baris_header: int = 13) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    meta = [
        [judul],
        [],
        ["Period", f": {awal:%d/%m/%Y} - {akhir:%d/%m/%Y}"],
        ["Branch", f": Kedai Ampyang {cabang}"],
        ["Sales Type", ": Sales"],
        ["Sales Report Type", ": All"],
    ]
    for i, r in enumerate(meta, start=1):
        for j, v in enumerate(r, start=1):
            ws.cell(i, j, v)
    for j, k in enumerate(kolom, start=1):
        ws.cell(baris_header, j, k)
    n = baris_header
    for r in baris:
        n += 1
        for j, k in enumerate(kolom, start=1):
            v = r.get(k)
            ws.cell(n, j, float(v) if isinstance(v, Decimal) else v)
    n += 1
    ws.cell(n, 1, "Total")
    for j, k in enumerate(kolom, start=1):
        if k in footer:
            ws.cell(n, j, rp_id(footer[k]))
    wb.save(path)
    return path


def footer_dari(baris: list[dict], kolom: list[str]) -> dict:
    return {k: sum((Decimal(str(r.get(k) or 0)) for r in baris), Decimal(0)) for k in kolom}


def buat_bill(path, baris, cabang="Rungkut", awal=date(2026, 9, 1), akhir=date(2026, 9, 7),
              footer=None, **kw) -> Path:
    kol = ["Pax Total", "Subtotal", "Menu Discount", "Bill Discount", "Voucher Discount",
           "Tax Total", "Grand Total"]
    return _tulis(Path(path), "Sales Recapitulation Report", KOLOM_BILL, baris,
                  footer if footer is not None else footer_dari(baris, kol), cabang, awal, akhir, **kw)


def buat_cogs(path, baris, cabang="Rungkut", awal=date(2026, 9, 1), akhir=date(2026, 9, 7),
              footer=None, **kw) -> Path:
    kol = ["Qty", "Total", "Discount Total", "COGS Total"]
    return _tulis(Path(path), "Sales Menu COGS Report", KOLOM_COGS, baris,
                  footer if footer is not None else footer_dari(baris, kol), cabang, awal, akhir, **kw)


def bill(no, tgl, jam="12:00", sub=50000, pax=1, vp="DINE IN", disk=0, **kw) -> dict:
    sub = Decimal(sub)
    pajak = (sub - Decimal(disk)) * Decimal("0.1")
    r = {"Sales Number": no, "Bill Number": f"B{no}", "Sales Date": tgl.strftime("%d-%m-%Y"),
         "Sales In Time": jam, "Sales Out Time": jam, "Visit Purpose": vp, "Table": "1",
         "Pax Total": pax, "Subtotal": sub, "Menu Discount": Decimal(disk), "Bill Discount": Decimal(0),
         "Voucher Discount": Decimal(0), "Tax Total": pajak, "Grand Total": sub - Decimal(disk) + pajak,
         "Promotion": None, "Cashier": "Kasir A"}
    r.update(kw)
    return r


def item(no, tgl, menu, qty, price, cogs, kat="FOOD", detail="NASI", **kw) -> dict:
    total = Decimal(qty) * Decimal(price)
    r = {"Sales Number": no, "Sales Date": tgl.strftime("%d-%m-%Y"), "Menu": menu,
         "Menu Category": kat, "Menu Category Detail": detail, "Qty": qty, "Price": Decimal(price),
         "Total": total, "Discount Total": Decimal(0), "COGS Total": Decimal(cogs),
         "COGS Total (%)": None, "Margin": total - Decimal(cogs)}
    r.update(kw)
    return r
