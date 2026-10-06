"""Bagian dashboard dari laporan ESB opsional (hanya data yang lolos cek silang saat unggah).

- Metode pembayaran        (Sales Recapitulation Detail Report) — tab Overview
- Staf & pembatalan        (Staff Sales & Cancel + Cancel Menu Detail) — tab Overview
- Rincian promo ESB        (Promotion Report) — tab Promo
- Data pelanggan ESB ORDER (Customer Data Report) — tab Membership, terpisah dari loyalty

Setiap bagian menyebut cakupan harinya. Bila laporan tidak diunggah untuk
sebagian hari periode, angkanya diberi label "dari x dari y hari"; bila tidak
ada sama sekali: "Tidak diketahui — [laporan] belum diunggah".
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from app import pengaturan
from app.angka import format_angka, format_persen, format_rupiah
from app.hitung.data import DataRentang
from app.hitung.minggu import ringkas_tanggal
from app.hitung.nilai import persen
from app.hitung.overview import tgl

NAMA = {"recap_detail": "Sales Recapitulation Detail Report", "promotion": "Promotion Report",
        "staff": "Staff Sales & Cancel Report", "cancel": "Cancel Menu Detail Report", "customer": "Customer Data Report"}


def _hari(a: date, z: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((z - a).days + 1)]


def cakupan(con, cabang: str, jenis: str, d: DataRentang) -> set[date]:
    rows = con.execute("SELECT awal, akhir FROM esb_opsional WHERE cabang = ? AND jenis = ? AND awal <= ? AND akhir >= ?",
                       [cabang, jenis, d.akhir, d.awal]).fetchall()
    return {t for a, z in rows for t in _hari(max(a, d.awal), min(z, d.akhir))}


def _status(con, d: DataRentang, jenis: str) -> tuple[set[date], dict | None, str]:
    """(hari tercakup, info-tidak-tersedia, label cakupan)."""
    hari = cakupan(con, d.cabang, jenis, d)
    if not hari:
        return hari, {"tersedia": False, "alasan": f"{NAMA[jenis]} periode ini belum diunggah (opsional)"}, ""
    kurang = [t for t in d.hari if t not in hari]
    label = f"dari {len(hari)} dari {len(d.hari)} hari (belum diunggah: {ringkas_tanggal(kurang)})" if kurang else ""
    return hari, None, label


# ---------------------------------------------------------------------------

_NOMINAL = re.compile(r"\s*\([\d.,]+\)")


def metode_bayar_bersih(teks: str | None) -> str:
    """'MEMBER DEPOSIT (200.000),QRIS BCA (441.022)' -> 'Kombinasi: MEMBER DEPOSIT + QRIS BCA'."""
    if not teks:
        return "Tidak tercatat"
    bagian = [_NOMINAL.sub("", b).strip() for b in str(teks).split(",") if b.strip()]
    return bagian[0] if len(bagian) == 1 else "Kombinasi: " + " + ".join(bagian)


def metode_bayar(con, d: DataRentang) -> dict:
    hari, tak, label = _status(con, d, "recap_detail")
    if tak:
        return tak
    rows = con.execute("""SELECT p.payment_method, b.grand_total FROM esb_bayar p
                          JOIN esb_bill b ON b.sales_number = p.sales_number AND b.cabang = p.cabang
                          WHERE p.cabang = ? AND b.sales_type = 'Sales' AND b.sales_date BETWEEN ? AND ?""",
                       [d.cabang, min(hari), max(hari)]).fetchall()
    per = defaultdict(lambda: [0, Decimal(0)])
    for m, gt in rows:
        k = metode_bayar_bersih(m)
        per[k][0] += 1
        per[k][1] += Decimal(gt or 0)
    n, total = len(rows), sum((v[1] for v in per.values()), Decimal(0))
    baris = [{"Metode bayar": k, "Bill": v[0], "Porsi bill": format_persen(persen(v[0], n)),
              "Grand Total": format_rupiah(v[1]), "Porsi omzet": format_persen(persen(v[1], total))}
             for k, v in sorted(per.items(), key=lambda kv: -kv[1][0])]
    return {"tersedia": True, "baris": baris, "cakupan": label,
            "catatan": ["Sumber: Sales Recapitulation Detail Report (kolom Payment Method), Grand Total dari Bill Report.",
                        "Bill yang dibayar dengan beberapa cara ditulis 'Kombinasi'; nominal per cara bayar tidak dipecah."]}


def staf(con, d: DataRentang) -> dict:
    """Staff Report tidak punya tanggal: hanya export yang periodenya di dalam periode ini yang dipakai."""
    rows = con.execute("SELECT unggahan_id, awal, akhir FROM esb_opsional WHERE cabang = ? AND jenis = 'staff' AND awal <= ? AND akhir >= ?",
                       [d.cabang, d.akhir, d.awal]).fetchall()
    di_dalam = [(u, a, z) for u, a, z in rows if a >= d.awal and z <= d.akhir]
    silang = [(a, z) for u, a, z in rows if not (a >= d.awal and z <= d.akhir)]
    if not di_dalam:
        if silang:
            return {"tersedia": False, "alasan": "Staff Report yang ada (" + ", ".join(f"{tgl(a)} – {tgl(z)}" for a, z in silang)
                    + ") melewati batas periode ini, dan laporan itu tidak punya rincian per tanggal"}
        return {"tersedia": False, "alasan": "Staff Sales & Cancel Report periode ini belum diunggah (opsional)"}
    uid = [u for u, _, _ in di_dalam]
    q = con.execute(f"""SELECT staf, sum(sales_qty), sum(sales_total), sum(cancel_qty), sum(cancel_total), sum(void_qty),
                               sum(void_total), sum(remove_qty), sum(remove_total)
                        FROM esb_staf WHERE cabang = ? AND unggahan_id IN ({",".join("?" * len(uid))}) GROUP BY 1""",
                    [d.cabang, *uid]).fetchall()
    hari = {t for _, a, z in di_dalam for t in _hari(a, z)}
    baris = []
    for s, sq, st, cq, ct, vq, vt, rq, rt in sorted(q, key=lambda r: -(r[2] or 0)):
        if not any((sq, cq, vq, rq)):
            continue
        baris.append({"Staf pencatat pesanan": "(ESB ORDER, tanpa staf)" if s == "-" else s,
                      "Item terjual": format_angka(sq), "Penjualan (Subtotal)": format_rupiah(st),
                      "Cancel": f"{format_angka(cq)} item · {format_rupiah(ct)}" if cq else "-",
                      "Void": f"{format_angka(vq)} item · {format_rupiah(vt)}" if vq else "-",
                      "Remove": f"{format_angka(rq)} item · {format_rupiah(rt)}" if rq else "-"})
    kurang = [t for t in d.hari if t not in hari]
    return {"tersedia": True, "baris": baris,
            "cakupan": f"dari {len(hari)} dari {len(d.hari)} hari (belum diunggah: {ringkas_tanggal(kurang)})" if kurang else "",
            "catatan": ["Staf = yang menginput pesanan (kolom Waiter di ESB), bukan kasir yang menerima pembayaran. "
                        "Terbukti: penjualan per staf sama dengan Σ Subtotal per Waiter di Sales Recapitulation Detail Report.",
                        "Baris tanpa staf = pesanan ESB ORDER (pelanggan pesan sendiri); totalnya sama dengan bill ESB ORDER.",
                        "Penjualan per staf memakai basis Subtotal (sebelum diskon, pajak, dan service charge).",
                        "'Remove' adalah istilah ESB; artinya belum dikonfirmasi, jadi angkanya ditampilkan apa adanya."]}


def pembatalan(con, d: DataRentang) -> dict:
    hari, tak, label = _status(con, d, "cancel")
    if tak:
        return tak
    rows = con.execute("""SELECT tanggal, menu, jenis_batal, qty, subtotal, total, dipesan_oleh, dibatalkan_oleh, catatan,
                                 waktu_pesan, waktu_batal
                          FROM esb_batal WHERE cabang = ? AND tanggal BETWEEN ? AND ? ORDER BY waktu_batal""",
                       [d.cabang, d.awal, d.akhir]).fetchall()
    rows = [r for r in rows if r[0] in hari]
    per_jenis = Counter()
    nilai = defaultdict(Decimal)
    for r in rows:
        per_jenis[r[2]] += int(r[3] or 0)
        nilai[r[2]] += Decimal(r[4] or 0)
    ringkas = [{"Jenis": j, "Item": per_jenis[j], "Nilai (Subtotal)": format_rupiah(nilai[j])} for j in sorted(per_jenis)]
    baris = [{"Tanggal": tgl(r[0]), "Menu": r[1], "Jenis": r[2], "Qty": format_angka(r[3]), "Subtotal": format_rupiah(r[4]),
              "Dipesan oleh": r[6] or "-", "Dibatalkan oleh": r[7] or "-",
              "Selang": f"{int((r[10] - r[9]).total_seconds() // 60)} menit" if r[9] and r[10] else "-",
              "Catatan pembatalan": r[8] or "-"} for r in rows]
    return {"tersedia": True, "ringkas": ringkas, "baris": baris, "cakupan": label,
            "catatan": ["Sumber: Cancel Menu Detail Report; total per staf sudah dicocokkan dengan Staff Sales & Cancel Report saat unggah.",
                        "Item yang dibatalkan tidak ada di Bill Report dan COGS Report, jadi tidak memengaruhi omzet di dashboard.",
                        "Selang = waktu pesan sampai waktu dibatalkan."]}


def _kunci(x: str) -> str:
    return " ".join(str(x).split()).upper()


def _tanpa_label_bill(x: str) -> str:
    """Promotion Report menambahkan '(BILL DISCOUNT)' pada nama promo diskon bill (terlihat di export asli)."""
    return re.sub(r"\s*\(BILL DISCOUNT\)\s*$", "", " ".join(str(x).split()), flags=re.IGNORECASE)


def rincian_promo(con, d: DataRentang) -> dict:
    hari, tak, label = _status(con, d, "promotion")
    if tak:
        return tak
    rows = con.execute("""SELECT sales_date, sales_number, promotion_type, promotion_name, menu, qty, discount_total, voucher_discount
                          FROM esb_promo WHERE cabang = ? AND sales_date BETWEEN ? AND ?""", [d.cabang, d.awal, d.akhir]).fetchall()
    rows = [r for r in rows if r[0] in hari]
    internal = {_kunci(x) for x in pengaturan.ambil(con, "promotion_internal")}
    per = defaultdict(lambda: {"bill": set(), "diskon": Decimal(0), "menu": Counter(), "tingkat": set(), "tipe": set()})
    for t, sn, tipe, nama, menu, qty, disk, vouch in rows:
        p = per[" ".join(str(nama).split())]
        p["bill"].add(sn)
        p["diskon"] += Decimal(disk or 0) + Decimal(vouch or 0)
        p["tipe"].add(tipe)
        if menu and menu != "-":
            p["menu"][menu] += Decimal(qty or 0)
            p["tingkat"].add("menu")
        else:
            p["tingkat"].add("bill")
    baris = []
    for nama, p in sorted(per.items(), key=lambda kv: -kv[1]["diskon"]):
        baris.append({"Promo (Promotion Report)": nama, "Diterapkan ke": " & ".join(sorted(p["tingkat"])),
                      "Jenis": "internal" if _kunci(_tanpa_label_bill(nama)) in internal else "promo",
                      "Bill": len(p["bill"]), "Total diskon": format_rupiah(p["diskon"]),
                      "Menu yang didiskon (qty)": ", ".join(f"{m} ({format_angka(q)})" for m, q in p["menu"].most_common(6)) or "-"})
    return {"tersedia": True, "baris": baris, "cakupan": label,
            "catatan": ["Sumber: Promotion Report. Saat unggah, Σ diskon per bill sudah dicocokkan dengan diskon menu + bill + voucher di Bill Report.",
                        "Berbeda dengan tabel di atas, diskon bill yang memakai lebih dari satu promo sudah terpecah per promo di sini.",
                        "Jenis 'internal' dari daftar diskon internal di Pengaturan."]}


def pelanggan_esb(con, d: DataRentang) -> dict:
    hari, tak, label = _status(con, d, "customer")
    if tak:
        return tak
    n_order = con.execute("""SELECT count(*) FROM esb_bill WHERE cabang = ? AND sales_type = 'Sales' AND visit_purpose = 'ESB ORDER'
                             AND sales_date BETWEEN ? AND ?""", [d.cabang, d.awal, d.akhir]).fetchone()[0]
    rows = con.execute("SELECT sales_date, sales_number, telp FROM esb_pelanggan WHERE cabang = ? AND sales_date BETWEEN ? AND ?",
                       [d.cabang, d.awal, d.akhir]).fetchall()
    rows = [r for r in rows if r[0] in hari]
    telp = [r[2] for r in rows if r[2]]
    unik = Counter(telp)
    member = set()
    if unik:
        try:
            member = {r[0] for r in con.execute(
                f"SELECT DISTINCT nomor FROM loy_pelanggan WHERE nomor IN ({','.join('?' * len(unik))})", list(unik)).fetchall()}
        except Exception:  # tabel loyalty belum ada
            member = set()
    kartu = [
        {"Hal": "Bill ESB ORDER di periode ini", "Nilai": format_angka(n_order)},
        {"Hal": "Bill dengan data pelanggan ESB", "Nilai": f"{format_angka(len(rows))}"},
        {"Hal": "…yang mencantumkan nomor telepon", "Nilai": f"{format_angka(len(telp))} ({format_persen(persen(len(telp), len(rows)))})" if rows else "0"},
        {"Hal": "Nomor telepon unik", "Nilai": format_angka(len(unik))},
        {"Hal": "Nomor yang memesan ≥2 kali di periode ini", "Nilai": format_angka(sum(1 for v in unik.values() if v >= 2))},
        {"Hal": "Nomor yang sudah member loyalty (cocok nomor WA)", "Nilai":
            f"{format_angka(len(member))} dari {format_angka(len(unik))}" if unik else "-"},
    ]
    return {"tersedia": True, "kartu": kartu, "cakupan": label,
            "catatan": ["Sumber: Customer Data Report ESB, hanya baris yang Sales Number-nya ada di Bill Report periode ini. "
                        "Isinya data pelanggan ESB ORDER (pesan sendiri lewat QR).",
                        "Nama dan email tidak dibaca. Nomor telepon disimpan sebagai sidik (hash) saja, sama seperti data loyalty, "
                        "sehingga bisa dicocokkan tanpa menyimpan nomor aslinya.",
                        "Data ini terpisah dari member loyalty; baris terakhir hanya menghitung nomor yang sama di kedua sumber."]}


def kualitas(con, d: DataRentang) -> list[dict]:
    hasil = []
    for jenis, nama in NAMA.items():
        hari = cakupan(con, d.cabang, jenis, d)
        hasil.append({"file": f"{nama} (opsional)", "status": "ada" if hari else "tidak ada",
                      "keterangan": f"{len(hari)}/{len(d.hari)} hari" if hari else "opsional; bagian yang memakainya tampil 'Tidak diketahui'"})
    return hasil
