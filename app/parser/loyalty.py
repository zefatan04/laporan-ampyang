"""Membaca CSV ekspor web loyalty "Keluarga Ampyang".

Jenis file dikenali dari header (bukan nama file). Format terbukti dari
ekspor asli 6 Okt 2026: UTF-8 dengan BOM, koma, kolom `Cabang` di akhir.

Privasi: nomor WA TIDAK disimpan. Yang disimpan hanya sidik (SHA-256 dari
nomor yang dinormalkan ke 08xx), cukup untuk menghitung member berulang dan
menyambungkan antar file. Nama member, catatan pesanan, alergi, menu
favorit, dan alamat IP member tidak dibaca.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from app.parser.esb import Catatan
from app.pengaturan_bawaan import CABANG


@dataclass(frozen=True)
class JenisLoyalty:
    kode: str
    nama: str
    penanda: tuple[str, ...]


TRANSAKSI = JenisLoyalty("transaksi", "Riwayat Transaksi (loyalty)",
                         ("Waktu", "Nomor WA", "Nominal Bill", "Stempel Didapat", "Dicatat Kasir"))
KLAIM = JenisLoyalty("klaim", "Riwayat Klaim (loyalty)",
                     ("Waktu Klaim", "Nomor WA", "Nama Hadiah", "Status", "Diserahkan Kasir"))
HARIAN = JenisLoyalty("harian", "Rekap Harian (loyalty)",
                      ("Tanggal", "Jumlah Bill", "Stempel Diberikan", "Omzet Tercatat", "Klaim Dibuat"))
PELANGGAN = JenisLoyalty("pelanggan", "Rekap Pelanggan (loyalty)",
                         ("Nomor WA", "Tanggal Gabung", "Status Verifikasi", "Jumlah Transaksi"))
LOG = JenisLoyalty("log", "Log Aktivitas (loyalty)",
                   ("Waktu", "Kode Kejadian", "Kejadian", "Alamat IP"))
HADIAH = JenisLoyalty("hadiah", "Daftar Hadiah (loyalty)", ("Nama Hadiah", "Tingkat", "Stok", "Total Diklaim"))
PROMO = JenisLoyalty("promo_loyalty", "Daftar Promo (loyalty)", ("Judul", "Label", "Mulai", "Selesai"))
SEMUA = (TRANSAKSI, KLAIM, HARIAN, PELANGGAN, LOG, HADIAH, PROMO)

# Kejadian log yang dipakai laporan. Sisanya (kasir online/logout, dll.) tidak disimpan.
LOG_DIPAKAI = {"daftar", "pendaftaran_beruntun", "pendaftaran_janggal", "login_ok", "klaim", "serah_ok",
               "klaim_promo_eksklusif", "serah_promo_eksklusif_ok"}


def sidik(nomor) -> str | None:
    """Sidik nomor WA. '6281…', '81…', '081…' -> sama."""
    digit = re.sub(r"\D", "", str(nomor or ""))
    if not digit:
        return None
    if digit.startswith("62"):
        digit = "0" + digit[2:]
    elif not digit.startswith("0"):
        digit = "0" + digit
    return hashlib.sha256(digit.encode()).hexdigest()[:16]


@dataclass
class HasilLoyalty:
    nama_file: str
    jenis: JenisLoyalty | None
    data: pd.DataFrame | None = None
    cabang: list[str] = field(default_factory=list)
    galat: list[Catatan] = field(default_factory=list)
    peringatan: list[Catatan] = field(default_factory=list)
    tanggal_snapshot: date | None = None

    @property
    def bisa_dipakai(self) -> bool:
        return self.jenis is not None and not self.galat and self.data is not None


def _uang(v) -> Decimal | None:
    v = (v or "").strip()
    if v in ("", "-"):
        return None
    if not re.fullmatch(r"-?\d+(\.\d+)?", v):
        raise ValueError(f"angka tidak dikenali: {v!r}")
    return Decimal(v)


def _int(v) -> int | None:
    d = _uang(v)
    return None if d is None else int(d)


def _waktu(v) -> datetime | None:
    v = (v or "").strip()
    return None if v in ("", "-") else datetime.strptime(v, "%Y-%m-%d %H:%M:%S")


def _tgl(v) -> date | None:
    v = (v or "").strip()
    return None if v in ("", "-") else date.fromisoformat(v)


def kenali(header: list[str]) -> JenisLoyalty | None:
    h = {x.strip() for x in header}
    for j in SEMUA:
        if all(p in h for p in j.penanda):
            return j
    return None


def baca_teks(isi: bytes) -> str | None:
    """CSV loyalty = UTF-8 (dengan/tanpa BOM). Selain itu bukan file loyalty."""
    try:
        return isi.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def baca_file_loyalty(path: str | Path, nama_file: str | None = None) -> HasilLoyalty:
    path = Path(path)
    nama = nama_file or path.name
    teks = baca_teks(path.read_bytes())
    h = HasilLoyalty(nama, None)
    if teks is None:
        h.galat.append(Catatan(None, "Bukan CSV UTF-8."))
        return h
    baris = list(csv.reader(io.StringIO(teks)))
    if not baris:
        h.galat.append(Catatan(None, "File kosong."))
        return h
    h.jenis = kenali(baris[0])
    if h.jenis is None:
        h.galat.append(Catatan(1, "Jenis file loyalty tidak dikenali dari header."))
        return h
    kolom = [x.strip() for x in baris[0]]
    rekaman = [dict(zip(kolom, r)) for r in baris[1:] if any(x.strip() for x in r)]
    if "Cabang" not in kolom:
        h.galat.append(Catatan(1, "Kolom 'Cabang' tidak ada. Ekspor ulang dari web loyalty versi terbaru."))
        return h

    m = re.search(r"(\d{8})\.csv$", nama)
    if h.jenis is PELANGGAN and m:
        h.tanggal_snapshot = datetime.strptime(m.group(1), "%Y%m%d").date()

    olah = {
        TRANSAKSI: _transaksi, KLAIM: _klaim, HARIAN: _harian, PELANGGAN: _pelanggan,
        LOG: _log, HADIAH: _katalog, PROMO: _katalog,
    }[h.jenis]
    hasil = []
    for i, r in enumerate(rekaman, start=2):
        try:
            hasil.append(olah(r))
        except (ValueError, KeyError) as e:
            h.galat.append(Catatan(i, str(e)))
    df = pd.DataFrame(hasil)
    if h.jenis is LOG and len(df):
        df = df[df["kode"].isin(LOG_DIPAKAI)].reset_index(drop=True)
    h.data = df
    cab = sorted({r.get("Cabang", "").strip() for r in rekaman})
    h.cabang = cab
    tak = [c for c in cab if c not in CABANG and not (h.jenis in (PROMO,) and c == "Semua Cabang")]
    if tak:
        h.galat.append(Catatan(None, f"Cabang tidak dikenal: {', '.join(tak)}"))
    return h


def _transaksi(r: dict) -> dict:
    return {"waktu": _waktu(r["Waktu"]), "nomor": sidik(r["Nomor WA"]), "nominal": _uang(r["Nominal Bill"]),
            "stempel": _int(r["Stempel Didapat"]), "hangus": _int(r.get("Stempel Hangus")),
            "stempel_setelah": _int(r.get("Stempel Setelahnya")), "kasir": r["Dicatat Kasir"].strip(),
            "cabang": r["Cabang"].strip()}


def _klaim(r: dict) -> dict:
    return {"waktu": _waktu(r["Waktu Klaim"]), "nomor": sidik(r["Nomor WA"]), "tingkat": _int(r.get("Tingkat")),
            "hadiah": r["Nama Hadiah"].strip(), "status": r["Status"].strip(),
            "waktu_serah": _waktu(r.get("Waktu Diserahkan")), "kasir_serah": (r.get("Diserahkan Kasir") or "").strip(),
            "cabang": r["Cabang"].strip()}


def _harian(r: dict) -> dict:
    return {"tanggal": _tgl(r["Tanggal"]), "bill": _int(r["Jumlah Bill"]), "stempel": _int(r["Stempel Diberikan"]),
            "omzet": _uang(r["Omzet Tercatat"]), "klaim_dibuat": _int(r["Klaim Dibuat"]),
            "hadiah_diserahkan": _int(r.get("Hadiah Diserahkan")),
            "member_baru_semua": _int(r.get("Member Baru (semua cabang)")),
            "login": _int(r.get("Login Berhasil")),
            "member_baru_cabang": _int(r.get("Member Baru (didaftarkan kasir cabang ini)")),
            "cabang": r["Cabang"].strip()}


def _pelanggan(r: dict) -> dict:
    return {"nomor": sidik(r["Nomor WA"]), "gabung": _tgl(r["Tanggal Gabung"]),
            "terverifikasi": r["Status Verifikasi"].strip().lower().startswith("terverifikasi"),
            "stempel_kini": _int(r.get("Stempel Sekarang")), "stempel_total": _int(r.get("Stempel Seumur Hidup")),
            "transaksi": _int(r["Jumlah Transaksi"]), "belanja": _uang(r.get("Total Belanja")),
            "terakhir": _tgl(r.get("Belanja Terakhir")), "klaim": _int(r.get("Jumlah Klaim")),
            "klaim_diambil": _int(r.get("Klaim Diambil")),
            "kasir_pendaftar": (r.get("Kasir Pendaftar") or "-").strip(),
            "cabang_pendaftaran": (r.get("Cabang Pendaftaran") or "Tidak diketahui").strip(),
            "cabang": r["Cabang"].strip()}


def _log(r: dict) -> dict:
    kode = r["Kode Kejadian"].strip()
    ket = (r.get("Keterangan") or "").strip()
    # Keterangan pendaftaran_janggal berformat "Nama (nomor): alasan"; hanya alasannya yang disimpan.
    if kode == "pendaftaran_janggal" and "): " in ket:
        ket = ket.split("): ", 1)[1]
    elif kode not in ("pendaftaran_beruntun", "pendaftaran_janggal"):
        ket = ""
    return {"waktu": _waktu(r["Waktu"]), "kode": kode, "nomor": sidik(r.get("Nomor WA/Login")),
            "ip": (r.get("Alamat IP") or "").strip() if kode in ("daftar", "pendaftaran_beruntun", "pendaftaran_janggal") else "",
            "keterangan": ket, "cabang": r["Cabang"].strip()}


def _katalog(r: dict) -> dict:
    return {k: v.strip() for k, v in r.items()}
