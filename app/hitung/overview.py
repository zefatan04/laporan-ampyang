"""Tab Overview Omzet.

Angka utama omzet = Grand Total (sudah termasuk pajak & service charge), dari
Bill Report dengan Sales Type = 'Sales'. Rata-rata bill memakai bill F&B
saja (keputusan 6 Okt 2026): bill yang memuat item non-F&B (sewa raket,
mahjong, aksesoris) dikeluarkan dari rata-rata dan dihitung terpisah.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from app.angka import format_angka, format_persen, format_rupiah
from app.hitung.data import DataRentang
from app.hitung.nilai import TIDAK_DIKETAHUI, asal, bagi, jumlah, nilai, persen, tidak_diketahui
from app.validasi import NAMA_HARI

SUMBER_BILL = "Bill Report (Sales Recapitulation Report)"
SUMBER_COGS = "Sales Menu COGS Report"
F_SALES = "Sales Type = 'Sales'"


def tgl(t: date) -> str:
    from app.hitung.minggu import BULAN
    return f"{NAMA_HARI[t.weekday()]} {t.day} {BULAN[t.month - 1]}"


# ---------------------------------------------------------------------------
# Komposisi bill: F&B murni / campuran / non-F&B saja
# ---------------------------------------------------------------------------

def komposisi_bill(d: DataRentang) -> pd.DataFrame:
    """Satu baris per bill Sales: grand_total, sales_date, jenis ('fnb'|'campuran'|'non_fnb'|'tanpa_item')."""
    b = d.bill[["sales_number", "sales_date", "grand_total", "subtotal", "visit_purpose"]].copy()
    if not len(b):
        b["jenis"] = []
        return b
    c = d.cogs
    non = c.assign(non=c["kelompok"] == "non_fnb").groupby("sales_number")["non"].agg(["any", "all"])
    def jenis(sn):
        if sn not in non.index:
            return "tanpa_item"
        a, s = non.loc[sn, "any"], non.loc[sn, "all"]
        return "non_fnb" if s else ("campuran" if a else "fnb")
    b["jenis"] = b["sales_number"].map(jenis)
    return b


# ---------------------------------------------------------------------------
# Ringkasan angka mentah (dipakai kartu dan perbandingan)
# ---------------------------------------------------------------------------

def ringkas(d: DataRentang) -> dict:
    kb = komposisi_bill(d)
    buka = set(d.hari_buka)
    fnb = kb[kb["jenis"] == "fnb"]
    di_buka = kb[kb["sales_date"].isin(buka)]
    return {
        "ada_data": d.ada_data,
        "lengkap": d.lengkap,
        "hari_data": len(d.tercakup),
        "hari_rentang": len(d.hari),
        "hari_buka": len(d.hari_buka),
        "gt": jumlah(d.bill["grand_total"]),
        "sub": jumlah(d.bill["subtotal"]),
        "bill": len(d.bill),
        "bill_fnb": len(fnb),
        "gt_fnb": jumlah(fnb["grand_total"]),
        "gt_buka": jumlah(di_buka["grand_total"]),
        "bill_buka": len(di_buka),
        "fnb_buka": len(di_buka[di_buka["jenis"] == "fnb"]),
        "gt_fnb_buka": jumlah(di_buka[di_buka["jenis"] == "fnb"]["grand_total"]),
        "kb": kb,
    }


def _asal_rentang(d: DataRentang) -> list[str]:
    f = [F_SALES, f"Cabang = {d.cabang}", f"Tanggal {d.awal:%d-%m-%Y} s/d {d.akhir:%d-%m-%Y}"]
    if d.tanpa_data:
        f.append(f"Hanya {len(d.tercakup)} dari {len(d.hari)} hari yang ada datanya")
    return f


def _dikeluarkan_non_sales(d: DataRentang) -> dict:
    n = int((d.bill_semua["sales_type"] != "Sales").sum())
    return {"alasan": "Sales Type bukan 'Sales' (mis. Non Sales)", "jumlah": n}


def _peringatan(d: DataRentang) -> list[str]:
    p = []
    if d.rekon_gagal:
        p.append("Sebagian data periode ini disimpan walau rekonsiliasi tidak cocok. Angka bisa salah.")
    if d.ada_data and not d.lengkap:
        p.append(f"Parsial: data hanya {len(d.tercakup)} dari {len(d.hari)} hari.")
    return p


def kartu(d: DataRentang, r: dict) -> dict:
    if not d.ada_data:
        alasan = f"belum ada Bill + COGS Report {d.cabang} yang diunggah untuk {d.awal:%d-%m-%Y} s/d {d.akhir:%d-%m-%Y}"
        return {k: tidak_diketahui(alasan) for k in
                ("grand_total", "subtotal", "jumlah_bill", "rata_bill_fnb", "omzet_per_hari_buka",
                 "hari_terbaik", "hari_terlemah", "omzet_non_fnb")}
    pr = _peringatan(d)
    filt = _asal_rentang(d)
    ns = _dikeluarkan_non_sales(d)
    kb = r["kb"]
    k = {}
    k["grand_total"] = nilai(r["gt"], "rupiah", asal(
        "Σ Grand Total", [f"{SUMBER_BILL} · kolom Grand Total"], filt, r["bill"], [ns],
        ["Grand Total sudah termasuk pajak (PB1) dan service charge."]), peringatan=pr)
    k["subtotal"] = nilai(r["sub"], "rupiah", asal(
        "Σ Subtotal", [f"{SUMBER_BILL} · kolom Subtotal"], filt, r["bill"], [ns],
        ["Subtotal = harga menu sebelum diskon, pajak, dan service charge."]), peringatan=pr)
    k["jumlah_bill"] = nilai(r["bill"], "angka", asal(
        "Jumlah Sales Number", [f"{SUMBER_BILL} · kolom Sales Number"], filt, r["bill"], [ns]), peringatan=pr)

    keluar = [
        ns,
        {"alasan": "Bill berisi item non-F&B saja (jasa/aksesoris)", "jumlah": int((kb["jenis"] == "non_fnb").sum())},
        {"alasan": "Bill campuran F&B + non-F&B (Grand Total tidak bisa dipisah tanpa estimasi)",
         "jumlah": int((kb["jenis"] == "campuran").sum())},
        {"alasan": "Bill tanpa baris di COGS Report (isi bill tidak diketahui)", "jumlah": int((kb["jenis"] == "tanpa_item").sum())},
    ]
    a = asal("Σ Grand Total bill F&B ÷ jumlah bill F&B",
             [f"{SUMBER_BILL} · Grand Total", f"{SUMBER_COGS} · Menu Category (untuk menentukan isi bill)"],
             filt + ["Bill F&B = semua itemnya makanan/minuman/add-on"], r["bill_fnb"], keluar)
    rb = bagi(r["gt_fnb"], r["bill_fnb"])
    k["rata_bill_fnb"] = (nilai(rb, "rupiah", a, peringatan=pr) if rb is not None
                         else tidak_diketahui("tidak ada bill F&B di periode ini", a))

    hb = d.hari_buka
    keluar_hari = [ns, {"alasan": "Hari tutup (0 transaksi): " + ", ".join(tgl(t) for t in d.tutup), "jumlah": len(d.tutup)},
                   {"alasan": "Hari parsial: " + ", ".join(tgl(t) for t in d.parsial), "jumlah": len(d.parsial)},
                   {"alasan": "Hari tanpa data unggahan", "jumlah": len(d.tanpa_data)}]
    a = asal("Σ Grand Total di hari buka ÷ jumlah hari buka", [f"{SUMBER_BILL} · Grand Total, Sales Date"],
             filt, r["bill_buka"], keluar_hari, [f"{len(hb)} hari buka dipakai sebagai pembagi."])
    v = bagi(r["gt_buka"], len(hb))
    k["omzet_per_hari_buka"] = nilai(v, "rupiah", a, peringatan=pr) if v is not None else tidak_diketahui("tidak ada hari buka", a)

    per_hari = d.bill[d.bill["sales_date"].isin(set(hb))].groupby("sales_date")["grand_total"].agg(jumlah)
    a = asal("Hari dengan Σ Grand Total tertinggi/terendah di antara hari buka",
             [f"{SUMBER_BILL} · Grand Total, Sales Date"], filt, r["bill_buka"], keluar_hari)
    if len(per_hari) >= 2:
        hi, lo = per_hari.idxmax(), per_hari.idxmin()
        k["hari_terbaik"] = {**nilai(per_hari[hi], "rupiah", a, peringatan=pr), "label": tgl(hi)}
        k["hari_terlemah"] = {**nilai(per_hari[lo], "rupiah", a, peringatan=pr), "label": tgl(lo)}
    else:
        k["hari_terbaik"] = k["hari_terlemah"] = tidak_diketahui("butuh minimal 2 hari buka", a)

    non = d.cogs[d.cogs["kelompok"] == "non_fnb"]
    k["omzet_non_fnb"] = nilai(jumlah(non["total"]), "rupiah", asal(
        "Σ Total item non-F&B", [f"{SUMBER_COGS} · kolom Total, Menu Category"],
        filt + ["Menu Category = JASA / AKSESORIS"], len(non),
        catatan=["Basis Subtotal (sebelum pajak/service), karena COGS Report tidak punya Grand Total.",
                 "Sudah termasuk di dalam Grand Total di atas."]), peringatan=pr)
    return k


# ---------------------------------------------------------------------------
# Harian, rekonsiliasi, diskon, channel
# ---------------------------------------------------------------------------

def harian(d: DataRentang, libur: dict[str, str]) -> list[dict]:
    g = d.bill.groupby("sales_date").agg(gt=("grand_total", jumlah), bill=("sales_number", "size")) if len(d.bill) else None
    tutup, parsial, ada = set(d.tutup), set(d.parsial), set(d.tercakup)
    hasil = []
    for t in d.hari:
        status = "tanpa_data" if t not in ada else "tutup" if t in tutup else "parsial" if t in parsial else "buka"
        punya = g is not None and t in g.index
        hasil.append({"tanggal": t.isoformat(), "label": tgl(t), "status": status,
                      "libur": libur.get(t.isoformat()),
                      "grand_total": str(g.loc[t, "gt"]) if punya else ("0" if status == "tutup" else None),
                      "bill": int(g.loc[t, "bill"]) if punya else (0 if status == "tutup" else None)})
    return hasil


KOMPONEN = [
    ("Subtotal", "subtotal", +1), ("Diskon menu", "menu_discount", -1), ("Diskon bill", "bill_discount", -1),
    ("Diskon voucher", "voucher_discount", -1), ("Service charge", "service_charge_total", +1),
    ("Pajak (PB1)", "tax_total", +1), ("Ongkos kirim", "delivery_cost", +1), ("Order fee", "order_fee", +1),
    ("Platform fee", "platform_fee", +1), ("Penjualan voucher", "voucher_sales_total", +1),
    ("Pembulatan", "rounding_total", +1),
]


def rekonsiliasi(d: DataRentang) -> dict | None:
    if not d.ada_data:
        return None
    b = d.bill
    baris = []
    hitung = Decimal(0)
    for label, kol, tanda in KOMPONEN:
        v = jumlah(b[kol])
        if v == 0 and kol not in ("subtotal", "tax_total", "service_charge_total"):
            continue
        hitung += tanda * v
        baris.append({"label": label, "tanda": "+" if tanda > 0 else "−", "teks": format_rupiah(v)})
    gt = jumlah(b["grand_total"])
    selisih = gt - hitung
    per_bill = b.apply(lambda r: r["grand_total"] - sum(t * (r[k] or 0) for _, k, t in KOMPONEN), axis=1)
    beda = b.loc[per_bill.abs() >= Decimal("0.5"), ["sales_number"]].assign(selisih=per_bill[per_bill.abs() >= Decimal("0.5")])
    return {
        "baris": baris,
        "hasil_hitung": format_rupiah(hitung),
        "grand_total": format_rupiah(gt),
        "selisih": format_rupiah(selisih),
        "selisih_nol": abs(selisih) < Decimal("0.5"),
        "catatan": (f"Selisih {format_rupiah(selisih)} berasal dari {len(beda)} bill yang Grand Total-nya di ESB "
                    "berbeda dari jumlah komponennya (pembulatan ESB). Angka utama tetap Grand Total ESB."
                    if len(beda) else "Komponen menjumlah tepat ke Grand Total."),
        "bill_selisih": [{"Sales Number": s, "Selisih": format_rupiah(v)} for s, v in
                         zip(beda["sales_number"].head(50), beda["selisih"].head(50))],
    }


def diskon(d: DataRentang, r: dict) -> list[dict]:
    if not d.ada_data:
        return []
    hasil = []
    for label, kol in (("Diskon menu", "menu_discount"), ("Diskon bill", "bill_discount"), ("Diskon voucher", "voucher_discount")):
        v = jumlah(d.bill[kol])
        n = int((d.bill[kol].map(lambda x: (x or 0) != 0)).sum())
        a = asal(f"Σ {kol} ÷ Σ Grand Total × 100%", [f"{SUMBER_BILL} · kolom {label.replace('Diskon', '').strip().title()} Discount"],
                 _asal_rentang(d), n)
        hasil.append({"label": label, "nominal": nilai(v, "rupiah", a), "bill": n,
                      "persen_omzet": nilai(persen(v, r["gt"]), "persen", a) if r["gt"] else tidak_diketahui("omzet 0")})
    total = sum(Decimal(h["nominal"]["nilai"]) for h in hasil)
    a = asal("Σ semua diskon ÷ Σ Grand Total × 100%", [SUMBER_BILL], _asal_rentang(d), len(d.bill))
    hasil.append({"label": "Total diskon", "nominal": nilai(total, "rupiah", a), "bill": None,
                  "persen_omzet": nilai(persen(total, r["gt"]), "persen", a) if r["gt"] else tidak_diketahui("omzet 0")})
    # Promo terbanyak menurut kolom Promotion (rincian per promo ada di tab Promo).
    return hasil


def per_channel(d: DataRentang, r: dict) -> list[dict]:
    if not d.ada_data or not len(d.bill):
        return []
    kb = r["kb"]
    hasil = []
    for ch, g in kb.groupby("visit_purpose", dropna=False):
        gt = jumlah(g["grand_total"])
        fnb = g[g["jenis"] == "fnb"]
        a = asal("Per Visit Purpose: Σ Grand Total, jumlah bill, rata-rata bill F&B",
                 [f"{SUMBER_BILL} · Visit Purpose, Grand Total"], _asal_rentang(d), len(g))
        rb = bagi(jumlah(fnb["grand_total"]), len(fnb))
        hasil.append({"channel": ch or "(kosong)", "bill": len(g), "grand_total": nilai(gt, "rupiah", a),
                      "porsi_omzet": nilai(persen(gt, r["gt"]), "persen", a),
                      "rata_bill_fnb": nilai(rb, "rupiah", a) if rb is not None else tidak_diketahui("tidak ada bill F&B")})
    return sorted(hasil, key=lambda h: -Decimal(h["grand_total"]["nilai"]))


# ---------------------------------------------------------------------------
# Perbandingan & dekomposisi
# ---------------------------------------------------------------------------

def _selisih_teks(a: Decimal, b: Decimal, jenis: str) -> dict:
    s = a - b
    tanda = "+" if s > 0 else ("−" if s < 0 else "±")
    if jenis == "rupiah":
        teks = f"{tanda}{format_rupiah(abs(s))}"
    else:
        teks = f"{tanda}{format_angka(abs(s), 1 if jenis == 'desimal' else 0)}"
    p = persen(s, b)
    return {"teks": teks, "persen": (f"{tanda}{format_persen(abs(p))}" if p is not None else "—"),
            "arah": "naik" if s > 0 else ("turun" if s < 0 else "tetap")}


def banding(cur: DataRentang, rc: dict, prev: DataRentang, rp: dict, label_prev: str) -> dict:
    if not cur.ada_data:
        return {"label": label_prev, "tersedia": False, "alasan": "periode ini belum ada data"}
    if not prev.ada_data:
        return {"label": label_prev, "tersedia": False,
                "alasan": f"belum ada data {prev.cabang} untuk {prev.awal:%d-%m-%Y} s/d {prev.akhir:%d-%m-%Y}"}
    per_hari = not (rc["lengkap"] and rp["lengkap"])
    def m(r):
        hb = r["hari_buka"] or None
        return {
            "omzet": bagi(r["gt_buka"], hb) if per_hari else r["gt"],
            "bill": bagi(r["bill_buka"], hb) if per_hari else Decimal(r["bill"]),
            "rata_bill_fnb": bagi(r["gt_fnb"], r["bill_fnb"]),
            "omzet_per_hari_buka": bagi(r["gt_buka"], hb),
            "hari_buka": Decimal(r["hari_buka"]),
        }
    a, b = m(rc), m(rp)
    label = {
        "omzet": "Grand Total per hari buka" if per_hari else "Grand Total",
        "bill": "Bill per hari buka" if per_hari else "Jumlah bill",
        "rata_bill_fnb": "Rata-rata bill F&B",
        "omzet_per_hari_buka": "Grand Total per hari buka",
        "hari_buka": "Hari buka",
    }
    jenis = {"omzet": "rupiah", "bill": "desimal" if per_hari else "angka", "rata_bill_fnb": "rupiah",
             "omzet_per_hari_buka": "rupiah", "hari_buka": "angka"}
    baris = []
    for k in label:
        if per_hari and k == "omzet_per_hari_buka":
            continue
        if a[k] is None or b[k] is None:
            baris.append({"metrik": label[k], "sekarang": "Tidak diketahui", "sebelumnya": "Tidak diketahui",
                          "selisih": {"teks": "—", "persen": "—", "arah": "tetap"}})
            continue
        fmt = lambda v: format_rupiah(v) if jenis[k] == "rupiah" else format_angka(v, 1 if jenis[k] == "desimal" else 0)
        baris.append({"metrik": label[k], "sekarang": fmt(a[k]), "sebelumnya": fmt(b[k]),
                      "selisih": _selisih_teks(a[k], b[k], jenis[k])})
    return {"label": label_prev, "tersedia": True, "per_hari": per_hari, "baris": baris,
            "catatan": ("Salah satu periode tidak lengkap, jadi dibandingkan per hari buka, bukan total."
                        if per_hari else "Kedua periode lengkap; dibandingkan total."),
            "dekomposisi": dekomposisi(rc, rp, per_hari)}


def dekomposisi(rc: dict, rp: dict, per_hari: bool) -> dict:
    """Omzet bill F&B = jumlah bill F&B × rata-rata bill F&B, dipecah secara log:
    Δ omzet × ln(N1/N0)/ln(O1/O0) dari jumlah bill, sisanya dari rata-rata bill."""
    def oan(r):
        if per_hari:
            hb = r["hari_buka"]
            if not hb:
                return None
            n = Decimal(r["fnb_buka"]) / hb
            o = r["gt_fnb_buka"] / hb
        else:
            n, o = Decimal(r["bill_fnb"]), r["gt_fnb"]
        if not n or not o:
            return None
        return o, n, o / n
    x1, x0 = oan(rc), oan(rp)
    a = asal("Omzet F&B = bill F&B × rata-rata bill F&B; kontribusi = ΔOmzet × ln(rasio komponen) ÷ ln(rasio omzet)",
             [f"{SUMBER_BILL} · Grand Total", f"{SUMBER_COGS} · Menu Category"],
             ["Hanya bill F&B (tanpa item jasa/aksesoris)"] + (["Per hari buka"] if per_hari else []))
    if x1 is None or x0 is None:
        return {"tersedia": False, "alasan": "jumlah bill atau omzet F&B nol di salah satu periode", "asal": a}
    (o1, n1, r1), (o0, n0, r0) = x1, x0
    do = o1 - o0
    ln_o, ln_n, ln_a = (o1 / o0).ln(), (n1 / n0).ln(), (r1 / r0).ln()
    if ln_o == 0:
        kn = ka = Decimal(0)
    else:
        kn, ka = do * ln_n / ln_o, do * ln_a / ln_o
    unit = " per hari buka" if per_hari else ""
    return {"tersedia": True, "asal": a,
            "omzet": {"sekarang": format_rupiah(o1), "sebelumnya": format_rupiah(o0), **_selisih_teks(o1, o0, "rupiah")},
            "dari_jumlah_bill": {"teks": _selisih_teks(kn, Decimal(0), "rupiah")["teks"],
                                 "keterangan": f"bill F&B{unit}: {format_angka(n0, 1)} → {format_angka(n1, 1)} "
                                               f"({_selisih_teks(n1, n0, 'desimal')['persen']})"},
            "dari_rata_bill": {"teks": _selisih_teks(ka, Decimal(0), "rupiah")["teks"],
                               "keterangan": f"rata-rata bill F&B: {format_rupiah(r0)} → {format_rupiah(r1)} "
                                             f"({_selisih_teks(r1, r0, 'rupiah')['persen']})"}}
