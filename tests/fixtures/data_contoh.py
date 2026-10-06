"""Database contoh lengkap untuk tes browser semua tab (data buatan, bukan data asli).

- ESB Rungkut & Mawar 31 Agu – 4 Okt 2026 (5 minggu), beberapa bill per hari:
  makanan, kudapan, minuman panas/dingin, paket WFA (anak Rp0), promo.
- Loyalty Rungkut 28 Sep – 4 Okt (dari tes loyalty).
- Instagram Brand 31 Agu – 4 Okt, keenam metrik, Pengikut dengan hari kosong.
- Pengaturan: promo, kampanye, konten, menu baru, input manual IG Rungkut.
- Narasi tersimpan untuk tab Overview Rungkut Oktober (lewat jalur tempel manual).
"""
from datetime import date, timedelta
from pathlib import Path

from app import db, db_ig, db_loyalty, narasi, pengaturan
from app.hitung import dashboard
from app.parser.esb import baca_file_esb
from app.parser.instagram import baca_file_ig
from app.parser.loyalty import baca_file_loyalty
from app.validasi import validasi_unggahan
from app import validasi_loyalty as vl
from tests.fixtures.buat_esb import bill, buat_bill, buat_cogs, item
from tests.fixtures.buat_ig import buat_ig

AWAL, AKHIR = date(2026, 8, 31), date(2026, 10, 4)
NASI = {"kat": "FOOD", "detail": "BUBUR & NASI"}
MIE = {"kat": "FOOD", "detail": "MIE"}
KUDAPAN = {"kat": "FOOD", "detail": "KUDAPAN"}
WFA = {"kat": "FOOD", "detail": "COMBO MEAL WFA"}
KOPI = {"kat": "BEVERAGE", "detail": "KOPI"}
TEH = {"kat": "BEVERAGE", "detail": "TEH"}

# (isi bill, promo) — isi = [(menu, qty, harga, hpp per unit, kategori)]
POLA = [
    ([("Nasi Goreng Ampyang", 2, 35000, 12000, NASI), ("Es Teh Tarik", 2, 15000, 4000, TEH)], None),
    ([("Mie Goreng Ayam Jamur", 1, 32000, 11000, MIE), ("Kopi Susu Panas", 1, 18000, 5000, KOPI),
      ("Tahu Walik", 1, 20000, 6000, KUDAPAN)], "PROMO MEMBERSHIP SERBUK HEMAT"),
    ([("Paket WFA", 1, 45000, 0, WFA), ("Roti Bakar Srikaya", 1, 0, 7000, KUDAPAN), ("Kopi Susu Panas", 1, 0, 5000, KOPI)], None),
    ([("Tahu Walik", 2, 20000, 6000, KUDAPAN), ("Es Jeruk", 2, 15000, 3500, {"kat": "BEVERAGE", "detail": "JUS"})], None),
]


def _hari(a, z):
    return [a + timedelta(days=i) for i in range((z - a).days + 1)]


def _esb(con, tmp: Path):
    bills, items = [], []
    for cabang, kode in (("Rungkut", "R"), ("Mawar", "M")):
        for i, t in enumerate(_hari(AWAL, AKHIR)):
            n = 6 + (t.weekday() >= 5) * 4 + (i % 3) - (cabang == "Mawar") * 2
            for j in range(n):
                isi, promo = POLA[(i + j) % len(POLA)]
                if cabang == "Mawar" and j == 0:  # menu yang hanya ada di Mawar (untuk tes laporan khusus cabang)
                    isi = isi + [("Pisang Goreng Keju", 1, 23000, 7000, KUDAPAN)]
                sn = f"{kode}{t:%m%d}{j:02d}"
                sub = sum(q * h for _, q, h, _, _ in isi)
                jam = f"{8 + (j * 2) % 13:02d}:{(j * 7) % 60:02d}:00" if j < n - 1 else "20:30:00"
                vp = ("DINE IN", "TAKE AWAY", "GOFOOD", "ESB ORDER")[j % 4]
                bills.append(bill(sn, t, jam, sub, vp=vp, cabang=cabang, sc=3 if cabang == "Rungkut" else 0, Promotion=promo))
                items += [item(sn, t, m, q, h, c * q, cabang=cabang, **k) for m, q, h, c, k in isi]
    fs = [baca_file_esb(buat_bill(tmp / "contoh-bill.xlsx", bills, cabang=["Rungkut", "Mawar"], awal=AWAL, akhir=AKHIR)),
          baca_file_esb(buat_cogs(tmp / "contoh-cogs.xlsx", items, cabang=["Rungkut", "Mawar"], awal=AWAL, akhir=AKHIR))]
    fs += [baca_file_esb(p) for p in _opsional(tmp, bills, items)]
    lap = validasi_unggahan(fs, AWAL, AKHIR)
    assert not lap.terblokir, [(c.nama, c.ringkasan) for c in lap.cek if c.status == "gagal"]
    assert {k: sorted(v) for k, v in lap.opsional.simpan.items()} == {
        k: ["Mawar", "Rungkut"] for k in ("promotion", "recap_detail", "staff", "cancel", "customer")}, \
        [(c.nama, c.ringkasan, c.rincian) for c in lap.cek if c.nomor >= 30]
    db.simpan_unggahan(con, fs, lap, AWAL, AKHIR, simpan_walau_tidak_cocok=True)


def _opsional(tmp: Path, bills: list[dict], items: list[dict]) -> list[Path]:
    """Kelima laporan ESB opsional, disusun dari bill & item yang sama supaya lolos cek silang."""
    from tests.test_esb_opsional import K_CANCEL, K_CUST, K_PROMO, K_RECAP, K_STAFF
    from tests.fixtures.buat_esb import _tulis, footer_dari
    kd = ["Rungkut", "Mawar"]
    per_bill = {b["Sales Number"]: b for b in bills}
    bayar = {sn: ("QRIS (ESB ORDER)" if b["Visit Purpose"] == "ESB ORDER" else
                  ("QRIS BCA", "CASH", "DEBIT CARD BCA", "MEMBER DEPOSIT (10.000),QRIS BCA (5.000)")[int(sn[-2:]) % 4])
             for sn, b in per_bill.items()}
    promo = [{"Branch": b["Branch"], "Sales Date": b["Sales Date"], "Promotion Type": "MENU DISCOUNT(RP)",
              "Promotion Name": "PROMO MEMBERSHIP SERBUK HEMAT", "Sales Number": sn, "Menu Name": "Mie Goreng Ayam Jamur",
              "Qty": 1, "Discount Total": 0, "Voucher Discount": 0, "Bill Total": b["Grand Total"]}
             for sn, b in per_bill.items() if b["Promotion"]]
    recap = [{"Sales Number": i["Sales Number"], "Sales Type": "Sales", "Sales Date": i["Sales Date"], "Branch": i["Branch"],
              "Visit Purpose": per_bill[i["Sales Number"]]["Visit Purpose"], "Payment Method": bayar[i["Sales Number"]],
              "Menu": i["Menu"], "Order Mode": "EZO QS" if bayar[i["Sales Number"]].startswith("QRIS (ESB") else "POS",
              "Qty": i["Qty"], "Subtotal": i["Total"]} for i in items]
    staf = []
    for c, nama in (("Rungkut", "Aisha"), ("Mawar", "Budi")):
        for esb, user in ((False, nama), (True, "-")):
            x = [i for i in items if i["Branch"].endswith(c) and (per_bill[i["Sales Number"]]["Visit Purpose"] == "ESB ORDER") == esb]
            staf.append({"User": user, "Branch": f"Kedai Ampyang - {c}", "Sales Qty": sum(i["Qty"] for i in x),
                         "Sales Total": sum(i["Total"] for i in x), "Cancel Qty": 0, "Cancel Total": 0, "Void Qty": 0,
                         "Void Total": 0, "Remove Qty": 0, "Remove Total": 0})
    staf[0].update({"Cancel Qty": 1, "Cancel Total": 15000})
    batal = [{"Sales Number": "RX0929", "Branch": "Kedai Ampyang - Rungkut", "Menu": "Es Teh Tarik", "Menu Category": "BEVERAGE",
              "Menu Category Detail": "TEH", "Order By": "Aisha", "Order Time": "2026-09-29 17:16:15", "Cancel / Void By": "Aisha",
              "Cancel / Void Time": "2026-09-29 17:27:46", "Cancel / Void": "Cancel", "Cancel Notes": "salah input",
              "Qty": 1, "Subtotal": 15000, "Total": 16500}]
    cust = [{"Order ID": f"O{n}", "Sales Type": "Dine In (Quick service)", "Sales Number": sn, "Full Name": "Pelanggan",
             "Email": "-", "Phone Number": f"0812000{n % 7:04d}"}
            for n, (sn, b) in enumerate(per_bill.items()) if b["Visit Purpose"] == "ESB ORDER" and b["Branch"].endswith("Rungkut")]
    return [
        _tulis(tmp / "contoh-promo.xlsx", "Promotion Report", K_PROMO, promo,
               footer_dari(promo, ["Qty", "Discount Total", "Voucher Discount", "Bill Total"]), kd, AWAL, AKHIR),
        _tulis(tmp / "contoh-recap.xlsx", "Sales Recapitulation Detail", K_RECAP, recap, None, kd, AWAL, AKHIR,
               baris_header=11, label_bawah=[("Rounding Total", "0")]),
        _tulis(tmp / "contoh-staff.xlsx", "Staff Sales & Cancel Report", K_STAFF, staf, None, kd, AWAL, AKHIR,
               baris_header=12, sales_type="Sales"),
        _tulis(tmp / "contoh-cancel.xlsx", "Cancel Menu Detail Report", K_CANCEL, batal, None, kd, AWAL, AKHIR, baris_header=12),
        _tulis(tmp / "contoh-customer.xlsx", "Customer Data Report", K_CUST, cust, None, kd, AWAL, AKHIR, baris_header=10),
    ]


def _loyalty(con, tmp: Path):
    from tests.test_loyalty import _file_loyalty
    a, z = date(2026, 9, 28), date(2026, 10, 4)
    fs = [baca_file_loyalty(p) for p in _file_loyalty(tmp)]
    cek = vl.validasi_loyalty(fs, a, z, db_loyalty.periode_tersimpan(con), None)
    db_loyalty.simpan(con, fs, cek, a, z, simpan_walau_tidak_cocok=True)


def _instagram(con, tmp: Path):
    hari = _hari(AWAL, AKHIR)
    metrik = {"Tayangan": lambda i: 400 + 37 * (i % 9), "Jangkauan": lambda i: 150 + 11 * (i % 7),
              "Interaksi konten": lambda i: 5 + i % 13, "Kunjungan Profil Instagram": lambda i: 20 + i % 11,
              "Klik tautan Instagram": lambda i: 30 + i % 5 if hari[i] >= date(2026, 9, 21) and hari[i] <= date(2026, 9, 27) else 0}
    fs = [baca_file_ig(buat_ig(tmp / f"ig-{j}.csv", judul, {t: f(i) for i, t in enumerate(hari)}))
          for j, (judul, f) in enumerate(metrik.items())]
    fs.append(baca_file_ig(buat_ig(tmp / "ig-pengikut.csv", "Pengikut Instagram",
                                   {t: 1 + i % 3 for i, t in enumerate(hari) if i % 4})))
    cek, info = db_ig.validasi(fs, "Brand", {})
    db_ig.simpan(con, fs, "Brand", cek, info["gabung"], False)


def _pengaturan(con):
    simpan = lambda k, v: pengaturan.simpan(con, k, pengaturan.periksa(k, v))
    simpan("promo", [{"nama": "Serbuk Hemat", "mulai": "2026-09-28", "selesai": "2026-10-04", "cabang": "keduanya",
                      "promotion_esb": ["PROMO MEMBERSHIP SERBUK HEMAT"], "menu_promo": ["Mie Goreng Ayam Jamur"]}])
    simpan("kampanye", [{"nama": "Iklan Tahu Walik", "cabang": "keduanya", "akun": "Brand", "mulai": "2026-09-21",
                         "selesai": "2026-09-27", "anggaran": "700000", "platform": "Instagram Ads", "tujuan": "Kunjungan profil",
                         "menu_promo": ["Tahu Walik"]}])
    simpan("konten", [{"tanggal": "2026-09-25", "akun": "Brand", "format": "Reels", "topik": "Tahu Walik"}])
    simpan("menu_baru", [{"nama": "Tahu Walik", "mulai": "2026-09-01", "tab": "kudapan"}])
    simpan("ig_manual", [{"akun": "Rungkut", "senin": "2026-09-28", "nilai": {"tayangan": "500", "pengikut": "3"}}])


JAWABAN_CONTOH = """=== overview ===
FAKTA: Data periode ini lengkap untuk dicek di tabel harian.
DUGAAN: Akhir pekan lebih ramai karena rombongan keluarga.
SARAN: Siapkan stok Tahu Walik lebih banyak untuk Sabtu dan Minggu.
"""


def isi(path: Path, tmp: Path):
    tmp.mkdir(parents=True, exist_ok=True)
    with db.koneksi(path) as con:
        _esb(con, tmp)
        _loyalty(con, tmp)
        _instagram(con, tmp)
        _pengaturan(con)
        data = dashboard.hitung(con, "Rungkut", 2026, 10, "bulan")
        data["narasi"] = {"aktif": False, "tab": narasi.status(con, data)}
        narasi.simpan_manual(con, data, JAWABAN_CONTOH)
