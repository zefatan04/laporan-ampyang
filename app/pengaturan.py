"""Pengaturan yang bisa diubah user, disimpan di DuckDB (tabel `pengaturan`).

Nilai yang belum pernah diubah diambil dari app/pengaturan_bawaan.py.
"""

from __future__ import annotations

import json

from app import pengaturan_bawaan as B

BAWAAN = {
    "kategori": B.KATEGORI,
    "suhu_per_menu": B.SUHU_PER_MENU,
    "hari_libur": [{"tanggal": t, "nama": n} for t, n in B.HARI_LIBUR],
    "ramadan": [{"awal": a, "akhir": z} for a, z in B.RAMADAN],
    "hari_libur_terverifikasi": False,
    "target_omzet": {},
    "menu_baru": [],
    # [{"nama", "mulai", "selesai", "cabang": Rungkut|Mawar|keduanya, "promotion_esb": [...], "menu_promo": [...]}]
    "promo": [],
    # Nama di kolom Promotion ESB yang bukan promo pemasaran (tidak dinilai).
    "promotion_internal": ["Discount Karyawan 10 %", "Discount BOD"],
    # Selisih omzet terhadap pembanding di dalam ±ambang dianggap Netral.
    "ambang_netral_persen": 5,  # [{"nama": "Tahu Walik", "mulai": "2026-09-01", "tab": "kudapan"}]  # {"Rungkut|2026-10": 250000000} - kosong = tidak ditampilkan
}


def _pastikan(con):
    con.execute("CREATE TABLE IF NOT EXISTS pengaturan (kunci VARCHAR PRIMARY KEY, nilai JSON NOT NULL)")


def ambil(con, kunci: str):
    _pastikan(con)
    r = con.execute("SELECT nilai FROM pengaturan WHERE kunci = ?", [kunci]).fetchone()
    return json.loads(r[0]) if r else json.loads(json.dumps(BAWAAN[kunci]))


def simpan(con, kunci: str, nilai):
    if kunci not in BAWAAN:
        raise KeyError(kunci)
    _pastikan(con)
    con.execute("INSERT OR REPLACE INTO pengaturan VALUES (?, ?)", [kunci, json.dumps(nilai)])


def semua(con) -> dict:
    return {k: ambil(con, k) for k in BAWAAN}


def periksa(kunci: str, nilai):
    """Validasi isian Pengaturan sebelum disimpan. Salah format = ditolak, bukan ditebak."""
    from datetime import date

    if kunci == "hari_libur":
        hasil = []
        for x in nilai or []:
            date.fromisoformat(x["tanggal"])
            if not str(x.get("nama", "")).strip():
                raise ValueError(f"Nama hari libur {x['tanggal']} kosong.")
            hasil.append({"tanggal": x["tanggal"], "nama": str(x["nama"]).strip()})
        return sorted(hasil, key=lambda x: x["tanggal"])
    if kunci == "ramadan":
        for x in nilai or []:
            if date.fromisoformat(x["akhir"]) < date.fromisoformat(x["awal"]):
                raise ValueError("Tanggal akhir Ramadan lebih awal dari tanggal awal.")
        return nilai or []
    if kunci == "hari_libur_terverifikasi":
        return bool(nilai)
    if kunci == "target_omzet":
        hasil = {}
        for k, v in (nilai or {}).items():
            cabang, _, bulan = k.partition("|")
            if cabang not in ("Rungkut", "Mawar"):
                raise ValueError(f"Cabang tidak dikenal: {cabang}")
            date.fromisoformat(bulan + "-01")
            if int(v) <= 0:
                raise ValueError("Target harus lebih dari 0.")
            hasil[k] = int(v)
        return hasil
    if kunci == "suhu_per_menu":
        for m, s in (nilai or {}).items():
            if s not in ("panas", "dingin"):
                raise ValueError(f"Suhu '{s}' untuk {m} harus 'panas' atau 'dingin'.")
        return nilai or {}
    if kunci == "menu_baru":
        hasil = []
        for x in nilai or []:
            date.fromisoformat(x["mulai"])
            if x.get("tab") not in ("makanan", "kudapan", "minuman"):
                raise ValueError(f"Tab untuk {x.get('nama')} harus makanan, kudapan, atau minuman.")
            if not str(x.get("nama", "")).strip():
                raise ValueError("Nama menu baru kosong.")
            hasil.append({"nama": str(x["nama"]).strip(), "mulai": x["mulai"], "tab": x["tab"]})
        return hasil
    if kunci == "promo":
        hasil = []
        for x in nilai or []:
            nama = str(x.get("nama", "")).strip()
            if not nama:
                raise ValueError("Nama promo kosong.")
            a, z = date.fromisoformat(x["mulai"]), date.fromisoformat(x["selesai"])
            if z < a:
                raise ValueError(f"Promo {nama}: tanggal selesai lebih awal dari mulai.")
            if x.get("cabang") not in ("Rungkut", "Mawar", "keduanya"):
                raise ValueError(f"Promo {nama}: cabang harus Rungkut, Mawar, atau keduanya.")
            bersih = lambda xs: [" ".join(str(v).split()) for v in (xs or []) if str(v).strip()]
            hasil.append({"nama": nama, "mulai": x["mulai"], "selesai": x["selesai"], "cabang": x["cabang"],
                          "promotion_esb": bersih(x.get("promotion_esb")), "menu_promo": bersih(x.get("menu_promo"))})
        return hasil
    if kunci == "promotion_internal":
        return [" ".join(str(v).split()) for v in (nilai or []) if str(v).strip()]
    if kunci == "ambang_netral_persen":
        v = float(nilai)
        if not 0 <= v <= 50:
            raise ValueError("Ambang netral harus 0–50%.")
        return v
    if kunci == "kategori":
        if set(nilai) != set(BAWAAN["kategori"]):
            raise ValueError("Kunci kategori tidak lengkap.")
        return {k: [str(x).strip() for x in v if str(x).strip()] for k, v in nilai.items()}
    raise ValueError(kunci)
