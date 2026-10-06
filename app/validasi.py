"""Laporan validasi unggahan ESB, ditampilkan sebelum data disimpan.

Setiap cek menghasilkan status:
  lulus       cek berhasil
  gagal       angka tidak cocok / aturan dilanggar
  peringatan  tidak menghalangi, tapi user perlu tahu (mis. salah input resep)
  tidak_bisa  cek tidak bisa dijalankan karena data yang dibutuhkan tidak ada

Cek 2 (footer) dan 3 (silang) yang gagal tidak menghalangi penyimpanan,
tapi user wajib mencentang "simpan walau tidak cocok" (lihat butuh_konfirmasi).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from app import pengaturan_bawaan as P
from app.angka import format_angka, format_rupiah
from app.parser.esb import BILL, COGS, HasilBaca, daftar_cabang_metadata

LULUS, GAGAL, PERINGATAN, TIDAK_BISA = "lulus", "gagal", "peringatan", "tidak_bisa"


@dataclass
class Cek:
    nomor: int
    nama: str
    status: str
    ringkasan: str
    rincian: list[dict] = field(default_factory=list)
    file: str | None = None


@dataclass
class LaporanValidasi:
    cek: list[Cek]

    @property
    def butuh_konfirmasi(self) -> bool:
        """True bila cek 2 atau 3 gagal: simpan hanya dengan centang khusus."""
        return any(c.nomor in (2, 3) and c.status == GAGAL for c in self.cek)

    @property
    def terblokir(self) -> bool:
        """True bila ada file yang tidak bisa dibaca sama sekali, atau cabang/periode salah."""
        return any(c.nomor in (0, 1) and c.status == GAGAL for c in self.cek)


def _jumlah(seri: pd.Series) -> Decimal:
    return sum((v for v in seri if v is not None and not pd.isna(v)), Decimal(0))


# ---------------------------------------------------------------------------
# Cek 0: file terbaca
# ---------------------------------------------------------------------------

def cek_terbaca(h: HasilBaca) -> Cek:
    if h.galat:
        return Cek(0, "File terbaca", GAGAL,
                   f"{len(h.galat)} masalah saat membaca file.",
                   [{"Baris": c.baris or "-", "Masalah": c.pesan} for c in h.galat], h.nama_file)
    rincian = [{"Baris": c.baris or "-", "Catatan": c.pesan} for c in h.peringatan]
    n = 0 if h.data is None else len(h.data)
    per_cabang = ""
    if h.data is not None and len(h.data):
        hit = h.data.groupby("cabang").size()
        per_cabang = " (" + ", ".join(f"{c}: {format_angka(v)}" for c, v in hit.items()) + ")"
        non = h.data[h.data["sales_type"] != "Sales"]
        if len(non):
            jenis = ", ".join(sorted({str(v) for v in non["sales_type"]}))
            rincian.append({"Baris": ", ".join(map(str, non["baris_excel"].head(10))),
                            "Catatan": f"{len(non)} baris Sales Type '{jenis}': ikut rekonsiliasi footer, "
                                       "dikeluarkan dari semua analisa (filter Sales Type = 'Sales')."})
    status = PERINGATAN if rincian else LULUS
    return Cek(0, "File terbaca", status,
               f"{h.jenis.nama if h.jenis else '?'}: header baris {h.baris_header}, "
               f"{format_angka(n)} baris data{per_cabang}, "
               f"footer {'baris ' + str(h.baris_footer) if h.baris_footer else 'tidak ada'}.",
               rincian, h.nama_file)


# ---------------------------------------------------------------------------
# Cek 1: cabang & periode
# ---------------------------------------------------------------------------

def cek_cabang_periode(h: HasilBaca, awal: date, akhir: date, cabang: list[str] | None = None) -> Cek:
    """Satu export ESB bisa berisi beberapa cabang. `cabang` = cabang yang
    diharapkan user; None = terima cabang apa pun yang tercantum di metadata."""
    rincian, gagal = [], False
    meta = daftar_cabang_metadata(h.cabang)
    di_data = sorted(set(h.data["cabang"].dropna())) if h.data is not None else []
    if meta is None:
        rincian.append({"Hal": "Cabang (metadata)", "Di file": h.cabang or "tidak ada",
                        "Diharapkan": ", ".join(cabang or []) or "-", "Hasil": "tidak dikenali"})
        gagal = True
    else:
        harap = sorted(cabang) if cabang else meta
        ok = meta == harap
        rincian.append({"Hal": "Cabang (metadata)", "Di file": ", ".join(meta),
                        "Diharapkan": ", ".join(harap), "Hasil": "cocok" if ok else "tidak cocok"})
        gagal |= not ok
        lebih = sorted(set(di_data) - set(meta))
        kosong = sorted(set(meta) - set(di_data))
        if lebih:
            gagal = True
            rincian.append({"Hal": "Cabang di baris data", "Di file": ", ".join(lebih),
                            "Diharapkan": ", ".join(meta), "Hasil": "ada cabang di luar metadata"})
        if kosong:
            rincian.append({"Hal": "Cabang di baris data", "Di file": "-", "Diharapkan": ", ".join(kosong),
                            "Hasil": "tidak ada transaksi sama sekali (perlu dicek)"})

    pilihan = f"{awal:%d-%m-%Y} s/d {akhir:%d-%m-%Y}"
    if h.periode is None:
        rincian.append({"Hal": "Periode", "Di file": h.metadata.get("period", "tidak ada"),
                        "Diharapkan": pilihan, "Hasil": "tidak bisa dibaca"})
        gagal = True
    else:
        a, b = h.periode
        ok = (a, b) == (awal, akhir)
        rincian.append({"Hal": "Periode", "Di file": f"{a:%d-%m-%Y} s/d {b:%d-%m-%Y}",
                        "Diharapkan": pilihan, "Hasil": "cocok" if ok else "tidak cocok"})
        gagal |= not ok

    if h.data is not None and "sales_date" in h.data:
        tgl = [t for t in h.data["sales_date"] if t is not None]
        luar = sorted({t for t in tgl if t < awal or t > akhir})
        if luar:
            gagal = True
            rincian.append({"Hal": "Tanggal transaksi", "Di file": ", ".join(f"{t:%d-%m-%Y}" for t in luar[:10]),
                            "Diharapkan": pilihan, "Hasil": f"{len(luar)} tanggal di luar periode"})
        if any(t is None for t in h.data["sales_date"]):
            gagal = True
            rincian.append({"Hal": "Tanggal transaksi", "Di file": "ada baris tanpa tanggal",
                            "Diharapkan": pilihan, "Hasil": "tidak lengkap"})
    return Cek(1, "Cabang dan periode", GAGAL if gagal else LULUS,
               "Cabang dan periode di file sesuai pilihan." if not gagal else
               "Cabang atau periode di file tidak sesuai pilihan.", rincian, h.nama_file)


# ---------------------------------------------------------------------------
# Cek 2: rekonsiliasi footer
# ---------------------------------------------------------------------------

def cek_footer(h: HasilBaca) -> Cek:
    if h.jenis is not None and not h.jenis.punya_footer:
        return Cek(2, "Rekonsiliasi footer", TIDAK_BISA,
                   f"{h.jenis.nama} dari ESB tidak punya baris footer. Kebenarannya dicek lewat "
                   "rekonsiliasi silang dengan Bill Report (cek 3).", file=h.nama_file)
    if h.data is None or not h.footer:
        return Cek(2, "Rekonsiliasi footer", TIDAK_BISA,
                   "Footer atau data tidak terbaca, total tidak bisa dicocokkan.", file=h.nama_file)
    kode = {k.nama: k for k in h.jenis.kolom}
    rincian, gagal = [], False
    for nama in h.jenis.kolom_footer:
        if nama not in h.footer:
            continue
        k = kode[nama]
        hitung = _jumlah(h.data[k.kode])
        footer = h.footer[nama]
        uang = k.tipe == "uang"
        toleransi = P.TOLERANSI_RUPIAH if uang else P.TOLERANSI_QTY
        if footer is None:
            hasil, selisih = "footer kosong", None
            gagal = True
        else:
            selisih = hitung - footer
            ok = abs(selisih) <= toleransi
            gagal |= not ok
            hasil = "cocok" if ok else "TIDAK COCOK"
        fmt = format_rupiah if uang else format_angka
        rincian.append({"Kolom": nama, "Σ baris data": fmt(hitung), "Footer ESB": fmt(footer),
                        "Selisih": "-" if selisih is None else fmt(selisih), "Hasil": hasil})
    return Cek(2, "Rekonsiliasi footer", GAGAL if gagal else LULUS,
               "Jumlah baris data sama dengan footer ESB (toleransi Rp1)." if not gagal else
               "Jumlah baris data berbeda dengan footer ESB.", rincian, h.nama_file)


# ---------------------------------------------------------------------------
# Cek 3: rekonsiliasi silang Bill vs COGS
# ---------------------------------------------------------------------------

def cek_silang(bill: HasilBaca | None, cogs: HasilBaca | None) -> Cek:
    if bill is None or cogs is None or bill.data is None or cogs.data is None:
        kurang = [n for n, h in (("Bill Report", bill), ("COGS Report", cogs)) if h is None or h.data is None]
        return Cek(3, "Rekonsiliasi Bill vs COGS", TIDAK_BISA,
                   "Tidak bisa dicek: " + ", ".join(kurang) + " tidak ada atau tidak terbaca.")
    b, c = bill.data, cogs.data
    rincian, gagal = [], False

    if bill.periode != cogs.periode:
        gagal = True
        fmt = lambda p: f"{p[0]:%d-%m-%Y} s/d {p[1]:%d-%m-%Y}" if p else "tidak terbaca"
        rincian.append({"Hal": "Periode export", "Bill": fmt(bill.periode), "COGS": fmt(cogs.periode),
                        "Selisih": "BERBEDA — export ulang dengan periode yang sama"})

    # Ringkasan per cabang per tanggal: menunjukkan di mana selisihnya.
    sb = b.groupby(["cabang", "sales_date"])["subtotal"].agg(_jumlah)
    sc = c.groupby(["cabang", "sales_date"])["total"].agg(_jumlah)
    for k in sorted(set(sb.index) | set(sc.index)):
        vb, vc = sb.get(k), sc.get(k)
        if vb is None or vc is None or abs(vb - vc) > P.TOLERANSI_RUPIAH:
            gagal = True
            rincian.append({"Hal": f"{k[0]} {k[1]:%d-%m-%Y}",
                            "Bill": format_rupiah(vb) if vb is not None else "tidak ada",
                            "COGS": format_rupiah(vc) if vc is not None else "tidak ada",
                            "Selisih": format_rupiah((vb or 0) - (vc or 0))})

    sub_bill, tot_cogs = _jumlah(b["subtotal"]), _jumlah(c["total"])
    per_bill = b.groupby("sales_number")["subtotal"].agg(_jumlah)
    per_cogs = c.groupby("sales_number")["total"].agg(_jumlah)
    nomor_bill, nomor_cogs = set(per_bill.index), set(per_cogs.index)
    rincian.insert(0, {"Hal": "Σ Subtotal (Bill) vs Σ Total (COGS)", "Bill": format_rupiah(sub_bill),
                       "COGS": format_rupiah(tot_cogs), "Selisih": format_rupiah(sub_bill - tot_cogs)})
    rincian.insert(1, {"Hal": "Jumlah Sales Number unik", "Bill": format_angka(len(nomor_bill)),
                       "COGS": format_angka(len(nomor_cogs)), "Selisih": format_angka(len(nomor_bill) - len(nomor_cogs))})
    # Bila periode berbeda, bill di tanggal yang hanya ada di salah satu file
    # sudah dijelaskan oleh baris "Periode export". Rincian per bill hanya
    # untuk tanggal yang ada di kedua file, supaya selisih sungguhan tidak
    # tenggelam.
    tgl_b = b.groupby("sales_number")["sales_date"].first()
    tgl_c = c.groupby("sales_number")["sales_date"].first()
    bersama = set(tgl_b) & set(tgl_c)
    if bill.periode != cogs.periode and bersama:
        bb = b[b["sales_date"].isin(bersama)]
        cc = c[c["sales_date"].isin(bersama)]
        selisih = _jumlah(bb["subtotal"]) - _jumlah(cc["total"])
        rincian.insert(1, {"Hal": f"Hanya tanggal yang ada di kedua file ({min(bersama):%d-%m} s/d {max(bersama):%d-%m})",
                           "Bill": format_rupiah(_jumlah(bb["subtotal"])) + f" · {bb['sales_number'].nunique()} bill",
                           "COGS": format_rupiah(_jumlah(cc["total"])) + f" · {cc['sales_number'].nunique()} bill",
                           "Selisih": format_rupiah(selisih)})
    luar = 0
    beda = []
    for n in sorted(nomor_bill | nomor_cogs):
        t = tgl_b.get(n, tgl_c.get(n))
        if bill.periode != cogs.periode and t not in bersama:
            luar += 1
            continue
        vb, vc = per_bill.get(n), per_cogs.get(n)
        if vb is None or vc is None or abs(vb - vc) > P.TOLERANSI_RUPIAH:
            beda.append({"Sales Number": n,
                         "Subtotal Bill": format_rupiah(vb) if vb is not None else "tidak ada",
                         "Total COGS": format_rupiah(vc) if vc is not None else "tidak ada",
                         "Selisih": format_rupiah(vb - vc) if vb is not None and vc is not None else "-"})
    gagal |= abs(sub_bill - tot_cogs) > P.TOLERANSI_RUPIAH or nomor_bill != nomor_cogs or bool(beda)
    if not gagal:
        ringkasan = "Σ Total COGS = Σ Subtotal Bill dan nomor bill sama."
    elif luar:
        ringkasan = (f"Periode Bill dan COGS berbeda ({luar} bill hanya ada di salah satu file). "
                     f"Di tanggal yang sama-sama ada: {len(beda)} bill berbeda.")
    else:
        ringkasan = f"Bill dan COGS tidak cocok ({len(beda)} bill berbeda)."
    return Cek(3, "Rekonsiliasi Bill vs COGS", GAGAL if gagal else LULUS, ringkasan, rincian + beda)


# ---------------------------------------------------------------------------
# Cek 4: duplikat & tumpang tindih
# ---------------------------------------------------------------------------

def cek_duplikat(bill: HasilBaca | None, awal: date, akhir: date,
                 tersimpan: list[dict] | None = None) -> Cek:
    """`tersimpan`: [{cabang, jenis, awal, akhir}] periode yang sudah ada di database."""
    rincian, gagal = [], False
    if bill is not None and bill.data is not None:
        hitung = bill.data["sales_number"].value_counts()
        ganda = hitung[hitung > 1]
        for nomor, n in ganda.items():
            gagal = True
            baris = bill.data.loc[bill.data["sales_number"] == nomor, "baris_excel"].tolist()
            rincian.append({"Jenis": "Sales Number ganda", "Detail": f"{nomor} ({n}x, baris {', '.join(map(str, baris))})"})
    cabang = set(bill.data["cabang"].dropna()) if bill is not None and bill.data is not None else set()
    tumpang = [t for t in (tersimpan or [])
               if t["cabang"] in cabang and t["awal"] <= akhir and t["akhir"] >= awal]
    for t in tumpang:
        rincian.append({"Jenis": "Periode tumpang tindih",
                        "Detail": f"{t['cabang']} {t['jenis']}: {t['awal']:%d-%m-%Y} s/d {t['akhir']:%d-%m-%Y} sudah tersimpan"})
    if tumpang:
        return Cek(4, "Duplikat", GAGAL, "Ada periode yang tumpang tindih dengan data tersimpan. "
                                         "Pilih 'ganti' untuk menimpa periode itu.", rincian)
    return Cek(4, "Duplikat", GAGAL if gagal else LULUS,
               "Tidak ada Sales Number ganda dan tidak ada periode tumpang tindih." if not gagal else
               "Ada Sales Number ganda.", rincian)


# ---------------------------------------------------------------------------
# Cek 5: kelengkapan hari
# ---------------------------------------------------------------------------

NAMA_HARI = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")


def nilai_hari_parsial(bill_per_hari: dict[date, int], jam_terakhir: dict[date, str | None],
                       cabang: str) -> dict | None:
    """Nilai tanggal TERAKHIR yang punya transaksi. None = tidak parsial.

    Pembanding: median jumlah bill di hari yang sama dalam seminggu (selain
    tanggal itu sendiri). Kalau belum ada hari yang sama, pakai median semua
    hari buka, dan catat bahwa pembandingnya lebih lemah.
    """
    buka = {t: n for t, n in bill_per_hari.items() if n > 0}
    if len(buka) < 2:
        return None
    t = max(buka)
    lain = {d: n for d, n in buka.items() if d != t}
    sama = [n for d, n in lain.items() if d.weekday() == t.weekday()]
    pembanding = sama or list(lain.values())
    median = float(pd.Series(pembanding).median())
    alasan = []
    if buka[t] < P.PARSIAL_AMBANG_BILL * median:
        dasar = f"median {NAMA_HARI[t.weekday()]}" if sama else "median semua hari buka (belum ada hari yang sama)"
        alasan.append(f"{buka[t]} bill, di bawah {int(P.PARSIAL_AMBANG_BILL * 100)}% {dasar} ({format_angka(Decimal(str(median)), 1)})")
    tutup = P.JAM_OPERASIONAL[cabang][t.weekday()][1]
    jam = jam_terakhir.get(t)
    if jam:
        hh, mm = map(int, jam.split(":"))
        if (tutup * 60) - (hh * 60 + mm) > P.PARSIAL_AMBANG_JAM * 60:
            alasan.append(f"bill terakhir masuk {jam}, lebih dari {P.PARSIAL_AMBANG_JAM} jam sebelum tutup ({tutup:02d}:00)")
    return {"tanggal": t, "alasan": alasan} if alasan else None


def cek_kelengkapan(bill: HasilBaca | None, awal: date, akhir: date) -> Cek:
    if bill is None or bill.data is None:
        return Cek(5, "Kelengkapan hari", TIDAK_BISA, "Bill Report tidak ada atau tidak terbaca.")
    d = bill.data[bill.data["sales_type"] == "Sales"]
    semua = [awal + timedelta(days=i) for i in range((akhir - awal).days + 1)]
    rincian, ringkas, ada_masalah = [], [], False
    for cabang in sorted(set(d["cabang"].dropna())):
        dc = d[d["cabang"] == cabang]
        per_hari = dc.groupby("sales_date").size().to_dict()
        jam_akhir = dc.groupby("sales_date")["sales_in_time"].max().to_dict()
        kosong = [t for t in semua if per_hari.get(t, 0) == 0]
        rincian += [{"Cabang": cabang, "Tanggal": f"{t:%d-%m-%Y}", "Hari": NAMA_HARI[t.weekday()],
                     "Status": "tanpa transaksi (dianggap tutup)"} for t in kosong]
        parsial = nilai_hari_parsial({t: per_hari.get(t, 0) for t in semua}, jam_akhir, cabang)
        if parsial:
            t = parsial["tanggal"]
            rincian.append({"Cabang": cabang, "Tanggal": f"{t:%d-%m-%Y}", "Hari": NAMA_HARI[t.weekday()],
                            "Status": "kemungkinan parsial, dikeluarkan dari rata-rata harian: " + "; ".join(parsial["alasan"])})
        ada_masalah |= bool(kosong or parsial)
        ringkas.append(f"{cabang} {len(semua) - len(kosong)}/{len(semua)} hari"
                       + (f" (parsial: {parsial['tanggal']:%d-%m})" if parsial else ""))
    return Cek(5, "Kelengkapan hari", PERINGATAN if ada_masalah else LULUS,
               "Hari dengan transaksi: " + "; ".join(ringkas) + ".", rincian)


# ---------------------------------------------------------------------------
# Cek 6 & 7: data HPP
# ---------------------------------------------------------------------------

def tandai_salah_input_cogs(cogs: pd.DataFrame) -> pd.Series:
    """True untuk baris Price > 0 dengan HPP per unit > 1,5 x Price."""
    def salah(r) -> bool:
        p, q, c = r["price"], r["qty"], r["cogs_total"]
        if p is None or q is None or c is None or p <= 0 or q <= 0:
            return False
        return (c / q) > Decimal(str(P.FAKTOR_SALAH_INPUT_COGS)) * p
    return cogs.apply(salah, axis=1).astype(bool) if len(cogs) else pd.Series(dtype=bool)


def tandai_tanpa_hpp(cogs: pd.DataFrame) -> pd.Series:
    """True untuk baris Price > 0 dan COGS Total = 0 (menu tanpa resep)."""
    def tanpa(r) -> bool:
        p, c = r["price"], r["cogs_total"]
        return p is not None and p > 0 and (c is None or c == 0)
    return cogs.apply(tanpa, axis=1).astype(bool) if len(cogs) else pd.Series(dtype=bool)


def cek_salah_input(cogs: HasilBaca | None) -> Cek:
    if cogs is None or cogs.data is None:
        return Cek(6, "Salah input resep/COGS", TIDAK_BISA, "COGS Report tidak ada atau tidak terbaca.")
    c = cogs.data
    m = tandai_salah_input_cogs(c)
    pilih = c[m]
    rincian = []
    for (menu, tgl), g in pilih.groupby(["menu_bersih", "sales_date"], sort=True):
        rincian.append({"Menu": menu, "Tanggal": f"{tgl:%d-%m-%Y}", "Jumlah baris": len(g),
                        "Harga": format_rupiah(g["price"].iloc[0]),
                        "COGS tercatat": format_rupiah(_jumlah(g["cogs_total"])),
                        "HPP/unit": format_rupiah(_jumlah(g["cogs_total"]) / _jumlah(g["qty"]))})
    return Cek(6, "Salah input resep/COGS", PERINGATAN if len(pilih) else LULUS,
               f"{len(pilih)} baris ditandai salah input (HPP/unit > {format_angka(Decimal(str(P.FAKTOR_SALAH_INPUT_COGS)), 1)}× harga) "
               "dan dikeluarkan dari perhitungan margin." if len(pilih) else "Tidak ada baris yang HPP-nya melebihi batas.",
               rincian, cogs.nama_file)


def cek_tanpa_hpp(cogs: HasilBaca | None) -> Cek:
    if cogs is None or cogs.data is None:
        return Cek(7, "Menu tanpa data HPP", TIDAK_BISA, "COGS Report tidak ada atau tidak terbaca.")
    c = cogs.data
    pilih = c[tandai_tanpa_hpp(c)]
    rincian = []
    for menu, g in pilih.groupby("menu_bersih", sort=True):
        rincian.append({"Menu": menu, "Jumlah baris": len(g), "Qty": format_angka(_jumlah(g["qty"])),
                        "Omzet (Total)": format_rupiah(_jumlah(g["total"]))})
    total = _jumlah(pilih["total"])
    return Cek(7, "Menu tanpa data HPP", PERINGATAN if len(pilih) else LULUS,
               f"{len(rincian)} menu ({len(pilih)} baris, omzet {format_rupiah(total)}) tanpa data HPP; "
               "tidak ikut margin blended." if len(pilih) else "Semua menu berbayar punya data HPP.",
               rincian, cogs.nama_file)


# ---------------------------------------------------------------------------
# Gabungan
# ---------------------------------------------------------------------------

def validasi_unggahan(files: list[HasilBaca], awal: date, akhir: date,
                      tersimpan: list[dict] | None = None,
                      cabang: list[str] | None = None) -> LaporanValidasi:
    cek: list[Cek] = []
    for h in files:
        cek.append(cek_terbaca(h))
    pakai = [h for h in files if h.bisa_dipakai]
    for h in pakai:
        cek.append(cek_cabang_periode(h, awal, akhir, cabang))
    for h in pakai:
        cek.append(cek_footer(h))

    def satu(jenis):
        cocok = [h for h in pakai if h.jenis is jenis]
        if len(cocok) > 1:
            cek.append(Cek(0, f"File {jenis.nama}", GAGAL,
                           f"Ada {len(cocok)} file {jenis.nama} untuk satu unggahan. Unggah satu saja.",
                           [{"File": h.nama_file} for h in cocok]))
            return None
        return cocok[0] if cocok else None

    bill, cogs = satu(BILL), satu(COGS)
    for jenis, h in ((BILL, bill), (COGS, cogs)):
        if h is None and not any(f.jenis is jenis for f in files):
            cek.append(Cek(0, f"File {jenis.nama}", GAGAL if jenis.wajib_unggah else PERINGATAN,
                           f"{jenis.nama} (wajib) tidak ada di unggahan ini."))
    cek.append(cek_silang(bill, cogs))
    cek.append(cek_duplikat(bill, awal, akhir, tersimpan))
    cek.append(cek_kelengkapan(bill, awal, akhir))
    cek.append(cek_salah_input(cogs))
    cek.append(cek_tanpa_hpp(cogs))
    cek.sort(key=lambda c: c.nomor)
    return LaporanValidasi(cek)
