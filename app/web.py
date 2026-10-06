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

from app import db
from app.hitung import dashboard
from app.parser.esb import baca_file_esb, daftar_cabang_metadata
from app.validasi import validasi_unggahan

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


@app.post("/api/unggah")
async def unggah(awal: date = Form(...), akhir: date = Form(...), cabang: str = Form(""),
                 files: list[UploadFile] = File(...)):
    if akhir < awal:
        raise HTTPException(400, "Tanggal akhir lebih awal dari tanggal mulai.")
    _bersihkan_antre()
    hasil = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            p = Path(tmp) / Path(f.filename or "file.xlsx").name
            with p.open("wb") as keluar:
                shutil.copyfileobj(f.file, keluar)
            hasil.append(baca_file_esb(p, nama_file=f.filename))

    harap = [c.strip() for c in cabang.split(",") if c.strip()] or None
    with db.koneksi() as con:
        tersimpan = db.periode_tersimpan(con)
    lap = validasi_unggahan(hasil, awal, akhir, tersimpan=tersimpan, cabang=harap)
    cabang_data = sorted({c for h in hasil if h.data is not None for c in h.data["cabang"].dropna()})
    tumpang = [p for p in tersimpan if p["cabang"] in cabang_data and p["awal"] <= akhir and p["akhir"] >= awal]

    token = secrets.token_urlsafe(16)
    _ANTRE[token] = {"waktu": time.time(), "hasil": hasil, "laporan": lap, "awal": awal, "akhir": akhir}
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
        } for h in hasil],
        "cek": [asdict(c) for c in lap.cek],
        "terblokir": lap.terblokir,
        "butuh_konfirmasi": lap.butuh_konfirmasi,
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
    with db.koneksi() as con:
        try:
            uid = db.simpan_unggahan(con, antre["hasil"], antre["laporan"], antre["awal"], antre["akhir"],
                                     ganti=req.ganti, simpan_walau_tidak_cocok=req.simpan_walau_tidak_cocok)
        except db.TidakBolehDisimpan as e:
            raise HTTPException(409, str(e)) from e
    _ANTRE.pop(req.token, None)
    return {"unggahan_id": uid}


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
