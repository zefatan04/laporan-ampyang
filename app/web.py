"""Server web lokal (FastAPI). Dibuka di http://localhost:8000."""

from __future__ import annotations

import secrets
import shutil
import tempfile
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import db, db_loyalty
from app.hitung import dashboard
from app.parser.esb import baca_file_esb, daftar_cabang_metadata
from app.parser.loyalty import baca_file_loyalty, baca_teks, kenali
from app.validasi import validasi_unggahan
from app import validasi_loyalty as vl

STATIC = db.AKAR / "static"
app = FastAPI(title="Laporan Ampyang", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# Hasil baca yang menunggu tombol "Simpan". Aplikasi ini dipakai satu orang
# di satu laptop, jadi cukup disimpan di memori dan kedaluwarsa sendiri.
_ANTRE: dict[str, dict] = {}
UMUR_ANTRE = 60 * 60


def _bersihkan_antre():
    batas = time.time() - UMUR_ANTRE
    for k in [k for k, v in _ANTRE.items() if v["waktu"] < batas]:
        _ANTRE.pop(k, None)


@app.get("/")
def beranda():
    return FileResponse(STATIC / "index.html")


def _jenis_csv(isi: bytes) -> str | None:
    teks = baca_teks(isi)
    if teks is None:
        return None
    baris = teks.splitlines()[:1]
    return "loyalty" if baris and kenali([x.strip().strip('"') for x in baris[0].split(",")]) else None


@app.post("/api/unggah")
async def unggah(awal: date = Form(...), akhir: date = Form(...), cabang: str = Form(""),
                 files: list[UploadFile] = File(...)):
    """Semua file sekaligus: .xlsx dibaca sebagai export ESB, .csv dikenali dari isinya (loyalty)."""
    if akhir < awal:
        raise HTTPException(400, "Tanggal akhir lebih awal dari tanggal mulai.")
    _bersihkan_antre()
    esb, loy, asing = [], [], []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            p = Path(tmp) / Path(f.filename or "file").name
            with p.open("wb") as keluar:
                shutil.copyfileobj(f.file, keluar)
            if p.suffix.lower() == ".csv":
                if _jenis_csv(p.read_bytes()) == "loyalty":
                    loy.append(baca_file_loyalty(p, nama_file=f.filename))
                else:
                    asing.append(f.filename)
            else:
                esb.append(baca_file_esb(p, nama_file=f.filename))

    harap = [c.strip() for c in cabang.split(",") if c.strip()] or None
    with db.koneksi() as con:
        tersimpan = db.periode_tersimpan(con)
        tersimpan_loy = db_loyalty.periode_tersimpan(con)
    cek, terblokir, konfirmasi, tumpang = [], False, False, []
    lap = None
    if esb:
        lap = validasi_unggahan(esb, awal, akhir, tersimpan=tersimpan, cabang=harap)
        cek += lap.cek
        terblokir |= lap.terblokir
        konfirmasi |= lap.butuh_konfirmasi
        cab = sorted({c for h in esb if h.data is not None for c in h.data["cabang"].dropna()})
        tumpang += [{**p, "jenis": f"ESB {p['jenis']}"} for p in tersimpan
                    if p["cabang"] in cab and p["awal"] <= akhir and p["akhir"] >= awal]
    cek_loy = []
    if loy:
        cek_loy = vl.validasi_loyalty(loy, awal, akhir, tersimpan_loy, harap)
        cek += cek_loy
        terblokir |= vl.terblokir(cek_loy)
        konfirmasi |= vl.butuh_konfirmasi(cek_loy)
        cab = {c for h in loy if h.bisa_dipakai and h.jenis in vl.BERKALA for c in vl.cabang_file(h)}
        tumpang += [{**p, "jenis": "loyalty"} for p in tersimpan_loy
                    if p["cabang"] in cab and p["awal"] <= akhir and p["akhir"] >= awal]
    if asing:
        from app.validasi import GAGAL, Cek
        cek.append(Cek(0, "File tidak dikenali", GAGAL,
                       "File CSV ini bukan ekspor loyalty yang dikenal (CSV Instagram diolah mulai tahap 8). "
                       "Keluarkan dari unggahan.", [{"File": n} for n in asing]))
        terblokir = True

    token = secrets.token_urlsafe(16)
    _ANTRE[token] = {"waktu": time.time(), "esb": esb, "laporan": lap, "loyalty": loy, "cek_loyalty": cek_loy,
                     "awal": awal, "akhir": akhir, "terblokir": terblokir}
    return {
        "token": token,
        "file": [{
            "nama": h.nama_file,
            "jenis": h.jenis.nama if h.jenis else None,
            "kode": h.jenis.kode if h.jenis else None,
            "diolah": bool(h.jenis and h.jenis.kolom),
            "cabang": daftar_cabang_metadata(h.cabang) or ([h.cabang] if h.cabang else []),
            "periode": list(h.periode) if h.periode else None,
            "baris": 0 if h.data is None else len(h.data),
        } for h in esb] + [{
            "nama": h.nama_file,
            "jenis": h.jenis.nama if h.jenis else None,
            "kode": h.jenis.kode if h.jenis else None,
            "diolah": h.jenis is not None,
            "cabang": vl.cabang_file(h) if h.jenis else [],
            "periode": [h.tanggal_snapshot, h.tanggal_snapshot] if h.tanggal_snapshot else None,
            "baris": 0 if h.data is None else len(h.data),
        } for h in loy] + [{"nama": n, "jenis": None, "kode": None, "diolah": False, "cabang": [], "periode": None, "baris": 0}
                           for n in asing],
        "cek": [asdict(c) for c in cek],
        "terblokir": terblokir,
        "butuh_konfirmasi": konfirmasi,
        "tumpang_tindih": tumpang,
    }


class PermintaanSimpan(BaseModel):
    token: str
    ganti: bool = False
    simpan_walau_tidak_cocok: bool = False


@app.post("/api/simpan")
def simpan(req: PermintaanSimpan):
    antre = _ANTRE.get(req.token)
    if antre is None:
        raise HTTPException(410, "Hasil pemeriksaan sudah kedaluwarsa. Unggah ulang file-nya.")
    if antre["terblokir"]:
        raise HTTPException(409, "Validasi menunjukkan ada file yang tidak bisa disimpan.")
    hasil = {}
    with db.koneksi() as con:
        try:
            # Syarat kedua kelompok diperiksa dulu supaya tidak tersimpan setengah.
            if antre["esb"]:
                lap = antre["laporan"]
                if lap.butuh_konfirmasi and not req.simpan_walau_tidak_cocok:
                    raise db.TidakBolehDisimpan("Rekonsiliasi ESB tidak cocok. Centang 'simpan walau tidak cocok'.")
            if antre["loyalty"] and vl.butuh_konfirmasi(antre["cek_loyalty"]) and not req.simpan_walau_tidak_cocok:
                raise db.TidakBolehDisimpan("Rekonsiliasi loyalty tidak cocok. Centang 'simpan walau tidak cocok'.")
            if antre["esb"]:
                hasil["unggahan_id"] = db.simpan_unggahan(con, antre["esb"], antre["laporan"], antre["awal"], antre["akhir"],
                                                          ganti=req.ganti, simpan_walau_tidak_cocok=req.simpan_walau_tidak_cocok)
            if antre["loyalty"]:
                hasil["unggahan_loyalty_id"] = db_loyalty.simpan(con, antre["loyalty"], antre["cek_loyalty"], antre["awal"],
                                                                 antre["akhir"], ganti=req.ganti,
                                                                 simpan_walau_tidak_cocok=req.simpan_walau_tidak_cocok)
        except db.TidakBolehDisimpan as e:
            raise HTTPException(409, str(e)) from e
    _ANTRE.pop(req.token, None)
    return hasil


@app.delete("/api/periode-loyalty/{unggahan_id}/{cabang}")
def hapus_loyalty(unggahan_id: int, cabang: str):
    with db.koneksi() as con:
        if not db_loyalty.hapus_periode(con, unggahan_id, cabang):
            raise HTTPException(404, "Periode loyalty tidak ditemukan.")
    return {"ok": True}


@app.get("/api/riwayat")
def lihat_riwayat():
    with db.koneksi() as con:
        return db.riwayat(con)


@app.delete("/api/periode/{unggahan_id}/{cabang}")
def hapus(unggahan_id: int, cabang: str):
    with db.koneksi() as con:
        if not db.hapus_periode(con, unggahan_id, cabang):
            raise HTTPException(404, "Periode tidak ditemukan.")
    return {"ok": True}


@app.get("/api/dashboard/bulan")
def daftar_bulan():
    with db.koneksi() as con:
        return {"bulan": dashboard.bulan_tersedia(con)}


@app.get("/api/dashboard")
def lihat_dashboard(cabang: str, bulan: str, pilih: str = "bulan"):
    if cabang not in ("Rungkut", "Mawar"):
        raise HTTPException(400, "Cabang tidak dikenal.")
    try:
        tahun, b = (int(x) for x in bulan.split("-"))
        date(tahun, b, 1)
    except ValueError as e:
        raise HTTPException(400, "Format bulan harus YYYY-MM.") from e
    with db.koneksi() as con:
        return dashboard.hitung(con, cabang, tahun, b, pilih)


@app.get("/api/pengaturan")
def lihat_pengaturan():
    from app import pengaturan
    with db.koneksi() as con:
        return pengaturan.semua(con)


@app.put("/api/pengaturan/{kunci}")
def ubah_pengaturan(kunci: str, isi: dict):
    from app import pengaturan
    if kunci not in pengaturan.BAWAAN:
        raise HTTPException(404, "Pengaturan tidak dikenal.")
    try:
        nilai = pengaturan.periksa(kunci, isi.get("nilai"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    with db.koneksi() as con:
        pengaturan.simpan(con, kunci, nilai)
    return {"ok": True}
