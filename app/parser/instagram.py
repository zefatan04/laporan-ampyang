"""Membaca CSV Instagram Insights (ekspor Meta Business Suite).

Format terbukti dari ekspor asli akun Brand (Agustus–September 2026):
UTF-16 LE dengan BOM, baris 1 `sep=,`, baris 2 judul metrik, baris 3
`"Tanggal","Primary"`, lalu satu baris per hari `"2026-09-21T00:00:00","137"`.

Satu file = satu metrik satu akun. Akun (Rungkut/Mawar/Brand) TIDAK ada di
isi file, jadi dipilih user saat unggah.

Pengikut: Instagram tidak menulis hari bernilai 0, jadi baris yang hilang
tidak boleh dianggap 0. Tanggal itu ditampilkan "tidak tercatat".
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from app.parser.esb import Catatan

AKUN = ("Rungkut", "Mawar", "Brand")


@dataclass(frozen=True)
class MetrikIG:
    kode: str
    nama: str
    judul: str  # baris ke-2 file


METRIK = (
    MetrikIG("tayangan", "Tayangan", "Tayangan"),
    MetrikIG("jangkauan", "Jangkauan", "Jangkauan"),
    MetrikIG("interaksi", "Interaksi konten", "Interaksi konten"),
    MetrikIG("kunjungan", "Kunjungan profil", "Kunjungan Profil Instagram"),
    MetrikIG("klik", "Klik tautan", "Klik tautan Instagram"),
    MetrikIG("pengikut", "Pengikut baru", "Pengikut Instagram"),
)
PER_KODE = {m.kode: m for m in METRIK}
PER_JUDUL = {m.judul.lower(): m for m in METRIK}

_WAKTU = re.compile(r"^(\d{4}-\d{2}-\d{2})T00:00:00$")
BOM_UTF16LE = b"\xff\xfe"


@dataclass
class HasilIG:
    nama_file: str
    metrik: MetrikIG | None = None
    data: pd.DataFrame | None = None  # kolom: tanggal (date), nilai (int)
    galat: list[Catatan] = field(default_factory=list)
    peringatan: list[Catatan] = field(default_factory=list)

    @property
    def bisa_dipakai(self) -> bool:
        return self.metrik is not None and not self.galat and self.data is not None

    @property
    def periode(self) -> tuple[date, date] | None:
        if self.data is None or not len(self.data):
            return None
        return min(self.data["tanggal"]), max(self.data["tanggal"])


def teks_ig(isi: bytes) -> str | None:
    """Teks file bila berformat CSV Instagram (UTF-16 LE + BOM, baris pertama `sep=`)."""
    if not isi.startswith(BOM_UTF16LE):
        return None
    try:
        teks = isi[2:].decode("utf-16-le")
    except UnicodeDecodeError:
        return None
    return teks if teks.lstrip().lower().startswith("sep=") else None


def baca_file_ig(path: str | Path, nama_file: str | None = None) -> HasilIG:
    path = Path(path)
    h = HasilIG(nama_file or path.name)
    teks = teks_ig(path.read_bytes())
    if teks is None:
        h.galat.append(Catatan(None, "Bukan CSV Instagram Insights (harus UTF-16 dengan baris pertama 'sep=,')."))
        return h
    baris = [b for b in csv.reader(io.StringIO(teks)) if any(x.strip() for x in b)]
    if len(baris) < 3:
        h.galat.append(Catatan(None, "File terlalu pendek: butuh baris sep=, judul metrik, dan header Tanggal/Primary."))
        return h
    judul = baris[1][0].strip() if baris[1] else ""
    h.metrik = PER_JUDUL.get(judul.lower())
    if h.metrik is None:
        h.galat.append(Catatan(2, f"Judul metrik '{judul}' belum dikenal. Yang dikenal: "
                                  + ", ".join(m.judul for m in METRIK) + ". Kirim contoh file ini supaya bisa ditambahkan."))
        return h
    header = [x.strip() for x in baris[2]]
    if header != ["Tanggal", "Primary"]:
        h.galat.append(Catatan(3, f"Header harus \"Tanggal\",\"Primary\", ditemukan {header}."))
        return h

    nilai: dict[date, int] = {}
    for i, b in enumerate(baris[3:], start=4):
        if len(b) != 2:
            h.galat.append(Catatan(i, f"Baris harus 2 kolom, ditemukan {len(b)}."))
            continue
        m = _WAKTU.match(b[0].strip())
        if not m:
            h.galat.append(Catatan(i, f"Tanggal '{b[0]}' bukan format harian YYYY-MM-DDT00:00:00."))
            continue
        t = date.fromisoformat(m.group(1))
        v = b[1].strip()
        if not v.isdigit():
            h.galat.append(Catatan(i, f"Nilai '{v}' bukan bilangan bulat ≥ 0."))
            continue
        v = int(v)
        if t in nilai and nilai[t] != v:
            h.galat.append(Catatan(i, f"Tanggal {t:%d-%m-%Y} muncul dua kali dengan nilai berbeda ({nilai[t]} dan {v})."))
            continue
        nilai[t] = v
    if h.galat:
        return h
    h.data = pd.DataFrame({"tanggal": sorted(nilai), "nilai": [nilai[t] for t in sorted(nilai)]})
    if not nilai:
        h.peringatan.append(Catatan(None, "File tidak berisi baris tanggal."))
    return h
