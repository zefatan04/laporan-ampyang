"""Tab Performa Promo.

Tiga bagian:
1. Promo yang tercatat di kolom Promotion Bill Report pada periode yang
   dilihat (otomatis): jumlah bill, total diskon, omzet bill.
2. Evaluasi promo yang didaftarkan di Pengaturan (nama, periode, cabang,
   nama promo di ESB, menu promo): dibanding PEMBANDING = rata-rata hari yang
   sama dalam seminggu dari 4 minggu sebelum promo (A), dan 4 minggu sebelum +
   4 minggu sesudah bila datanya ada (B). Hari libur, Ramadan, hari tutup,
   parsial, dan tanpa data tidak dipakai sebagai pembanding. Kedua hasil
   ditampilkan sebagai rentang; kesimpulan memakai sisi pesimis.
3. Paket (SKU kelompok paket, mis. COMBO MEAL WFA): harga paket vs harga
   normal isinya, HPP paket dari item pendamping Rp0, dst.

Kesimpulan hanya menyatakan selisih terhadap pembanding pada waktu yang
sama. Itu bukan bukti sebab-akibat, dan teks kesimpulan menyebutnya.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from app import pengaturan
from app import pengaturan_bawaan as P
from app.angka import format_angka, format_persen, format_rupiah
from app.hitung.data import DataRentang, muat
from app.hitung.foot_traffic import _jam, _jendela
from app.hitung.nilai import asal, bagi, jumlah, persen
from app.hitung.overview import SUMBER_BILL, SUMBER_COGS, _selisih_teks, komposisi_bill, tgl
from app.validasi import NAMA_HARI

MINGGU_PEMBANDING = 4


def nama_promo(teks) -> list[str]:
    """'PROMO A, PROMO A' -> ['PROMO A']; 'A, B' -> ['A', 'B']. Spasi ujung dibuang."""
    if teks is None or (isinstance(teks, float) and teks != teks):
        return []
    hasil = []
    for x in str(teks).split(","):
        x = " ".join(x.split())
        if x and x.upper() not in [h.upper() for h in hasil]:
            hasil.append(x)
    return hasil


def _kunci(x: str) -> str:
    return " ".join(str(x).split()).upper()


# ---------------------------------------------------------------------------
# 1. Promo tercatat di ESB pada periode yang dilihat
# ---------------------------------------------------------------------------

def promo_esb(d: DataRentang, internal: list[str], terdaftar: list[dict]) -> dict:
    if not d.ada_data:
        return {"tersedia": False, "alasan": "belum ada data periode ini"}
    b = d.bill.copy()
    b["promo"] = b["promotion"].map(nama_promo)
    b["diskon"] = b.apply(lambda r: (r["menu_discount"] or 0) + (r["bill_discount"] or 0) + (r["voucher_discount"] or 0), axis=1)
    kb = komposisi_bill(d).set_index("sales_number")["jenis"]
    b["fnb"] = b["sales_number"].map(lambda s: kb.get(s) == "fnb")
    tanpa = b[b["promo"].map(len) == 0]
    int_set = {_kunci(x) for x in internal}
    daftar_set = {_kunci(n): p["nama"] for p in terdaftar for n in p.get("promotion_esb", [])}
    baris = []
    for nama in sorted({n for ps in b["promo"] for n in ps}, key=str.upper):
        g = b[b["promo"].map(lambda ps: _kunci(nama) in [_kunci(x) for x in ps])]
        tunggal = g[g["promo"].map(len) == 1]
        fnb = g[g["fnb"]]
        menu_disk = "-"
        # Discount Total di COGS juga berisi alokasi diskon bill, jadi hanya bill
        # yang diskonnya murni diskon menu yang bisa menunjukkan menu promonya.
        murni = g[(g["menu_discount"] > 0) & (g["bill_discount"] == 0) & (g["voucher_discount"] == 0)]
        if len(murni):
            c = d.cogs[d.cogs["sales_number"].isin(set(murni["sales_number"])) & (d.cogs["discount_total"] > 0)]
            q = c.groupby("menu_bersih")["qty"].agg(jumlah).sort_values(ascending=False, key=lambda x: x.map(float))
            menu_disk = ", ".join(f"{m} ({format_angka(v)})" for m, v in q.head(5).items()) or "-"
        jenis = ("internal" if _kunci(nama) in int_set else
                 f"promo: {daftar_set[_kunci(nama)]}" if _kunci(nama) in daftar_set else "belum diatur")
        baris.append({
            "Promotion (ESB)": nama, "Jenis": jenis, "Bill": len(g),
            "Total diskon": format_rupiah(jumlah(tunggal["diskon"])) + (f" (+{len(g) - len(tunggal)} bill gabungan)" if len(g) > len(tunggal) else ""),
            "Omzet bill (Grand Total)": format_rupiah(jumlah(g["grand_total"])),
            "Rata-rata bill F&B": format_rupiah(bagi(jumlah(fnb["grand_total"]), len(fnb))) if len(fnb) else "Tidak diketahui",
            "Porsi bill": format_persen(persen(len(g), len(b))),
            "Menu kena diskon menu (qty)": menu_disk if menu_disk == "-" else f"{menu_disk} — dari {len(murni)} bill berdiskon menu saja",
        })
    gabungan = b[b["promo"].map(len) > 1]
    fnb_tanpa = tanpa[tanpa["fnb"]]
    return {
        "tersedia": True, "baris": baris,
        "tanpa_promo": {"bill": len(tanpa), "rata_bill_fnb": format_rupiah(bagi(jumlah(fnb_tanpa["grand_total"]), len(fnb_tanpa))) if len(fnb_tanpa) else "Tidak diketahui"},
        "catatan": [
            "Total diskon = Menu Discount + Bill Discount + Voucher Discount di Bill Report.",
            f"{len(gabungan)} bill memakai lebih dari satu promo; diskonnya tidak bisa dibagi antar promo tanpa menebak, jadi tidak masuk total diskon per promo."
            if len(gabungan) else "Tidak ada bill yang memakai lebih dari satu promo.",
            "Jenis 'internal' (mis. diskon karyawan) diatur di Pengaturan; tidak dinilai sebagai promo pemasaran.",
        ],
        "asal": asal("Per nama di kolom Promotion: jumlah bill, Σ diskon, Σ Grand Total",
                     [f"{SUMBER_BILL} · Promotion, Menu/Bill/Voucher Discount, Grand Total"],
                     ["Sales Type = 'Sales'", f"Cabang = {d.cabang}"], len(b)),
    }


# ---------------------------------------------------------------------------
# 2. Evaluasi promo terdaftar
# ---------------------------------------------------------------------------

def _libur(con) -> set[date]:
    hasil = {date.fromisoformat(x["tanggal"]) for x in pengaturan.ambil(con, "hari_libur")}
    for r in pengaturan.ambil(con, "ramadan"):
        t, z = date.fromisoformat(r["awal"]), date.fromisoformat(r["akhir"])
        while t <= z:
            hasil.add(t)
            t += timedelta(days=1)
    return hasil


def harian(d: DataRentang, menu_promo: set[str]) -> dict[date, dict]:
    """Angka per hari buka (tanpa tutup/parsial/tanpa data)."""
    if not d.ada_data:
        return {}
    kb = komposisi_bill(d)
    c = d.cogs
    bayar = c[(c["price"] > 0) & (c["kelompok"] != "non_fnb")]
    mp = bayar["menu_bersih"].map(lambda m: _kunci(m) in menu_promo)
    hasil = {}
    for t in d.hari_buka:
        k = kb[kb["sales_date"] == t]
        fnb = k[k["jenis"] == "fnb"]
        bt = bayar[bayar["sales_date"] == t]
        mpt = mp[bayar["sales_date"] == t]
        hasil[t] = {
            "omzet": jumlah(k["grand_total"]), "bill": Decimal(len(k)),
            "gt_fnb": jumlah(fnb["grand_total"]), "bill_fnb": Decimal(len(fnb)),
            "qty_promo": jumlah(bt[mpt]["qty"]), "omzet_promo": jumlah(bt[mpt]["total"]),
            "omzet_non_promo": jumlah(bt[~mpt]["total"]),
        }
    return hasil


def banding_pembanding(aktual: dict[date, dict], pembanding: dict[date, dict], metrik: str) -> dict:
    """Σ aktual vs Σ harapan (rata-rata hari yang sama dalam seminggu di pembanding)."""
    per_hari = defaultdict(list)
    for t, v in pembanding.items():
        per_hari[t.weekday()].append(v[metrik])
    akt = harap = Decimal(0)
    dipakai, tanpa = [], []
    for t, v in sorted(aktual.items()):
        sampel = per_hari.get(t.weekday())
        if not sampel:
            tanpa.append(t)
            continue
        akt += v[metrik]
        harap += sum(sampel) / len(sampel)
        dipakai.append(t)
    return {"aktual": akt, "harapan": harap, "hari": dipakai, "tanpa_pembanding": tanpa,
            "sampel": {NAMA_HARI[h]: len(v) for h, v in sorted(per_hari.items())},
            "persen": persen(akt - harap, harap) if harap else None}


def _saring(h: dict, libur: set) -> dict:
    return {t: v for t, v in h.items() if t not in libur}


def _ringkas_banding(nama: str, x: dict | None, jenis: str = "rupiah") -> dict:
    if x is None:
        return {"metrik": nama, "teks": "Tidak diketahui", "persen": None}
    if not x["hari"]:
        return {"metrik": nama, "teks": "Tidak diketahui — tidak ada hari promo yang punya pembanding hari yang sama", "persen": None}
    f = format_rupiah if jenis == "rupiah" else (lambda v: format_angka(v, 1))
    s = _selisih_teks(x["aktual"], x["harapan"], jenis if jenis == "rupiah" else "desimal")
    return {"metrik": nama, "aktual": f(x["aktual"]), "harapan": f(x["harapan"]), "selisih": s,
            "hari": len(x["hari"]), "persen": x["persen"],
            "teks": f"{f(x['aktual'])} vs pembanding {f(x['harapan'])} ({s['persen']})"}


def evaluasi(con, cabang: str, p: dict, libur: set) -> dict:
    mulai, selesai = date.fromisoformat(p["mulai"]), date.fromisoformat(p["selesai"])
    menu_promo = {_kunci(m) for m in p.get("menu_promo", [])}
    ambang = Decimal(str(pengaturan.ambil(con, "ambang_netral_persen")))

    dp = muat(con, cabang, mulai, selesai)
    da = muat(con, cabang, mulai - timedelta(days=7 * MINGGU_PEMBANDING), mulai - timedelta(days=1))
    ds = muat(con, cabang, selesai + timedelta(days=1), selesai + timedelta(days=7 * MINGGU_PEMBANDING))
    hp = harian(dp, menu_promo)
    ha = _saring(harian(da, menu_promo), libur)
    hs = _saring(harian(ds, menu_promo), libur)
    hp_banding = _saring(hp, libur)
    libur_promo = sorted(set(hp) - set(hp_banding))

    hasil = {"nama": p["nama"], "cabang": cabang, "periode": f"{tgl(mulai)} – {tgl(selesai)}",
             "data_promo": f"{len(dp.tercakup)}/{len(dp.hari)} hari ada data",
             "pembanding_a": f"{tgl(da.awal)} – {tgl(da.akhir)}: {len(ha)} hari buka dipakai",
             "pembanding_b": (f"A + {tgl(ds.awal)} – {tgl(ds.akhir)}: {len(hs)} hari buka sesudah promo" if hs
                              else "belum ada data 4 minggu sesudah promo"),
             "menu_promo": p.get("menu_promo", []), "promotion_esb": p.get("promotion_esb", [])}

    # --- angka langsung dari Bill Report (tidak butuh pembanding) ----------
    esb = {_kunci(x) for x in p.get("promotion_esb", [])}
    if esb and dp.ada_data:
        b = dp.bill
        pakai = b[b["promotion"].map(lambda x: any(_kunci(n) in esb for n in nama_promo(x)))]
        diskon = jumlah(pakai["menu_discount"]) + jumlah(pakai["bill_discount"]) + jumlah(pakai["voucher_discount"])
        hasil["bill_promo"] = {"Bill memakai promo": format_angka(len(pakai)),
                               "Total diskon": format_rupiah(diskon),
                               "Omzet bill yang memakai promo (Grand Total)": format_rupiah(jumlah(pakai["grand_total"])),
                               "Porsi bill selama promo": format_persen(persen(len(pakai), len(b))) if len(b) else "—"}
    else:
        hasil["bill_promo"] = None
        hasil["bill_promo_alasan"] = ("nama promo di ESB belum diisi di Pengaturan" if not esb
                                      else "belum ada data selama periode promo")

    if not hp_banding:
        hasil["kesimpulan"] = {"label": "Belum bisa disimpulkan",
                               "alasan": [f"Belum ada data hari buka {cabang} selama periode promo."]}
        return hasil

    a = {m: banding_pembanding(hp_banding, ha, m) for m in ("omzet", "bill", "omzet_promo", "qty_promo", "omzet_non_promo")}
    bb = ({m: banding_pembanding(hp_banding, {**ha, **hs}, m) for m in ("omzet", "bill", "omzet_promo", "qty_promo", "omzet_non_promo")}
          if hs else None)

    def baris(m, nama, jenis="rupiah"):
        ra, rb = _ringkas_banding(nama, a[m], jenis), _ringkas_banding(nama, bb[m], jenis) if bb else None
        return {"metrik": nama, "A": ra["teks"], "B": rb["teks"] if rb else "Tidak diketahui — belum ada data sesudah promo",
                "pa": ra["persen"], "pb": rb["persen"] if rb else None}
    tabel = [baris("omzet", "Omzet cabang (Grand Total)"), baris("bill", "Jumlah bill", "angka")]
    if menu_promo:
        tabel += [baris("omzet_promo", "Omzet menu promo (Total)"), baris("qty_promo", "Qty menu promo", "angka"),
                  baris("omzet_non_promo", "Omzet menu non-promo (Total) — tanda kanibalisasi")]
    hasil["banding"] = tabel
    hasil["hari_dibandingkan"] = len(a["omzet"]["hari"])
    hasil["hari_tanpa_pembanding"] = [tgl(t) for t in a["omzet"]["tanpa_pembanding"]]
    hasil["libur_dikeluarkan"] = [tgl(t) for t in libur_promo]
    hasil["sampel_a"] = a["omzet"]["sampel"]

    # rata-rata bill F&B selama vs sebelum
    def rata(h):
        n = sum(v["bill_fnb"] for v in h.values())
        return bagi(sum((v["gt_fnb"] for v in h.values()), Decimal(0)), n) if n else None
    r1, r0 = rata(hp_banding), rata(ha)
    hasil["rata_bill"] = ({"selama": format_rupiah(r1), "sebelum": format_rupiah(r0), "selisih": _selisih_teks(r1, r0, "rupiah")}
                          if r1 is not None and r0 is not None else None)

    # efek setelah promo: 7 hari pertama sesudah selesai vs pembanding A
    h7 = {t: v for t, v in hs.items() if t <= selesai + timedelta(days=7)}
    if h7 and ha:
        e = banding_pembanding(h7, ha, "omzet")
        hasil["setelah"] = _ringkas_banding("Omzet 7 hari setelah promo", e)
        if menu_promo:
            hasil["setelah_menu"] = _ringkas_banding("Qty menu promo 7 hari setelah promo", banding_pembanding(h7, ha, "qty_promo"), "angka")
    else:
        hasil["setelah"] = {"teks": "Tidak diketahui — " + ("belum ada data setelah promo selesai" if not h7 else "belum ada data pembanding")}

    hasil["kesimpulan"] = _kesimpulan(a, bb, ha, hp_banding, ambang, bool(menu_promo), mulai)
    return hasil


def _kesimpulan(a, bb, ha, hp, ambang: Decimal, ada_menu: bool, mulai: date) -> dict:
    oa = a["omzet"]
    kurang = []
    if len(ha) < 14:
        kurang.append(f"pembanding 4 minggu sebelum {tgl(mulai)} hanya punya {len(ha)} hari buka (butuh minimal 14)")
    if len(oa["hari"]) < max(1, len(hp)) / 2:
        kurang.append(f"hanya {len(oa['hari'])} dari {len(hp)} hari promo punya pembanding hari yang sama")
    if kurang or oa["persen"] is None:
        return {"label": "Belum bisa disimpulkan", "alasan": ["Data kurang: " + "; ".join(kurang or ["pembanding kosong"]) + "."]}
    ps = [oa["persen"]] + ([bb["omzet"]["persen"]] if bb and bb["omzet"]["persen"] is not None else [])
    pes, opt = min(ps), max(ps)
    rentang = (f"{format_persen(pes)} s/d {format_persen(opt)}" if len(ps) > 1 else format_persen(pes))
    alasan = [f"Omzet cabang di {len(oa['hari'])} hari promo {rentang} dibanding pembanding hari yang sama "
              f"(sisi pesimis dipakai untuk kesimpulan; ambang netral ±{format_angka(ambang)}%)."]
    if pes > ambang:
        label = "Menambah omzet"
    elif opt < -ambang:
        label = "Mengurangi omzet"
    elif -ambang <= pes and opt <= ambang:
        label = "Netral"
    else:
        label = "Belum bisa disimpulkan"
        alasan.append("Kedua pembanding memberi arah berbeda terhadap ambang netral.")
    if ada_menu:
        mp, nm = a["omzet_promo"]["persen"], a["omzet_non_promo"]["persen"]
        if mp is not None and nm is not None:
            alasan.append(f"Omzet menu promo {format_persen(mp)}, omzet menu non-promo {format_persen(nm)} dibanding pembanding A.")
            if mp > 0 and nm < -ambang:
                alasan.append("Tanda kanibalisasi: menu non-promo turun lebih dari ambang saat menu promo naik.")
    alasan.append("Ini perbandingan waktu, bukan bukti sebab-akibat: faktor lain (cuaca, acara, kampanye lain) tidak dikendalikan.")
    return {"label": label, "alasan": alasan}


def promo_terdaftar(con, d: DataRentang) -> list[dict]:
    libur = _libur(con)
    hasil = []
    for p in pengaturan.ambil(con, "promo"):
        if p["cabang"] not in (d.cabang, "keduanya"):
            continue
        mulai, selesai = date.fromisoformat(p["mulai"]), date.fromisoformat(p["selesai"])
        # Tampilkan promo yang berjalan di periode ini, atau selesai ≤ 4 minggu sebelumnya (efek setelah promo).
        if mulai <= d.akhir and selesai >= d.awal - timedelta(days=7 * MINGGU_PEMBANDING):
            hasil.append(evaluasi(con, d.cabang, p, libur))
    return hasil


# ---------------------------------------------------------------------------
# 3. Paket
# ---------------------------------------------------------------------------

def _harga_normal(con, cabang: str) -> dict[str, Decimal]:
    rows = con.execute("""SELECT menu_bersih, price, count(*) n FROM esb_cogs
                          WHERE cabang = ? AND price > 0 AND sales_type = 'Sales' GROUP BY 1, 2""", [cabang]).fetchall()
    per = defaultdict(list)
    for m, h, n in rows:
        per[_kunci(m)].append((n, h))
    return {m: max(v)[1] for m, v in per.items()}  # modus; seri -> harga tertinggi


def paket(con, d: DataRentang) -> dict:
    if not d.ada_data:
        return {"tersedia": False, "alasan": "belum ada data periode ini"}
    c = d.cogs
    pk = c[(c["kelompok"] == "paket") & (c["price"] > 0)]
    if not len(pk):
        return {"tersedia": True, "baris": [], "catatan": ["Tidak ada penjualan SKU paket di periode ini."]}
    normal = _harga_normal(con, d.cabang)
    bill_pk = set(pk["sales_number"])
    per_bill = c[c["sales_number"].isin(bill_pk)].groupby("sales_number")
    info = {}
    for sn, g in per_bill:
        g_pk = g[(g["kelompok"] == "paket") & (g["price"] > 0)]
        anak = g[g["price"] == 0]
        lain = g[(g["price"] > 0) & (g["kelompok"] != "paket")]
        info[sn] = {"sku": g_pk["menu_bersih"].iloc[0] if g_pk["menu_bersih"].nunique() == 1 else None,
                    "n": jumlah(g_pk["qty"]), "anak": anak, "lain": len(lain) > 0,
                    "bersih": jumlah(g_pk["total"]) - jumlah(g_pk["discount_total"]),
                    "tanggal": g["sales_date"].iloc[0]}
    bill = d.bill.set_index("sales_number")
    baris = []
    for sku, g in pk.groupby("menu_bersih"):
        bills = [sn for sn in set(g["sales_number"])]
        bersih = [sn for sn in bills if info[sn]["sku"] == sku and info[sn]["n"] == 1]
        hpp, normal_isi, margin, bersih_n, isi = [], [], [], [], Counter()
        harga_tak = set()
        for sn in bersih:
            anak = info[sn]["anak"]
            hpp.append(jumlah(anak["cogs_total"]))
            margin.append(info[sn]["bersih"] - hpp[-1])
            bersih_n.append(info[sn]["bersih"])
            isi[" + ".join(f"{format_angka(q)}× {m}" if q != 1 else m
                           for m, q in sorted(zip(anak["menu_bersih"], anak["qty"])))] += 1
            harga = [(m, q, normal.get(_kunci(m))) for m, q in zip(anak["menu_bersih"], anak["qty"])]
            if all(h is not None for _, _, h in harga):
                normal_isi.append(sum((q * h for _, q, h in harga), Decimal(0)))
            else:
                harga_tak |= {m for m, _, h in harga if h is None}
        harga_paket = Counter(g["price"]).most_common(1)[0][0]
        rata = lambda xs: bagi(sum(xs, Decimal(0)), len(xs)) if xs else None
        rn = rata(normal_isi)
        baris.append({
            "Paket": sku, "Terjual": format_angka(jumlah(g["qty"])), "Bill": len(bills),
            "Harga paket": format_rupiah(harga_paket),
            "Harga normal isi (rata-rata)": format_rupiah(rn) if rn is not None else "Tidak diketahui",
            "Hemat pelanggan per paket": format_rupiah(rn - harga_paket) if rn is not None else "—",
            "HPP paket (rata-rata)": format_rupiah(rata(hpp)) if hpp else "Tidak diketahui",
            "Margin per paket (rata-rata)": format_rupiah(rata(margin)) if margin else "Tidak diketahui",
            "Margin %": format_persen(persen(sum(margin, Decimal(0)), sum(bersih_n, Decimal(0)))) if margin and sum(bersih_n, Decimal(0)) else "—",
            "Bill paket + item lain": format_persen(persen(sum(1 for sn in bills if info[sn]["lain"]), len(bills))),
            "_isi": isi.most_common(5), "_keluar": len(bills) - len(bersih), "_tak": sorted(harga_tak),
            "_normal_n": len(normal_isi),
        })
    semua = list(info)
    saja = [sn for sn in semua if not info[sn]["lain"]]
    hb = len(d.hari_buka) or None
    per_hari = Counter(NAMA_HARI[info[sn]["tanggal"].weekday()] for sn in semua)
    per_jam = Counter(_jendela(_jam(bill.loc[sn, "sales_in_time"])) for sn in semua if sn in bill.index)
    catatan = [
        "HPP paket = Σ COGS item pendamping Rp0 di bill yang sama (SKU paket tercatat HPP 0).",
        "Harga normal isi = modus harga jual berbayar tiap item pendamping di semua data tersimpan cabang ini.",
        "Rincian harga normal, HPP, dan isi hanya dari bill berisi tepat 1 paket, supaya item pendamping tidak tertukar.",
    ]
    for r in baris:
        if r["_keluar"]:
            catatan.append(f"{r['Paket']}: {r['_keluar']} bill berisi lebih dari 1 paket, dikeluarkan dari rincian harga/HPP.")
        if r["_tak"]:
            catatan.append(f"{r['Paket']}: harga normal tidak diketahui untuk {', '.join(r['_tak'])} (tidak pernah dijual berbayar); "
                           f"harga normal isi dari {r['_normal_n']} bill.")
    return {
        "tersedia": True,
        "baris": [{k: v for k, v in r.items() if not k.startswith("_")} for r in baris],
        "isi": [{"Paket": r["Paket"], "Isi (item Rp0)": i, "Bill": n} for r in baris for i, n in r["_isi"]],
        "paket_saja_per_hari": format_angka(bagi(len(saja), hb), 1) if hb else "—",
        "paket_saja": len(saja), "bill_paket": len(semua),
        "per_hari": [{"Hari": h, "Hari buka": n, "Bill paket": per_hari.get(h, 0),
                      "Rata-rata per hari buka": format_angka(bagi(per_hari.get(h, 0), n), 1) if n else "—"}
                     for i, h in enumerate(NAMA_HARI) for n in [sum(1 for t in d.hari_buka if t.weekday() == i)]],
        "per_jendela": [{"Jendela": j["nama"], "Bill paket": per_jam.get(j["nama"], 0)} for j in P.JENDELA_WAKTU]
                       + ([{"Jendela": "Di luar jendela", "Bill paket": per_jam["Di luar jendela"]}] if per_jam.get("Di luar jendela") else []),
        "catatan": catatan,
        "asal": asal("Per SKU kelompok paket", [f"{SUMBER_COGS} · Menu, Price, Qty, COGS Total, Sales Number"],
                     ["Sales Type = 'Sales'", f"Cabang = {d.cabang}"], len(pk)),
    }


def hitung(con, d: DataRentang) -> dict:
    terdaftar = pengaturan.ambil(con, "promo")
    return {
        "esb": promo_esb(d, pengaturan.ambil(con, "promotion_internal"), terdaftar),
        "terdaftar": promo_terdaftar(con, d),
        "jumlah_terdaftar": len(terdaftar),
        "paket": paket(con, d),
        "ambang": pengaturan.ambil(con, "ambang_netral_persen"),
    }
