"""Pengelompokan baris COGS ke kelompok menu, dan panas/dingin minuman."""

from __future__ import annotations

import re

import pandas as pd

from app import pengaturan_bawaan as B


def _u(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().upper()


def kelompok(kategori: str | None, detail: str | None, aturan: dict) -> str:
    k, d = _u(kategori), _u(detail)
    up = lambda kunci: {_u(x) for x in aturan.get(kunci, [])}
    if k in up("non_fnb_kategori"):
        return "non_fnb"
    if k in up("makanan_kategori"):
        if d in up("paket_detail"):
            return "paket"
        if d in up("kudapan_detail"):
            return "kudapan"
        if d in up("toast_detail"):
            return "toast"
        return "makanan_utama"
    if k in up("minuman_kategori"):
        return "minuman"
    if k in up("minuman_kemasan_kategori"):
        return "minuman_kemasan"
    if k in up("addon_kategori"):
        return "addon"
    if k in up("zuper_food_kategori"):
        return "zuper_food"
    return "lainnya"


def tambah_kelompok(cogs: pd.DataFrame, aturan: dict) -> pd.DataFrame:
    c = cogs.copy()
    c["kelompok"] = [kelompok(k, d, aturan) for k, d in zip(c["menu_category"], c["menu_category_detail"])]
    return c


def suhu(nama_menu: str, per_menu: dict) -> str:
    """'panas' | 'dingin' | 'tidak_diketahui'. Daftar per menu menang atas kata kunci."""
    for n, s in per_menu.items():
        if _u(n) == _u(nama_menu):
            return s
    if re.search(B.SUHU_KATA_PANAS, nama_menu or "", re.IGNORECASE):
        return "panas"
    if re.search(B.SUHU_KATA_DINGIN, nama_menu or "", re.IGNORECASE):
        return "dingin"
    return "tidak_diketahui"
