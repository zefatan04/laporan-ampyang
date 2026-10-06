"""Narasi temuan per tab lewat Claude API, dengan verifikasi angka otomatis.

Alur:
1. `muatan(data, tab)` menyusun JSON untuk model dari hasil dashboard yang
   SUDAH dihitung Python: hanya angka agregat, nama menu, dan catatan
   kualitas data. Yang tidak dikirim: asal-usul angka, nama kasir, alamat IP,
   jam/nominal transaksi member per baris, nomor bill (lihat `_BUANG`).
2. Model menulis 3–6 temuan (structured output).
3. `verifikasi()` mengambil semua angka dari setiap kalimat dan mencocokkan
   ke angka di JSON (toleransi pembulatan sesuai jumlah digit yang ditulis).
   Kalimat dengan angka yang tidak ditemukan dibuang dan dicatat.
4. Hasil disimpan per cabang + periode + tab beserta sidik data (`versi`).
   Kalau data berubah (unggah ulang, pengaturan diubah), sidiknya beda dan
   narasi ditandai kedaluwarsa, tidak dibuat ulang otomatis.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

log = logging.getLogger("ampyang.narasi")

MODEL = "claude-opus-5-5"
EFFORT = "high"
TAB = {
    "overview": ("overview", "Overview Omzet"),
    "makanan": ("makanan", "Performa Makanan"),
    "kudapan": ("kudapan", "Performa Kudapan"),
    "minuman": ("minuman", "Performa Minuman"),
    "foot": ("foot_traffic", "Foot Traffic"),
    "promo": ("promo", "Performa Promo"),
    "membership": ("membership", "Progress Membership Keluarga Ampyang"),
    "sosmed": ("sosmed", "Performa Sosial Media & Campaign/Konten"),
}
MAKS_BARIS = 40
JENIS = ("fakta", "dugaan", "belum_bisa_disimpulkan", "saran")

SKEMA = """CREATE TABLE IF NOT EXISTS narasi (cabang VARCHAR NOT NULL, awal DATE NOT NULL, akhir DATE NOT NULL,
    tab VARCHAR NOT NULL, versi VARCHAR NOT NULL, temuan JSON NOT NULL, dibuang JSON NOT NULL, model VARCHAR NOT NULL,
    waktu TIMESTAMP NOT NULL, PRIMARY KEY (cabang, awal, akhir, tab));"""


class NarasiGagal(Exception):
    pass


# ---------------------------------------------------------------------------
# Muatan untuk model
# ---------------------------------------------------------------------------

# Kunci yang tidak pernah dikirim: asal-usul (panjang, tidak perlu untuk
# narasi), data orang (kasir, IP), dan rincian per baris transaksi.
_BUANG = {"asal", "IP", "Kasir", "per_kasir", "rincian", "bill_selisih", "Waktu", "Jam", "menu",
          "jendela_waktu", "tombol", "menyusul", "harian_alasan"}
_HITUNG_SAJA = {"tanpa_esb", "ganda"}  # daftar baris diganti jumlahnya


def _bersihkan(x, kunci: str = ""):
    if isinstance(x, dict):
        if {"teks", "status", "asal"} <= set(x):  # Nilai
            r = {"teks": x["teks"]}
            if x.get("label"):
                r["keterangan"] = x["label"]
            if x["status"] != "pasti":
                r["status"] = x["status"]
            if x.get("peringatan"):
                r["peringatan"] = x["peringatan"]
            return r
        hasil = {}
        for k, v in x.items():
            if k in _BUANG:
                continue
            if k in _HITUNG_SAJA and isinstance(v, list):
                hasil[f"jumlah_{k}"] = len(v)
                continue
            hasil[k] = _bersihkan(v, k)
        return hasil
    if isinstance(x, list):
        isi = [_bersihkan(v, kunci) for v in x[:MAKS_BARIS]]
        if len(x) > MAKS_BARIS:
            isi.append(f"(+{len(x) - MAKS_BARIS} baris lain tidak dikirim)")
        return isi
    return x


def muatan(data: dict, tab: str) -> dict:
    kunci, judul = TAB[tab]
    q = data["kualitas"]
    return {
        "tab": judul,
        "cabang": data["cabang"],
        "periode": data["periode"],
        "sebagian_data_disimpan_walau_rekonsiliasi_gagal": data["peringatan_merah"],
        "kualitas_data": _bersihkan({k: q[k] for k in ("file", "hari", "baris_dikeluarkan", "hari_libur_terverifikasi") if k in q}),
        "isi_tab": _bersihkan(data[kunci]),
    }


def versi(m: dict) -> str:
    return hashlib.sha256(json.dumps(m, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Verifikasi angka
# ---------------------------------------------------------------------------

_ANGKA = re.compile(
    r"(?<![\w.,])(?:Rp\s?)?(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"
    r"(?:\s?(%|persen|juta|jt|ribu|rb|miliar)\b|(%))?", re.IGNORECASE)
_KALI = {"juta": 6, "jt": 6, "ribu": 3, "rb": 3, "miliar": 9}


def angka_di_teks(teks: str) -> list[tuple[Decimal, Decimal, str]]:
    """[(nilai, ketelitian, potongan teks)]. Ketelitian = setengah satuan digit terakhir yang ditulis."""
    hasil = []
    for m in _ANGKA.finditer(teks):
        s = m.group(1)
        satuan = (m.group(2) or m.group(3) or "").lower()
        bulat, _, pecahan = s.replace(".", "").partition(",")
        try:
            v = Decimal(f"{bulat}.{pecahan}" if pecahan else bulat)
        except InvalidOperation:
            continue
        pangkat = _KALI.get(satuan, 0)
        v = v.scaleb(pangkat)
        teliti = Decimal(1).scaleb(pangkat - len(pecahan)) / 2
        hasil.append((v, teliti, m.group(0)))
    return hasil


def angka_di_json(x) -> set[Decimal]:
    hasil: set[Decimal] = set()
    if isinstance(x, dict):
        for v in x.values():
            hasil |= angka_di_json(v)
    elif isinstance(x, list):
        for v in x:
            hasil |= angka_di_json(v)
    elif isinstance(x, bool) or x is None:
        pass
    elif isinstance(x, (int, float, Decimal)):
        hasil.add(abs(Decimal(str(x))))
    elif isinstance(x, str):
        hasil |= {abs(v) for v, _, _ in angka_di_teks(x)}
        try:  # angka mentah tanpa format, mis. "277.8292"
            hasil.add(abs(Decimal(x)))
        except InvalidOperation:
            pass
    return hasil


def cocok(v: Decimal, teliti: Decimal, kumpulan: set[Decimal]) -> bool:
    v = abs(v)
    return any(abs(v - a) <= teliti + Decimal("1e-9") for a in kumpulan)


def _kalimat(teks: str) -> list[str]:
    # Titik koma dilarang di gaya tulisan: dipecah jadi dua kalimat.
    teks = re.sub(r";\s*(\w?)", lambda m: ". " + m.group(1).upper(), teks.strip())
    bagian = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", teks)
    return [b[0].upper() + b[1:] if b else b for b in (x.strip() for x in bagian) if b]


def verifikasi(temuan: list[dict], m: dict) -> tuple[list[dict], list[dict]]:
    """Buang kalimat yang memuat angka di luar JSON. Kembalikan (temuan bersih, dibuang)."""
    kumpulan = angka_di_json(m)
    bersih, dibuang = [], []
    for t in temuan:
        simpan = []
        for k in _kalimat(t["teks"]):
            asing = [s for v, teliti, s in angka_di_teks(k) if not cocok(v, teliti, kumpulan)]
            if asing:
                dibuang.append({"kalimat": k, "angka_tidak_ditemukan": asing})
                log.warning("Narasi: kalimat dibuang, angka %s tidak ada di data: %s", asing, k)
            else:
                simpan.append(k)
        if simpan:
            teks = " ".join(simpan)
            awal = {"dugaan": "Dugaan", "saran": "Saran"}.get(t["jenis"])
            if awal and not teks.lower().startswith(awal.lower()):
                teks = f"{awal}: " + teks[0].lower() + teks[1:]  # dugaan & saran selalu berlabel, juga saat teks disalin
            bersih.append({"teks": teks, "jenis": t["jenis"]})
    return bersih, dibuang


# ---------------------------------------------------------------------------
# Panggilan model
# ---------------------------------------------------------------------------

ATURAN = """Aturan keras:
1. Hanya boleh menyebut angka yang ada di JSON, ditulis persis seperti di JSON (format Indonesia, mis. Rp1.234.567, 12,5%). Jangan menghitung angka baru: jangan menjumlah, mengurangi, membagi, membulatkan ke "juta", atau menghitung persen sendiri. Setiap angka di teks diperiksa otomatis ke JSON, dan kalimat dengan angka yang tidak ada di JSON akan dibuang.
2. Angka bertanda "Tidak diketahui", status "tidak_diketahui", atau berlabel "batas bawah"/"batas atas"/"estimasi" harus disebut dengan labelnya, atau tidak disebut sama sekali.
3. Kalau data untuk sebuah kesimpulan tidak cukup, tulis "belum bisa disimpulkan" dan sebut data apa yang kurang.
4. Bedakan fakta dan dugaan. Fakta = langsung terbaca dari angka. Penjelasan kemungkinan sebab = dugaan, dan kalimatnya diawali "Dugaan:".
5. Jangan menyebut sebab-akibat hanya dari dua hal yang terjadi pada waktu yang sama atau dari korelasi.
6. Kalau data Instagram tidak diunggah, katakan begitu dan jangan menyimpulkan apa pun soal media sosial.
7. Kalau JSON menandai sebagian data disimpan walau rekonsiliasi gagal, temuan pertama harus menyebut bahwa angka periode ini bisa salah.
8. Saran (bila ada) adalah tindakan untuk tim marketing, dengan argumen yang bersandar pada angka di JSON. Saran tidak boleh memuat angka baru seperti target atau persentase kenaikan yang tidak ada di JSON.

Gaya:
- Bahasa Indonesia yang wajar dan langsung, seperti ditulis orang yang paham kedai ini.
- Tanpa kalimat pembuka atau penutup basa-basi. Langsung ke isi.
- Satu temuan = satu atau dua kalimat pendek. Pakai titik, jangan titik koma.
- Hindari pola "bukan X, melainkan Y", "bukan hanya X, tetapi juga Y", kata "signifikan", "menariknya", "perlu dicatat", "secara keseluruhan".
- Sebut nama menu, hari, dan tanggal seperti di JSON.
- Urutkan dari temuan yang paling penting untuk keputusan marketing."""

SISTEM = """Kamu menulis temuan untuk laporan mingguan/bulanan tim marketing Kedai Ampyang, kopitiam di Surabaya.
Pembacanya pemilik dan tim marketing. Kamu menerima JSON berisi angka yang sudah dihitung oleh program untuk satu tab dashboard.

Tulis 3 sampai 6 temuan, ditambah paling banyak 2 saran. Jenis: "fakta", "dugaan", "belum_bisa_disimpulkan", atau "saran".

""" + ATURAN

SKEMA_KELUARAN = {
    "type": "object",
    "properties": {
        "temuan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "teks": {"type": "string"},
                    "jenis": {"type": "string", "enum": list(JENIS)},
                },
                "required": ["teks", "jenis"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["temuan"],
    "additionalProperties": False,
}


def aktif() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _klien():
    import anthropic
    return anthropic.Anthropic()


def minta_model(m: dict, klien=None) -> tuple[list[dict], str]:
    """Kirim muatan ke Claude, kembalikan (temuan mentah, model yang menjawab)."""
    import anthropic

    klien = klien or _klien()
    try:
        r = klien.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SISTEM,
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SKEMA_KELUARAN}},
            # Bila model utama menolak, server mengulang di model cadangan yang dipilih Anthropic.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": "Data tab (JSON):\n" + json.dumps(m, ensure_ascii=False, default=str)}],
        )
    except anthropic.AuthenticationError as e:
        raise NarasiGagal("API key Claude ditolak. Periksa ANTHROPIC_API_KEY di file .env.") from e
    except anthropic.RateLimitError as e:
        raise NarasiGagal("Batas pemakaian Claude API tercapai. Coba lagi beberapa menit lagi.") from e
    except anthropic.APIConnectionError as e:
        raise NarasiGagal("Tidak bisa terhubung ke Claude API. Periksa koneksi internet.") from e
    except anthropic.APIStatusError as e:
        raise NarasiGagal(f"Claude API mengembalikan galat {e.status_code}.") from e
    if r.stop_reason == "refusal":
        raise NarasiGagal("Claude menolak membuat narasi untuk data ini.")
    if r.stop_reason == "max_tokens":
        raise NarasiGagal("Jawaban Claude terpotong (batas panjang).")
    teks = next((b.text for b in r.content if b.type == "text"), None)
    if teks is None:
        raise NarasiGagal("Jawaban Claude tidak berisi teks.")
    try:
        temuan = json.loads(teks)["temuan"]
    except (ValueError, KeyError, TypeError) as e:
        raise NarasiGagal("Jawaban Claude tidak sesuai format.") from e
    return [{"teks": str(t["teks"]), "jenis": t["jenis"]} for t in temuan], r.model


# ---------------------------------------------------------------------------
# Simpan & ambil
# ---------------------------------------------------------------------------

def pastikan(con):
    con.execute(SKEMA)


def buat(con, data: dict, tab: str, klien=None) -> dict:
    if tab not in TAB:
        raise NarasiGagal("Tab tidak dikenal.")
    if not aktif() and klien is None:
        raise NarasiGagal("Narasi otomatis tidak aktif: ANTHROPIC_API_KEY belum diisi di file .env.")
    m = muatan(data, tab)
    mentah, model = minta_model(m, klien)
    _simpan(con, data, tab, m, mentah, model)
    return status(con, data)[tab]


def _simpan(con, data: dict, tab: str, m: dict, mentah: list[dict], model: str) -> tuple[list[dict], list[dict]]:
    temuan, dibuang = verifikasi(mentah, m)
    pastikan(con)
    p = data["periode"]
    con.execute("INSERT OR REPLACE INTO narasi VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [data["cabang"], p["awal"], p["akhir"], tab, versi(m), json.dumps(temuan, ensure_ascii=False),
                 json.dumps(dibuang, ensure_ascii=False), model, datetime.now()])
    return temuan, dibuang


# ---------------------------------------------------------------------------
# Jalur manual (tanpa API): paket untuk Claude -> tempel jawaban -> verifikasi
# ---------------------------------------------------------------------------

MODEL_MANUAL = "Claude (ditempel manual)"
LABEL = {"FAKTA": "fakta", "DUGAAN": "dugaan", "BELUM BISA DISIMPULKAN": "belum_bisa_disimpulkan", "SARAN": "saran"}
_BARIS_TAB = re.compile(r"^\W*===\s*([a-z_]+)\s*===\W*$", re.IGNORECASE)
_BARIS_LABEL = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*\**\s*(FAKTA|DUGAAN|BELUM BISA DISIMPULKAN|SARAN)\s*\**\s*:\s*\**\s*(.+)$",
                          re.IGNORECASE)


def paket(data: dict) -> str:
    """Satu file Markdown: instruksi + format jawaban + data semua tab. Diunggah/ditempel user ke Claude."""
    p = data["periode"]
    judul = f"{data['cabang']} · {p['label']} ({p['awal']} s/d {p['akhir']})"
    bagian = [
        f"# Paket analisa Kedai Ampyang — {judul}",
        "",
        "Kamu menulis temuan untuk laporan tim marketing Kedai Ampyang, kopitiam di Surabaya (cabang Rungkut dan Mawar). "
        "Pembacanya pemilik dan tim marketing. Di bawah ada data delapan tab dashboard dalam JSON. Semua angka sudah dihitung "
        "oleh program dari export kasir (ESB), web loyalty, dan Instagram. Jangan menghitung ulang.",
        "",
        "Untuk SETIAP tab, tulis 3 sampai 6 temuan, lalu paling banyak 2 saran tindakan beserta argumennya.",
        "",
        ATURAN,
        "",
        "## Format jawaban (wajib, supaya bisa dicek otomatis)",
        "",
        "Tulis hanya blok berikut, satu blok per tab, dengan kode tab persis seperti di judul data. Setiap baris diawali salah "
        "satu label: FAKTA, DUGAAN, BELUM BISA DISIMPULKAN, atau SARAN. Satu baris = satu temuan. Tanpa teks lain di luar blok.",
        "",
        "```",
        "=== overview ===",
        "FAKTA: ...",
        "DUGAAN: ...",
        "BELUM BISA DISIMPULKAN: ...",
        "SARAN: ...",
        "=== makanan ===",
        "FAKTA: ...",
        "```",
        "",
        "## Data",
    ]
    for tab, (_, nama) in TAB.items():
        bagian += ["", f"### Tab `{tab}` — {nama}", "", "```json",
                   json.dumps(muatan(data, tab), ensure_ascii=False, indent=1, default=str), "```"]
    return "\n".join(bagian) + "\n"


def baca_jawaban(teks: str) -> tuple[dict[str, list[dict]], list[str]]:
    """Jawaban Claude (format === tab === + baris berlabel) -> ({tab: [temuan]}, catatan)."""
    hasil: dict[str, list[dict]] = {}
    catatan, tab = [], None
    for baris in teks.splitlines():
        if not baris.strip() or baris.strip().startswith("```"):
            continue
        m = _BARIS_TAB.match(baris.strip())
        if m:
            kode = m.group(1).lower()
            tab = kode if kode in TAB else None
            if tab is None:
                catatan.append(f"Bagian '{m.group(1)}' bukan kode tab yang dikenal; dilewati.")
            else:
                hasil.setdefault(tab, [])
            continue
        if tab is None:
            continue
        m = _BARIS_LABEL.match(baris)
        if m:
            hasil[tab].append({"teks": m.group(2).strip().strip("*").strip(), "jenis": LABEL[m.group(1).upper()]})
        elif hasil[tab]:  # sambungan baris sebelumnya
            hasil[tab][-1]["teks"] += " " + baris.strip()
        else:
            catatan.append(f"Tab {tab}: baris tanpa label dilewati: \"{baris.strip()[:80]}\"")
    if not hasil:
        raise NarasiGagal("Tidak ada bagian '=== kode tab ===' di jawaban. Pastikan yang ditempel jawaban Claude untuk paket dari aplikasi ini.")
    return hasil, catatan


def simpan_manual(con, data: dict, teks: str) -> dict:
    jawaban, catatan = baca_jawaban(teks)
    ringkas = {}
    for tab, temuan in jawaban.items():
        if not temuan:
            catatan.append(f"Tab {tab}: tidak ada baris berlabel; tab ini tidak diubah.")
            continue
        bersih, dibuang = _simpan(con, data, tab, muatan(data, tab), temuan, MODEL_MANUAL)
        ringkas[tab] = {"temuan": len(bersih), "dibuang": len(dibuang)}
    return {"tab": ringkas, "catatan": catatan}


def status(con, data: dict) -> dict:
    """Narasi tersimpan untuk semua tab periode ini: 'ada', 'kedaluwarsa' (data berubah), atau 'belum'."""
    pastikan(con)
    p = data["periode"]
    rows = con.execute("SELECT tab, versi, temuan, dibuang, model, waktu FROM narasi WHERE cabang = ? AND awal = ? AND akhir = ?",
                       [data["cabang"], p["awal"], p["akhir"]]).fetchall()
    simpan = {r[0]: r for r in rows}
    hasil = {}
    for tab in TAB:
        if tab not in simpan:
            hasil[tab] = {"status": "belum"}
            continue
        _, v, temuan, dibuang, model, waktu = simpan[tab]
        hasil[tab] = {"status": "ada" if v == versi(muatan(data, tab)) else "kedaluwarsa",
                      "temuan": json.loads(temuan), "dibuang": json.loads(dibuang), "model": model,
                      "waktu": waktu.isoformat(timespec="minutes")}
    return hasil
