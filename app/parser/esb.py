"""Membaca file export ESB (.xlsx).

Bentuk umum export ESB:

    baris 1..n   metadata  (judul, Period, Branch, Sales Type, ...)
    baris h      header kolom
    baris h+1..  data, satu baris per bill / per item
    baris akhir  footer berisi total, angka berformat Indonesia

Baris header dicari otomatis dari isi (tidak di-hardcode). Nomor baris yang
sudah terbukti di export asli dipakai sebagai cek silang: kalau berbeda,
dicatat sebagai peringatan, bukan dianggap salah.

Parser ini sengaja tidak memperbaiki apa pun secara diam-diam. Setiap baris
yang tidak bisa dibaca, dibuang, atau tidak dikenali dicatat beserta
alasannya, lalu diputuskan di tahap validasi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
import pandas as pd

from app.angka import AngkaTidakValid, baca_angka, baca_jam, baca_tanggal


def norm(teks) -> str:
    """Kunci pembanding nama kolom/metadata: huruf kecil, spasi tunggal."""
    return re.sub(r"\s+", " ", str(teks or "")).strip().lower()


def bersihkan_nama_menu(teks) -> str:
    """'Nasi  Goreng Jawa ' -> 'Nasi Goreng Jawa'. Huruf besar-kecil dibiarkan."""
    return re.sub(r"\s+", " ", str(teks or "")).strip()


# ---------------------------------------------------------------------------
# Definisi jenis laporan
# ---------------------------------------------------------------------------

UANG, ANGKA, TANGGAL, JAM, TEKS, PERSEN = "uang", "angka", "tanggal", "jam", "teks", "persen"


@dataclass(frozen=True)
class Kolom:
    nama: str            # nama di export ESB
    kode: str            # nama internal (snake_case) di database
    tipe: str
    wajib: bool = True   # tanpa kolom ini file tidak bisa dipakai


@dataclass(frozen=True)
class JenisLaporan:
    kode: str
    nama: str
    wajib_unggah: bool
    baris_header_terbukti: int
    penanda: tuple[str, ...]       # semua harus ada di header untuk dikenali
    kolom: tuple[Kolom, ...] = ()  # kosong = baru dikenali, belum diparse
    kolom_id: str | None = None    # kolom yang selalu terisi di baris data
    # Kolom yang dijumlahkan di footer dan wajib cocok dengan Σ baris data.
    kolom_footer: tuple[str, ...] = ()


BILL = JenisLaporan(
    kode="bill",
    nama="Sales Recapitulation Report – Bill Report",
    wajib_unggah=True,
    baris_header_terbukti=13,
    penanda=("Sales Number", "Bill Number", "Visit Purpose", "Grand Total"),
    kolom_id="Sales Number",
    kolom=(
        Kolom("Sales Number", "sales_number", TEKS),
        Kolom("Bill Number", "bill_number", TEKS),
        Kolom("Sales Date", "sales_date", TANGGAL),
        Kolom("Sales In Time", "sales_in_time", JAM),
        Kolom("Sales Out Time", "sales_out_time", JAM, wajib=False),
        Kolom("Visit Purpose", "visit_purpose", TEKS),
        Kolom("Table", "table_name", TEKS, wajib=False),
        Kolom("Pax Total", "pax_total", ANGKA),
        Kolom("Subtotal", "subtotal", UANG),
        Kolom("Menu Discount", "menu_discount", UANG),
        Kolom("Bill Discount", "bill_discount", UANG),
        Kolom("Voucher Discount", "voucher_discount", UANG),
        Kolom("Tax Total", "tax_total", UANG),
        Kolom("Grand Total", "grand_total", UANG),
        Kolom("Promotion", "promotion", TEKS, wajib=False),
        Kolom("Cashier", "cashier", TEKS, wajib=False),
        Kolom("Sales Type", "sales_type", TEKS, wajib=False),
    ),
    kolom_footer=("Pax Total", "Subtotal", "Menu Discount", "Bill Discount",
                  "Voucher Discount", "Tax Total", "Grand Total"),
)

COGS = JenisLaporan(
    kode="cogs",
    nama="Sales Menu COGS Report",
    wajib_unggah=True,
    baris_header_terbukti=13,
    penanda=("Menu", "Qty", "COGS Total"),
    kolom_id="Sales Number",
    kolom=(
        Kolom("Sales Number", "sales_number", TEKS),
        Kolom("Sales Date", "sales_date", TANGGAL),
        Kolom("Menu", "menu", TEKS),
        Kolom("Menu Category", "menu_category", TEKS),
        Kolom("Menu Category Detail", "menu_category_detail", TEKS),
        Kolom("Qty", "qty", ANGKA),
        Kolom("Price", "price", UANG),
        Kolom("Total", "total", UANG),
        Kolom("Discount Total", "discount_total", UANG),
        Kolom("COGS Total", "cogs_total", UANG),
        Kolom("COGS Total (%)", "cogs_total_pct", PERSEN, wajib=False),
        Kolom("Margin", "margin", UANG, wajib=False),
        Kolom("Sales Type", "sales_type", TEKS, wajib=False),
    ),
    kolom_footer=("Qty", "Total", "Discount Total", "COGS Total"),
)

# Laporan opsional: untuk sekarang hanya dikenali jenisnya. Parser
# lengkapnya menyusul di tahap yang memakainya.
RECAP_DETAIL = JenisLaporan("recap_detail", "Sales Recapitulation Detail Report", False, 11,
                            ("Sales Number", "Menu", "Qty", "Bill Number"))
PROMOTION = JenisLaporan("promotion", "Promotion Report", False, 13,
                         ("Promotion Name",))
CUSTOMER = JenisLaporan("customer", "Customer Data Report", False, 11,
                        ("Order ID", "Full Name", "Phone Number"))
STAFF = JenisLaporan("staff", "Staff Sales & Cancel Report", False, 12,
                     ("User", "Cancel Qty"))
CANCEL = JenisLaporan("cancel", "Cancel Menu Detail Report", False, 12,
                      ("Menu", "Cancel Notes"))

# Urutan penting: yang penandanya paling spesifik dicek lebih dulu.
SEMUA_JENIS = (BILL, COGS, RECAP_DETAIL, PROMOTION, CUSTOMER, STAFF, CANCEL)


# ---------------------------------------------------------------------------
# Hasil baca
# ---------------------------------------------------------------------------

@dataclass
class Catatan:
    baris: int | None   # nomor baris Excel (1-indexed), None = tingkat file
    pesan: str


@dataclass
class HasilBaca:
    nama_file: str
    jenis: JenisLaporan | None
    judul: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    baris_header: int | None = None
    kolom_file: list[str] = field(default_factory=list)
    kolom_hilang: list[str] = field(default_factory=list)
    data: pd.DataFrame | None = None
    footer: dict[str, Decimal | None] = field(default_factory=dict)
    baris_footer: int | None = None
    galat: list[Catatan] = field(default_factory=list)       # menghalangi pemakaian
    peringatan: list[Catatan] = field(default_factory=list)  # perlu dibaca user
    periode: tuple[date, date] | None = None

    @property
    def cabang(self) -> str | None:
        return self.metadata.get("branch")

    @property
    def bisa_dipakai(self) -> bool:
        return self.jenis is not None and not self.galat and self.data is not None


# ---------------------------------------------------------------------------
# Pembacaan
# ---------------------------------------------------------------------------

def _baca_sel(path: Path) -> list[list]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _kosong(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _isi(baris: list) -> list:
    return [v for v in baris if not _kosong(v)]


# Footer ESB biasanya menaruh teks "Total"/"Grand Total" di kolom pertama,
# yang sering juga kolom nomor transaksi. Baris seperti itu bukan data.
_TEKS_TOTAL = re.compile(r"^\s*(grand\s*)?(sub\s*)?total\b", re.IGNORECASE)


def _baris_data(baris: list, i_id: int) -> bool:
    if len(baris) <= i_id or _kosong(baris[i_id]):
        return False
    return not _TEKS_TOTAL.match(str(baris[i_id]))


def kenali_jenis(baris_baris: list[list], batas: int = 40) -> tuple[JenisLaporan | None, int | None]:
    """Cari baris header di `batas` baris pertama dan tentukan jenis laporan.

    Mengembalikan (jenis, indeks_0_baris_header). Yang dicari adalah baris
    yang memuat SEMUA kolom penanda suatu jenis.
    """
    for i, baris in enumerate(baris_baris[:batas]):
        sel = {norm(v) for v in baris if not _kosong(v)}
        if len(sel) < 2:
            continue
        for jenis in SEMUA_JENIS:
            if all(norm(p) in sel for p in jenis.penanda):
                return jenis, i
    return None, None


def _baca_metadata(baris_baris: list[list]) -> tuple[str | None, dict[str, str]]:
    """Judul = sel teks pertama. Pasangan kunci-nilai dari baris di atas header.

    Bentuk yang diterima: ['Period', ': 01/09/2026 - 30/09/2026'],
    ['Period', ':', '01/09/2026 - ...'], atau ['Period : 01/09/2026 - ...'].
    """
    judul, meta = None, {}
    for baris in baris_baris:
        isi = [str(v).strip() for v in _isi(baris)]
        if not isi:
            continue
        if len(isi) == 1 and ":" not in isi[0]:
            if judul is None:
                judul = isi[0]
            continue
        if len(isi) == 1:
            kunci, _, nilai = isi[0].partition(":")
        else:
            kunci, nilai = isi[0], " ".join(isi[1:])
        kunci = norm(kunci.rstrip(":"))
        nilai = nilai.strip().lstrip(":").strip()
        if kunci and kunci not in meta:
            meta[kunci] = nilai
    return judul, meta


def baca_periode(teks: str | None) -> tuple[date, date] | None:
    """'01/09/2026 - 30/09/2026' atau '1 Sep 2026 - 30 Sep 2026'."""
    if not teks:
        return None
    bagian = re.split(r"\s+(?:-|–|s/d|to|sampai)\s+", teks.strip())
    if len(bagian) != 2:
        raise ValueError(f"format Period tidak dikenali: {teks!r}")
    awal, akhir = baca_tanggal(bagian[0]), baca_tanggal(bagian[1])
    if awal is None or akhir is None or akhir < awal:
        raise ValueError(f"format Period tidak dikenali: {teks!r}")
    return awal, akhir


def _ubah(nilai, tipe: str):
    if tipe in (UANG, ANGKA, PERSEN):
        return baca_angka(nilai)
    if tipe == TANGGAL:
        return baca_tanggal(nilai)
    if tipe == JAM:
        j = baca_jam(nilai)
        return None if j is None else f"{j[0]:02d}:{j[1]:02d}"
    return None if _kosong(nilai) else str(nilai).strip()


def baca_file_esb(path: str | Path, nama_file: str | None = None) -> HasilBaca:
    path = Path(path)
    hasil = HasilBaca(nama_file=nama_file or path.name, jenis=None)
    try:
        sel = _baca_sel(path)
    except Exception as e:  # file rusak / bukan xlsx
        hasil.galat.append(Catatan(None, f"File tidak bisa dibuka sebagai .xlsx: {e}"))
        return hasil

    jenis, i_header = kenali_jenis(sel)
    if jenis is None:
        hasil.galat.append(Catatan(None, "Jenis laporan ESB tidak dikenali dari isi file "
                                         "(baris header dengan kolom penanda tidak ditemukan)."))
        return hasil
    hasil.jenis = jenis
    hasil.baris_header = i_header + 1
    hasil.judul, hasil.metadata = _baca_metadata(sel[:i_header])

    if hasil.baris_header != jenis.baris_header_terbukti:
        hasil.peringatan.append(Catatan(hasil.baris_header,
            f"Header ditemukan di baris {hasil.baris_header}, berbeda dari export yang sudah "
            f"terbukti (baris {jenis.baris_header_terbukti}). Periksa apakah pengaturan export berubah."))

    try:
        hasil.periode = baca_periode(hasil.metadata.get("period"))
    except ValueError as e:
        hasil.peringatan.append(Catatan(None, str(e)))
    if hasil.periode is None and "period" not in hasil.metadata:
        hasil.peringatan.append(Catatan(None, "Metadata 'Period' tidak ditemukan di atas header."))
    if "branch" not in hasil.metadata:
        hasil.peringatan.append(Catatan(None, "Metadata 'Branch' tidak ditemukan di atas header."))

    header = sel[i_header]
    hasil.kolom_file = [str(v).strip() if not _kosong(v) else "" for v in header]

    if not jenis.kolom:
        # Jenis opsional yang parsernya belum dibuat: cukup dikenali.
        hasil.peringatan.append(Catatan(None, f"{jenis.nama} dikenali, tetapi belum diolah "
                                              "pada versi ini."))
        return hasil

    # Peta nama kolom -> indeks. Nama ganda dicatat: tidak boleh memilih salah satu diam-diam.
    indeks: dict[str, int] = {}
    for j, nama in enumerate(hasil.kolom_file):
        k = norm(nama)
        if not k:
            continue
        if k in indeks:
            hasil.galat.append(Catatan(hasil.baris_header, f"Kolom '{nama}' muncul lebih dari sekali."))
        indeks[k] = j
    for k in jenis.kolom:
        if norm(k.nama) not in indeks and k.wajib:
            hasil.kolom_hilang.append(k.nama)
    if hasil.kolom_hilang:
        hasil.galat.append(Catatan(hasil.baris_header,
            "Kolom wajib tidak ada: " + ", ".join(hasil.kolom_hilang)))
        return hasil
    kolom_ada = [k for k in jenis.kolom if norm(k.nama) in indeks]

    # --- Pisahkan data dan footer -----------------------------------------
    i_id = indeks[norm(jenis.kolom_id)]
    badan = sel[i_header + 1:]
    nomor = list(range(i_header + 2, i_header + 2 + len(badan)))  # nomor baris Excel
    terakhir_data = max((n for n, b in zip(nomor, badan) if _baris_data(b, i_id)), default=None)
    if terakhir_data is None:
        hasil.galat.append(Catatan(None, "Tidak ada baris data di bawah header."))
        return hasil

    # Baris tanpa nomor transaksi di tengah data tidak dikenal bentuknya.
    for n, b in zip(nomor, badan):
        if n > terakhir_data:
            break
        if _isi(b) and not _baris_data(b, i_id):
            hasil.galat.append(Catatan(n, f"Baris tanpa '{jenis.kolom_id}' di tengah data: "
                                          f"{_ringkas(b)}. Bentuk baris ini belum dikenal."))

    # Footer = baris setelah data terakhir yang memuat angka di kolom footer.
    i_footer_kol = {nama: indeks[norm(nama)] for nama in jenis.kolom_footer if norm(nama) in indeks}
    calon = []
    for n, b in zip(nomor, badan):
        if n <= terakhir_data or not _isi(b):
            continue
        punya_angka = any(j < len(b) and not _kosong(b[j]) for j in i_footer_kol.values())
        (calon.append((n, b)) if punya_angka else
         hasil.peringatan.append(Catatan(n, f"Baris setelah data diabaikan: {_ringkas(b)}")))
    if not calon:
        hasil.galat.append(Catatan(None, "Baris footer (total) tidak ditemukan. Rekonsiliasi tidak bisa dilakukan."))
    else:
        if len(calon) > 1:
            for n, b in calon[1:]:
                hasil.galat.append(Catatan(n, f"Ada lebih dari satu baris mirip footer: {_ringkas(b)}"))
        hasil.baris_footer, b = calon[0]
        for nama, j in i_footer_kol.items():
            try:
                hasil.footer[nama] = baca_angka(b[j]) if j < len(b) else None
            except AngkaTidakValid as e:
                hasil.galat.append(Catatan(hasil.baris_footer, f"Footer kolom {nama}: {e}"))

    # --- Baris data ------------------------------------------------------
    rekaman = []
    for n, b in zip(nomor, badan):
        if n > terakhir_data:
            break
        if not _baris_data(b, i_id):
            continue
        r = {"baris_excel": n}
        for k in kolom_ada:
            j = indeks[norm(k.nama)]
            mentah = b[j] if j < len(b) else None
            try:
                r[k.kode] = _ubah(mentah, k.tipe)
            except ValueError as e:
                hasil.galat.append(Catatan(n, f"Kolom {k.nama}: {e}"))
                r[k.kode] = None
        rekaman.append(r)

    df = pd.DataFrame(rekaman)
    for k in jenis.kolom:  # kolom opsional yang tidak ada tetap dibuat, berisi kosong
        if k.kode not in df.columns:
            df[k.kode] = None
    if "menu" in df.columns:
        df["menu_bersih"] = df["menu"].map(bersihkan_nama_menu)
    hasil.data = df
    return hasil


def _ringkas(baris: list, n: int = 6) -> str:
    isi = [str(v) for v in _isi(baris)]
    return " | ".join(isi[:n]) + (" | …" if len(isi) > n else "")
