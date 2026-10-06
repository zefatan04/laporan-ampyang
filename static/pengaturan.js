"use strict";
/* global api, esc */

const LABEL_KATEGORI = {
  non_fnb_kategori: "Non-F&B (Menu Category)", makanan_kategori: "Makanan (Menu Category)",
  kudapan_detail: "Kudapan (Detail)", toast_detail: "Toast (Detail)", paket_detail: "Paket (Detail)",
  minuman_kategori: "Minuman (Menu Category)", minuman_kemasan_kategori: "Minuman kemasan (Menu Category)",
  addon_kategori: "Add-on & kemasan (Menu Category)", zuper_food_kategori: "Zuper Food (Menu Category)",
};

async function muatPengaturan() {
  const s = await api("/api/pengaturan");
  document.getElementById("isi-libur").value = s.hari_libur.map((x) => `${x.tanggal} ${x.nama}`).join("\n");
  document.getElementById("isi-ramadan").value = s.ramadan.map((x) => `${x.awal} ${x.akhir}`).join("\n");
  document.getElementById("isi-libur-ok").checked = !!s.hari_libur_terverifikasi;
  document.getElementById("isi-target").value = Object.entries(s.target_omzet)
    .map(([k, v]) => `${k.replace("|", " ")} ${v}`).join("\n");
  document.getElementById("isi-suhu").value = Object.entries(s.suhu_per_menu).map(([m, v]) => `${m} = ${v}`).join("\n");
  document.getElementById("isi-kategori").innerHTML = Object.entries(s.kategori).map(([k, v]) =>
    `<label>${esc(LABEL_KATEGORI[k] || k)}<input data-kat="${esc(k)}" value="${esc(v.join(", "))}"></label>`).join("");
}

const baris = (id) => document.getElementById(id).value.split("\n").map((x) => x.trim()).filter(Boolean);

async function kirim(kunci, nilai) {
  await api(`/api/pengaturan/${kunci}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nilai }) });
}

const PENYIMPAN = {
  async libur() {
    const libur = baris("isi-libur").map((x) => {
      const m = x.match(/^(\d{4}-\d{2}-\d{2})\s+(.+)$/);
      if (!m) throw new Error(`Baris hari libur tidak sesuai format: "${x}"`);
      return { tanggal: m[1], nama: m[2] };
    });
    const ramadan = baris("isi-ramadan").map((x) => {
      const m = x.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})$/);
      if (!m) throw new Error(`Baris Ramadan tidak sesuai format: "${x}"`);
      return { awal: m[1], akhir: m[2] };
    });
    await kirim("hari_libur", libur);
    await kirim("ramadan", ramadan);
    await kirim("hari_libur_terverifikasi", document.getElementById("isi-libur-ok").checked);
  },
  async target() {
    const t = {};
    baris("isi-target").forEach((x) => {
      const m = x.match(/^(Rungkut|Mawar)\s+(\d{4}-\d{2})\s+([\d.]+)$/);
      if (!m) throw new Error(`Baris target tidak sesuai format: "${x}"`);
      t[`${m[1]}|${m[2]}`] = Number(m[3].replace(/\./g, ""));
    });
    await kirim("target_omzet", t);
  },
  async kategori() {
    const k = {};
    document.querySelectorAll("[data-kat]").forEach((el) => {
      k[el.dataset.kat] = el.value.split(",").map((x) => x.trim()).filter(Boolean);
    });
    await kirim("kategori", k);
  },
  async suhu() {
    const s = {};
    baris("isi-suhu").forEach((x) => {
      const m = x.match(/^(.+?)\s*=\s*(panas|dingin)$/i);
      if (!m) throw new Error(`Baris tidak sesuai format "Nama menu = panas/dingin": "${x}"`);
      s[m[1].trim()] = m[2].toLowerCase();
    });
    await kirim("suhu_per_menu", s);
  },
};

document.getElementById("hal-pengaturan").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-simpan]");
  if (!b) return;
  const hasil = b.parentElement.querySelector(".hasil");
  b.disabled = true;
  try {
    await PENYIMPAN[b.dataset.simpan]();
    hasil.innerHTML = `<span class="naik">Tersimpan.</span>`;
  } catch (err) {
    hasil.innerHTML = `<span class="turun">${esc(err.message)}</span>`;
  } finally {
    b.disabled = false;
  }
});

window.bukaPengaturan = muatPengaturan;
if (location.hash.startsWith("#pengaturan")) muatPengaturan();
