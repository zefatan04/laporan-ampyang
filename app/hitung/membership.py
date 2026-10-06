"""Tab Progress Membership Keluarga Ampyang.

Sumber: CSV ekspor web loyalty (terpisah dari ESB). Angka dari ESB hanya
dipakai sebagai pembagi (porsi bill/omzet member) dan untuk mencocokkan
setiap transaksi member ke bill ESB.

Terbukti dari data 28 Sep – 4 Okt 2026: "Nominal Bill" loyalty = Grand Total
ESB (49 dari 54 transaksi cocok persis; tidak ada yang cocok ke Subtotal).
Transaksi yang tidak punya pasangan bill ESB di hari yang sama ditampilkan
di bagian kualitas, bukan dibuang diam-diam.

Customer Data Report ESB (pelanggan di POS) tidak dicampur dengan member
loyalty.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd

from app import db_loyalty
from app.angka import format_angka, format_persen, format_rupiah
from app.hitung.data import DataRentang, muat
from app.hitung.nilai import asal, bagi, jumlah, nilai, persen, tidak_diketahui
from app.hitung.overview import SUMBER_BILL, _selisih_teks, komposisi_bill, tgl

S_TRX = "Riwayat Transaksi (loyalty)"
S_HARIAN = "Rekap Harian (loyalty)"
S_PEL = "Rekap Pelanggan (loyalty)"
S_KLAIM = "Riwayat Klaim (loyalty)"
S_LOG = "Log Aktivitas (loyalty)"
STATUS_SERAH = "Sudah diserahkan"


@dataclass
class DataLoyalty:
    cabang: str
    awal: date
    akhir: date
    tercakup: list[date]
    trx: pd.DataFrame
    klaim: pd.DataFrame
    harian: pd.DataFrame
    log: pd.DataFrame
    pel: pd.DataFrame
    snapshot: date | None
    jenis_ada: set
    rekon_gagal: bool

    @property
    def hari(self):
        return [self.awal + timedelta(days=i) for i in range((self.akhir - self.awal).days + 1)]

    @property
    def ada_data(self):
        return bool(self.tercakup)

    @property
    def lengkap(self):
        return len(self.tercakup) == len(self.hari)


def _df(con, sql, params):
    return con.execute(sql, params).to_arrow_table().to_pandas()


def muat_loyalty(con, cabang: str, awal: date, akhir: date) -> DataLoyalty:
    db_loyalty.pastikan(con)
    per = con.execute("""SELECT awal, akhir, jenis, rekonsiliasi_gagal FROM periode_loyalty
                         WHERE cabang = ? AND awal <= ? AND akhir >= ?""", [cabang, akhir, awal]).fetchall()
    hari = [awal + timedelta(days=i) for i in range((akhir - awal).days + 1)]
    tercakup = sorted({h for h in hari for a, z, _, _ in per if a <= h <= z})
    jenis = {j for _, _, js, _ in per for j in json.loads(js)}
    a_ts, z_ts = datetime.combine(awal, datetime.min.time()), datetime.combine(akhir + timedelta(days=1), datetime.min.time())
    q = lambda t, kol: _df(con, f"SELECT * FROM {t} WHERE cabang = ? AND {kol} >= ? AND {kol} < ?", [cabang, a_ts, z_ts])
    harian = _df(con, "SELECT * FROM loy_harian WHERE cabang = ? AND tanggal BETWEEN ? AND ?", [cabang, awal, akhir])
    snap = con.execute("SELECT min(snapshot) FROM loy_pelanggan WHERE cabang = ? AND snapshot >= ?", [cabang, akhir]).fetchone()[0]
    if snap is None:
        snap = con.execute("SELECT max(snapshot) FROM loy_pelanggan WHERE cabang = ?", [cabang]).fetchone()[0]
    pel = _df(con, "SELECT * FROM loy_pelanggan WHERE cabang = ? AND snapshot = ?", [cabang, snap]) if snap else pd.DataFrame()
    return DataLoyalty(cabang, awal, akhir, tercakup, q("loy_transaksi", "waktu"), q("loy_klaim", "waktu"), harian,
                       q("loy_log", "waktu"), pel, snap, jenis, any(r[3] for r in per))


# ---------------------------------------------------------------------------
# Pencocokan transaksi member -> bill ESB
# ---------------------------------------------------------------------------

def cocokkan(trx: pd.DataFrame, d: DataRentang) -> pd.DataFrame:
    """Tambahkan kolom sales_number (None bila tidak ada pasangan).

    Pasangan = bill Sales cabang yang sama, tanggal yang sama, Grand Total
    selisih ≤ Rp1. Satu bill hanya untuk satu transaksi; bila ada beberapa
    calon, dipilih yang jam masuknya paling dekat sebelum transaksi dicatat.
    """
    t = trx.sort_values("waktu").copy()
    t["sales_number"] = None
    if not len(t) or not d.ada_data:
        return t
    b = d.bill[["sales_number", "sales_date", "sales_in_time", "grand_total"]].copy()
    dipakai = set()
    for i, r in t.iterrows():
        w = pd.Timestamp(r["waktu"]).to_pydatetime()
        cal = b[(b["sales_date"] == w.date()) & (b["grand_total"].map(lambda g: abs(Decimal(g) - Decimal(r["nominal"])) <= 1))
                & ~b["sales_number"].isin(dipakai)]
        if not len(cal):
            continue
        def jarak(jam):
            hh, mm = map(int, str(jam).split(":")[:2])
            selisih = (w.hour * 60 + w.minute) - (hh * 60 + mm)
            return (0 if selisih >= 0 else 1, abs(selisih))
        pilih = min(cal.itertuples(), key=lambda x: jarak(x.sales_in_time)).sales_number
        t.at[i, "sales_number"] = pilih
        dipakai.add(pilih)
    return t


# ---------------------------------------------------------------------------
# Hitung
# ---------------------------------------------------------------------------

def _ringkas(L: DataLoyalty, d: DataRentang) -> dict:
    t = cocokkan(L.trx, d)
    nomor = t["nomor"].value_counts() if len(t) else pd.Series(dtype=int)
    hari_dua = sorted(set(L.tercakup) & set(d.tercakup))
    tb = t[t["waktu"].map(lambda w: pd.Timestamp(w).date() in set(hari_dua))] if len(t) else t
    esb = d.bill[d.bill["sales_date"].isin(set(hari_dua))] if d.ada_data else d.bill
    return {
        "t": t, "bill": len(t), "omzet": jumlah(t["nominal"]) if len(t) else Decimal(0),
        "member_aktif": int(nomor.size), "repeat": int((nomor >= 2).sum()),
        "stempel": int(t["stempel"].sum()) if len(t) else 0, "hangus": int(t["hangus"].fillna(0).sum()) if len(t) else 0,
        "baru_semua": int(L.harian["member_baru_semua"].sum()) if len(L.harian) else 0,
        "baru_cabang": int(L.harian["member_baru_cabang"].sum()) if len(L.harian) else 0,
        "hari_dua": hari_dua, "bill_dua": len(tb), "omzet_dua": jumlah(tb["nominal"]) if len(tb) else Decimal(0),
        "esb_bill": len(esb), "esb_gt": jumlah(esb["grand_total"]) if len(esb) else Decimal(0),
        "klaim": len(L.klaim), "klaim_serah": int((L.klaim["status"] == STATUS_SERAH).sum()) if len(L.klaim) else 0,
    }


def hitung(con, d: DataRentang, dp: DataRentang, label_prev: str) -> dict:
    L = muat_loyalty(con, d.cabang, d.awal, d.akhir)
    if not L.ada_data and L.snapshot is None:
        alasan = f"belum ada CSV loyalty {d.cabang} untuk {d.awal:%d-%m-%Y} s/d {d.akhir:%d-%m-%Y}"
        return {"tersedia": False, "alasan": alasan}
    r = _ringkas(L, d)
    filt = [f"Cabang = {d.cabang}", f"Tanggal {d.awal:%d-%m-%Y} s/d {d.akhir:%d-%m-%Y}"] + (
        [f"Data loyalty hanya {len(L.tercakup)} dari {len(L.hari)} hari"] if not L.lengkap else [])
    pr = (["Sebagian data loyalty disimpan walau Rekap Harian tidak cocok."] if L.rekon_gagal else []) + (
        [f"Parsial: data loyalty hanya {len(L.tercakup)} dari {len(L.hari)} hari."] if L.ada_data and not L.lengkap else [])
    tak = lambda: tidak_diketahui(f"belum ada data loyalty berkala {d.cabang} di periode ini")
    k = {}

    # --- potret member (Rekap Pelanggan) ------------------------------------
    S = L.pel
    if L.snapshot is not None and len(S):
        lbl = f"per {tgl(L.snapshot)}" + (" (potret sebelum akhir periode)" if L.snapshot < d.akhir else "")
        a = asal("Jumlah nomor unik di Rekap Pelanggan", [f"{S_PEL} · Nomor WA"], [f"Potret {L.snapshot:%d-%m-%Y}"], len(S),
                 catatan=["Member bersifat lintas cabang; jumlah ini sama di kedua cabang."])
        k["total_member"] = {**nilai(S["nomor"].nunique(), "angka", a), "label": lbl}
        ver = int(S["terverifikasi"].sum())
        k["terverifikasi"] = {**nilai(ver, "angka", asal("Status Verifikasi = Terverifikasi", [f"{S_PEL} · Status Verifikasi"],
                                                          [f"Potret {L.snapshot:%d-%m-%Y}"], len(S))),
                              "label": f"{format_persen(persen(ver, len(S)))} dari semua member · {lbl}"}
        baru_s = S[S["gabung"].map(lambda g: g is not None and d.awal <= g <= d.akhir)]
        k["terverifikasi_baru"] = {**nilai(int(baru_s["terverifikasi"].sum()), "angka", asal(
            "Member bergabung di periode ini yang terverifikasi OTP", [f"{S_PEL} · Tanggal Gabung, Status Verifikasi"],
            filt, len(baru_s))), "label": f"dari {len(baru_s)} member baru (potret)"}
        pt = int((S["transaksi"] > 0).sum())
        k["pernah_transaksi"] = {**nilai(pt, "angka", asal("Member dengan Jumlah Transaksi > 0 di cabang ini",
                                                            [f"{S_PEL} · Jumlah Transaksi (cabang ini)"], [f"Potret {L.snapshot:%d-%m-%Y}"], len(S))),
                                 "label": f"{format_persen(persen(pt, len(S)))} dari semua member · {lbl}"}
        k["repeat_sejak_gabung"] = {**nilai(int((S["transaksi"] >= 2).sum()), "angka", asal(
            "Member dengan Jumlah Transaksi ≥ 2 di cabang ini sejak bergabung", [f"{S_PEL} · Jumlah Transaksi"],
            [f"Potret {L.snapshot:%d-%m-%Y}"], len(S))), "label": lbl}
    else:
        for x in ("total_member", "terverifikasi", "terverifikasi_baru", "pernah_transaksi", "repeat_sejak_gabung"):
            k[x] = tidak_diketahui("Rekap Pelanggan belum diunggah")

    if not L.ada_data:
        for x in ("member_baru", "member_baru_cabang", "member_aktif", "repeat", "bill_member", "omzet_member",
                  "porsi_bill", "porsi_omzet", "stempel", "klaim"):
            k[x] = tak()
        return {"tersedia": True, "berkala": False, "kartu": k, "snapshot": str(L.snapshot)}

    a = asal("Σ Member Baru (semua cabang) per hari", [f"{S_HARIAN} · Member Baru (semua cabang)"], filt, len(L.harian),
             catatan=["Pendaftaran bersifat lintas cabang (di web loyalty tidak disaring cabang)."])
    k["member_baru"] = nilai(r["baru_semua"], "angka", a, peringatan=pr)
    if len(S):
        cek = len(S[S["gabung"].map(lambda g: g is not None and d.awal <= g <= d.akhir)])
        if cek != r["baru_semua"]:
            k["member_baru"]["asal"]["catatan"].append(
                f"Potret Rekap Pelanggan mencatat {cek} member bergabung di periode ini (beda {cek - r['baru_semua']:+d}; "
                "akun yang dihapus atau tanggal gabung yang diubah bisa membuat selisih).")
    k["member_baru_cabang"] = nilai(r["baru_cabang"], "angka", asal(
        "Σ Member Baru (didaftarkan kasir cabang ini)", [f"{S_HARIAN} · Member Baru (didaftarkan kasir cabang ini)"], filt,
        len(L.harian), catatan=["Pendaftaran tanpa kasir (mandiri) tidak masuk hitungan cabang mana pun."]), peringatan=pr)
    a = asal("Nomor unik di Riwayat Transaksi periode ini", [f"{S_TRX} · Nomor WA (disimpan sebagai sidik)"], filt, r["bill"])
    k["member_aktif"] = nilai(r["member_aktif"], "angka", a, peringatan=pr)
    k["repeat"] = {**nilai(r["repeat"], "angka", asal("Nomor dengan ≥ 2 transaksi di periode ini", [f"{S_TRX} · Nomor WA"], filt,
                                                       r["bill"]), peringatan=pr),
                   "label": f"{format_persen(persen(r['repeat'], r['member_aktif']))} dari member bertransaksi" if r["member_aktif"] else ""}
    k["bill_member"] = nilai(r["bill"], "angka", asal("Jumlah baris Riwayat Transaksi", [S_TRX], filt, r["bill"]), peringatan=pr)
    k["omzet_member"] = nilai(r["omzet"], "rupiah", asal("Σ Nominal Bill", [f"{S_TRX} · Nominal Bill"], filt, r["bill"],
                                                          catatan=["Nominal Bill terbukti berbasis Grand Total ESB."]), peringatan=pr)
    if r["hari_dua"] and r["esb_bill"]:
        cat = [f"Dihitung di {len(r['hari_dua'])} hari yang punya data loyalty dan ESB."]
        k["porsi_bill"] = {**nilai(persen(r["bill_dua"], r["esb_bill"]), "persen", asal(
            "Bill member ÷ bill Sales ESB × 100%", [S_TRX, f"{SUMBER_BILL} · Sales Number"], filt, r["esb_bill"], catatan=cat),
            peringatan=pr), "label": f"{r['bill_dua']} dari {r['esb_bill']} bill"}
        k["porsi_omzet"] = {**nilai(persen(r["omzet_dua"], r["esb_gt"]), "persen", asal(
            "Σ Nominal Bill member ÷ Σ Grand Total ESB × 100%", [f"{S_TRX} · Nominal Bill", f"{SUMBER_BILL} · Grand Total"],
            filt, r["esb_bill"], catatan=cat), peringatan=pr), "label": f"{format_rupiah(r['omzet_dua'])} dari {format_rupiah(r['esb_gt'])}"}
    else:
        alasan = "belum ada data ESB di hari yang sama dengan data loyalty"
        k["porsi_bill"] = tidak_diketahui(alasan)
        k["porsi_omzet"] = tidak_diketahui(alasan)
    k["stempel"] = {**nilai(r["stempel"], "angka", asal("Σ Stempel Didapat", [f"{S_TRX} · Stempel Didapat"], filt, r["bill"]),
                            peringatan=pr), "label": f"{r['hangus']} stempel hangus"}
    if "klaim" in L.jenis_ada:
        k["klaim"] = {**nilai(r["klaim"], "angka", asal("Jumlah baris Riwayat Klaim", [S_KLAIM], filt, r["klaim"],
                                                         catatan=["Termasuk klaim milik staf (Rekap Harian tidak menghitungnya)."]),
                              peringatan=pr), "label": f"{r['klaim_serah']} sudah diserahkan"}
    else:
        k["klaim"] = tidak_diketahui("Riwayat Klaim belum diunggah")

    # --- rata-rata bill member vs non-member (bill F&B, dari bill ESB yang tercocokkan) ---
    t = r["t"]
    rata = None
    if d.ada_data and len(t):
        kb = komposisi_bill(d)
        sn_member = set(t["sales_number"].dropna())
        fnb = kb[kb["jenis"] == "fnb"]
        m, nm = fnb[fnb["sales_number"].isin(sn_member)], fnb[~fnb["sales_number"].isin(sn_member)]
        if len(m) and len(nm):
            a = asal("Rata-rata Grand Total bill F&B: member (tercocokkan ke ESB) vs non-member",
                     [S_TRX, f"{SUMBER_BILL} · Grand Total"], filt, len(fnb),
                     [{"alasan": "Transaksi member tanpa pasangan bill ESB", "jumlah": int(t["sales_number"].isna().sum())}],
                     ["Non-member = bill ESB yang tidak tercocokkan dengan transaksi loyalty (bisa termasuk member yang tidak menunjukkan kartu)."])
            vm, vn = bagi(jumlah(m["grand_total"]), len(m)), bagi(jumlah(nm["grand_total"]), len(nm))
            rata = {"member": nilai(vm, "rupiah", a), "non_member": nilai(vn, "rupiah", a),
                    "selisih": _selisih_teks(vm, vn, "rupiah"), "n_member": len(m), "n_non": len(nm),
                    "sampel_kecil": len(m) < 10}

    # --- per kasir ---------------------------------------------------------
    per_kasir = []
    if len(t):
        for kasir, g in t.groupby("kasir"):
            per_kasir.append({"Kasir": kasir, "Transaksi member": len(g), "Omzet": format_rupiah(jumlah(g["nominal"])),
                              "Stempel": int(g["stempel"].sum()), "Tanpa pasangan ESB": int(g["sales_number"].isna().sum())})
    if len(S):
        daftar = S[S["gabung"].map(lambda x: x is not None and d.awal <= x <= d.akhir) & (S["kasir_pendaftar"] != "-")]
        for kasir, n in daftar["kasir_pendaftar"].value_counts().items():
            row = next((x for x in per_kasir if x["Kasir"] == kasir), None)
            if row is None:
                row = {"Kasir": kasir, "Transaksi member": 0, "Omzet": "Rp0", "Stempel": 0, "Tanpa pasangan ESB": 0}
                per_kasir.append(row)
            row["Member didaftarkan"] = int(n)
    if len(L.klaim):
        for kasir, n in L.klaim[L.klaim["status"] == STATUS_SERAH]["kasir_serah"].value_counts().items():
            row = next((x for x in per_kasir if x["Kasir"] == kasir), None)
            if row is None:
                row = {"Kasir": kasir, "Transaksi member": 0, "Omzet": "Rp0", "Stempel": 0, "Tanpa pasangan ESB": 0}
                per_kasir.append(row)
            row["Hadiah diserahkan"] = int(n)
    for row in per_kasir:
        row.setdefault("Member didaftarkan", 0)
        row.setdefault("Hadiah diserahkan", 0)
    per_kasir.sort(key=lambda x: -x["Transaksi member"])

    # --- klaim per hadiah & promo eksklusif --------------------------------
    hadiah = []
    if len(L.klaim):
        for h, g in L.klaim.groupby("hadiah"):
            hadiah.append({"Hadiah": h, "Klaim": len(g), "Sudah diserahkan": int((g["status"] == STATUS_SERAH).sum()),
                           "Status lain": ", ".join(f"{s} {n}" for s, n in Counter(g[g["status"] != STATUS_SERAH]["status"]).items()) or "-"})
    lg = L.log
    eksklusif = {"klaim": int((lg["kode"] == "klaim_promo_eksklusif").sum()) if len(lg) else 0,
                 "diserahkan": int((lg["kode"] == "serah_promo_eksklusif_ok").sum()) if len(lg) else 0}

    # --- kualitas pendaftaran (bagian tetap) --------------------------------
    flag = lg[lg["kode"].isin(["pendaftaran_beruntun", "pendaftaran_janggal"])] if len(lg) else lg
    # Member yang sama, nominal sama, hari yang sama, lebih dari sekali: kemungkinan satu bill dicatat dua kali.
    ganda = []
    if len(t):
        tt = t.assign(tgl=t["waktu"].map(lambda w: pd.Timestamp(w).date()))
        for (_, _, nom), g in tt.groupby(["nomor", "tgl", "nominal"]):
            if len(g) > 1:
                ganda.append({"Tanggal": tgl(g["tgl"].iloc[0]), "Nominal": format_rupiah(nom), "Dicatat": f"{len(g)}×",
                              "Jam": ", ".join(pd.Timestamp(w).strftime("%H:%M") for w in g["waktu"]),
                              "Kasir": ", ".join(sorted(set(g["kasir"]))),
                              "Stempel": int(g["stempel"].sum()),
                              "Bill ESB cocok": int(g["sales_number"].notna().sum())})
    kualitas = {
        "tersedia": "log" in L.jenis_ada,
        "daftar": int((lg["kode"] == "daftar").sum()) if len(lg) else 0,
        "beruntun": int((flag["kode"] == "pendaftaran_beruntun").sum()) if len(flag) else 0,
        "janggal": int((flag["kode"] == "pendaftaran_janggal").sum()) if len(flag) else 0,
        "rincian": [{"Waktu": pd.Timestamp(x.waktu).strftime("%d-%m %H:%M"),
                     "Tanda": "beruntun" if x.kode == "pendaftaran_beruntun" else "janggal",
                     "Keterangan": x.keterangan, "IP": x.ip or "-"} for x in flag.sort_values("waktu").itertuples()] if len(flag) else [],
        "tanpa_esb": [{"Waktu": pd.Timestamp(x.waktu).strftime("%d-%m %H:%M"), "Kasir": x.kasir,
                       "Nominal": format_rupiah(x.nominal)} for x in t[t["sales_number"].isna()].itertuples()] if len(t) else [],
        "esb_ada": d.ada_data,
        "ganda": ganda,
        "catatan": ["Tanda 'beruntun' = beberapa pendaftaran dari satu IP dalam 1 jam; 'janggal' = nama/nomor tidak wajar.",
                    "Transaksi tanpa pasangan ESB = tidak ada bill Sales di cabang & tanggal yang sama dengan Grand Total sama "
                    "(selisih ≤ Rp1). Bisa salah ketik nominal, bill dicatat di hari lain, atau transaksi yang perlu diperiksa.",
                    "Dicatat ganda = member, tanggal, dan nominal sama lebih dari sekali; stempel bisa ikut ganda."],
    }

    harian = [{"Tanggal": tgl(x.tanggal), "Bill member": int(x.bill), "Omzet tercatat": format_rupiah(x.omzet),
               "Stempel": int(x.stempel), "Member baru (semua cabang)": int(x.member_baru_semua),
               "Member baru (kasir cabang ini)": int(x.member_baru_cabang), "Login": int(x.login),
               "Klaim dibuat": int(x.klaim_dibuat)} for x in L.harian.sort_values("tanggal").itertuples()]

    # --- dibanding periode sebelumnya --------------------------------------
    Lp = muat_loyalty(con, dp.cabang, dp.awal, dp.akhir)
    if not Lp.ada_data:
        banding = {"label": label_prev, "tersedia": False,
                   "alasan": f"belum ada data loyalty {dp.cabang} untuk {dp.awal:%d-%m-%Y} s/d {dp.akhir:%d-%m-%Y}"}
    else:
        rp = _ringkas(Lp, dp)
        per_hari = not (L.lengkap and Lp.lengkap)
        def m(x, n):
            return bagi(x, n) if per_hari else Decimal(x)
        baris = []
        for nama, a1, a0, jenis in (
            ("Member baru (semua cabang)", m(r["baru_semua"], len(L.tercakup)), m(rp["baru_semua"], len(Lp.tercakup)), "angka"),
            ("Bill member", m(r["bill"], len(L.tercakup)), m(rp["bill"], len(Lp.tercakup)), "angka"),
            ("Member bertransaksi", Decimal(r["member_aktif"]), Decimal(rp["member_aktif"]), "angka"),
            ("Member repeat (≥2 transaksi)", Decimal(r["repeat"]), Decimal(rp["repeat"]), "angka"),
            ("Porsi bill member", persen(r["bill_dua"], r["esb_bill"]), persen(rp["bill_dua"], rp["esb_bill"]), "persen"),
        ):
            if a1 is None or a0 is None:
                baris.append({"metrik": nama, "sekarang": "Tidak diketahui", "sebelumnya": "Tidak diketahui",
                              "selisih": {"teks": "—", "persen": "—", "arah": "tetap"}})
                continue
            f = format_persen if jenis == "persen" else (lambda v: format_angka(v, 1 if per_hari else 0))
            s = _selisih_teks(a1, a0, "desimal")
            if jenis == "persen":
                s = {**s, "teks": s["teks"] + " poin", "persen": "—"}
            baris.append({"metrik": nama + (" per hari" if per_hari and nama in ("Member baru (semua cabang)", "Bill member") else ""),
                          "sekarang": f(a1), "sebelumnya": f(a0), "selisih": s})
        banding = {"label": label_prev, "tersedia": True, "per_hari": per_hari, "baris": baris,
                   "catatan": "Member baru dan bill member dibandingkan per hari bila salah satu periode tidak lengkap."}

    return {"tersedia": True, "berkala": True, "kartu": k, "rata_bill": rata, "per_kasir": per_kasir, "hadiah": hadiah,
            "eksklusif": eksklusif, "kualitas": kualitas, "harian": harian, "banding": banding,
            "snapshot": str(L.snapshot) if L.snapshot else None,
            "customer_data_esb": {"tersedia": False, "alasan": "Customer Data Report ESB belum diunggah (dibaca terpisah, tidak dicampur dengan member loyalty)."}}
