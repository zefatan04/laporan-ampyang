"""Setiap angka dashboard dibungkus `Nilai`: angka + teks tampilan + asal-usul.

Asal-usul (`asal`) adalah isi tombol "Dari mana angka ini?": rumus, file &
kolom sumber, filter, jumlah baris, dan baris yang dikeluarkan beserta
alasannya. Angka yang tidak bisa dihitung tetap punya Nilai, dengan
status 'tidak_diketahui' dan alasan.
"""

from __future__ import annotations

from decimal import Decimal

from app.angka import format_angka, format_persen, format_rupiah

PASTI, ESTIMASI, TIDAK_DIKETAHUI = "pasti", "estimasi", "tidak_diketahui"


def asal(rumus: str, sumber: list[str], filter: list[str] | None = None, baris: int | None = None,
         dikeluarkan: list[dict] | None = None, catatan: list[str] | None = None) -> dict:
    return {"rumus": rumus, "sumber": sumber, "filter": filter or [], "baris": baris,
            "dikeluarkan": [d for d in (dikeluarkan or []) if d.get("jumlah")], "catatan": catatan or []}


def _teks(v, jenis: str) -> str:
    if jenis == "rupiah":
        return format_rupiah(v)
    if jenis == "persen":
        return format_persen(v)
    if jenis == "desimal":
        return format_angka(v, 1)
    return format_angka(v)


def nilai(v, jenis: str, a: dict, status: str = PASTI, peringatan: list[str] | None = None) -> dict:
    """jenis: 'rupiah' | 'angka' | 'desimal' | 'persen' (v dalam satuan persen)."""
    teks = _teks(v, jenis)
    if status == ESTIMASI:
        teks += " (estimasi)"
    return {"nilai": None if v is None else str(v), "teks": teks, "jenis": jenis, "status": status,
            "alasan": None, "asal": a, "peringatan": peringatan or []}


def tidak_diketahui(alasan: str, a: dict | None = None) -> dict:
    return {"nilai": None, "teks": f"Tidak diketahui — {alasan}", "jenis": None, "status": TIDAK_DIKETAHUI,
            "alasan": alasan, "asal": a, "peringatan": []}


def bagi(a, b) -> Decimal | None:
    if a is None or b in (None, 0):
        return None
    return Decimal(a) / Decimal(b)


def persen(a, b) -> Decimal | None:
    h = bagi(a, b)
    return None if h is None else h * 100


def jumlah(seri) -> Decimal:
    return sum((Decimal(v) for v in seri if v is not None), Decimal(0))
