"""Lingkup "khusus cabang": isi dashboard hanya dari data cabang yang dipilih.

Dipakai untuk laporan yang dibagikan ke satu cabang (tampilan, ekspor HTML,
paket untuk Claude). Yang dikeluarkan:
- angka gabungan semua cabang (total member, terverifikasi, member baru
  semua cabang dari web loyalty, persentase "dari semua member");
- baris cabang lain di kampanye yang menyasar beberapa cabang, termasuk
  biaya "dibagi ke semua cabang sasaran" (dihitung dari bill cabang lain);
- keterangan jendela waktu dan catatan yang menyebut cabang lain;
- nama file unggahan (bisa memuat nama cabang lain).

Fungsi ini bekerja pada hasil `dashboard.hitung`, jadi rumus angka yang
tersisa sama persis dengan tampilan lengkap.
"""

from __future__ import annotations

import copy
import re

from app.pengaturan_bawaan import CABANG

GABUNGAN_MEMBER = ("total_member", "terverifikasi", "terverifikasi_baru", "member_baru")
KOLOM_GABUNGAN = "Member baru (semua cabang)"


def _lain(cabang: str) -> list[str]:
    return [c for c in CABANG if c != cabang]


def _sebut(teks, nama: list[str]) -> bool:
    return isinstance(teks, str) and any(re.search(rf"\b{re.escape(n)}\b", teks, re.I) for n in nama)


def _jendela(rows: list[dict], cabang: str, kunci_ket: str, kunci_bill: tuple[str, ...]) -> list[dict]:
    hasil = []
    for r in rows:
        ket = r.get(kunci_ket)
        if _sebut(ket, _lain(cabang)):
            if kunci_bill and not any(r.get(k) for k in kunci_bill):
                continue  # jendela cabang lain dan cabang ini tidak punya bill di jam itu
            r = {**r, kunci_ket: None}
        elif isinstance(ket, str):
            r = {**r, kunci_ket: re.sub(rf"^hanya {re.escape(cabang)}[,]?\s*", "", ket, flags=re.I) or None}
        hasil.append(r)
    return hasil


def _membership(m: dict):
    k = m.get("kartu") or {}
    for x in GABUNGAN_MEMBER:
        k.pop(x, None)
    for x in ("pernah_transaksi",):
        if isinstance(k.get(x), dict) and "label" in k[x]:
            k[x]["label"] = re.sub(r"^[^·]*dari semua member · ", "", k[x]["label"])
    m["harian"] = [{c: v for c, v in r.items() if c != KOLOM_GABUNGAN} for r in m.get("harian", [])]
    b = m.get("banding")
    if b and b.get("baris"):
        b["baris"] = [r for r in b["baris"] if not str(r.get("metrik", "")).startswith(KOLOM_GABUNGAN)]


def _kampanye(k: dict, cabang: str):
    lain = _lain(cabang)
    k["cabang"] = cabang
    k["tambahan_bill"] = [r for r in k.get("tambahan_bill", []) if r.get("Cabang") not in lain]
    k["korelasi"] = [r for r in k.get("korelasi", []) if r.get("Cabang") not in lain]
    k["biaya_bill"] = [r for r in k.get("biaya_bill", [])
                       if not _sebut(r.get("Cara bagi"), lain) and not str(r.get("Cara bagi", "")).startswith("Dibagi")]
    k["batas_bawah"] = False
    k["catatan"] = [c for c in k.get("catatan", []) if not c.startswith("Dibebankan penuh") and "dua cabang" not in c]
    k["catatan"].append("Biaya iklan per bill tambahan = seluruh anggaran dibagi tambahan bill cabang ini.")


def terapkan(data: dict) -> dict:
    d = copy.deepcopy(data)
    cabang = d["cabang"]
    d["lingkup"] = "khusus"

    _membership(d.get("membership") or {})

    ft = d.get("foot_traffic") or {}
    if ft.get("jendela"):
        ft["jendela"] = _jendela(ft["jendela"], cabang, "keterangan", ("bill_hari_kerja", "bill_akhir_pekan"))
    d["jendela_waktu"] = _jendela(d.get("jendela_waktu", []), cabang, "berlaku", ())

    s = d.get("sosmed") or {}
    s["catatan"] = [c for c in s.get("catatan", []) if "kedua cabang" not in c and not _sebut(c, _lain(cabang))]
    for k in (s.get("kampanye") or {}).get("daftar", []):
        _kampanye(k, cabang)

    for r in (d.get("kualitas") or {}).get("rekonsiliasi", []):
        r["file"] = "Bill Report + Sales Menu COGS Report"
    return d
