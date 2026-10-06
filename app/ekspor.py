"""Ekspor dashboard menjadi SATU file HTML mandiri.

File berisi CSS, Chart.js, data dashboard (JSON), dan script tampilan yang
sama dengan aplikasi, semuanya inline. Bisa dibuka offline dengan
klik dua kali dan dikirim ke atasan; tab dan "Dari mana angka ini?" tetap
berfungsi. Tombol yang butuh server (unggah, buat narasi, pindah periode)
tidak ada di file ekspor.
"""

from __future__ import annotations

import json
from datetime import datetime
from html import escape

from fastapi.encoders import jsonable_encoder

from app.db import AKAR

STATIC = AKAR / "static"
_TAMBAHAN_CSS = """
.ekspor-ket { color: #fbe0d5; font-size: .85rem; margin-left: auto; }
@media print { .kepala { print-color-adjust: exact; -webkit-print-color-adjust: exact; } }
"""


def _skrip(teks: str) -> str:
    # Penutup tag di dalam script inline akan memotong dokumen; diloloskan.
    return teks.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def nama_file(data: dict) -> str:
    p = data["periode"]
    return f"Laporan-Ampyang-{data['cabang']}-{p['awal']}_{p['akhir']}.html"


def html(data: dict) -> str:
    data = jsonable_encoder(data)
    p = data["periode"]
    judul = f"Laporan Ampyang · {data['cabang']} · {p['label']}"
    baca = lambda nama: (STATIC / nama).read_text(encoding="utf-8")
    isi_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    waktu = datetime.now().strftime("%d-%m-%Y %H:%M")
    return f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(judul)}</title>
<style>{baca("app.css")}{_TAMBAHAN_CSS}</style>
</head>
<body>
<header class="kepala">
  <div class="kepala-isi">
    <div class="merek">Kedai Ampyang <span>Laporan</span></div>
    <span class="ekspor-ket">Diekspor {escape(waktu)} · file mandiri, bisa dibuka tanpa aplikasi</span>
  </div>
</header>
<main class="isi">
<section id="hal-dashboard" class="hal">
  <div class="eyebrow" id="dash-minggu"></div>
  <h1 id="dash-judul">{escape(judul)}</h1>
  <p class="sub" id="dash-sub"></p>
  <div id="dash-peringatan"></div>
  <nav class="tab" id="dash-tab" aria-label="Isi dashboard"></nav>
  <div id="dash-isi"></div>
  <div id="dash-kualitas"></div>
</section>
</main>
<dialog id="dialog-asal">
  <div class="dialog-kepala">
    <h2 id="asal-judul">Dari mana angka ini?</h2>
    <button class="tombol" id="asal-tutup" aria-label="Tutup">Tutup</button>
  </div>
  <div id="asal-isi"></div>
</dialog>
<script>{_skrip(baca("vendor/chart.umd.js"))}</script>
<script>window.DATA_EKSPOR = {isi_json};</script>
<script>{_skrip(baca("dasar.js"))}</script>
<script>{_skrip(baca("dashboard.js"))}</script>
</body>
</html>
"""
