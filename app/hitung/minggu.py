"""Aturan minggu: Senin–Minggu. Minggu ke-n suatu bulan = minggu yang hari
SENIN-nya jatuh di bulan itu. Hari awal bulan sebelum Senin pertama masuk
minggu terakhir bulan sebelumnya, tapi tetap dihitung di Bulan Penuh."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
BULAN_PANJANG = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
                 "September", "Oktober", "November", "Desember"]


@dataclass(frozen=True)
class Rentang:
    kode: str     # 'M1'..'M5' atau 'bulan'
    label: str    # 'M2 · 7–13 Sep' / 'Bulan Penuh · Oktober 2026'
    awal: date
    akhir: date

    @property
    def hari(self) -> list[date]:
        return [self.awal + timedelta(days=i) for i in range((self.akhir - self.awal).days + 1)]


def label_tanggal(a: date, b: date) -> str:
    if a == b:
        return f"{a.day} {BULAN[a.month - 1]}"
    if a.month == b.month:
        return f"{a.day}–{b.day} {BULAN[a.month - 1]}"
    return f"{a.day} {BULAN[a.month - 1]}–{b.day} {BULAN[b.month - 1]}"


def minggu_bulan(tahun: int, bulan: int) -> list[Rentang]:
    hasil, n = [], 0
    for hari in range(1, calendar.monthrange(tahun, bulan)[1] + 1):
        t = date(tahun, bulan, hari)
        if t.weekday() == 0:
            n += 1
            akhir = t + timedelta(days=6)
            hasil.append(Rentang(f"M{n}", f"M{n} · {label_tanggal(t, akhir)}", t, akhir))
    return hasil


def bulan_penuh(tahun: int, bulan: int) -> Rentang:
    akhir = date(tahun, bulan, calendar.monthrange(tahun, bulan)[1])
    return Rentang("bulan", f"Bulan Penuh · {BULAN_PANJANG[bulan - 1]} {tahun}", date(tahun, bulan, 1), akhir)


def bulan_sebelumnya(tahun: int, bulan: int) -> tuple[int, int]:
    return (tahun - 1, 12) if bulan == 1 else (tahun, bulan - 1)


def minggu_sebelumnya(r: Rentang) -> Rentang:
    a = r.awal - timedelta(days=7)
    b = a + timedelta(days=6)
    return Rentang("sebelumnya", f"Minggu sebelumnya · {label_tanggal(a, b)}", a, b)


def ringkas_tanggal(daftar) -> str:
    """[1,2,3,5 Okt] -> '1–3 Okt, 5 Okt'. Tanggal berurutan digabung jadi rentang."""
    hs = sorted(set(daftar))
    if not hs:
        return "-"
    bagian, mulai, sebelum = [], hs[0], hs[0]
    for t in hs[1:]:
        if t - sebelum == timedelta(days=1):
            sebelum = t
            continue
        bagian.append(label_tanggal(mulai, sebelum))
        mulai = sebelum = t
    bagian.append(label_tanggal(mulai, sebelum))
    return ", ".join(bagian)
