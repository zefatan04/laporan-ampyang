"""Tab Performa Sosial Media & Campaign/Konten.

Bagian:
1. Per akun Instagram yang relevan untuk cabang (akun cabang itu + akun
   Brand): tayangan, jangkauan, interaksi, kunjungan profil, klik tautan,
   pengikut baru; harian dan vs periode sebelumnya.
2. Kampanye dari Pengaturan yang menyasar cabang ini: tanggal iklan
   terdeteksi (klik tautan > 0) vs tanggal isian, metrik IG vs pembanding,
   biaya per klik / 1.000 jangkauan / pengikut, tambahan bill di cabang
   sasaran vs pembanding, biaya iklan per bill tambahan (rentang dibebankan
   penuh ke satu cabang vs dibagi ke semua cabang sasaran), korelasi klik
   harian vs tambahan bill harian.
3. Daftar konten (Pengaturan) di periode ini.

Aturan kejujuran angka:
- Data IG opsional. Tanpa data: "Tidak diketahui — data Instagram periode ini
  tidak diunggah". Bagian kampanye yang hanya butuh ESB tetap dihitung.
- Tanggal tanpa baris di dalam rentang unggahan = "tidak tercatat", bukan 0.
  Total yang kehilangan hari diberi label "batas bawah".
- Jangkauan harian tidak dijumlah menjadi jangkauan periode (akun yang sama
  bisa terhitung di beberapa hari). Kartu memakai rata-rata per hari.
- Input manual mingguan diberi label "input manual". Analisa yang butuh
  data harian tidak dihitung dari input manual.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

from app import db_ig, pengaturan
from app.angka import format_angka, format_rupiah
from app.hitung.data import DataRentang, muat
from app.hitung.minggu import label_tanggal, ringkas_tanggal
from app.hitung.nilai import asal, bagi, nilai, tidak_diketahui
from app.hitung.overview import SUMBER_BILL, _selisih_teks, tgl
from app.hitung.promo import MINGGU_PEMBANDING, _libur, _ringkas_banding, banding_pembanding, harian as harian_esb
from app.parser.instagram import METRIK, PER_KODE

SUMBER_IG = "CSV Instagram Insights (Meta Business Suite)"
JENDELA_DETEKSI = 14  # hari sebelum/sesudah kampanye yang diperiksa untuk klik tautan


def akun_cabang(cabang: str) -> list[str]:
    return [cabang, "Brand"]


def _hari(a: date, z: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((z - a).days + 1)]


def _senin(t: date) -> date:
    return t - timedelta(days=t.weekday())


# ---------------------------------------------------------------------------
# 1. Per akun
# ---------------------------------------------------------------------------

class DataIG:
    """Nilai harian satu akun untuk satu rentang + input manual mingguan."""

    def __init__(self, con, akun: str, awal: date, akhir: date, senin_periode: list[date]):
        self.akun, self.awal, self.akhir = akun, awal, akhir
        self.hari = _hari(awal, akhir)
        self.nilai, self.cak = db_ig.harian(con, akun, awal, akhir)
        self.senin_periode = senin_periode
        semua = {(x["akun"], x["senin"]): x["nilai"] for x in pengaturan.ambil(con, "ig_manual")}
        self.manual = {s: semua[(akun, s.isoformat())] for s in senin_periode if (akun, s.isoformat()) in semua}

    @property
    def ada_harian(self) -> bool:
        return any(self.nilai.get(m.kode) for m in METRIK) or any(self.cak.get(m.kode) for m in METRIK)

    @property
    def ada(self) -> bool:
        return self.ada_harian or bool(self.manual)

    def status(self, kode: str):
        v, c = self.nilai.get(kode, {}), self.cak.get(kode, set())
        ada = [t for t in self.hari if t in v]
        tak_tercatat = [t for t in self.hari if t in c and t not in v]
        tak_unggah = [t for t in self.hari if t not in c]
        return v, ada, tak_tercatat, tak_unggah


def kartu_metrik(x: DataIG, kode: str) -> dict:
    m = PER_KODE[kode]
    v, ada, tt, tu = x.status(kode)
    rentang = f"{x.awal:%d-%m-%Y} s/d {x.akhir:%d-%m-%Y}"
    sumber = [f"{SUMBER_IG} · akun {x.akun} · file '{m.judul}' · kolom Primary"]
    keluar = [{"alasan": "Hari tidak tercatat (ada di rentang unggahan, tanpa baris)", "jumlah": len(tt)},
              {"alasan": "Hari tidak diunggah", "jumlah": len(tu)}]
    if ada:
        peringatan = []
        if tt:
            alasan = ("Instagram tidak menulis hari dengan 0 pengikut baru; tidak dianggap 0" if kode == "pengikut"
                      else "baris hari itu tidak ada di file")
            peringatan.append(f"{len(tt)} hari tidak tercatat ({ringkas_tanggal(tt)}): {alasan}.")
        if tu:
            peringatan.append(f"{len(tu)} hari belum diunggah ({ringkas_tanggal(tu)}).")
        if kode == "jangkauan":
            r = bagi(sum(v[t] for t in ada), len(ada))
            n = nilai(r, "angka", asal("Σ jangkauan harian ÷ jumlah hari yang ada datanya", sumber, [rentang], len(ada), keluar,
                                       ["Jangkauan harian tidak dijumlah: akun yang sama bisa terjangkau di beberapa hari, "
                                        "jadi jumlahnya bukan jumlah akun unik. Jangkauan unik mingguan/bulanan ada di aplikasi Instagram."]),
                      peringatan=peringatan)
            n["label"] = f"rata-rata per hari dari {len(ada)} hari"
            return {"judul": "Jangkauan (rata-rata per hari)", "n": n, "lengkap": not (tt or tu), "angka": r, "per_hari": True}
        total = Decimal(sum(v[t] for t in ada))
        n = nilai(total, "angka", asal(f"Σ {m.nama.lower()} harian", sumber, [rentang], len(ada), keluar), peringatan=peringatan)
        if tt or tu:
            n["teks"] += " (batas bawah)"
        n["label"] = f"{len(ada)} dari {len(x.hari)} hari tercatat"
        return {"judul": m.nama, "n": n, "lengkap": not (tt or tu), "angka": total}

    # tanpa data harian -> input manual mingguan
    minggu = [s for s in x.senin_periode if kode in x.manual.get(s, {})]
    if minggu:
        if kode == "jangkauan" and len(x.senin_periode) > 1:
            return {"judul": "Jangkauan", "n": tidak_diketahui(
                "hanya ada input manual mingguan, dan jangkauan mingguan tidak bisa dijumlah antar minggu (akun yang sama terhitung berulang)"),
                    "lengkap": False, "angka": None}
        total = Decimal(sum(x.manual[s][kode] for s in minggu))
        kurang = [s for s in x.senin_periode if s not in minggu]
        catatan = ["Angka disalin user dari aplikasi Instagram / Meta Business Suite (Pengaturan → Input manual Instagram)."]
        if len(x.senin_periode) > 1:
            catatan.append("Bulan memakai minggu Senin–Minggu yang Seninnya di bulan ini, jadi bukan bulan kalender persis.")
        n = nilai(total, "angka", asal("Σ input manual mingguan",
                                       [f"Pengaturan · input manual Instagram akun {x.akun}"],
                                       [f"Minggu mulai {', '.join(f'{s:%d-%m-%Y}' for s in minggu)}"], len(minggu), [], catatan),
                  peringatan=[f"Belum ada input minggu {', '.join(f'{s:%d-%m}' for s in kurang)}."] if kurang else [])
        n["teks"] += " (batas bawah)" if kurang else ""
        n["label"] = "input manual" + (" · jangkauan mingguan (akun unik)" if kode == "jangkauan" else "")
        return {"judul": m.nama if kode != "jangkauan" else "Jangkauan mingguan", "n": n, "lengkap": not kurang,
                "angka": total, "manual": True}
    return {"judul": m.nama if kode != "jangkauan" else "Jangkauan (rata-rata per hari)",
            "n": tidak_diketahui(f"data Instagram akun {x.akun} periode ini tidak diunggah"), "lengkap": False, "angka": None}


def _banding_akun(x: DataIG, p: DataIG, label: str) -> dict:
    if not x.ada:
        return {"label": label, "tersedia": False, "alasan": f"data Instagram akun {x.akun} periode ini tidak diunggah"}
    if not p.ada:
        return {"label": label, "tersedia": False,
                "alasan": f"data Instagram akun {x.akun} {p.awal:%d-%m-%Y} s/d {p.akhir:%d-%m-%Y} tidak diunggah"}
    baris = []
    for m in METRIK:
        a, b = kartu_metrik(x, m.kode), kartu_metrik(p, m.kode)
        if not (a["lengkap"] and b["lengkap"]) or a["angka"] is None or b["angka"] is None \
                or a.get("per_hari") != b.get("per_hari") or a.get("manual") != b.get("manual"):
            sebab = ("salah satu periode tidak lengkap" if (a["angka"] is not None and b["angka"] is not None)
                     else "tidak ada data")
            baris.append({"metrik": a["judul"], "sekarang": a["n"]["teks"], "sebelumnya": b["n"]["teks"],
                          "selisih": {"teks": "—", "persen": sebab, "arah": "tetap"}})
            continue
        baris.append({"metrik": a["judul"], "sekarang": a["n"]["teks"], "sebelumnya": b["n"]["teks"],
                      "selisih": _selisih_teks(Decimal(a["angka"]), Decimal(b["angka"]), "angka")})
    return {"label": label, "tersedia": True, "baris": baris,
            "catatan": "Selisih hanya dihitung bila kedua periode lengkap dan dari jenis data yang sama (harian vs harian, manual vs manual)."}


def _harian_akun(x: DataIG, libur: dict, konten: list[dict]) -> list[dict]:
    hasil = []
    for t in x.hari:
        r = {"tanggal": t.isoformat(), "label": tgl(t), "libur": libur.get(t.isoformat()),
             "konten": [f"{k['format']}: {k['topik']}".strip(": ") for k in konten if k["tanggal"] == t.isoformat()]}
        for m in METRIK:
            v, c = x.nilai.get(m.kode, {}), x.cak.get(m.kode, set())
            r[m.kode] = v.get(t)
            r[m.kode + "_status"] = "ada" if t in v else ("tidak tercatat" if t in c else "tidak diunggah")
        hasil.append(r)
    return hasil


def _manual_vs_harian(con, akun: str, senin_periode: list[date]) -> list[dict]:
    hasil = []
    for x in pengaturan.ambil(con, "ig_manual"):
        s = date.fromisoformat(x["senin"])
        if x["akun"] != akun or s not in senin_periode:
            continue
        d = DataIG(con, akun, s, s + timedelta(days=6), [s])
        for kode, v in x["nilai"].items():
            h, ada, tt, tu = d.status(kode)
            if not ada or tt or tu:
                continue
            total = sum(h[t] for t in ada)
            hasil.append({"Minggu": label_tanggal(s, s + timedelta(days=6)), "Metrik": PER_KODE[kode].nama,
                          "Input manual": format_angka(v), "Σ CSV harian": format_angka(total),
                          "Selisih": format_angka(total - v),
                          "Catatan": ("wajar beda: jangkauan mingguan = akun unik, Σ harian menghitung akun berulang"
                                      if kode == "jangkauan" else "dashboard memakai CSV harian")})
    return hasil


def per_akun(con, akun: str, awal: date, akhir: date, senin_periode: list[date],
             prev: tuple[date, date, list[date]], label_prev: str, libur: dict, konten: list[dict],
             kampanye_akun: list[dict]) -> dict:
    x = DataIG(con, akun, awal, akhir, senin_periode)
    p = DataIG(con, akun, prev[0], prev[1], prev[2])
    hasil = {"akun": akun, "ada": x.ada, "ada_harian": x.ada_harian, "manual": bool(x.manual) and not x.ada_harian,
             "kartu": [kartu_metrik(x, m.kode) for m in METRIK],
             "banding": _banding_akun(x, p, label_prev)}
    for k in hasil["kartu"]:
        for kunci in ("angka", "lengkap", "per_hari", "manual"):
            k.pop(kunci, None)
    if x.ada_harian:
        hasil["harian"] = _harian_akun(x, libur, [k for k in konten if k["akun"] == akun])
        klik = x.nilai.get("klik", {})
        positif = [t for t in x.hari if klik.get(t, 0) > 0]
        terdaftar = {t for k in kampanye_akun for t in _hari(date.fromisoformat(k["mulai"]), date.fromisoformat(k["selesai"]))}
        tanpa = [t for t in positif if t not in terdaftar]
        hasil["klik_positif"] = {
            "hari": ringkas_tanggal(positif) if positif else None,
            "tanpa_kampanye": ringkas_tanggal(tanpa) if tanpa else None,
            "cakupan": len([t for t in x.hari if t in x.cak.get("klik", set())]),
        }
    else:
        hasil["harian_alasan"] = ("butuh data harian (CSV); input manual mingguan tidak punya rincian per hari"
                                  if x.manual else f"data Instagram akun {akun} periode ini tidak diunggah")
    hasil["manual_vs_harian"] = _manual_vs_harian(con, akun, senin_periode)
    return hasil


# ---------------------------------------------------------------------------
# 2. Kampanye
# ---------------------------------------------------------------------------

def _korelasi(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx == 0 or syy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / math.sqrt(sxx * syy)


def _rentang_teks(vs: list[Decimal], f) -> str:
    vs = sorted(vs)
    return f(vs[0]) if len(vs) == 1 or vs[0] == vs[-1] else f"{f(vs[0])} s/d {f(vs[-1])}"


def _deteksi(k: dict, x: DataIG, mulai: date, selesai: date) -> dict:
    klik, cak = x.nilai.get("klik", {}), x.cak.get("klik", set())
    hari_k = _hari(mulai, selesai)
    if not any(t in cak for t in hari_k):
        alasan = ("butuh data harian (CSV klik tautan); input manual mingguan tidak bisa menunjukkan tanggal iklan"
                  if x.manual else f"CSV Klik tautan akun {k['akun']} untuk tanggal kampanye belum diunggah")
        return {"tersedia": False, "alasan": alasan}
    jendela = _hari(mulai - timedelta(days=JENDELA_DETEKSI), selesai + timedelta(days=JENDELA_DETEKSI))
    terdeteksi = [t for t in jendela if klik.get(t, 0) > 0]
    luar = [t for t in terdeteksi if not mulai <= t <= selesai]
    diam = [t for t in hari_k if t in cak and klik.get(t, 0) == 0]
    tanpa = [t for t in hari_k if t not in cak]
    jendela_tanpa = [t for t in jendela if t not in cak and not mulai <= t <= selesai]
    pra = [t for t in _hari(mulai - timedelta(days=7 * MINGGU_PEMBANDING), mulai - timedelta(days=JENDELA_DETEKSI + 1))
           if klik.get(t, 0) > 0]
    peringatan = []
    if luar:
        peringatan.append(f"Ada klik tautan di luar tanggal isian: {ringkas_tanggal(luar)}. Periksa tanggal kampanye di Pengaturan.")
    if diam:
        peringatan.append(f"Tidak ada klik tautan di sebagian tanggal isian: {ringkas_tanggal(diam)}. Iklan mungkin belum/tidak berjalan di hari itu.")
    catatan = [f"Diperiksa {JENDELA_DETEKSI} hari sebelum s/d {JENDELA_DETEKSI} hari sesudah tanggal isian."]
    if tanpa:
        catatan.append(f"Data klik belum diunggah untuk tanggal kampanye {ringkas_tanggal(tanpa)}.")
    if jendela_tanpa:
        catatan.append(f"Data klik belum diunggah di sekitar kampanye: {ringkas_tanggal(jendela_tanpa)}; iklan di tanggal itu tidak bisa dideteksi.")
    if pra:
        catatan.append(f"Klik tautan juga ada sebelum kampanye ({ringkas_tanggal(pra)}). Klik bisa berasal dari tautan di bio, "
                       "jadi klik > 0 bukan penanda iklan yang bersih untuk akun ini.")
    return {"tersedia": True, "terdeteksi": ringkas_tanggal(terdeteksi) if terdeteksi else "tidak ada hari dengan klik > 0",
            "isian": label_tanggal(mulai, selesai), "cocok": not (luar or diam), "peringatan": peringatan, "catatan": catatan}


def _hari_kampanye_lain(semua: list[dict], k: dict, kunci: str, nilai_kunci: set[str]) -> set[date]:
    hasil = set()
    for j in semua:
        if j is k or j[kunci] not in nilai_kunci:
            continue
        hasil |= set(_hari(date.fromisoformat(j["mulai"]), date.fromisoformat(j["selesai"])))
    return hasil


def _metrik_ig(x: DataIG, mulai: date, selesai: date, keluar: set[date]) -> dict:
    if not x.ada_harian:
        return {"tersedia": False, "alasan": "butuh data harian (CSV)" if x.manual else
                f"data Instagram akun {x.akun} di sekitar kampanye tidak diunggah"}
    baris = []
    for m in METRIK:
        v = x.nilai.get(m.kode, {})
        harian = {t: {"v": Decimal(n)} for t, n in v.items() if t not in keluar}
        akt = {t: h for t, h in harian.items() if mulai <= t <= selesai}
        pa = {t: h for t, h in harian.items() if t < mulai}
        ps = {t: h for t, h in harian.items() if t > selesai}
        if not akt:
            baris.append({"Metrik": m.nama, "Selama kampanye": "Tidak diketahui — tidak ada data harian",
                          "A: 4 minggu sebelum": "—", "B: 4 minggu sebelum + 4 minggu sesudah": "—"})
            continue
        a = banding_pembanding(akt, pa, "v") if pa else None
        b = banding_pembanding(akt, {**pa, **ps}, "v") if ps else None
        nama = m.nama + (" (Σ harian)" if m.kode == "jangkauan" else "")
        ra = _ringkas_banding(nama, a, "angka") if a else {"teks": "Tidak diketahui — data 4 minggu sebelum tidak diunggah"}
        rb = _ringkas_banding(nama, b, "angka") if b else {"teks": "Tidak diketahui — data 4 minggu sesudah tidak diunggah"}
        if b and not pa:
            rb["teks"] = "hanya dari 4 minggu sesudah (data sebelum tidak diunggah): " + rb["teks"]
        hari_akt = len([t for t in _hari(mulai, selesai) if t not in keluar])
        baris.append({"Metrik": nama, "Selama kampanye": f"{format_angka(sum(h['v'] for h in akt.values()))} ({len(akt)}/{hari_akt} hari)",
                      "A: 4 minggu sebelum": ra["teks"], "B: 4 minggu sebelum + 4 minggu sesudah": rb["teks"]})
    libur_k = [t for t in _hari(mulai, selesai) if t in keluar]
    return {"tersedia": True, "baris": baris,
            "catatan": ([f"Hari libur di dalam kampanye dikeluarkan dari kolom 'Selama kampanye': {ringkas_tanggal(libur_k)}."] if libur_k else [])
            + ["Pembanding = rata-rata hari yang sama dalam seminggu; hanya hari kampanye yang punya pembanding hari yang sama ikut dihitung.",
                        "Hari libur/Ramadan dan hari kampanye lain akun ini tidak dipakai sebagai pembanding.",
                        "Pengikut: hari tidak tercatat tidak ikut, baik di kampanye maupun di pembanding."]}


def _biaya(k: dict, x: DataIG, mulai: date, selesai: date) -> list[dict]:
    ang = Decimal(k["anggaran"]) if k.get("anggaran") else None
    hari_k = _hari(mulai, selesai)
    hasil = []
    for kode, judul, per in (("klik", "Biaya per klik tautan", 1), ("jangkauan", "Biaya per 1.000 jangkauan", 1000),
                             ("pengikut", "Biaya per pengikut baru", 1)):
        v, c = x.nilai.get(kode, {}), x.cak.get(kode, set())
        ada = [t for t in hari_k if t in v]
        sumber = [f"Pengaturan · anggaran kampanye '{k['nama']}'", f"{SUMBER_IG} · akun {k['akun']} · {PER_KODE[kode].judul}"]
        if ang is None:
            hasil.append({"judul": judul, "n": tidak_diketahui("anggaran kampanye belum diisi di Pengaturan")})
            continue
        if not ada:
            hasil.append({"judul": judul, "n": tidak_diketahui(
                "butuh data harian (CSV)" if x.manual else f"data {PER_KODE[kode].nama.lower()} selama kampanye tidak diunggah")})
            continue
        total = sum(v[t] for t in ada)
        if total == 0:
            hasil.append({"judul": judul, "n": tidak_diketahui(f"{PER_KODE[kode].nama.lower()} selama kampanye = 0")})
            continue
        kurang = [t for t in hari_k if t not in v]
        catatan = ["Semua klik/jangkauan/pengikut selama kampanye ikut dihitung, termasuk yang organik (bukan dari iklan)."]
        if kode == "jangkauan":
            catatan.append("Jangkauan = Σ jangkauan harian. Akun yang sama bisa terhitung di beberapa hari, jadi biaya per 1.000 "
                           "akun unik sebenarnya lebih tinggi. Angka akun unik ada di Meta Ads Manager.")
        n = nilai(ang / total * per, "rupiah",
                  asal(f"Anggaran ÷ Σ {PER_KODE[kode].nama.lower()} harian selama kampanye" + (" × 1.000" if per == 1000 else ""),
                       sumber, [f"{tgl(mulai)} – {tgl(selesai)}"], len(ada),
                       [{"alasan": "Hari kampanye tanpa data", "jumlah": len(kurang)}], catatan),
                  peringatan=[f"{len(kurang)} hari tanpa data ({ringkas_tanggal(kurang)}); biaya ini batas atas."] if kurang else [])
        if kurang:
            n["teks"] += " (batas atas)"
        n["label"] = f"dari {format_angka(total)} {PER_KODE[kode].nama.lower()}" + (" (Σ harian)" if kode == "jangkauan" else "")
        hasil.append({"judul": judul, "n": n})
    return hasil


def _tambahan_bill(con, c: str, mulai: date, selesai: date, keluar: set[date]) -> dict:
    awal_a = mulai - timedelta(days=7 * MINGGU_PEMBANDING)
    akhir_b = selesai + timedelta(days=7 * MINGGU_PEMBANDING)
    dk, da, ds = muat(con, c, mulai, selesai), muat(con, c, awal_a, mulai - timedelta(days=1)), muat(con, c, selesai + timedelta(days=1), akhir_b)
    saring = lambda h: {t: v for t, v in h.items() if t not in keluar}
    hk, ha, hs = saring(harian_esb(dk, set())), saring(harian_esb(da, set())), saring(harian_esb(ds, set()))
    hasil = {"cabang": c, "hari_kampanye": len(_hari(mulai, selesai)), "hari_data": len(dk.tercakup),
             "pembanding_a": f"{tgl(da.awal)} – {tgl(da.akhir)}: {len(ha)} hari buka", "pembanding_b":
             f"+ {tgl(ds.awal)} – {tgl(ds.akhir)}: {len(hs)} hari buka" if hs else "belum ada data 4 minggu sesudah"}
    if not hk:
        hasil.update(tersedia=False, alasan=f"data ESB {c} selama kampanye belum diunggah")
        return hasil
    if not ha:
        hasil.update(tersedia=False, alasan=f"data ESB {c} 4 minggu sebelum kampanye ({tgl(da.awal)} – {tgl(da.akhir)}) belum diunggah")
        return hasil
    a = banding_pembanding(hk, ha, "bill")
    b = banding_pembanding(hk, {**ha, **hs}, "bill") if hs else None
    if not a["hari"]:
        hasil.update(tersedia=False, alasan="tidak ada hari kampanye yang punya pembanding hari yang sama")
        return hasil
    tambah = [a["aktual"] - a["harapan"]] + ([b["aktual"] - b["harapan"]] if b and b["hari"] else [])
    # tambahan harian (pembanding A) untuk korelasi
    per_hari = {}
    for t, v in ha.items():
        per_hari.setdefault(t.weekday(), []).append(v["bill"])
    harian = {t: v["bill"] - sum(per_hari[t.weekday()]) / len(per_hari[t.weekday()])
              for t, v in hk.items() if t.weekday() in per_hari}
    hasil.update(tersedia=True, tambahan=tambah, hari_dibanding=len(a["hari"]), harian=harian,
                 aktual=a["aktual"], harapan_a=a["harapan"], harapan_b=b["harapan"] if b and b["hari"] else None,
                 lengkap=len(a["hari"]) == hasil["hari_kampanye"])
    return hasil


def evaluasi_kampanye(con, k: dict, semua: list[dict], libur: set[date]) -> dict:
    mulai, selesai = date.fromisoformat(k["mulai"]), date.fromisoformat(k["selesai"])
    sasaran = ["Rungkut", "Mawar"] if k["cabang"] == "keduanya" else [k["cabang"]]
    ang = Decimal(k["anggaran"]) if k.get("anggaran") else None
    awal_j = mulai - timedelta(days=7 * MINGGU_PEMBANDING)
    akhir_j = selesai + timedelta(days=7 * MINGGU_PEMBANDING)
    x = DataIG(con, k["akun"], awal_j, akhir_j,
               sorted({_senin(t) for t in _hari(mulai, selesai)}))
    # Libur keluar dari hari kampanye dan pembanding; hari kampanye lain hanya keluar dari pembanding.
    hari_k = set(_hari(mulai, selesai))
    lain_akun = _hari_kampanye_lain(semua, k, "akun", {k["akun"]})
    hasil = {"nama": k["nama"], "periode": f"{tgl(mulai)} – {tgl(selesai)}", "cabang": k["cabang"], "akun": k["akun"],
             "anggaran": format_rupiah(ang) if ang is not None else "belum diisi",
             "platform": k.get("platform") or "-", "tujuan": k.get("tujuan") or "-", "menu_promo": k.get("menu_promo", []),
             "deteksi": _deteksi(k, x, mulai, selesai),
             "metrik_ig": _metrik_ig(x, mulai, selesai, libur | (lain_akun - hari_k)),
             "biaya_ig": _biaya(k, x, mulai, selesai)}

    # tambahan bill per cabang sasaran
    per_cab = []
    for c in sasaran:
        lain_cab = _hari_kampanye_lain(semua, k, "cabang", {c, "keduanya"})
        per_cab.append(_tambahan_bill(con, c, mulai, selesai, libur | (lain_cab - hari_k)))
    tabel_bill, biaya_bill, korelasi = [], [], []
    for r in per_cab:
        if not r["tersedia"]:
            tabel_bill.append({"Cabang": r["cabang"], "Tambahan bill vs pembanding": f"Tidak diketahui — {r['alasan']}",
                               "Hari dibandingkan": "—", "Pembanding": r["pembanding_a"]})
            continue
        tabel_bill.append({
            "Cabang": r["cabang"],
            "Tambahan bill vs pembanding": _rentang_teks(r["tambahan"], lambda v: format_angka(v, 1)) + " bill"
                                           + ("" if r["lengkap"] else f" (dari {r['hari_dibanding']} hari)"),
            "Hari dibandingkan": f"{r['hari_dibanding']}/{r['hari_kampanye']}",
            "Pembanding": f"A {r['pembanding_a']}; B {r['pembanding_b']}"})
    ada = [r for r in per_cab if r["tersedia"]]
    batas_bawah = len(ada) < len(sasaran)
    if ang is None:
        biaya_bill.append({"Cara bagi": "—", "Biaya iklan per bill tambahan": "Tidak diketahui — anggaran kampanye belum diisi di Pengaturan"})
    else:
        def per_bill(tambahan: list[Decimal]) -> str:
            pos = [t for t in tambahan if t > 0]
            if not pos:
                return f"Tidak diketahui — tidak ada tambahan bill di atas pembanding ({_rentang_teks(tambahan, lambda v: format_angka(v, 1))})"
            teks = _rentang_teks([ang / t for t in pos], format_rupiah)
            if len(pos) < len(tambahan):
                teks += " (salah satu pembanding tidak menunjukkan tambahan bill; sisi pesimis = tidak terbayar)"
            return teks
        for r in per_cab:
            if r["tersedia"]:
                biaya_bill.append({"Cara bagi": f"Dibebankan penuh ke {r['cabang']}", "Biaya iklan per bill tambahan": per_bill(r["tambahan"])})
            else:
                biaya_bill.append({"Cara bagi": f"Dibebankan penuh ke {r['cabang']}",
                                   "Biaya iklan per bill tambahan": f"Tidak diketahui — {r['alasan']}"})
        if len(sasaran) > 1 and ada:
            # Jumlahkan per sisi pembanding (A dengan A, B dengan B) supaya tidak tercampur.
            n_sisi = min(len(r["tambahan"]) for r in ada)
            gab = [sum((r["tambahan"][i] for r in ada), Decimal(0)) for i in range(n_sisi)]
            teks = per_bill(gab)
            if batas_bawah and not teks.startswith("Tidak diketahui"):
                teks += " — konversi batas bawah: data " + ", ".join(r["cabang"] for r in per_cab if not r["tersedia"]) + " tidak ada"
            biaya_bill.append({"Cara bagi": "Dibagi ke semua cabang sasaran (anggaran ÷ Σ tambahan bill)",
                               "Biaya iklan per bill tambahan": teks})
        elif len(sasaran) > 1:
            biaya_bill.append({"Cara bagi": "Dibagi ke semua cabang sasaran (anggaran ÷ Σ tambahan bill)",
                               "Biaya iklan per bill tambahan": "Tidak diketahui — data ESB kedua cabang selama kampanye belum ada"})
    # korelasi klik harian vs tambahan bill harian
    klik = x.nilai.get("klik", {})
    for r in per_cab:
        if not r["tersedia"]:
            korelasi.append({"Cabang": r["cabang"], "Korelasi": f"Tidak diketahui — {r['alasan']}"})
            continue
        if not x.ada_harian:
            korelasi.append({"Cabang": r["cabang"], "Korelasi": "Tidak diketahui — butuh data klik tautan harian (CSV)"})
            continue
        pasangan = [(float(klik[t]), float(v)) for t, v in sorted(r["harian"].items()) if t in klik]
        if len(pasangan) < 7:
            korelasi.append({"Cabang": r["cabang"], "Korelasi": f"Tidak diketahui — hanya {len(pasangan)} hari punya klik dan tambahan bill (butuh minimal 7)"})
            continue
        kr = _korelasi([a for a, _ in pasangan], [b for _, b in pasangan])
        korelasi.append({"Cabang": r["cabang"], "Korelasi": "Tidak diketahui — klik atau tambahan bill tidak bervariasi" if kr is None
                         else f"r = {format_angka(Decimal(str(round(kr, 2))), 2)} dari {len(pasangan)} hari"})
    hasil.update(tambahan_bill=tabel_bill, biaya_bill=biaya_bill, korelasi=korelasi, batas_bawah=batas_bawah,
                 catatan=["Tambahan bill = Σ bill hari kampanye − Σ pembanding (rata-rata hari yang sama dalam seminggu). "
                          "A = 4 minggu sebelum, B = 4 minggu sebelum + 4 minggu sesudah. Sisi pesimis dipakai untuk kesimpulan.",
                          "Hari libur/Ramadan, hari tutup, hari parsial, dan hari kampanye lain untuk cabang ini tidak dipakai sebagai pembanding.",
                          "Dibebankan penuh = seluruh anggaran dibagi tambahan bill satu cabang. Dibagi = anggaran dibagi jumlah tambahan bill semua cabang sasaran.",
                          "Korelasi klik harian vs tambahan bill harian (pembanding A) hanya menunjukkan apakah keduanya naik-turun bersama, bukan bukti sebab-akibat.",
                          f"Sumber bill: {SUMBER_BILL}."]
                 + (["Kampanye menyasar dua cabang tapi data salah satu cabang tidak ada: angka konversi gabungan adalah batas bawah."]
                    if batas_bawah and len(sasaran) > 1 else []))
    return hasil


def kampanye(con, d: DataRentang) -> dict:
    semua = pengaturan.ambil(con, "kampanye")
    libur = _libur(con)
    tampil = []
    for k in semua:
        if k["cabang"] not in (d.cabang, "keduanya"):
            continue
        mulai, selesai = date.fromisoformat(k["mulai"]), date.fromisoformat(k["selesai"])
        if mulai <= d.akhir and selesai >= d.awal - timedelta(days=7 * MINGGU_PEMBANDING):
            tampil.append(evaluasi_kampanye(con, k, semua, libur))
    return {"jumlah_terdaftar": len(semua), "daftar": tampil}


# ---------------------------------------------------------------------------
# Rakit
# ---------------------------------------------------------------------------

def hitung(con, d: DataRentang, senin_periode: list[date], prev: tuple[date, date, list[date]],
           label_prev: str, libur: dict) -> dict:
    konten = pengaturan.ambil(con, "konten")
    semua_k = pengaturan.ambil(con, "kampanye")
    akun = []
    for a in akun_cabang(d.cabang):
        akun.append(per_akun(con, a, d.awal, d.akhir, senin_periode, prev, label_prev, libur, konten,
                             [k for k in semua_k if k["akun"] == a]))
    konten_periode = [{"Tanggal": tgl(date.fromisoformat(k["tanggal"])), "Akun": k["akun"], "Format": k["format"] or "-",
                       "Topik": k["topik"] or "-"} for k in konten
                      if k["akun"] in akun_cabang(d.cabang) and d.awal.isoformat() <= k["tanggal"] <= d.akhir.isoformat()]
    return {
        "akun": akun,
        "kampanye": kampanye(con, d),
        "konten": konten_periode,
        "jumlah_konten": len(konten),
        "catatan": [
            "Akun Brand dipakai bersama kedua cabang, jadi angkanya sama di tampilan Rungkut dan Mawar.",
            "Export Meta Ads Manager belum diolah: belum ada contoh file. Kirim satu contoh bila tersedia.",
        ],
    }


def kualitas(con, d: DataRentang, senin_periode: list[date]) -> list[dict]:
    hasil = []
    for a in akun_cabang(d.cabang):
        x = DataIG(con, a, d.awal, d.akhir, senin_periode)
        if x.ada_harian:
            penuh = [t for t in x.hari if all(t in x.cak.get(m.kode, set()) for m in METRIK)]
            ket = f"{len(penuh)}/{len(x.hari)} hari ada keenam metrik"
            st = "ada"
        elif x.manual:
            ket, st = f"input manual {len(x.manual)} minggu (tanpa rincian harian)", "input manual"
        else:
            ket, st = "opsional; metrik Instagram tampil 'Tidak diketahui'", "tidak ada"
        hasil.append({"file": f"Instagram Insights akun {a} (opsional)", "status": st, "keterangan": ket})
    return hasil
