"""Tes browser (Playwright + Chromium) atas data contoh: semua halaman dan kedelapan tab,
kedua cabang, layar laptop dan HP (390px), file HTML ekspor, dan alur tempel jawaban Claude.

Syarat lulus: 0 error di konsol browser, tanpa scroll horizontal, tombol
"Dari mana angka ini?" membuka penjelasan.

Dilewati otomatis bila Playwright/Chromium belum terpasang
(pasang: `pip install playwright` lalu `python -m playwright install chromium`).
"""
import os
import socket
import threading
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from tests.fixtures import data_contoh  # noqa: E402

TAB = ["overview", "makanan", "kudapan", "minuman", "foot", "promo", "membership", "sosmed"]
LEBAR = [1280, 390]


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import uvicorn
    d = tmp_path_factory.mktemp("browser")
    data_contoh.isi(d / "c.duckdb", d / "tmp")
    lama = os.environ.get("AMPYANG_DB")
    os.environ["AMPYANG_DB"] = str(d / "c.duckdb")
    port = _port()
    srv = uvicorn.Server(uvicorn.Config("app.web:app", host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", d
    srv.should_exit = True
    t.join(5)
    if lama is None:
        os.environ.pop("AMPYANG_DB", None)
    else:
        os.environ["AMPYANG_DB"] = lama


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        jalur = os.environ.get("AMPYANG_CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
        try:
            b = p.chromium.launch(executable_path=jalur) if jalur else p.chromium.launch()
        except Exception as e:  # browser belum dipasang
            pytest.skip(f"Chromium tidak tersedia: {e}")
        yield b
        b.close()


class Halaman:
    def __init__(self, browser, lebar):
        self.page = browser.new_page(viewport={"width": lebar, "height": 900}, accept_downloads=True)
        self.lebar = lebar
        self.galat = []
        self.page.on("console", lambda m: m.type == "error" and self.galat.append(m.text))
        self.page.on("pageerror", lambda e: self.galat.append(str(e)))

    def cek_layout(self, konteks):
        lebar_doc = self.page.evaluate("document.documentElement.scrollWidth")
        assert lebar_doc <= self.lebar, f"{konteks}: scroll horizontal ({lebar_doc}px > {self.lebar}px)"
        assert not self.galat, f"{konteks}: error konsol {self.galat}"

    def tunggu_dashboard(self):
        self.page.wait_for_function(
            "document.querySelector('#dash-tab button') && !document.querySelector('#dash-isi').textContent.includes('Menghitung')")


@pytest.mark.parametrize("lebar", LEBAR)
@pytest.mark.parametrize("cabang,bulan,pilih", [("Rungkut", "2026-09", "bulan"), ("Mawar", "2026-09", "M4"),
                                                ("Rungkut", "2026-10", "bulan")])
def test_semua_tab(server, browser, lebar, cabang, bulan, pilih):
    url, _ = server
    h = Halaman(browser, lebar)
    h.page.goto(f"{url}/#dashboard?cabang={cabang}&bulan={bulan}&pilih={pilih}&tab=overview")
    h.tunggu_dashboard()
    for tab in TAB:
        h.page.click(f"#dash-tab button[data-tab={tab}]")
        assert h.page.get_attribute(f"#dash-tab button[data-tab={tab}]", "aria-selected") == "true"
        assert "Tidak diketahui — undefined" not in h.page.inner_text("#dash-isi")
        tombol = h.page.locator("#dash-isi .tautan-asal")
        if tombol.count():
            tombol.first.scroll_into_view_if_needed()
            tombol.first.click()
            assert h.page.is_visible("#dialog-asal") and "Rumus" in h.page.inner_text("#asal-isi")
            h.page.click("#asal-tutup")
        h.cek_layout(f"{cabang} {bulan} {pilih} tab {tab} @{lebar}px")
    h.page.close()


@pytest.mark.parametrize("lebar", LEBAR)
def test_halaman_lain(server, browser, lebar):
    url, _ = server
    h = Halaman(browser, lebar)
    for hal, penanda in (("upload", "#form-unggah"), ("riwayat", "#riwayat-minggu table"),
                         ("riwayat", "#riwayat-ig table"), ("pengaturan", "#isi-kampanye")):
        h.page.goto(f"{url}/#{hal}")
        h.page.wait_for_selector(penanda)
        h.page.wait_for_timeout(200)
        h.cek_layout(f"halaman {hal} @{lebar}px")
    h.page.wait_for_function("document.getElementById('isi-kampanye').value.includes('Iklan Tahu Walik')")
    h.page.close()


def test_tempel_jawaban_claude(server, browser):
    url, _ = server
    h = Halaman(browser, 1280)
    h.page.goto(f"{url}/#dashboard?cabang=Mawar&bulan=2026-09&pilih=bulan&tab=minuman")
    h.tunggu_dashboard()
    with h.page.expect_download() as unduh:
        h.page.click("[data-paket]")
    assert unduh.value.suggested_filename.startswith("Paket-Claude-Ampyang-Mawar-2026-09-01")
    h.page.click("[data-tempel]")
    h.page.fill("#tempel-isi", "=== minuman ===\nFAKTA: Es Jeruk tercatat sebagai minuman dingin.\nFAKTA: Omzet minuman Rp999.999.999.")
    h.page.click("#tempel-kirim")
    h.page.wait_for_selector("#tempel-hasil .pesan.sukses")
    h.page.click("#tempel-tutup")
    h.page.wait_for_selector(".narasi .lencana.lulus")
    teks = h.page.inner_text(".narasi")
    assert "Es Jeruk tercatat sebagai minuman dingin." in teks and "1 kalimat dibuang" in teks
    h.cek_layout("tempel jawaban")
    h.page.close()


@pytest.mark.parametrize("lebar", LEBAR)
def test_ekspor_html_mandiri(server, browser, lebar):
    url, d = server
    h = Halaman(browser, lebar)
    h.page.goto(f"{url}/#dashboard?cabang=Rungkut&bulan=2026-10&pilih=bulan&tab=overview")
    h.tunggu_dashboard()
    with h.page.expect_download() as unduh:
        h.page.click("#dash-unduh")
    berkas = d / f"ekspor-{lebar}.html"
    unduh.value.save_as(berkas)
    h.galat.clear()
    # Dibuka dari disk, tanpa server.
    h.page.goto(berkas.as_uri())
    h.page.wait_for_selector("#dash-tab button")
    assert h.page.locator("[data-tempel], [data-paket], #dash-unduh").count() == 0  # tombol server tidak ikut
    assert h.page.is_visible(".narasi .lencana.lulus")
    for tab in TAB:
        h.page.click(f"#dash-tab button[data-tab={tab}]")
        tombol = h.page.locator("#dash-isi .tautan-asal")
        if tombol.count():
            tombol.first.scroll_into_view_if_needed()
            tombol.first.click()
            assert h.page.is_visible("#dialog-asal")
            h.page.click("#asal-tutup")
        h.cek_layout(f"ekspor tab {tab} @{lebar}px")
    h.page.close()
