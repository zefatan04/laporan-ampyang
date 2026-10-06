"use strict";
// Fungsi bersama: dipakai aplikasi dan file HTML ekspor (yang tidak punya app.js).

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
