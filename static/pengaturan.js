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
  document.getElementById("isi-menu-baru").value = s.menu_baru.map((x) => `${x.nama} | ${x.mulai} | ${x.tab}`).join("\n");
  document.getElementById("isi-promo").value = s.promo.map((p) =>
    [p.nama, p.mulai, p.selesai, p.cabang, p.promotion_esb.join("; "), p.menu_promo.join("; ")].join(" | ")).join("\n");
  document.getElementById("isi-internal").value = s.promotion_internal.join("; ");
  document.getElementById("isi-ambang").value = s.ambang_netral_persen;
  document.getElementById("isi-kampanye").value = s.kampanye.map((k) =>
    [k.nama, k.mulai, k.selesai, k.cabang, k.anggaran, k.akun, k.platform, k.tujuan, k.menu_promo.join("; ")].join(" | ")).join("\n");
  document.getElementById("isi-konten").value = s.konten.map((k) => [k.tanggal, k.akun, k.format, k.topik].join(" | ")).join("\n");
  document.getElementById("isi-ig-manual").value = s.ig_manual.map((x) =>
    `${x.akun} | ${x.senin} | ${Object.entries(x.nilai).map(([m, v]) => `${m}=${v}`).join(" ; ")}`).join("\n");
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
  async promo() {
    const daftar = baris("isi-promo").map((x) => {
      const b = x.split("|").map((y) => y.trim());
      while (b.length < 6) b.push("");
      if (b.length > 6 || !b[0] || !/^\d{4}-\d{2}-\d{2}$/.test(b[1]) || !/^\d{4}-\d{2}-\d{2}$/.test(b[2])
          || !["Rungkut", "Mawar", "keduanya"].includes(b[3])) {
        throw new Error(`Baris promo tidak sesuai format: "${x}"`);
      }
      const pisah = (v) => v.split(";").map((y) => y.trim()).filter(Boolean);
      return { nama: b[0], mulai: b[1], selesai: b[2], cabang: b[3], promotion_esb: pisah(b[4]), menu_promo: pisah(b[5]) };
    });
    await kirim("promo", daftar);
    await kirim("promotion_internal", document.getElementById("isi-internal").value.split(";").map((y) => y.trim()).filter(Boolean));
    await kirim("ambang_netral_persen", Number(document.getElementById("isi-ambang").value));
  },
  async menuBaru() {
    const m = baris("isi-menu-baru").map((x) => {
      const b = x.split("|").map((y) => y.trim());
      if (b.length !== 3 || !/^\d{4}-\d{2}-\d{2}$/.test(b[1]) || !["makanan", "kudapan", "minuman"].includes(b[2])) {
        throw new Error(`Baris tidak sesuai format "Nama | YYYY-MM-DD | tab": "${x}"`);
      }
      return { nama: b[0], mulai: b[1], tab: b[2] };
    });
    await kirim("menu_baru", m);
  },
  async kampanye() {
    const daftar = baris("isi-kampanye").map((x) => {
      const b = x.split("|").map((y) => y.trim());
      while (b.length < 9) b.push("");
      if (b.length > 9 || !b[0] || !/^\d{4}-\d{2}-\d{2}$/.test(b[1]) || !/^\d{4}-\d{2}-\d{2}$/.test(b[2])
          || !["Rungkut", "Mawar", "keduanya"].includes(b[3]) || !/^\d*$/.test(b[4]) || !["Brand", "Rungkut", "Mawar"].includes(b[5])) {
        throw new Error(`Baris kampanye tidak sesuai format (anggaran tanpa titik, akun Brand/Rungkut/Mawar): "${x}"`);
      }
      return { nama: b[0], mulai: b[1], selesai: b[2], cabang: b[3], anggaran: b[4], akun: b[5], platform: b[6], tujuan: b[7],
               menu_promo: b[8].split(";").map((y) => y.trim()).filter(Boolean) };
    });
    await kirim("kampanye", daftar);
  },
  async konten() {
    const daftar = baris("isi-konten").map((x) => {
      const b = x.split("|").map((y) => y.trim());
      while (b.length < 4) b.push("");
      if (b.length > 4 || !/^\d{4}-\d{2}-\d{2}$/.test(b[0]) || !["Brand", "Rungkut", "Mawar"].includes(b[1])) {
        throw new Error(`Baris konten tidak sesuai format "YYYY-MM-DD | akun | format | topik": "${x}"`);
      }
      return { tanggal: b[0], akun: b[1], format: b[2], topik: b[3] };
    });
    await kirim("konten", daftar);
  },
  async igManual() {
    const daftar = baris("isi-ig-manual").map((x) => {
      const b = x.split("|").map((y) => y.trim());
      if (b.length !== 3 || !["Brand", "Rungkut", "Mawar"].includes(b[0]) || !/^\d{4}-\d{2}-\d{2}$/.test(b[1])) {
        throw new Error(`Baris tidak sesuai format "akun | Senin YYYY-MM-DD | metrik=angka ; …": "${x}"`);
      }
      const nilai = {};
      b[2].split(";").map((y) => y.trim()).filter(Boolean).forEach((p) => {
        const m = p.match(/^(tayangan|jangkauan|interaksi|kunjungan|klik|pengikut)\s*=\s*(\d+)$/);
        if (!m) throw new Error(`"${p}" harus metrik=angka tanpa titik (metrik: tayangan, jangkauan, interaksi, kunjungan, klik, pengikut).`);
        nilai[m[1]] = m[2];
      });
      return { akun: b[0], senin: b[1], nilai };
    });
    await kirim("ig_manual", daftar);
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
