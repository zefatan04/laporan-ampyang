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
    "target_omzet": {},  # {"Rungkut|2026-10": 250000000} - kosong = tidak ditampilkan
    "menu_baru": [],  # [{"nama": "Tahu Walik", "mulai": "2026-09-01", "tab": "kudapan"}]
    # [{"nama", "mulai", "selesai", "cabang": Rungkut|Mawar|keduanya, "promotion_esb": [...], "menu_promo": [...]}]
    "promo": [],
    # Nama di kolom Promotion ESB yang bukan promo pemasaran (tidak dinilai).
    "promotion_internal": ["Discount Karyawan 10 %", "Discount BOD"],
    # Selisih omzet terhadap pembanding di dalam ±ambang dianggap Netral.
    "ambang_netral_persen": 5,
    # [{"nama", "cabang": Rungkut|Mawar|keduanya, "akun": Rungkut|Mawar|Brand, "mulai", "selesai",
    #   "anggaran": "1500000" (teks desimal), "platform", "tujuan", "menu_promo": [...]}]
    "kampanye": [],
    # [{"tanggal", "akun", "format", "topik"}]
    "konten": [],
    # Total mingguan disalin dari aplikasi Instagram saat CSV harian tidak bisa diunduh.
    # [{"akun", "senin": "2026-09-28", "nilai": {"tayangan": 1234, ...}}] - metrik yang tidak diisi tidak ada
    "ig_manual": [],
}

AKUN_IG = ("Rungkut", "Mawar", "Brand")
METRIK_IG = ("tayangan", "jangkauan", "interaksi", "kunjungan", "klik", "pengikut")


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
    if kunci == "kampanye":
        from decimal import Decimal, InvalidOperation
        hasil = []
        for x in nilai or []:
            nama = str(x.get("nama", "")).strip()
            if not nama:
                raise ValueError("Nama kampanye kosong.")
            a, z = date.fromisoformat(x["mulai"]), date.fromisoformat(x["selesai"])
            if z < a:
                raise ValueError(f"Kampanye {nama}: tanggal selesai lebih awal dari mulai.")
            if x.get("cabang") not in ("Rungkut", "Mawar", "keduanya"):
                raise ValueError(f"Kampanye {nama}: cabang sasaran harus Rungkut, Mawar, atau keduanya.")
            if x.get("akun") not in AKUN_IG:
                raise ValueError(f"Kampanye {nama}: akun Instagram harus Rungkut, Mawar, atau Brand.")
            angg = str(x.get("anggaran", "")).strip()
            if angg:
                try:
                    d = Decimal(angg)
                except InvalidOperation as e:
                    raise ValueError(f"Kampanye {nama}: anggaran '{angg}' bukan angka (tulis tanpa titik, mis. 1500000).") from e
                if d < 0:
                    raise ValueError(f"Kampanye {nama}: anggaran tidak boleh negatif.")
                angg = str(d)
            bersih = lambda xs: [" ".join(str(v).split()) for v in (xs or []) if str(v).strip()]
            hasil.append({"nama": nama, "cabang": x["cabang"], "akun": x["akun"], "mulai": x["mulai"], "selesai": x["selesai"],
                          "anggaran": angg, "platform": str(x.get("platform", "")).strip(),
                          "tujuan": str(x.get("tujuan", "")).strip(), "menu_promo": bersih(x.get("menu_promo"))})
        return hasil
    if kunci == "konten":
        hasil = []
        for x in nilai or []:
            date.fromisoformat(x["tanggal"])
            if x.get("akun") not in AKUN_IG:
                raise ValueError(f"Konten {x['tanggal']}: akun harus Rungkut, Mawar, atau Brand.")
            hasil.append({"tanggal": x["tanggal"], "akun": x["akun"], "format": str(x.get("format", "")).strip(),
                          "topik": str(x.get("topik", "")).strip()})
        return sorted(hasil, key=lambda x: x["tanggal"])
    if kunci == "ig_manual":
        hasil, kunci_ada = [], set()
        for x in nilai or []:
            t = date.fromisoformat(x["senin"])
            if t.weekday() != 0:
                raise ValueError(f"Input manual Instagram: {x['senin']} bukan hari Senin.")
            if x.get("akun") not in AKUN_IG:
                raise ValueError(f"Input manual {x['senin']}: akun harus Rungkut, Mawar, atau Brand.")
            if (x["akun"], x["senin"]) in kunci_ada:
                raise ValueError(f"Input manual {x['akun']} minggu {x['senin']} ditulis dua kali.")
            kunci_ada.add((x["akun"], x["senin"]))
            isi = {}
            for m, v in (x.get("nilai") or {}).items():
                if m not in METRIK_IG:
                    raise ValueError(f"Metrik '{m}' tidak dikenal. Pakai: {', '.join(METRIK_IG)}.")
                if not str(v).isdigit():
                    raise ValueError(f"Input manual {x['akun']} {x['senin']}: {m} = '{v}' harus bilangan bulat tanpa titik.")
                isi[m] = int(v)
            if not isi:
                raise ValueError(f"Input manual {x['akun']} {x['senin']}: belum ada angka yang diisi.")
            hasil.append({"akun": x["akun"], "senin": x["senin"], "nilai": isi})
        return sorted(hasil, key=lambda x: (x["senin"], x["akun"]))
    if kunci == "kategori":
        if set(nilai) != set(BAWAAN["kategori"]):
            raise ValueError("Kunci kategori tidak lengkap.")
        return {k: [str(x).strip() for x in v if str(x).strip()] for k, v in nilai.items()}
    raise ValueError(kunci)
