"""Tab Performa Makanan, Kudapan, dan Minuman.

Aturan (spesifikasi + temuan data asli):
- Omzet menu = kolom Total COGS Report (qty × harga, sebelum diskon) = basis
  Subtotal Bill Report. Omzet bersih = Total − Discount Total (Discount
  Total terbukti berisi diskon menu + diskon bill yang dialokasikan ke item).
- Baris Price = 0 = item yang dibundel di paket: dikeluarkan dari omzet dan
  qty penjualan reguler, tetapi biaya bahannya dihitung sebagai "biaya item
  gratis di paket" (kebocoran biaya bundling).
- Margin hanya dari baris Price > 0 dan COGS Total > 0, setelah membuang
  baris salah input (HPP/unit > 1,5 × harga). Margin = omzet bersih − COGS
  (sama dengan kolom Margin ESB). Omzet tanpa data HPP tidak ikut margin
  blended dan ditampilkan terpisah, beserta % omzet yang tercakup.
- Attach rate dihitung terhadap bill F&B (bill yang memuat minimal satu
  item makanan/minuman), dua versi: hanya item berbayar (utama) dan
  termasuk item paket.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

import pandas as pd

from app import pengaturan
from app.angka import format_angka, format_persen, format_rupiah
from app.hitung.data import DataRentang
from app.hitung.kategori import suhu
from app.hitung.nilai import asal, bagi, jumlah, nilai, persen, tidak_diketahui
from app.hitung.overview import SUMBER_COGS, _asal_rentang, _selisih_teks, komposisi_bill, tgl

TAB = {
    "makanan": {"judul": "Makanan utama", "kelompok": ["makanan_utama"],
                "tambahan": [("zuper_food", "Zuper Food")]},
    "kudapan": {"judul": "Kudapan (termasuk Toast)", "kelompok": ["kudapan", "toast"],
                "tambahan": [("toast", "Toast (terpisah)")]},
    "minuman": {"judul": "Minuman", "kelompok": ["minuman"],
                "tambahan": [("minuman_kemasan", "Minuman kemasan (showcase)")]},
}
N_TOP = 10


def _modus(seri) -> Decimal | None:
    xs = [Decimal(v) for v in seri if v is not None and Decimal(v) > 0]
    if not xs:
        return None
    hit = Counter(xs)
    tertinggi = max(hit.values())
    return max(v for v, n in hit.items() if n == tertinggi)  # seri: ambil harga tertinggi, dicatat di asal


def _layak_margin(c: pd.DataFrame) -> pd.Series:
    return (c["price"] > 0) & (c["cogs_total"] > 0) & ~c["salah_input"]


def tabel_menu(c: pd.DataFrame) -> pd.DataFrame:
    """Satu baris per menu (berbayar saja). Uang tetap Decimal."""
    bayar = c[c["price"] > 0]
    if not len(bayar):
        return pd.DataFrame(columns=["menu", "sub", "qty", "omzet", "diskon", "bersih", "hpp", "margin",
                                     "bersih_hpp", "baris", "baris_hpp", "tanpa_hpp", "salah", "harga"])
    hasil = []
    for menu, g in bayar.groupby("menu_bersih"):
        ok = g[_layak_margin(g)]
        bersih_ok = jumlah(ok["total"]) - jumlah(ok["discount_total"])
        hasil.append({
            "menu": menu,
            "sub": ", ".join(sorted({str(x) for x in g["menu_category_detail"].dropna()})),
            "qty": jumlah(g["qty"]), "omzet": jumlah(g["total"]), "diskon": jumlah(g["discount_total"]),
            "bersih": jumlah(g["total"]) - jumlah(g["discount_total"]),
            "hpp": jumlah(ok["cogs_total"]), "bersih_hpp": bersih_ok,
            "margin": bersih_ok - jumlah(ok["cogs_total"]) if len(ok) else None,
            "baris": len(g), "baris_hpp": len(ok),
            "tanpa_hpp": int(g["tanpa_hpp"].sum()), "salah": int(g["salah_input"].sum()),
            "tinggi": int(g["hpp_tinggi"].sum()), "rendah": int(g["hpp_rendah"].sum()),
            "harga": _modus(g["price"]),
        })
    return pd.DataFrame(hasil).sort_values("omzet", ascending=False, key=lambda s: s.map(float)).reset_index(drop=True)


def _baris_menu(r) -> dict:
    if r["margin"] is None:
        alasan = "semua baris salah input resep" if r["salah"] and not r["tanpa_hpp"] else "tanpa data HPP"
        margin, mpersen = f"Tidak diketahui — {alasan}", "—"
    else:
        margin = format_rupiah(r["margin"])
        mpersen = format_persen(persen(r["margin"], r["bersih_hpp"]))
    ket = []
    if r["margin"] is not None and r["baris_hpp"] < r["baris"]:
        ket.append(f"margin dari {r['baris_hpp']} dari {r['baris']} baris")
    if r["tinggi"]:
        ket.append(f"{r['tinggi']} baris HPP terlalu tinggi")
    if r["rendah"]:
        ket.append(f"{r['rendah']} baris HPP terlalu rendah")
    return {"Menu": r["menu"], "Sub-kategori": r["sub"], "Qty": format_angka(r["qty"]),
            "Omzet (Total)": format_rupiah(r["omzet"]), "Omzet bersih": format_rupiah(r["bersih"]),
            "Harga (modus)": format_rupiah(r["harga"]) if r["harga"] is not None else "-",
            "Margin": margin, "Margin %": mpersen, "Catatan": "; ".join(ket) or "-"}


def _ringkas_kelompok(d: DataRentang, kelompok: list[str]) -> dict:
    c = d.cogs[d.cogs["kelompok"].isin(kelompok)]
    bayar = c[c["price"] > 0]
    gratis = c[c["price"] == 0]
    ok = bayar[_layak_margin(bayar)]
    bersih_ok = jumlah(ok["total"]) - jumlah(ok["discount_total"])
    return {"c": c, "bayar": bayar, "gratis": gratis,
            "omzet": jumlah(bayar["total"]), "bersih": jumlah(bayar["total"]) - jumlah(bayar["discount_total"]),
            "qty": jumlah(bayar["qty"]), "menu": bayar["menu_bersih"].nunique(),
            "bersih_ok": bersih_ok, "hpp_ok": jumlah(ok["cogs_total"]),
            "omzet_tanpa_hpp": jumlah(bayar[bayar["tanpa_hpp"]]["total"]),
            "baris_tanpa_hpp": int(bayar["tanpa_hpp"].sum()), "baris_salah": int(bayar["salah_input"].sum()),
            "qty_gratis": jumlah(gratis["qty"]), "biaya_gratis": jumlah(gratis["cogs_total"])}


def _basis_attach(d: DataRentang) -> set:
    kb = komposisi_bill(d)
    return set(kb[kb["jenis"].isin(["fnb", "campuran"])]["sales_number"])


def attach(d: DataRentang, kelompok: list[str], label: str) -> dict:
    basis = _basis_attach(d)
    c = d.cogs[d.cogs["kelompok"].isin(kelompok) & d.cogs["sales_number"].isin(basis)]
    bayar = set(c[c["price"] > 0]["sales_number"])
    semua = set(c["sales_number"])
    a = asal(f"Bill F&B yang memuat {label} ÷ semua bill F&B × 100%",
             [f"{SUMBER_COGS} · Sales Number, Menu Category, Price"], _asal_rentang(d) + [
                 "Bill F&B = bill yang memuat minimal satu item makanan/minuman (bill jasa/aksesoris saja tidak dihitung)"],
             len(basis), catatan=["Versi utama: hanya item berbayar (Price > 0)."])
    if not basis:
        return {"berbayar": tidak_diketahui("tidak ada bill F&B", a), "termasuk_paket": tidak_diketahui("tidak ada bill F&B", a)}
    return {"berbayar": nilai(persen(len(bayar), len(basis)), "persen", a),
            "termasuk_paket": nilai(persen(len(semua), len(basis)), "persen", a),
            "bill_berbayar": len(bayar), "bill_semua": len(semua), "basis": len(basis)}


def _sub_kategori(r: dict) -> list[dict]:
    b = r["bayar"]
    hasil = []
    for sub, g in b.groupby("menu_category_detail", dropna=False):
        ok = g[_layak_margin(g)]
        bo = jumlah(ok["total"]) - jumlah(ok["discount_total"])
        m = bo - jumlah(ok["cogs_total"])
        hasil.append({"Sub-kategori": sub or "(kosong)", "Menu": g["menu_bersih"].nunique(),
                      "Qty": format_angka(jumlah(g["qty"])), "Omzet (Total)": format_rupiah(jumlah(g["total"])),
                      "Porsi omzet": format_persen(persen(jumlah(g["total"]), r["omzet"])) if r["omzet"] else "—",
                      "Margin %": format_persen(persen(m, bo)) if bo else "Tidak diketahui",
                      "_omzet": jumlah(g["total"])})
    hasil.sort(key=lambda x: -x["_omzet"])
    for h in hasil:
        h.pop("_omzet")
    return hasil


def _kartu(d: DataRentang, r: dict, judul: str) -> dict:
    filt = _asal_rentang(d) + [f"Kelompok: {judul}", "Price > 0 (item paket Rp0 dikeluarkan)"]
    pr = (["Sebagian data disimpan walau rekonsiliasi tidak cocok."] if d.rekon_gagal else []) + \
         ([f"Parsial: data hanya {len(d.tercakup)} dari {len(d.hari)} hari."] if not d.lengkap else [])
    k = {}
    k["omzet"] = nilai(r["omzet"], "rupiah", asal("Σ Total baris berbayar", [f"{SUMBER_COGS} · Total"], filt,
                       len(r["bayar"]), [{"alasan": "Item Rp0 dalam paket", "jumlah": len(r["gratis"])}],
                       ["Basis Subtotal: sebelum diskon, pajak, dan service charge."]), peringatan=pr)
    k["omzet_bersih"] = nilai(r["bersih"], "rupiah", asal("Σ (Total − Discount Total) baris berbayar",
                              [f"{SUMBER_COGS} · Total, Discount Total"], filt, len(r["bayar"]),
                              catatan=["Discount Total = diskon menu + diskon bill yang dialokasikan ESB ke item."]),
                              peringatan=pr)
    k["qty"] = nilai(r["qty"], "angka", asal("Σ Qty baris berbayar", [f"{SUMBER_COGS} · Qty"], filt, len(r["bayar"]),
                     [{"alasan": "Item Rp0 dalam paket", "jumlah": len(r["gratis"])}]), peringatan=pr)
    cakup = persen(r["bersih_ok"], r["bersih"])
    a = asal("(Σ omzet bersih − Σ COGS) ÷ Σ omzet bersih, hanya baris ber-HPP",
             [f"{SUMBER_COGS} · Total, Discount Total, COGS Total"],
             filt + ["COGS Total > 0", "Bukan salah input resep (HPP/unit antara 5% dan 150% harga)"],
             len(r["bayar"]) - r["baris_tanpa_hpp"] - r["baris_salah"],
             [{"alasan": "Tanpa data HPP (COGS = 0)", "jumlah": r["baris_tanpa_hpp"]},
              {"alasan": "Salah input resep (HPP terlalu tinggi/rendah)", "jumlah": r["baris_salah"]}],
             [f"Mencakup {format_persen(cakup)} omzet bersih kelompok ini." if cakup is not None else "Cakupan tidak diketahui."])
    if r["bersih_ok"]:
        k["margin"] = {**nilai(persen(r["bersih_ok"] - r["hpp_ok"], r["bersih_ok"]), "persen", a, peringatan=pr),
                       "label": f"mencakup {format_persen(cakup)} omzet"}
    else:
        k["margin"] = tidak_diketahui("tidak ada baris dengan data HPP", a)
    k["omzet_tanpa_hpp"] = nilai(r["omzet_tanpa_hpp"], "rupiah", asal(
        "Σ Total baris berbayar dengan COGS Total = 0", [f"{SUMBER_COGS} · Total, COGS Total"], filt,
        r["baris_tanpa_hpp"], catatan=["Tidak ikut margin blended."]), peringatan=pr)
    k["biaya_gratis"] = {**nilai(r["biaya_gratis"], "rupiah", asal(
        "Σ COGS Total baris Price = 0", [f"{SUMBER_COGS} · Price, COGS Total"],
        _asal_rentang(d) + [f"Kelompok: {judul}", "Price = 0 (item yang dibundel di paket)"], len(r["gratis"]),
        catatan=["Biaya bahan item gratis di paket (kebocoran biaya bundling). Omzetnya ada di SKU paket."]),
        peringatan=pr), "label": f"{format_angka(r['qty_gratis'])} item gratis"}
    return k


def _sebelum(con, d: DataRentang, kelompok: list[str]) -> tuple[set, date | None]:
    """Menu berbayar yang pernah terjual sebelum periode ini, dan tanggal data tertua."""
    r = con.execute("""SELECT DISTINCT menu_bersih, menu_category, menu_category_detail FROM esb_cogs
                       WHERE cabang = ? AND sales_date < ? AND price > 0 AND sales_type = 'Sales'""",
                    [d.cabang, d.awal]).fetchall()
    from app.hitung.kategori import kelompok as klp
    aturan = pengaturan.ambil(con, "kategori")
    menu = {m for m, k, x in r if klp(k, x, aturan) in kelompok}
    awal = con.execute("SELECT min(sales_date) FROM esb_cogs WHERE cabang = ? AND sales_date < ?",
                       [d.cabang, d.awal]).fetchone()[0]
    return menu, awal


def _banding(d, r, dp, rp, label, judul, ekstra) -> dict:
    if not d.ada_data:
        return {"label": label, "tersedia": False, "alasan": "periode ini belum ada data"}
    if not dp.ada_data:
        return {"label": label, "tersedia": False,
                "alasan": f"belum ada data {dp.cabang} untuk {dp.awal:%d-%m-%Y} s/d {dp.akhir:%d-%m-%Y}"}
    per_hari = not (d.lengkap and dp.lengkap)
    hb1, hb0 = len(d.hari_buka) or None, len(dp.hari_buka) or None
    def skala(v, hb):
        return bagi(v, hb) if per_hari else v
    baris = []
    def tambah(metrik, a, b, jenis):
        if a is None or b is None:
            baris.append({"metrik": metrik, "sekarang": "Tidak diketahui", "sebelumnya": "Tidak diketahui",
                          "selisih": {"teks": "—", "persen": "—", "arah": "tetap"}})
            return
        f = {"rupiah": format_rupiah, "angka": lambda v: format_angka(v, 1 if per_hari else 0),
             "persen": format_persen}[jenis]
        s = _selisih_teks(Decimal(a), Decimal(b), "rupiah" if jenis == "rupiah" else "desimal")
        if jenis == "persen":
            s["teks"] += " poin"
            s["persen"] = "—"
        baris.append({"metrik": metrik, "sekarang": f(a), "sebelumnya": f(b), "selisih": s})
    suf = " per hari buka" if per_hari else ""
    tambah(f"Omzet {judul.lower()}{suf}", skala(r["omzet"], hb1), skala(rp["omzet"], hb0), "rupiah")
    tambah(f"Qty berbayar{suf}", skala(r["qty"], hb1), skala(rp["qty"], hb0), "angka")
    m1 = persen(r["bersih_ok"] - r["hpp_ok"], r["bersih_ok"]) if r["bersih_ok"] else None
    m0 = persen(rp["bersih_ok"] - rp["hpp_ok"], rp["bersih_ok"]) if rp["bersih_ok"] else None
    tambah("Margin blended", m1, m0, "persen")
    for nama, a, b in ekstra:
        tambah(nama, a, b, "persen")
    return {"label": label, "tersedia": True, "per_hari": per_hari, "baris": baris,
            "catatan": ("Salah satu periode tidak lengkap, jadi omzet dan qty dibandingkan per hari buka."
                        if per_hari else "Kedua periode lengkap; dibandingkan total.") +
                       " Selisih margin dan attach rate dalam poin persentase."}


def _naik_turun(tm: pd.DataFrame, tp: pd.DataFrame, d, dp) -> dict:
    if not dp.ada_data or not d.ada_data:
        return {"tersedia": False, "alasan": "belum ada data periode sebelumnya"}
    per_hari = not (d.lengkap and dp.lengkap)
    hb1, hb0 = len(d.hari_buka) or 1, len(dp.hari_buka) or 1
    a = {r["menu"]: r for _, r in tm.iterrows()}
    b = {r["menu"]: r for _, r in tp.iterrows()}
    baris = []
    for m in set(a) | set(b):
        o1 = a[m]["omzet"] if m in a else Decimal(0)
        o0 = b[m]["omzet"] if m in b else Decimal(0)
        q1 = a[m]["qty"] if m in a else Decimal(0)
        q0 = b[m]["qty"] if m in b else Decimal(0)
        if per_hari:
            o1, o0, q1, q0 = o1 / hb1, o0 / hb0, q1 / hb1, q0 / hb0
        if m in a and m in b:
            baris.append({"menu": m, "d": o1 - o0, "o1": o1, "o0": o0, "q1": q1, "q0": q0})
    fmt = lambda x: {"Menu": x["menu"], "Qty": f"{format_angka(x['q0'], 1 if per_hari else 0)} → {format_angka(x['q1'], 1 if per_hari else 0)}",
                     "Omzet": f"{format_rupiah(x['o0'])} → {format_rupiah(x['o1'])}",
                     "Selisih omzet": _selisih_teks(x["o1"], x["o0"], "rupiah")["teks"],
                     "%": _selisih_teks(x["o1"], x["o0"], "rupiah")["persen"]}
    naik = sorted([x for x in baris if x["d"] > 0], key=lambda x: -x["d"])[:5]
    turun = sorted([x for x in baris if x["d"] < 0], key=lambda x: x["d"])[:5]
    return {"tersedia": True, "per_hari": per_hari, "naik": [fmt(x) for x in naik], "turun": [fmt(x) for x in turun],
            "catatan": ("Per hari buka, karena salah satu periode tidak lengkap. " if per_hari else "") +
                       "Hanya menu yang terjual di kedua periode; menu baru/hilang ada di bagian sendiri."}


def _harga_berubah(tm: pd.DataFrame, tp: pd.DataFrame, dp) -> dict:
    if not dp.ada_data:
        return {"tersedia": False, "alasan": "belum ada data periode sebelumnya"}
    b = {r["menu"]: r["harga"] for _, r in tp.iterrows()}
    hasil = []
    for _, r in tm.iterrows():
        h0 = b.get(r["menu"])
        if h0 is not None and r["harga"] is not None and h0 != r["harga"]:
            hasil.append({"Menu": r["menu"], "Harga sebelumnya": format_rupiah(h0), "Harga sekarang": format_rupiah(r["harga"]),
                          "Selisih": _selisih_teks(r["harga"], h0, "rupiah")["teks"]})
    return {"tersedia": True, "baris": hasil,
            "catatan": "Harga = modus (nilai Price paling sering) baris berbayar per menu per periode. Kalau dua harga sama seringnya, diambil yang tertinggi."}


def _menu_baru_hilang(con, d, dp, kelompok, tm, tp) -> dict:
    sebelum, tertua = _sebelum(con, d, kelompok)
    kini = list(tm["menu"]) if len(tm) else []
    if tertua is None:
        baru = {"tersedia": False, "alasan": f"belum ada data {d.cabang} sebelum {d.awal:%d-%m-%Y}, jadi semua menu akan tampak baru"}
    else:
        bm = tm[~tm["menu"].isin(sebelum)] if len(tm) else tm
        baru = {"tersedia": True, "dasar": f"dibanding semua data tersimpan sejak {tgl(tertua)}",
                "baris": [{"Menu": r["menu"], "Qty": format_angka(r["qty"]), "Omzet": format_rupiah(r["omzet"])} for _, r in bm.iterrows()]}
    if not dp.ada_data:
        hilang = {"tersedia": False, "alasan": "belum ada data periode sebelumnya"}
    else:
        hm = tp[~tp["menu"].isin(kini)] if len(tp) else tp
        hilang = {"tersedia": True, "dasar": "terjual di periode sebelumnya, tidak terjual di periode ini",
                  "baris": [{"Menu": r["menu"], "Qty sebelumnya": format_angka(r["qty"]),
                             "Omzet sebelumnya": format_rupiah(r["omzet"])} for _, r in hm.iterrows()]}
    return {"baru": baru, "hilang": hilang}


def _menu_baru_pengaturan(con, d: DataRentang, tab: str) -> list[dict]:
    """Menu yang didaftarkan di Pengaturan sebagai menu baru untuk tab ini:
    penjualan sejak tanggal mulai sampai akhir periode yang sedang dilihat."""
    from app.hitung.data import muat
    hasil = []
    for m in pengaturan.ambil(con, "menu_baru") or []:
        if m["tab"] != tab:
            continue
        mulai = date.fromisoformat(m["mulai"])
        baris = {"Menu": m["nama"], "Mulai dijual": tgl(mulai)}
        if mulai > d.akhir:
            hasil.append({**baris, "Hari ada data": "-", "Qty berbayar": "-", "Omzet": "-", "Qty per hari buka": "-",
                          "Catatan": "tanggal mulai setelah periode ini"})
            continue
        dm = muat(con, d.cabang, mulai, d.akhir)
        if not dm.ada_data:
            hasil.append({**baris, "Hari ada data": f"0/{len(dm.hari)}", "Qty berbayar": "Tidak diketahui",
                          "Omzet": "Tidak diketahui", "Qty per hari buka": "Tidak diketahui",
                          "Catatan": "belum ada data unggahan sejak tanggal mulai"})
            continue
        g = dm.cogs[dm.cogs["menu_bersih"].str.upper() == m["nama"].strip().upper()]
        b = g[g["price"] > 0]
        gratis = jumlah(g[g["price"] == 0]["qty"])
        ket = []
        if not dm.lengkap:
            ket.append(f"data hanya {len(dm.tercakup)} dari {len(dm.hari)} hari")
        if gratis:
            ket.append(f"+ {format_angka(gratis)} gratis di paket")
        if not len(g):
            ket.append("belum terjual di data tersimpan (cek ejaan nama menu)")
        hasil.append({**baris, "Hari ada data": f"{len(dm.tercakup)}/{len(dm.hari)}",
                      "Qty berbayar": format_angka(jumlah(b["qty"])), "Omzet": format_rupiah(jumlah(b["total"])),
                      "Qty per hari buka": format_angka(bagi(jumlah(b["qty"]), len(dm.hari_buka)), 1) if dm.hari_buka else "—",
                      "Catatan": "; ".join(ket) or "-"})
    return hasil


def hitung(con, tab: str, d: DataRentang, dp: DataRentang, label_prev: str) -> dict:
    cfg = TAB[tab]
    judul, kel = cfg["judul"], cfg["kelompok"]
    if not d.ada_data:
        alasan = f"belum ada data {d.cabang} untuk {d.awal:%d-%m-%Y} s/d {d.akhir:%d-%m-%Y}"
        return {"tersedia": False, "alasan": alasan, "judul": judul,
                "kartu": {k: tidak_diketahui(alasan) for k in ("omzet", "omzet_bersih", "qty", "margin", "omzet_tanpa_hpp", "biaya_gratis")}}
    r = _ringkas_kelompok(d, kel)
    rp = _ringkas_kelompok(dp, kel) if dp.ada_data else None
    tm = tabel_menu(r["c"])
    tp = tabel_menu(rp["c"]) if rp else tabel_menu(d.cogs.iloc[0:0])

    hasil = {"tersedia": True, "judul": judul, "kartu": _kartu(d, r, judul),
             "sub_kategori": _sub_kategori(r),
             "menu": [_baris_menu(x) for _, x in tm.iterrows()],
             "top": [_baris_menu(x) for _, x in tm.head(N_TOP).iterrows()],
             "bottom": [_baris_menu(x) for _, x in tm.tail(N_TOP).iloc[::-1].iterrows()] if len(tm) > N_TOP else [],
             "catatan": ["Menu yang tidak terjual sama sekali tidak muncul di export ESB, jadi tidak terlihat di daftar bawah.",
                         "Omzet menu basis Subtotal (Total COGS Report), bukan Grand Total."]}
    ekstra = []
    if tab == "kudapan":
        a = attach(d, ["kudapan", "toast"], "kudapan/toast")
        a2 = attach(d, ["kudapan"], "kudapan (tanpa toast)")
        hasil["attach"] = [{"label": "Attach rate kudapan + toast", **a}, {"label": "Attach rate kudapan saja (tanpa toast)", **a2}]
        if dp.ada_data:
            ap = attach(dp, ["kudapan", "toast"], "kudapan/toast")
            ekstra.append(("Attach rate kudapan + toast (berbayar)", a["berbayar"]["nilai"] and Decimal(a["berbayar"]["nilai"]),
                           ap["berbayar"]["nilai"] and Decimal(ap["berbayar"]["nilai"])))
    if tab == "minuman":
        a = attach(d, ["minuman"], "minuman")
        a2 = attach(d, ["minuman", "minuman_kemasan"], "minuman termasuk kemasan")
        hasil["attach"] = [{"label": "Attach rate minuman", **a}, {"label": "Attach rate minuman termasuk minuman kemasan", **a2}]
        basis = _basis_attach(d)
        cm = d.cogs[(d.cogs["kelompok"] == "minuman") & d.cogs["sales_number"].isin(basis)]
        aa = asal("Σ qty minuman ÷ jumlah bill F&B", [f"{SUMBER_COGS} · Qty, Menu Category"], _asal_rentang(d), len(basis))
        hasil["kartu"]["minuman_per_bill"] = {**nilai(bagi(jumlah(cm[cm["price"] > 0]["qty"]), len(basis)), "desimal", aa),
                                             "label": f"termasuk paket: {format_angka(bagi(jumlah(cm['qty']), len(basis)), 1)}"} if basis else tidak_diketahui("tidak ada bill F&B")
        per_menu = pengaturan.ambil(con, "suhu_per_menu")
        b = r["bayar"].assign(suhu=r["bayar"]["menu_bersih"].map(lambda m: suhu(m, per_menu)))
        hasil["suhu"] = [{"Suhu": s.replace("_", " ").capitalize(), "Qty": format_angka(jumlah(g["qty"])),
                          "Porsi qty": format_persen(persen(jumlah(g["qty"]), r["qty"])) if r["qty"] else "—",
                          "Omzet": format_rupiah(jumlah(g["total"])),
                          "Porsi omzet": format_persen(persen(jumlah(g["total"]), r["omzet"])) if r["omzet"] else "—"}
                         for s, g in b.groupby("suhu")]
        hasil["suhu_tidak_diketahui"] = sorted(b[b["suhu"] == "tidak_diketahui"]["menu_bersih"].unique().tolist())
        if dp.ada_data:
            ap = attach(dp, ["minuman"], "minuman")
            ekstra.append(("Attach rate minuman (berbayar)", a["berbayar"]["nilai"] and Decimal(a["berbayar"]["nilai"]),
                           ap["berbayar"]["nilai"] and Decimal(ap["berbayar"]["nilai"])))

    hasil["tambahan"] = []
    for k, nama in cfg["tambahan"]:
        rt = _ringkas_kelompok(d, [k])
        if not len(rt["bayar"]) and not len(rt["gratis"]):
            continue
        hasil["tambahan"].append({"judul": nama, "omzet": format_rupiah(rt["omzet"]), "qty": format_angka(rt["qty"]),
                                  "menu": [_baris_menu(x) for _, x in tabel_menu(rt["c"]).iterrows()]})

    hasil["banding"] = _banding(d, r, dp, rp, label_prev, judul, ekstra)
    hasil["naik_turun"] = _naik_turun(tm, tp, d, dp) if rp else {"tersedia": False, "alasan": "belum ada data periode sebelumnya"}
    hasil["harga"] = _harga_berubah(tm, tp, dp) if rp else {"tersedia": False, "alasan": "belum ada data periode sebelumnya"}
    hasil["baru_hilang"] = _menu_baru_hilang(con, d, dp, kel, tm, tp)
    hasil["menu_baru_pengaturan"] = _menu_baru_pengaturan(con, d, tab)
    return hasil
