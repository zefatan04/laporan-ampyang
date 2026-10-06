"""Tab Foot Traffic.

Ukuran utama = jumlah bill. Pax TIDAK dipakai sebagai jumlah tamu (ESB
ORDER, GoFood, GrabFood selalu tercatat 1 pax). Perkiraan orang makan =
jumlah porsi makanan utama, termasuk porsi Rp0 di dalam paket (keputusan
6 Okt 2026). Lama layanan tidak dihitung: bill dine-in dibuka dan ditutup
di kasir, jadi Sales In/Out Time tidak mengukur antrean.
"""

from __future__ import annotations

from decimal import Decimal

from app import pengaturan_bawaan as P
from app.angka import format_angka
from app.hitung.data import DataRentang
from app.hitung.nilai import asal, bagi, jumlah, nilai, persen, tidak_diketahui
from app.hitung.overview import SUMBER_BILL, SUMBER_COGS, _asal_rentang, tgl
from app.validasi import NAMA_HARI

CATATAN_PAX = "Pax tidak dipakai: ESB ORDER, GoFood, dan GrabFood selalu tercatat 1 pax."


def _jam(s) -> int | None:
    try:
        return int(str(s)[:2])
    except (TypeError, ValueError):
        return None


def _jendela(jam: int | None) -> str:
    if jam is None:
        return "Jam tidak tercatat"
    for j in P.JENDELA_WAKTU:
        if j["dari"] <= jam <= j["sampai"]:
            return j["nama"]
    return "Di luar jendela"


def porsi_per_bill(d: DataRentang) -> dict:
    """Σ qty makanan utama per Sales Number (termasuk item Rp0 di dalam paket)."""
    m = d.cogs[d.cogs["kelompok"] == "makanan_utama"]
    return m.groupby("sales_number")["qty"].agg(jumlah).to_dict()


def hitung(d: DataRentang) -> dict:
    if not d.ada_data:
        alasan = f"belum ada data {d.cabang} untuk {d.awal:%d-%m-%Y} s/d {d.akhir:%d-%m-%Y}"
        return {"tersedia": False, "alasan": alasan,
                "kartu": {k: tidak_diketahui(alasan) for k in ("bill_per_hari", "orang_makan_per_hari", "porsi_per_bill")}}
    buka = set(d.hari_buka)
    hb = len(d.hari_buka)
    b = d.bill[d.bill["sales_date"].isin(buka)].copy()
    filt = _asal_rentang(d) + ["Hanya hari buka (tanpa hari tutup & parsial)"]
    keluar_hari = [{"alasan": "Hari tutup", "jumlah": len(d.tutup)},
                   {"alasan": "Hari parsial", "jumlah": len(d.parsial)},
                   {"alasan": "Bill di hari parsial", "jumlah": int(d.bill["sales_date"].isin(set(d.parsial)).sum())}]
    pr = (["Sebagian data disimpan walau rekonsiliasi tidak cocok."] if d.rekon_gagal else []) + \
         ([f"Parsial: data hanya {len(d.tercakup)} dari {len(d.hari)} hari."] if not d.lengkap else [])

    porsi = porsi_per_bill(d)
    b["porsi"] = b["sales_number"].map(lambda s: porsi.get(s, Decimal(0)))
    b["jam"] = b["sales_in_time"].map(_jam)
    b["jendela"] = b["jam"].map(_jendela)
    b["akhir_pekan"] = b["sales_date"].map(lambda t: t.weekday() >= 5)

    kartu = {}
    a = asal("Jumlah bill di hari buka ÷ jumlah hari buka", [f"{SUMBER_BILL} · Sales Number, Sales Date"],
             filt, len(b), keluar_hari, [CATATAN_PAX])
    v = bagi(len(b), hb)
    kartu["bill_per_hari"] = nilai(v, "desimal", a, peringatan=pr) if v is not None else tidak_diketahui("tidak ada hari buka", a)

    total_porsi = jumlah(b["porsi"])
    zuper = d.cogs[(d.cogs["kelompok"] == "zuper_food") & d.cogs["sales_date"].isin(buka)]
    a = asal("Σ porsi makanan utama di hari buka ÷ jumlah hari buka",
             [f"{SUMBER_COGS} · Qty, Menu Category, Menu Category Detail"],
             filt + ["Makanan utama = FOOD / FOOD PROMO, kecuali KUDAPAN, TOAST, COMBO MEAL WFA",
                     "Termasuk porsi Rp0 di dalam paket"], int(len(b)), keluar_hari,
             [f"Zuper Food tidak dihitung ({format_angka(jumlah(zuper['qty']))} porsi), sesuai pemisahan kelompok.",
              "Pesanan katering ikut terhitung; lihat rincian ukuran rombongan."])
    v = bagi(total_porsi, hb)
    kartu["orang_makan_per_hari"] = nilai(v, "desimal", a, peringatan=pr) if v is not None else tidak_diketahui("tidak ada hari buka", a)
    a = asal("Σ porsi makanan utama ÷ jumlah bill", [f"{SUMBER_COGS} · Qty", f"{SUMBER_BILL} · Sales Number"], filt, len(b))
    v = bagi(total_porsi, len(b))
    kartu["porsi_per_bill"] = nilai(v, "desimal", a, peringatan=pr) if v is not None else tidak_diketahui("tidak ada bill", a)

    # --- jendela waktu × hari kerja/akhir pekan --------------------------------
    n_kerja = sum(1 for t in d.hari_buka if t.weekday() < 5)
    n_libur = hb - n_kerja
    urutan = [j["nama"] for j in P.JENDELA_WAKTU] + ["Di luar jendela", "Jam tidak tercatat"]
    ket = {j["nama"]: j["berlaku"] for j in P.JENDELA_WAKTU}
    jendela = []
    for nama in urutan:
        g = b[b["jendela"] == nama]
        if nama in ("Di luar jendela", "Jam tidak tercatat") and not len(g):
            continue
        k, w = int((~g["akhir_pekan"]).sum()), int(g["akhir_pekan"].sum())
        j = next((x for x in P.JENDELA_WAKTU if x["nama"] == nama), None)
        jendela.append({
            "jendela": nama, "jam": f"{j['dari']:02d}:00–{j['sampai']:02d}:59" if j else "",
            "keterangan": ket.get(nama),
            "bill_hari_kerja": k, "bill_akhir_pekan": w,
            "per_hari_kerja": format_angka(bagi(k, n_kerja), 1) if n_kerja else "—",
            "per_hari_akhir_pekan": format_angka(bagi(w, n_libur), 1) if n_libur else "—",
            "porsi_bill": format_angka(persen(len(g), len(b)), 1) + "%" if len(b) else "—",
        })

    # --- per hari dalam seminggu ------------------------------------------------
    per_hari = []
    for i, nama in enumerate(NAMA_HARI):
        hari_i = [t for t in d.hari_buka if t.weekday() == i]
        g = b[b["sales_date"].map(lambda t: t.weekday() == i)]
        per_hari.append({"hari": nama, "hari_buka": len(hari_i), "bill": len(g),
                         "rata_per_hari": format_angka(bagi(len(g), len(hari_i)), 1) if hari_i else "—"})

    # --- per channel ------------------------------------------------------------
    channel = []
    for ch, g in b.groupby("visit_purpose", dropna=False):
        channel.append({"channel": ch or "(kosong)", "bill": len(g),
                        "per_hari": format_angka(bagi(len(g), hb), 1),
                        "porsi": format_angka(persen(len(g), len(b)), 1) + "%"})
    channel.sort(key=lambda r: -r["bill"])

    # --- ukuran rombongan -------------------------------------------------------
    def ember(p):
        p = int(p)
        return "4+" if p >= 4 else str(p)
    b["ember"] = b["porsi"].map(ember)
    rombongan = []
    for e in ["0", "1", "2", "3", "4+"]:
        n = int((b["ember"] == e).sum())
        rombongan.append({"porsi": e, "bill": n, "persen": format_angka(persen(n, len(b)), 1) + "%" if len(b) else "—"})
    besar = b[b["porsi"] >= P.AMBANG_PORSI_KATERING]
    catatan_rombongan = [
        "Ukuran rombongan = jumlah porsi makanan utama di satu bill.",
        "Bill 0 porsi = hanya minuman/kudapan/kemasan, atau pesanan Zuper Food saja.",
    ]
    if len(besar):
        catatan_rombongan.append(
            f"{len(besar)} bill berisi ≥{P.AMBANG_PORSI_KATERING} porsi (kemungkinan katering/pesanan besar), "
            f"total {format_angka(jumlah(besar['porsi']))} porsi: " +
            ", ".join(f"{tgl(t)} {format_angka(p)} porsi" for t, p in zip(besar["sales_date"], besar["porsi"])))

    harian_porsi = []
    for t in d.hari:
        if t in buka:
            g = b[b["sales_date"] == t]
            harian_porsi.append({"tanggal": t.isoformat(), "bill": len(g), "porsi": str(jumlah(g["porsi"]))})
        else:
            harian_porsi.append({"tanggal": t.isoformat(), "bill": None, "porsi": None})

    return {"tersedia": True, "kartu": kartu, "jendela": jendela,
            "hari_kerja": n_kerja, "hari_akhir_pekan": n_libur, "per_hari": per_hari,
            "channel": channel, "rombongan": rombongan, "catatan_rombongan": catatan_rombongan,
            "harian": harian_porsi,
            "catatan": [CATATAN_PAX,
                        "Lama layanan/antrean tidak bisa diukur dari data ESB (bill dibuka dan ditutup di kasir).",
                        "Akhir pekan = Sabtu & Minggu. Hari libur nasional ditandai di grafik harian."]}


def banding(cur: DataRentang, prev: DataRentang, label: str) -> dict:
    """Foot traffic selalu dibandingkan per hari buka (ukuran harian)."""
    if not cur.ada_data:
        return {"label": label, "tersedia": False, "alasan": "periode ini belum ada data"}
    if not prev.ada_data:
        return {"label": label, "tersedia": False,
                "alasan": f"belum ada data {prev.cabang} untuk {prev.awal:%d-%m-%Y} s/d {prev.akhir:%d-%m-%Y}"}
    from app.hitung.overview import _selisih_teks
    a, b = hitung(cur)["kartu"], hitung(prev)["kartu"]
    baris = []
    for k, label_k in (("bill_per_hari", "Bill per hari buka"), ("orang_makan_per_hari", "Perkiraan orang makan per hari"),
                       ("porsi_per_bill", "Porsi makanan utama per bill")):
        if a[k]["nilai"] is None or b[k]["nilai"] is None:
            baris.append({"metrik": label_k, "sekarang": a[k]["teks"], "sebelumnya": b[k]["teks"],
                          "selisih": {"teks": "—", "persen": "—", "arah": "tetap"}})
            continue
        x, y = Decimal(a[k]["nilai"]), Decimal(b[k]["nilai"])
        baris.append({"metrik": label_k, "sekarang": format_angka(x, 1), "sebelumnya": format_angka(y, 1),
                      "selisih": _selisih_teks(x, y, "desimal")})
    return {"label": label, "tersedia": True, "per_hari": True, "baris": baris,
            "catatan": "Dibandingkan per hari buka, jadi minggu parsial tetap sebanding."}
