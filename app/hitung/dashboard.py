"""Merakit isi dashboard untuk satu cabang, satu bulan, satu pilihan periode."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app import pengaturan
from app import pengaturan_bawaan as P
from app.angka import format_angka, format_rupiah
from app.hitung import foot_traffic, menu, overview
from app.hitung.data import DataRentang, muat
from app.hitung.minggu import (BULAN_PANJANG, Rentang, bulan_penuh, bulan_sebelumnya, label_tanggal,
                               minggu_bulan, minggu_sebelumnya, ringkas_tanggal)
from app.hitung.nilai import bagi, jumlah
from app.hitung.overview import tgl

TAB_MENYUSUL = {
    "promo": ("Performa Promo", 6), "membership": ("Progress Membership Keluarga Ampyang", 7),
    "sosmed": ("Performa Sosial Media & Campaign/Konten", 8),
}


def bulan_tersedia(con) -> list[str]:
    r = con.execute("SELECT min(awal), max(akhir) FROM periode").fetchone()
    if not r or r[0] is None:
        return []
    hasil, t = [], date(r[0].year, r[0].month, 1)
    while t <= r[1]:
        hasil.append(f"{t.year}-{t.month:02d}")
        t = date(t.year + (t.month == 12), t.month % 12 + 1, 1)
    return hasil


def _ringkas_label(d: DataRentang) -> str:
    if not d.ada_data:
        return "belum ada data"
    if d.lengkap:
        return f"{len(d.hari)} hari"
    return f"parsial ({len(d.tercakup)} hari)"


def _tabel_bulanan(con, cabang: str, tahun: int, bulan: int, minggu: list[Rentang], bp: DataRentang) -> dict:
    kolom = []
    data_minggu = []
    for m in minggu:
        d = muat(con, cabang, m.awal, m.akhir)
        data_minggu.append((m, d))
    def isi(label, d):
        r = overview.ringkas(d)
        ada = d.ada_data
        return {
            "label": label, "status": _ringkas_label(d),
            "Hari data": f"{len(d.tercakup)}/{len(d.hari)}",
            "Hari buka": str(len(d.hari_buka)) if ada else "—",
            "Grand Total": format_rupiah(r["gt"]) if ada else "Tidak diketahui",
            "Jumlah bill": format_angka(r["bill"]) if ada else "Tidak diketahui",
            "Rata-rata bill F&B": format_rupiah(bagi(r["gt_fnb"], r["bill_fnb"])) if ada and r["bill_fnb"] else "Tidak diketahui",
            "Grand Total / hari buka": format_rupiah(bagi(r["gt_buka"], len(d.hari_buka))) if ada and d.hari_buka else "Tidak diketahui",
            "Bill / hari buka": format_angka(bagi(r["bill_buka"], len(d.hari_buka)), 1) if ada and d.hari_buka else "Tidak diketahui",
        }
    for m, d in data_minggu:
        kolom.append(isi(m.label, d))
    kolom.append(isi("Bulan Penuh", bp))

    # Jembatan Σ minggu → Bulan Penuh. Minggu memakai aturan Senin, jadi
    # jumlahnya tidak sama dengan bulan kalender; selisihnya ditampilkan.
    hari_minggu = {t for m in minggu for t in m.hari}
    hari_bulan = set(bp.hari)
    awal = min(hari_minggu | hari_bulan) if hari_minggu else bp.awal
    akhir = max(hari_minggu | hari_bulan) if hari_minggu else bp.akhir
    semua = muat(con, cabang, awal, akhir)
    gt_hari = semua.bill.groupby("sales_date")["grand_total"].agg(jumlah).to_dict() if len(semua.bill) else {}
    bill_hari = semua.bill.groupby("sales_date").size().to_dict() if len(semua.bill) else {}
    keluar = sorted(hari_minggu - hari_bulan)
    masuk = sorted(hari_bulan - hari_minggu)
    def jml(hs, src):
        return sum((Decimal(src.get(t, 0)) for t in hs), Decimal(0))
    jembatan = [
        {"label": f"Σ minggu {minggu[0].kode}–{minggu[-1].kode}" if minggu else "Σ minggu",
         "grand_total": format_rupiah(jml(hari_minggu, gt_hari)), "bill": format_angka(jml(hari_minggu, bill_hari))},
    ]
    if keluar:
        jembatan.append({"label": f"− hari minggu ini yang jatuh di bulan lain ({ringkas_tanggal(keluar)})",
                         "grand_total": "−" + format_rupiah(jml(keluar, gt_hari)), "bill": "−" + format_angka(jml(keluar, bill_hari))})
    if masuk:
        jembatan.append({"label": f"+ hari bulan ini yang masuk minggu bulan lain ({ringkas_tanggal(masuk)})",
                         "grand_total": "+" + format_rupiah(jml(masuk, gt_hari)), "bill": "+" + format_angka(jml(masuk, bill_hari))})
    jembatan.append({"label": "= Bulan Penuh", "grand_total": format_rupiah(jml(hari_bulan, gt_hari)),
                     "bill": format_angka(jml(hari_bulan, bill_hari))})
    tanpa = [t for t in sorted(hari_minggu | hari_bulan) if t not in set(semua.tercakup)]
    return {"kolom": kolom, "jembatan": jembatan,
            "catatan": ("Hari tanpa data unggahan (dihitung 0 di jembatan ini): " + ringkas_tanggal(tanpa)) if tanpa else None}


def _kualitas(con, d: DataRentang, libur_ok: bool) -> dict:
    per = con.execute("""
        SELECT p.unggahan_id, p.jenis, p.awal, p.akhir, p.rekonsiliasi_gagal, u.file_bill, u.file_cogs
        FROM periode p JOIN unggahan u ON u.id = p.unggahan_id
        WHERE p.cabang = ? AND p.awal <= ? AND p.akhir >= ? ORDER BY p.awal""", [d.cabang, d.akhir, d.awal]).fetchall()
    def cakup(j):
        return len({t for t in d.hari for p in per if p[1] == j and p[2] <= t <= p[3]})
    file = [
        {"file": "Bill Report (wajib)", "status": "ada" if cakup("bill") else "tidak ada", "keterangan": f"{cakup('bill')}/{len(d.hari)} hari"},
        {"file": "Sales Menu COGS Report (wajib)", "status": "ada" if cakup("cogs") else "tidak ada", "keterangan": f"{cakup('cogs')}/{len(d.hari)} hari"},
    ] + [{"file": f, "status": "tidak ada", "keterangan": f"diolah mulai tahap {t}"} for f, t in (
        ("Promotion Report", 6), ("Customer Data Report", 7), ("Staff Sales & Cancel Report", 6),
        ("Cancel Menu Detail Report", 6), ("Data loyalty Keluarga Ampyang", 7), ("Instagram Insights (opsional)", 8))]
    rekon = []
    for uid in sorted({p[0] for p in per}):
        p = next(x for x in per if x[0] == uid)
        rekon.append({"unggahan": f"{p[2]:%d-%m-%Y} s/d {p[3]:%d-%m-%Y}", "file": f"{p[5]} + {p[6]}",
                      "status": "TIDAK COCOK (disimpan dengan konfirmasi)" if p[4] else "cocok"})
    c = d.cogs
    tanpa = c[c["tanpa_hpp"]]
    salah = c[c["salah_input"]]
    belum = sorted({f"{k} / {x}" for k, x in zip(c[c["kelompok"] == "lainnya"]["menu_category"],
                                                    c[c["kelompok"] == "lainnya"]["menu_category_detail"])})
    hari = []
    if d.tanpa_data:
        hari.append({"jenis": "Tanpa data unggahan", "tanggal": ringkas_tanggal(d.tanpa_data)})
    if d.tutup:
        hari.append({"jenis": "Tutup (0 transaksi)", "tanggal": ", ".join(tgl(t) for t in d.tutup)})
    if d.parsial:
        hari.append({"jenis": "Parsial (keluar dari rata-rata harian)", "tanggal": ", ".join(tgl(t) for t in d.parsial)})
    return {
        "file": file,
        "rekonsiliasi": rekon,
        "hari": hari,
        "baris_dikeluarkan": [
            {"hal": "Bill Sales Type bukan 'Sales'", "jumlah": int((d.bill_semua["sales_type"] != "Sales").sum())},
            {"hal": "Baris COGS salah input resep (HPP/unit > 1,5× harga) — keluar dari margin", "jumlah": int(len(salah))},
        ],
        "tanpa_hpp": {"menu": int(tanpa["menu_bersih"].nunique()), "baris": int(len(tanpa)),
                      "omzet": format_rupiah(jumlah(tanpa["total"])),
                      "daftar": sorted(tanpa["menu_bersih"].unique().tolist())},
        "kategori_belum_dipetakan": belum,
        "hari_libur_terverifikasi": libur_ok,
    }


def hitung(con, cabang: str, tahun: int, bulan: int, pilih: str) -> dict:
    minggu = minggu_bulan(tahun, bulan)
    bp = bulan_penuh(tahun, bulan)
    pilihan = {m.kode: m for m in minggu} | {"bulan": bp}
    if pilih not in pilihan:
        pilih = "bulan"
    r = pilihan[pilih]

    libur_list = pengaturan.ambil(con, "hari_libur")
    libur = {x["tanggal"]: x["nama"] for x in libur_list}
    for rd in pengaturan.ambil(con, "ramadan"):
        t, z = date.fromisoformat(rd["awal"]), date.fromisoformat(rd["akhir"])
        while t <= z:
            libur.setdefault(t.isoformat(), "Ramadan")
            t += timedelta(days=1)

    d = muat(con, cabang, r.awal, r.akhir)
    rc = overview.ringkas(d)

    tombol = []
    for m in minggu + [bp]:
        dm = d if m.kode == pilih else muat(con, cabang, m.awal, m.akhir)
        tombol.append({"kode": m.kode, "label": m.label if m.kode != "bulan" else "Bulan Penuh",
                       "status": _ringkas_label(dm), "ada_data": dm.ada_data, "lengkap": dm.lengkap})

    if pilih == "bulan":
        ty, tb = bulan_sebelumnya(tahun, bulan)
        prev_r = bulan_penuh(ty, tb)
        label_prev = f"Dibanding bulan sebelumnya ({BULAN_PANJANG[tb - 1]} {ty})"
    else:
        prev_r = minggu_sebelumnya(r)
        label_prev = f"Dibanding minggu sebelumnya ({label_tanggal(prev_r.awal, prev_r.akhir)})"
    dp = muat(con, cabang, prev_r.awal, prev_r.akhir)
    rp = overview.ringkas(dp)

    hasil = {
        "cabang": cabang, "tahun": tahun, "bulan": bulan, "pilih": pilih,
        "periode": {"label": r.label, "awal": r.awal.isoformat(), "akhir": r.akhir.isoformat(),
                    "status": _ringkas_label(d), "ada_data": d.ada_data, "lengkap": d.lengkap,
                    "hari_data": len(d.tercakup), "hari_rentang": len(d.hari)},
        "tombol": tombol,
        "peringatan_merah": bool(d.rekon_gagal),
        "overview": {
            "kartu": overview.kartu(d, rc),
            "harian": overview.harian(d, libur),
            "rekonsiliasi": overview.rekonsiliasi(d),
            "diskon": overview.diskon(d, rc),
            "channel": overview.per_channel(d, rc),
            "banding": overview.banding(d, rc, dp, rp, label_prev),
            "bulanan": _tabel_bulanan(con, cabang, tahun, bulan, minggu, d) if pilih == "bulan" else None,
            "target": (pengaturan.ambil(con, "target_omzet") or {}).get(f"{cabang}|{tahun}-{bulan:02d}"),
        },
        "foot_traffic": {**foot_traffic.hitung(d), "banding": foot_traffic.banding(d, dp, label_prev)},
        **{t: menu.hitung(con, t, d, dp, label_prev) for t in ("makanan", "kudapan", "minuman")},
        "kualitas": _kualitas(con, d, bool(pengaturan.ambil(con, "hari_libur_terverifikasi"))),
        "menyusul": [{"kode": k, "nama": n, "tahap": t} for k, (n, t) in TAB_MENYUSUL.items()],
        "jendela_waktu": P.JENDELA_WAKTU,
    }
    return hasil
