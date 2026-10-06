"""Membaca dan menampilkan angka berformat Indonesia.

Uang disimpan sebagai Decimal (dua angka di belakang koma, persis seperti
ESB), tidak pernah float. Pembulatan hanya terjadi di fungsi format_*.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

SEN = Decimal("0.01")
# ESB menyimpan nilai uang dengan pecahan hingga 4 desimal (mis. 4183.296,
# 2583.3333). Dibaca sampai 6 desimal supaya penjumlahan tidak bergeser dari
# footer; pembulatan ke rupiah hanya di tampilan.
PRESISI = Decimal("0.000001")

# "231.973.850,00", "-1.500", "(2.000,50)", "12,5"
_POLA_ID = re.compile(r"^[+-]?\d{1,3}(\.\d{3})*(,\d+)?$|^[+-]?\d+(,\d+)?$")


class AngkaTidakValid(ValueError):
    pass


def baca_angka(nilai) -> Decimal | None:
    """Ubah isi sel menjadi Decimal.

    Sel kosong -> None (bukan 0: kosong dan nol itu beda arti).
    Sel numerik dari Excel dipakai apa adanya. Teks dibaca dengan format
    Indonesia: titik pemisah ribuan, koma pemisah desimal. Teks yang tidak
    cocok pola itu ditolak, tidak ditebak.
    """
    if nilai is None:
        return None
    if isinstance(nilai, bool):
        raise AngkaTidakValid(f"nilai boolean bukan angka: {nilai!r}")
    if isinstance(nilai, int):
        return Decimal(nilai)
    if isinstance(nilai, float):
        # repr float terpendek lalu dibulatkan ke PRESISI, supaya 0.1+0.2
        # tidak membawa ekor 0.30000000000000004 ke dalam jumlah.
        return Decimal(repr(nilai)).quantize(PRESISI, rounding=ROUND_HALF_UP)
    if isinstance(nilai, Decimal):
        return nilai
    teks = str(nilai).strip().replace("Rp", "").replace(" ", "").replace(" ", "")
    if teks in ("", "-"):
        return None
    negatif = False
    if teks.startswith("(") and teks.endswith(")"):
        negatif, teks = True, teks[1:-1]
    if not _POLA_ID.match(teks):
        raise AngkaTidakValid(f"format angka tidak dikenali: {nilai!r}")
    teks = teks.replace(".", "").replace(",", ".")
    try:
        hasil = Decimal(teks)
    except InvalidOperation as e:  # pragma: no cover - sudah dijaga regex
        raise AngkaTidakValid(f"format angka tidak dikenali: {nilai!r}") from e
    return -hasil if negatif else hasil


_BULAN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mei": 5, "jun": 6,
    "jul": 7, "aug": 8, "agu": 8, "agt": 8, "ags": 8, "sep": 9, "oct": 10,
    "okt": 10, "nov": 11, "dec": 12, "des": 12,
}


def baca_tanggal(nilai) -> date | None:
    """Tanggal dari sel. Hanya format hari-bulan-tahun atau ISO.

    Format bulan-hari-tahun (gaya Amerika) sengaja tidak diterima: 03-09
    bisa 3 September atau 9 Maret, dan menebak itu persis yang dilarang.
    """
    if nilai is None:
        return None
    if isinstance(nilai, datetime):
        return nilai.date()
    if isinstance(nilai, date):
        return nilai
    teks = str(nilai).strip()
    if not teks:
        return None
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$", teks)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?:\s.*)?$", teks)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    m = re.match(r"^(\d{1,2})[\s-]+([A-Za-z]{3})[A-Za-z]*[\s-]+(\d{4})(?:\s.*)?$", teks)
    if m and m[2].lower() in _BULAN:
        return date(int(m[3]), _BULAN[m[2].lower()], int(m[1]))
    raise ValueError(f"format tanggal tidak dikenali: {nilai!r}")


def baca_jam(nilai) -> tuple[int, int] | None:
    """(jam, menit) dari sel waktu: datetime, time, atau teks 'HH:MM[:SS]'."""
    if nilai is None:
        return None
    if hasattr(nilai, "hour") and hasattr(nilai, "minute"):
        return nilai.hour, nilai.minute
    teks = str(nilai).strip()
    if not teks:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})(?::\d{2})?", teks)
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        raise ValueError(f"format jam tidak dikenali: {nilai!r}")
    return int(m[1]), int(m[2])


def format_rupiah(nilai: Decimal | int | None) -> str:
    if nilai is None:
        return "Tidak diketahui"
    bulat = int(Decimal(nilai).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    tanda = "−" if bulat < 0 else ""
    return f"{tanda}Rp{abs(bulat):,}".replace(",", ".")


def format_angka(nilai: Decimal | int | None, desimal: int = 0) -> str:
    if nilai is None:
        return "Tidak diketahui"
    q = Decimal(1).scaleb(-desimal)
    d = Decimal(nilai).quantize(q, rounding=ROUND_HALF_UP)
    tanda = "−" if d < 0 else ""
    bulat, _, pecahan = f"{abs(d):f}".partition(".")
    bulat = f"{int(bulat):,}".replace(",", ".")
    return f"{tanda}{bulat},{pecahan}" if desimal else f"{tanda}{bulat}"


def format_persen(nilai: Decimal | float | None, desimal: int = 1) -> str:
    """nilai dalam satuan persen (12.5 -> '12,5%')."""
    if nilai is None:
        return "Tidak diketahui"
    return f"{format_angka(Decimal(str(nilai)), desimal)}%"
