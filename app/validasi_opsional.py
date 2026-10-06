"""Validasi laporan ESB opsional, diunggah bersama Bill Report + COGS Report.

Setiap laporan dicocokkan dengan Bill/COGS di unggahan yang sama. Hanya data
cabang yang cocok yang disimpan; yang tidak cocok tidak disimpan dan dashboard
cabang itu menulis "Tidak diketahui" untuk bagian yang memakainya. Laporan
opsional tidak pernah menghalangi penyimpanan Bill + COGS.

  30 Promotion Report        footer = Σ baris; per bill Σ diskon = diskon menu + bill + voucher Bill Report
  31 Sales Recap. Detail     per cabang & tanggal Σ Subtotal = Bill; bill sama persis; 1 metode bayar per bill
  32 Staff Sales & Cancel    per cabang Σ Sales Total = Σ Subtotal Bill; Σ Sales Qty = Σ Qty COGS
  33 Cancel Menu Detail      per cabang & staf Σ cancel/void = Staff Report (bila ada)
  34 Customer Data           hanya baris yang Sales Number-nya ada di Bill Report unggahan ini

Terbukti dari export asli 28 Sep – 4 Okt 2026: kelima cek di atas cocok
persis untuk cabang yang ada di file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pandas as pd

from app.angka import format_angka, format_rupiah
from app.parser.esb import CANCEL, CUSTOMER, OPSIONAL, PROMOTION, RECAP_DETAIL, STAFF, HasilBaca, nama_cabang
from app.validasi import GAGAL, LULUS, PERINGATAN, TIDAK_BISA, Cek

TOLERANSI = Decimal("0.01")
BAIK = ("cocok", "disimpan", "dicatat", "diabaikan", "tidak ada data")


@dataclass
class HasilOpsional:
    cek: list[Cek] = field(default_factory=list)
    # {kode_jenis: {cabang: DataFrame siap simpan}}
    simpan: dict[str, dict[str, pd.DataFrame]] = field(default_factory=dict)


def _j(seri) -> Decimal:
    return sum((Decimal(v) for v in seri if v is not None and not pd.isna(v)), Decimal(0))


def _cabang_meta(h: HasilBaca) -> tuple[list[str], list[str]]:
    """(cabang dikenal, nama lain) dari metadata Branch."""
    kenal, lain = [], []
    for b in (h.cabang or "").split(","):
        if not b.strip():
            continue
        c = nama_cabang(b)
        (kenal if c else lain).append(c or b.strip())
    return sorted(set(kenal)), lain


def _periode_cocok(h: HasilBaca, awal: date, akhir: date) -> str | None:
    if h.periode is None:
        return "Period di file tidak terbaca"
    if h.periode != (awal, akhir):
        a, b = h.periode
        return f"Period file {a:%d-%m-%Y} s/d {b:%d-%m-%Y} berbeda dengan unggahan {awal:%d-%m-%Y} s/d {akhir:%d-%m-%Y}"
    return None


def _ringkas(nomor: int, nama: str, h: HasilBaca, simpan: list[str], rincian: list[dict], alasan_tolak: str | None = None) -> Cek:
    if alasan_tolak:
        return Cek(nomor, nama, PERINGATAN, f"Tidak disimpan: {alasan_tolak}. Bill + COGS tetap bisa disimpan.", rincian, h.nama_file)
    if not simpan:
        return Cek(nomor, nama, PERINGATAN, "Tidak ada cabang yang cocok dengan Bill Report; laporan ini tidak disimpan.",
                   rincian, h.nama_file)
    status = LULUS if all(r.get("Hasil", "cocok") in BAIK for r in rincian) else PERINGATAN
    return Cek(nomor, nama, status, f"Cocok dan disimpan untuk {', '.join(simpan)}.", rincian, h.nama_file)


# ---------------------------------------------------------------------------

def cek_promotion(h: HasilBaca, bill: HasilBaca, awal, akhir, hasil: HasilOpsional):
    p = _periode_cocok(h, awal, akhir)
    if p:
        hasil.cek.append(_ringkas(30, "Promotion Report", h, [], [], p))
        return
    d = h.data
    rincian = []
    for nama, kode in (("Qty", "qty"), ("Discount Total", "discount_total"), ("Voucher Discount", "voucher_discount"),
                       ("Bill Total", "bill_total")):
        f, s = h.footer.get(nama), _j(d[kode])
        if f is None or abs(f - s) > TOLERANSI:
            rincian.append({"Hal": f"Footer {nama}", "File": "-" if f is None else format_angka(f, 2),
                            "Hitung": format_angka(s, 2), "Hasil": "tidak cocok"})
    if rincian:
        hasil.cek.append(_ringkas(30, "Promotion Report", h, [], rincian, "total baris tidak sama dengan footer"))
        return
    kenal, lain = _cabang_meta(h)
    if lain:
        rincian.append({"Hal": "Cabang di metadata", "File": ", ".join(lain), "Hitung": "-",
                        "Hasil": "bukan Rungkut/Mawar; diabaikan"})
    b = bill.data
    simpan = []
    for c in sorted(set(b["cabang"].dropna())):
        if c not in kenal:
            rincian.append({"Hal": f"Cabang {c}", "File": "tidak ada di export", "Hitung": "-",
                            "Hasil": "tidak disimpan; export ulang Promotion Report dengan cabang ini"})
            continue
        dp = d[d["cabang"] == c].copy()
        dp["semua"] = dp["discount_total"].map(Decimal) + dp["voucher_discount"].map(lambda v: Decimal(v or 0))
        per = dp.groupby("sales_number")["semua"].agg(_j)
        bc = b[b["cabang"] == c].set_index("sales_number")
        salah = []
        for sn, v in per.items():
            if sn not in bc.index:
                salah.append({"Sales Number": sn, "Promotion Report": format_rupiah(v), "Bill Report": "bill tidak ada"})
                continue
            r = bc.loc[sn]
            harus = Decimal(r["menu_discount"] or 0) + Decimal(r["bill_discount"] or 0) + Decimal(r["voucher_discount"] or 0)
            if abs(harus - v) > TOLERANSI:
                salah.append({"Sales Number": sn, "Promotion Report": format_rupiah(v), "Bill Report": format_rupiah(harus)})
        from app.hitung.promo import nama_promo  # NaN/None = tanpa promo
        hilang = [sn for sn, r in bc.iterrows() if nama_promo(r["promotion"]) and sn not in per.index]
        if salah or hilang:
            rincian.append({"Hal": f"Cabang {c}", "File": f"{len(salah)} bill beda diskon, {len(hilang)} bill berpromo tidak ada",
                            "Hitung": "-", "Hasil": "tidak cocok; tidak disimpan"})
            continue
        simpan.append(c)
        rincian.append({"Hal": f"Cabang {c}", "File": f"{len(per)} bill, diskon {format_rupiah(_j(dp['semua']))}",
                        "Hitung": "= diskon menu + bill + voucher di Bill Report", "Hasil": "cocok"})
        hasil.simpan.setdefault(PROMOTION.kode, {})[c] = d[d["cabang"] == c]
    hasil.cek.append(_ringkas(30, "Promotion Report", h, simpan, rincian))


def cek_recap(h: HasilBaca, bill: HasilBaca, awal, akhir, hasil: HasilOpsional):
    p = _periode_cocok(h, awal, akhir)
    if p:
        hasil.cek.append(_ringkas(31, "Sales Recapitulation Detail Report", h, [], [], p))
        return
    d, b = h.data, bill.data
    rincian, simpan = [], []
    for c in sorted(set(b["cabang"].dropna())):
        dr, bc = d[d["cabang"] == c], b[b["cabang"] == c]
        if not len(dr):
            rincian.append({"Hal": f"Cabang {c}", "Isi": "tidak ada di export", "Hasil": "tidak disimpan"})
            continue
        sr = dr.groupby("sales_date")["subtotal"].agg(_j)
        sb = bc.groupby("sales_date")["subtotal"].agg(_j)
        beda_tgl = [t for t in set(sr.index) | set(sb.index) if abs(sr.get(t, Decimal(0)) - sb.get(t, Decimal(0))) > TOLERANSI]
        beda_bill = set(dr["sales_number"]) ^ set(bc["sales_number"])
        bayar = dr.groupby("sales_number")["payment_method"].nunique()
        ganda = int((bayar > 1).sum())
        if beda_tgl or beda_bill or ganda:
            rincian.append({"Hal": f"Cabang {c}", "Isi": f"{len(beda_tgl)} tanggal beda subtotal, {len(beda_bill)} bill tidak sama, "
                                                          f"{ganda} bill dengan >1 metode bayar", "Hasil": "tidak cocok; tidak disimpan"})
            continue
        simpan.append(c)
        rincian.append({"Hal": f"Cabang {c}", "Isi": f"{dr['sales_number'].nunique()} bill, subtotal {format_rupiah(_j(dr['subtotal']))} "
                                                      "= Bill Report per tanggal", "Hasil": "cocok"})
        per_bill = dr.groupby("sales_number", as_index=False).first()[
            ["sales_number", "cabang", "baris_excel", "sales_date", "payment_method", "order_mode"]]
        hasil.simpan.setdefault(RECAP_DETAIL.kode, {})[c] = per_bill
    if h.footer_label:
        rincian.append({"Hal": "Baris berlabel di bawah data", "Isi": "; ".join(f"{k}: {v if v is not None else '-'}" for k, v in h.footer_label.items()),
                        "Hasil": "dicatat"})
    hasil.cek.append(_ringkas(31, "Sales Recapitulation Detail Report", h, simpan, rincian))


def cek_staff(h: HasilBaca, bill: HasilBaca, cogs: HasilBaca | None, awal, akhir, hasil: HasilOpsional):
    p = _periode_cocok(h, awal, akhir)
    if not p and (h.metadata.get("sales type") or "").strip().lower() != "sales":
        p = f"Sales Type di export '{h.metadata.get('sales type')}', harus 'Sales' supaya bisa dicocokkan"
    if p:
        hasil.cek.append(_ringkas(32, "Staff Sales & Cancel Report", h, [], [], p))
        return
    d, b = h.data, bill.data
    rincian, simpan = [], []
    for c in sorted(set(b["cabang"].dropna())):
        ds = d[d["cabang"] == c]
        if not len(ds):
            rincian.append({"Hal": f"Cabang {c}", "Isi": "tidak ada di export", "Hasil": "tidak disimpan"})
            continue
        bs = b[(b["cabang"] == c) & (b["sales_type"] == "Sales")]
        ok_total = abs(_j(ds["sales_total"]) - _j(bs["subtotal"])) <= TOLERANSI
        ok_qty = True
        if cogs is not None:
            cs = cogs.data[(cogs.data["cabang"] == c) & (cogs.data["sales_type"] == "Sales")]
            ok_qty = abs(_j(ds["sales_qty"]) - _j(cs["qty"])) <= TOLERANSI
        if not (ok_total and ok_qty):
            rincian.append({"Hal": f"Cabang {c}", "Isi": f"Σ Sales Total {format_rupiah(_j(ds['sales_total']))} vs Subtotal Bill "
                                                          f"{format_rupiah(_j(bs['subtotal']))}", "Hasil": "tidak cocok; tidak disimpan"})
            continue
        simpan.append(c)
        rincian.append({"Hal": f"Cabang {c}", "Isi": f"Σ Sales Total {format_rupiah(_j(ds['sales_total']))} = Subtotal Bill; "
                                                      f"Σ Sales Qty {format_angka(_j(ds['sales_qty']))} = Qty COGS", "Hasil": "cocok"})
        hasil.simpan.setdefault(STAFF.kode, {})[c] = ds
    hasil.cek.append(_ringkas(32, "Staff Sales & Cancel Report", h, simpan, rincian))


def cek_cancel(h: HasilBaca, staff: HasilBaca | None, awal, akhir, hasil: HasilOpsional, cabang_bill: list[str]):
    p = _periode_cocok(h, awal, akhir)
    d = h.data
    if not p:
        luar = d[d["tanggal"].map(lambda t: t is None or t < awal or t > akhir)]
        if len(luar):
            p = f"{len(luar)} pembatalan di luar periode"
    if p:
        hasil.cek.append(_ringkas(33, "Cancel Menu Detail Report", h, [], [], p))
        return
    kenal, _ = _cabang_meta(h)
    staf_ok = (hasil.simpan.get(STAFF.kode) or {})
    rincian, simpan = [], []
    for c in cabang_bill:
        if c not in kenal:
            rincian.append({"Hal": f"Cabang {c}", "Isi": "tidak ada di export", "Hasil": "tidak disimpan"})
            continue
        dc = d[d["cabang"] == c]
        if c in staf_ok:
            st = staf_ok[c].groupby("staf")[["cancel_total", "void_total", "cancel_qty", "void_qty"]].agg(_j)
            beda = []
            for jenis, kol_t, kol_q in (("Cancel", "cancel_total", "cancel_qty"), ("Void", "void_total", "void_qty")):
                x = dc[dc["jenis_batal"] == jenis].groupby("dibatalkan_oleh")[["subtotal", "qty"]].agg(_j)
                for staf in set(x.index) | set(st.index[(st[kol_t] != 0) | (st[kol_q] != 0)]):
                    a = x.loc[staf] if staf in x.index else pd.Series({"subtotal": Decimal(0), "qty": Decimal(0)})
                    s = st.loc[staf] if staf in st.index else pd.Series({kol_t: Decimal(0), kol_q: Decimal(0)})
                    if abs(a["subtotal"] - s[kol_t]) > TOLERANSI or abs(a["qty"] - s[kol_q]) > TOLERANSI:
                        beda.append(f"{jenis} {staf}")
            if beda:
                rincian.append({"Hal": f"Cabang {c}", "Isi": "beda dengan Staff Report: " + ", ".join(sorted(beda)),
                                "Hasil": "tidak cocok; tidak disimpan"})
                continue
            rincian.append({"Hal": f"Cabang {c}", "Isi": f"{len(dc)} baris; total per staf = Staff Report", "Hasil": "cocok"})
        else:
            rincian.append({"Hal": f"Cabang {c}", "Isi": f"{len(dc)} baris; Staff Report tidak ada/tidak cocok, jadi tidak bisa dicek silang",
                            "Hasil": "disimpan"})
        simpan.append(c)
        hasil.simpan.setdefault(CANCEL.kode, {})[c] = dc
    hasil.cek.append(_ringkas(33, "Cancel Menu Detail Report", h, simpan, rincian))


def cek_customer(h: HasilBaca, bill: HasilBaca, hasil: HasilOpsional):
    b = bill.data.drop_duplicates("sales_number").set_index("sales_number")
    d = h.data.drop_duplicates("sales_number").copy()
    cocok = d[d["sales_number"].isin(b.index)].copy()
    cocok["cabang"] = cocok["sales_number"].map(b["cabang"])
    cocok["sales_date"] = cocok["sales_number"].map(b["sales_date"])
    rincian = [{"Hal": "Baris di file", "Isi": f"{len(h.data)} baris (file ini tidak dibatasi Period-nya)", "Hasil": "dicatat"},
               {"Hal": "Di luar unggahan ini", "Isi": f"{len(d) - len(cocok)} baris: Sales Number tidak ada di Bill Report unggahan ini "
                                                       "(periode lain atau cabang lain)", "Hasil": "diabaikan"}]
    simpan = []
    for c in sorted(set(b["cabang"].dropna())):
        x = cocok[cocok["cabang"] == c]
        esb_order = int(((bill.data["cabang"] == c) & (bill.data["visit_purpose"] == "ESB ORDER")).sum())
        simpan.append(c)
        hasil.simpan.setdefault(CUSTOMER.kode, {})[c] = x
        if not len(x):
            rincian.append({"Hal": f"Cabang {c}", "Isi": f"0 bill cocok (bill ESB ORDER: {esb_order})", "Hasil": "tidak ada data"})
            continue
        rincian.append({"Hal": f"Cabang {c}", "Isi": f"{len(x)} bill cocok; bill ESB ORDER di Bill Report: {esb_order}", "Hasil": "disimpan"})
    hasil.cek.append(_ringkas(34, "Customer Data Report", h, simpan, rincian))


def validasi(files: list[HasilBaca], bill: HasilBaca | None, cogs: HasilBaca | None, awal: date, akhir: date) -> HasilOpsional:
    hasil = HasilOpsional()
    per_jenis: dict = {}
    for h in files:
        if h.jenis in OPSIONAL and h.bisa_dipakai:
            per_jenis.setdefault(h.jenis.kode, []).append(h)
    nomor = {RECAP_DETAIL.kode: 31, PROMOTION.kode: 30, CUSTOMER.kode: 34, STAFF.kode: 32, CANCEL.kode: 33}
    satu = {}
    for kode, hs in per_jenis.items():
        if len(hs) > 1:
            hasil.cek.append(Cek(nomor[kode], hs[0].jenis.nama, PERINGATAN,
                                 f"Ada {len(hs)} file {hs[0].jenis.nama}; tidak ada yang disimpan. Unggah satu saja.",
                                 [{"File": h.nama_file} for h in hs]))
        else:
            satu[kode] = hs[0]
    if not satu:
        return hasil
    if bill is None:
        for h in satu.values():
            hasil.cek.append(Cek(nomor[h.jenis.kode], h.jenis.nama, TIDAK_BISA,
                                 "Butuh Bill Report yang terbaca di unggahan yang sama untuk dicocokkan; tidak disimpan.", file=h.nama_file))
        return hasil
    if PROMOTION.kode in satu:
        cek_promotion(satu[PROMOTION.kode], bill, awal, akhir, hasil)
    if RECAP_DETAIL.kode in satu:
        cek_recap(satu[RECAP_DETAIL.kode], bill, awal, akhir, hasil)
    if STAFF.kode in satu:
        cek_staff(satu[STAFF.kode], bill, cogs, awal, akhir, hasil)
    if CANCEL.kode in satu:
        cek_cancel(satu[CANCEL.kode], satu.get(STAFF.kode), awal, akhir, hasil, sorted(set(bill.data["cabang"].dropna())))
    if CUSTOMER.kode in satu:
        cek_customer(satu[CUSTOMER.kode], bill, hasil)
    return hasil
