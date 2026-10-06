"use strict";

// Semua teks dari file unggahan (nama menu, nama file) lewat esc() sebelum
// masuk ke HTML.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const tgl = (iso) => {
  if (!iso) return "-";
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return `${d} ${BULAN[m - 1]} ${y}`;
};
const LABEL_STATUS = {
  lulus: "Lulus", gagal: "Gagal", peringatan: "Perlu dibaca", tidak_bisa: "Tidak bisa dicek",
  lengkap: "Lengkap", sebagian: "Sebagian", tidak_ada: "Tidak ada",
};
const lencana = (s) => `<span class="lencana ${esc(s)}">${esc(LABEL_STATUS[s] || s)}</span>`;

async function api(url, opsi = {}) {
  const r = await fetch(url, opsi);
  let isi = null;
  try { isi = await r.json(); } catch { /* bukan JSON */ }
  if (!r.ok) throw new Error((isi && isi.detail) || `Permintaan gagal (${r.status})`);
  return isi;
}

function tabel(baris) {
  if (!baris || !baris.length) return "";
  const kolom = [...new Set(baris.flatMap((r) => Object.keys(r)))];
  const angka = (v) => /^[−-]?Rp|^[−-]?[\d.]+(,\d+)?$/.test(String(v));
  return `<div class="gulir"><table><thead><tr>${kolom.map((k) => `<th>${esc(k)}</th>`).join("")}</tr></thead>
    <tbody>${baris.map((r) => `<tr>${kolom.map((k) =>
      `<td class="${angka(r[k] ?? "") ? "angka" : ""}">${esc(r[k] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

// ------------------------------------------------------------------ navigasi
const HAL = ["upload", "riwayat", "dashboard", "pengaturan"];
function buka() {
  const [hal, query] = (location.hash.slice(1) || "upload").split("?");
  const aktif = HAL.includes(hal) ? hal : "upload";
  HAL.forEach((h) => { document.getElementById(`hal-${h}`).hidden = h !== aktif; });
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("aktif", a.dataset.hal === aktif));
  if (aktif === "riwayat") muatRiwayat();
  if (aktif === "dashboard" && window.bukaDashboard) window.bukaDashboard(query);
  if (aktif === "pengaturan" && window.bukaPengaturan) window.bukaPengaturan();
  if (aktif === "upload" && query) {
    const p = new URLSearchParams(query);
    const f = document.getElementById("form-unggah");
    if (p.get("awal")) f.awal.value = p.get("awal");
    if (p.get("akhir")) f.akhir.value = p.get("akhir");
  }
}
window.addEventListener("hashchange", buka);

// ------------------------------------------------------------------ upload
const form = document.getElementById("form-unggah");
const zona = document.getElementById("zona");
const inputFile = document.getElementById("input-file");
const hasilEl = document.getElementById("hasil-validasi");

(function isiMingguLalu() {
  // Bawaan: minggu penuh terakhir (Senin–Minggu).
  const h = new Date();
  const senin = new Date(h);
  senin.setDate(h.getDate() - ((h.getDay() + 6) % 7) - 7);
  const minggu = new Date(senin);
  minggu.setDate(senin.getDate() + 6);
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  form.awal.value = iso(senin);
  form.akhir.value = iso(minggu);
})();

function tampilkanDaftarFile() {
  const n = inputFile.files.length;
  document.getElementById("daftar-file").textContent =
    n ? [...inputFile.files].map((f) => f.name).join(" · ") : "Belum ada file dipilih.";
}
inputFile.addEventListener("change", tampilkanDaftarFile);
["dragenter", "dragover"].forEach((e) => zona.addEventListener(e, (ev) => { ev.preventDefault(); zona.classList.add("seret"); }));
["dragleave", "drop"].forEach((e) => zona.addEventListener(e, (ev) => { ev.preventDefault(); zona.classList.remove("seret"); }));
zona.addEventListener("drop", (ev) => { inputFile.files = ev.dataTransfer.files; tampilkanDaftarFile(); });

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!inputFile.files.length) { hasilEl.innerHTML = `<div class="pesan galat">Pilih file dulu.</div>`; return; }
  const tombol = document.getElementById("tombol-periksa");
  tombol.disabled = true;
  tombol.textContent = "Memeriksa…";
  hasilEl.innerHTML = "";
  try {
    const hasil = await api("/api/unggah", { method: "POST", body: new FormData(form) });
    tampilkanValidasi(hasil);
  } catch (e) {
    hasilEl.innerHTML = `<div class="pesan galat">${esc(e.message)}</div>`;
  } finally {
    tombol.disabled = false;
    tombol.textContent = "Periksa file";
  }
});

function tampilkanValidasi(h) {
  const pengenalan = h.file.map((f) => ({
    "File": f.nama,
    "Dikenali sebagai": f.jenis || "TIDAK DIKENALI",
    "Cabang": (f.cabang || []).join(", ") || "-",
    "Periode": f.periode ? `${tgl(f.periode[0])} – ${tgl(f.periode[1])}` : "-",
    "Baris data": f.diolah ? f.baris.toLocaleString("id-ID") : "belum diolah di versi ini",
  }));

  const kartuCek = h.cek.map((c) => `
    <div class="kartu cek ${esc(c.status)}">
      <div class="cek-judul">${lencana(c.status)} <span>${esc(c.nomor)}. ${esc(c.nama)}</span>
        ${c.file ? `<span class="cek-file">${esc(c.file)}</span>` : ""}</div>
      <p>${esc(c.ringkasan)}</p>
      ${c.rincian.length ? `<details ${c.status === "gagal" ? "open" : ""}><summary>Rincian (${c.rincian.length} baris)</summary>${tabel(c.rincian)}</details>` : ""}
    </div>`).join("");

  let kesimpulan;
  if (h.terblokir) {
    kesimpulan = `<div class="pesan galat">Data <b>tidak bisa disimpan</b>: file wajib tidak lengkap/tidak terbaca, atau cabang/periode di file tidak sesuai. Perbaiki lalu periksa ulang.</div>`;
  } else {
    const tumpang = h.tumpang_tindih.length ? `
      <label class="centang"><input type="checkbox" id="cek-ganti">
        <span>Ganti data yang sudah tersimpan: ${h.tumpang_tindih.map((p) =>
          `${esc(p.cabang)} ${esc(p.jenis)} ${tgl(p.awal)} – ${tgl(p.akhir)}`).join("; ")}</span></label>` : "";
    const konfirmasi = h.butuh_konfirmasi ? `
      <label class="centang"><input type="checkbox" id="cek-paksa">
        <span><b>Simpan walau tidak cocok.</b> Semua angka yang terdampak akan diberi peringatan merah di dashboard.</span></label>` : "";
    kesimpulan = `
      <div class="kartu">
        ${h.butuh_konfirmasi ? `<div class="pesan galat">Rekonsiliasi tidak cocok (lihat cek 2/3).</div>` : `<div class="pesan sukses">Validasi selesai. Baca hasilnya di atas, lalu simpan.</div>`}
        ${tumpang}${konfirmasi}
        <div class="aksi"><button class="tombol utama" id="tombol-simpan">Simpan</button></div>
        <div id="hasil-simpan"></div>
      </div>`;
  }

  hasilEl.innerHTML = `
    <h2>File yang dikenali</h2>
    <div class="kartu">${tabel(pengenalan)}</div>
    <h2>Laporan validasi</h2>
    ${kartuCek}
    ${kesimpulan}`;

  const tombolSimpan = document.getElementById("tombol-simpan");
  if (!tombolSimpan) return;
  const ganti = document.getElementById("cek-ganti");
  const paksa = document.getElementById("cek-paksa");
  const perbarui = () => {
    tombolSimpan.disabled = (ganti && !ganti.checked) || (paksa && !paksa.checked);
  };
  [ganti, paksa].forEach((el) => el && el.addEventListener("change", perbarui));
  perbarui();
  tombolSimpan.addEventListener("click", async () => {
    tombolSimpan.disabled = true;
    const out = document.getElementById("hasil-simpan");
    try {
      await api("/api/simpan", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: h.token, ganti: !!(ganti && ganti.checked), simpan_walau_tidak_cocok: !!(paksa && paksa.checked) }),
      });
      out.innerHTML = `<div class="pesan sukses">Tersimpan. <a href="#riwayat">Lihat riwayat data</a>.</div>`;
      form.reset();
      tampilkanDaftarFile();
    } catch (e) {
      out.innerHTML = `<div class="pesan galat">${esc(e.message)}</div>`;
      perbarui();
    }
  });
}

// ------------------------------------------------------------------ riwayat
const NAMA_JENIS = { bill: "Bill", cogs: "COGS" };

async function muatRiwayat() {
  const elM = document.getElementById("riwayat-minggu");
  const elP = document.getElementById("riwayat-periode");
  let r;
  try { r = await api("/api/riwayat"); } catch (e) {
    elM.innerHTML = `<div class="pesan galat">${esc(e.message)}</div>`;
    return;
  }
  if (!r.periode.length) {
    elM.innerHTML = `<div class="kartu kosong">Belum ada data tersimpan. <a href="#upload">Upload data ESB</a>.</div>`;
    elP.innerHTML = "";
    return;
  }
  const kolom = r.cabang.flatMap((c) => ["bill", "cogs"].map((j) => [c, j]));
  elM.innerHTML = `<div class="kartu"><div class="gulir"><table class="tabel-minggu tumpuk">
    <thead><tr><th>Minggu</th>${kolom.map(([c, j]) => `<th>${esc(c)} · ${NAMA_JENIS[j]}</th>`).join("")}</tr></thead>
    <tbody>${r.minggu.map((m) => `<tr><th>${tgl(m.senin)} – ${tgl(m.minggu)}</th>${kolom.map(([c, j]) => {
      const s = m.sel[`${c}|${j}`];
      return `<td data-label="${esc(c)} · ${NAMA_JENIS[j]}">${lencana(s.status)}<span class="ket">${esc(s.keterangan)}</span></td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div></div>`;

  // Satu baris per unggahan per cabang (Bill + COGS selalu berpasangan).
  const grup = new Map();
  r.periode.forEach((p) => {
    const k = `${p.unggahan_id}|${p.cabang}`;
    if (!grup.has(k)) grup.set(k, { ...p, baris: {} });
    grup.get(k).baris[p.jenis] = p.jumlah_baris;
  });
  elP.innerHTML = `<div class="kartu"><div class="gulir"><table class="tumpuk"><thead><tr>
      <th>Cabang · Periode</th><th class="angka">Baris Bill</th><th class="angka">Baris COGS</th>
      <th>Catatan</th><th>Diunggah</th><th>Tindakan</th></tr></thead><tbody>
    ${[...grup.values()].map((g) => `<tr>
      <th>${esc(g.cabang)} · ${tgl(g.awal)} – ${tgl(g.akhir)}</th>
      <td class="angka" data-label="Baris Bill">${(g.baris.bill ?? 0).toLocaleString("id-ID")}</td>
      <td class="angka" data-label="Baris COGS">${(g.baris.cogs ?? 0).toLocaleString("id-ID")}</td>
      <td data-label="Catatan">${[g.rekonsiliasi_gagal ? "rekonsiliasi tidak cocok" : "",
             g.hari_parsial ? `hari parsial ${tgl(g.hari_parsial)}` : "",
             g.hari_tutup.length ? `${g.hari_tutup.length} hari tutup` : ""].filter(Boolean).map(esc).join(" · ") || "-"}</td>
      <td data-label="Diunggah">${esc(String(g.waktu).slice(0, 16).replace("T", " "))}</td>
      <td><div class="aksi" style="margin:0">
        <a class="tombol" href="#upload?awal=${esc(g.awal)}&akhir=${esc(g.akhir)}">Unggah ulang</a>
        <button class="tombol bahaya" data-hapus="${esc(g.unggahan_id)}|${esc(g.cabang)}">Hapus</button></div></td>
    </tr>`).join("")}</tbody></table></div></div>`;

  elP.querySelectorAll("[data-hapus]").forEach((b) => b.addEventListener("click", async () => {
    const [id, cabang] = b.dataset.hapus.split("|");
    if (!confirm(`Hapus data ${cabang} periode ini (Bill dan COGS)? Tindakan ini tidak bisa dibatalkan.`)) return;
    try {
      await api(`/api/periode/${encodeURIComponent(id)}/${encodeURIComponent(cabang)}`, { method: "DELETE" });
      muatRiwayat();
    } catch (e) { alert(e.message); }
  }));
}

buka();
