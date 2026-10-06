"use strict";
/* global Chart, esc, tabel, api, tgl, BULAN */

// Animasi dimatikan supaya screenshot & cetak tidak terpotong.
Chart.defaults.animation = false;
Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
Chart.defaults.color = "#5d5853";

const TERAKOTA = "#b8451f";
const TAB = [
  ["overview", "Overview Omzet"], ["makanan", "Makanan"], ["kudapan", "Kudapan"], ["minuman", "Minuman"],
  ["foot", "Foot Traffic"], ["promo", "Promo"], ["membership", "Membership"], ["sosmed", "Sosmed & Campaign"],
];
const NAMA_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
  "Oktober", "November", "Desember"];

const keadaan = { cabang: "Rungkut", bulan: null, pilih: "bulan", tab: "overview", data: null };
const grafik = [];
const asalTerdaftar = [];

const rp = (v) => (v == null ? "—" : "Rp" + Math.round(Number(v)).toLocaleString("id-ID"));

// ---------------------------------------------------------------- kartu angka
function kartuAngka(judul, n, ket = "") {
  if (!n) return "";
  const i = asalTerdaftar.push({ judul, n }) - 1;
  const tak = n.status === "tidak_diketahui";
  const awas = (n.peringatan || []).map((p) => `<span class="awas">⚠ ${esc(p)}</span>`).join("");
  return `<div class="kartu-angka ${keadaan.data.peringatan_merah ? "merah" : ""}">
    <span class="judul">${esc(judul)}</span>
    <span class="angka-besar ${tak ? "tidak_diketahui" : ""}">${esc(n.teks)}</span>
    ${n.label ? `<span class="ket">${esc(n.label)}</span>` : ""}
    ${ket ? `<span class="ket">${esc(ket)}</span>` : ""}${awas}
    ${n.asal ? `<button class="tautan-asal" data-asal="${i}">Dari mana angka ini?</button>` : ""}
  </div>`;
}

function bukaAsal(i) {
  const { judul, n } = asalTerdaftar[i];
  const a = n.asal;
  const daftar = (xs) => (xs && xs.length ? `<ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "-");
  document.getElementById("asal-judul").textContent = judul;
  document.getElementById("asal-isi").innerHTML = `<dl class="asal">
    <dt>Angka</dt><dd>${esc(n.teks)}</dd>
    <dt>Rumus</dt><dd>${esc(a.rumus)}</dd>
    <dt>Sumber (file &amp; kolom)</dt><dd>${daftar(a.sumber)}</dd>
    <dt>Filter</dt><dd>${daftar(a.filter)}</dd>
    <dt>Jumlah baris dipakai</dt><dd>${a.baris == null ? "-" : Number(a.baris).toLocaleString("id-ID")}</dd>
    <dt>Dikeluarkan</dt><dd>${a.dikeluarkan.length ? `<ul>${a.dikeluarkan.map((d) =>
      `<li>${esc(d.alasan)}: <b>${Number(d.jumlah).toLocaleString("id-ID")}</b></li>`).join("")}</ul>` : "Tidak ada"}</dd>
    ${a.catatan.length ? `<dt>Catatan</dt><dd>${daftar(a.catatan)}</dd>` : ""}
    ${n.peringatan && n.peringatan.length ? `<dt>Peringatan</dt><dd>${daftar(n.peringatan)}</dd>` : ""}
  </dl>`;
  document.getElementById("dialog-asal").showModal();
}
document.getElementById("asal-tutup").addEventListener("click", () => document.getElementById("dialog-asal").close());

const selisih = (s) => `<span class="${esc(s.arah)}">${esc(s.teks)}</span> <span class="${esc(s.arah)}">(${esc(s.persen)})</span>`;

function bagianBanding(b) {
  if (!b) return "";
  if (!b.tersedia) {
    return `<h2>${esc(b.label)}</h2><div class="kartu kosong">Tidak diketahui — ${esc(b.alasan)}.</div>`;
  }
  const dek = b.dekomposisi;
  const dekHtml = !dek ? "" : dek.tersedia ? `
    <h3 class="sub-judul">Dari mana perubahan omzet F&amp;B?</h3>
    <div class="gulir"><table>
      <tr><td>Perubahan omzet bill F&amp;B${b.per_hari ? " per hari buka" : ""}</td><td class="angka">${esc(dek.omzet.sebelumnya)} → ${esc(dek.omzet.sekarang)}</td><td class="angka">${selisih(dek.omzet)}</td></tr>
      <tr><td>…karena jumlah bill<br><span class="ket">${esc(dek.dari_jumlah_bill.keterangan)}</span></td><td></td><td class="angka">${esc(dek.dari_jumlah_bill.teks)}</td></tr>
      <tr><td>…karena rata-rata bill<br><span class="ket">${esc(dek.dari_rata_bill.keterangan)}</span></td><td></td><td class="angka">${esc(dek.dari_rata_bill.teks)}</td></tr>
    </table></div>
    <p class="catatan">${esc(dek.asal.rumus)}</p>` :
    `<p class="catatan">Dekomposisi tidak diketahui — ${esc(dek.alasan)}.</p>`;
  return `<h2>${esc(b.label)}</h2><div class="kartu">
    <div class="gulir"><table><thead><tr><th>Metrik</th><th class="angka">Periode ini</th><th class="angka">Sebelumnya</th><th class="angka">Selisih</th></tr></thead>
    <tbody>${b.baris.map((r) => `<tr><td>${esc(r.metrik)}</td><td class="angka">${esc(r.sekarang)}</td>
      <td class="angka">${esc(r.sebelumnya)}</td><td class="angka">${selisih(r.selisih)}</td></tr>`).join("")}</tbody></table></div>
    <p class="catatan">${esc(b.catatan)}</p>${dekHtml}</div>`;
}

// ---------------------------------------------------------------- grafik
function grafikBatang(id, label, titik, ambil, format) {
  const el = document.getElementById(id);
  if (!el) return;
  const nilai = titik.map(ambil);
  grafik.push(new Chart(el, {
    type: "bar",
    data: {
      labels: titik.map((t) => t.label_pendek),
      datasets: [{ label, data: nilai, backgroundColor: TERAKOTA, borderRadius: 4, maxBarThickness: 28 }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (it) => titik[it[0].dataIndex].label_panjang,
            label: (it) => `${label}: ${format(it.raw)}`,
            afterLabel: (it) => titik[it.dataIndex].keterangan || "",
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { autoSkip: true, maxRotation: 0 } },
        y: { beginAtZero: true, grid: { color: "#ece9e5" }, border: { display: false },
             ticks: { callback: (v) => format(v) } },
      },
    },
  }));
}

const KET_STATUS = { tanpa_data: "Tidak ada data", tutup: "Tutup (0 transaksi)", parsial: "Hari parsial", buka: "" };

function titikHarian(harian) {
  return harian.map((h) => {
    const [y, m, d] = h.tanggal.split("-").map(Number);
    const ket = [KET_STATUS[h.status], h.libur ? `Libur: ${h.libur}` : ""].filter(Boolean).join(" · ");
    return { ...h, label_pendek: `${d}${h.libur ? "*" : ""}`, label_panjang: h.label, keterangan: ket };
  });
}

function tabelHarian(titik, kolom) {
  return `<details><summary>Lihat tabel harian</summary>${tabel(titik.map((t) => {
    const r = { Tanggal: t.label_panjang };
    kolom.forEach(([k, f]) => { r[k] = f(t); });
    r.Keterangan = t.keterangan || "-";
    return r;
  }))}</details>`;
}

// ---------------------------------------------------------------- tab Overview
function tabOverview(d) {
  const o = d.overview;
  const k = o.kartu;
  const titik = titikHarian(o.harian);
  const libur = titik.some((t) => t.libur) ? `<p class="catatan">* = hari libur nasional/Ramadan.</p>` : "";
  let h = `<div class="kisi-kartu">
    ${kartuAngka("Grand Total (omzet)", k.grand_total)}
    ${kartuAngka("Subtotal", k.subtotal)}
    ${kartuAngka("Jumlah bill", k.jumlah_bill)}
    ${kartuAngka("Rata-rata bill F&B", k.rata_bill_fnb)}
    ${kartuAngka("Grand Total per hari buka", k.omzet_per_hari_buka)}
    ${kartuAngka("Hari terbaik", k.hari_terbaik)}
    ${kartuAngka("Hari terlemah", k.hari_terlemah)}
    ${kartuAngka("Omzet non-F&B (jasa & aksesoris)", k.omzet_non_fnb, "Basis Subtotal, sudah termasuk di Grand Total")}
  </div>`;
  if (o.target) h += `<div class="kartu">Target omzet bulan ini (dari Pengaturan): <b>${rp(o.target)}</b></div>`;
  if (d.periode.ada_data) {
    h += `<h2>Grand Total harian</h2><div class="kartu"><div class="grafik"><canvas id="g-omzet"></canvas></div>${libur}
      ${tabelHarian(titik, [["Grand Total", (t) => (t.grand_total == null ? "Tidak ada data" : rp(t.grand_total))],
                            ["Bill", (t) => (t.bill == null ? "-" : t.bill)]])}</div>`;
  }
  h += bagianBanding(o.banding);
  if (o.bulanan) {
    const b = o.bulanan;
    const baris = ["status", "Hari data", "Hari buka", "Grand Total", "Jumlah bill", "Rata-rata bill F&B", "Grand Total / hari buka", "Bill / hari buka"];
    h += `<h2>Minggu per minggu</h2><div class="kartu"><div class="gulir"><table><thead><tr><th></th>
      ${b.kolom.map((c) => `<th class="angka">${esc(c.label)}</th>`).join("")}</tr></thead><tbody>
      ${baris.map((r) => `<tr><td>${esc(r === "status" ? "Kelengkapan" : r)}</td>${b.kolom.map((c) => `<td class="angka">${esc(c[r])}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div>
      <h3 class="sub-judul">Jembatan minggu → Bulan Penuh</h3>${tabel(b.jembatan.map((j) => ({ "": j.label, "Grand Total": j.grand_total, "Bill": j.bill })))}
      <p class="catatan">Minggu = Senin–Minggu, dan minggu ke-n = minggu yang hari Seninnya jatuh di bulan ini. Karena itu jumlah minggu tidak sama dengan Bulan Penuh.${b.catatan ? " " + esc(b.catatan) : ""}</p></div>`;
  }
  if (o.rekonsiliasi) {
    const r = o.rekonsiliasi;
    h += `<h2>Rekonsiliasi Subtotal → Grand Total</h2><div class="kartu"><div class="gulir"><table class="rekon">
      ${r.baris.map((b) => `<tr><td>${esc(b.tanda)}</td><td>${esc(b.label)}</td><td class="angka">${esc(b.teks)}</td></tr>`).join("")}
      <tr class="total"><td>=</td><td>Hasil hitung komponen</td><td class="angka">${esc(r.hasil_hitung)}</td></tr>
      <tr><td></td><td>Grand Total ESB</td><td class="angka">${esc(r.grand_total)}</td></tr>
      <tr><td></td><td>Selisih</td><td class="angka">${esc(r.selisih)}</td></tr></table></div>
      <p class="catatan">${esc(r.catatan)}</p>
      ${r.bill_selisih.length ? `<details><summary>Bill yang selisih (${r.bill_selisih.length}${r.bill_selisih.length >= 50 ? "+" : ""})</summary>${tabel(r.bill_selisih)}</details>` : ""}
    </div>`;
  }
  if (o.diskon.length) {
    h += `<h2>Diskon</h2><div class="kartu">${tabel(o.diskon.map((x) => ({
      Jenis: x.label, Nominal: x.nominal.teks, "Bill terkena": x.bill == null ? "-" : x.bill, "% terhadap Grand Total": x.persen_omzet.teks })))}</div>`;
  }
  if (o.channel.length) {
    h += `<h2>Per channel (Visit Purpose)</h2><div class="kartu">${tabel(o.channel.map((x) => ({
      Channel: x.channel, Bill: x.bill, "Grand Total": x.grand_total.teks, "Porsi omzet": x.porsi_omzet.teks,
      "Rata-rata bill F&B": x.rata_bill_fnb.teks })))}</div>`;
  }
  return { html: h, setelah: () => d.periode.ada_data && grafikBatang("g-omzet", "Grand Total", titik, (t) => (t.grand_total == null ? null : Number(t.grand_total)), rp) };
}

// ---------------------------------------------------------------- tab Foot Traffic
function tabFoot(d) {
  const f = d.foot_traffic;
  const k = f.kartu;
  let h = `<div class="kisi-kartu">
    ${kartuAngka("Bill per hari buka", k.bill_per_hari)}
    ${kartuAngka("Perkiraan orang makan per hari", k.orang_makan_per_hari, "= porsi makanan utama per hari buka")}
    ${kartuAngka("Porsi makanan utama per bill", k.porsi_per_bill)}
  </div>`;
  if (!f.tersedia) return { html: h + bagianBanding(f.banding), setelah: () => {} };
  const titik = titikHarian(d.overview.harian).map((t, i) => ({ ...t, porsi: f.harian[i].porsi }));
  h += `<h2>Bill harian</h2><div class="kartu"><div class="grafik"><canvas id="g-bill"></canvas></div>
    ${tabelHarian(titik, [["Bill", (t) => (t.bill == null ? "Tidak ada data" : t.bill)],
                          ["Porsi makanan utama", (t) => (t.porsi == null ? "-" : Number(t.porsi).toLocaleString("id-ID"))]])}</div>`;
  h += bagianBanding(f.banding);
  h += `<h2>Jendela waktu × hari kerja / akhir pekan</h2><div class="kartu">${tabel(f.jendela.map((j) => ({
    Jendela: j.jendela, Jam: j.jam, [`Bill hari kerja (${f.hari_kerja} hari)`]: j.bill_hari_kerja,
    "Per hari kerja": j.per_hari_kerja, [`Bill akhir pekan (${f.hari_akhir_pekan} hari)`]: j.bill_akhir_pekan,
    "Per hari akhir pekan": j.per_hari_akhir_pekan, "Porsi bill": j.porsi_bill, Keterangan: j.keterangan || "-" })))}
    <p class="catatan">Jam dari Sales In Time; batas akhir inklusif sampai menit :59. Jendela yang punya keterangan tidak dipakai untuk membandingkan antar cabang.</p></div>`;
  h += `<h2>Per hari dalam seminggu</h2><div class="kartu"><div class="grafik"><canvas id="g-hari"></canvas></div>
    ${tabel(f.per_hari.map((x) => ({ Hari: x.hari, "Hari buka": x.hari_buka, Bill: x.bill, "Rata-rata per hari": x.rata_per_hari })))}</div>`;
  h += `<h2>Per channel</h2><div class="kartu">${tabel(f.channel.map((x) => ({ Channel: x.channel, Bill: x.bill, "Per hari buka": x.per_hari, Porsi: x.porsi })))}</div>`;
  h += `<h2>Ukuran rombongan (porsi makanan utama per bill)</h2><div class="kartu">${tabel(f.rombongan.map((x) => ({ Porsi: x.porsi, Bill: x.bill, "%": x.persen })))}
    <ul class="catatan">${f.catatan_rombongan.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>`;
  h += `<ul class="catatan">${f.catatan.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`;
  const perHari = f.per_hari.map((x) => ({ label_pendek: x.hari.slice(0, 3), label_panjang: x.hari,
    keterangan: `${x.hari_buka} hari buka`, v: x.rata_per_hari === "—" ? null : Number(x.rata_per_hari.replace(/\./g, "").replace(",", ".")) }));
  const satu = (v) => (v == null ? "—" : Number(v).toLocaleString("id-ID", { maximumFractionDigits: 1 }));
  return { html: h, setelah: () => {
    grafikBatang("g-bill", "Bill", titik, (t) => t.bill, satu);
    grafikBatang("g-hari", "Rata-rata bill per hari", perHari, (t) => t.v, satu);
  } };
}

// ---------------------------------------------------------------- tab Makanan / Kudapan / Minuman
const KOLOM_MENU = ["Menu", "Sub-kategori", "Qty", "Omzet (Total)", "Omzet bersih", "Harga (modus)", "Margin", "Margin %", "Catatan"];

function tabelMenu(baris, kolom = KOLOM_MENU) {
  return tabel(baris.map((r) => Object.fromEntries(kolom.map((k) => [k, r[k]]))));
}

function bagianOpsional(judul, x, isi) {
  if (!x) return "";
  if (!x.tersedia) return `<h2>${esc(judul)}</h2><div class="kartu kosong">Tidak diketahui — ${esc(x.alasan)}.</div>`;
  return `<h2>${esc(judul)}</h2><div class="kartu">${isi(x)}</div>`;
}

function tabMenu(d, kode) {
  const t = d[kode];
  const k = t.kartu;
  let h = `<div class="kisi-kartu">
    ${kartuAngka(`Omzet ${t.judul.toLowerCase()}`, k.omzet, "Basis Subtotal (Total COGS), tanpa item paket Rp0")}
    ${kartuAngka("Omzet bersih (setelah diskon)", k.omzet_bersih)}
    ${kartuAngka("Qty terjual (berbayar)", k.qty)}
    ${kartuAngka("Margin blended", k.margin)}
    ${kartuAngka("Omzet tanpa data HPP", k.omzet_tanpa_hpp, "Tidak ikut margin")}
    ${kartuAngka("Biaya bahan item gratis di paket", k.biaya_gratis)}
    ${k.minuman_per_bill ? kartuAngka("Minuman per bill F&B (berbayar)", k.minuman_per_bill) : ""}
  </div>`;
  if (!t.tersedia) return { html: h, setelah: () => {} };
  if (t.attach) {
    h += `<h2>Attach rate</h2><div class="kisi-kartu">${t.attach.map((a) =>
      kartuAngka(`${a.label} · berbayar`, a.berbayar,
        a.basis != null ? `${a.bill_berbayar} dari ${a.basis} bill F&B · termasuk paket: ${a.termasuk_paket.teks}` : "")).join("")}</div>`;
  }
  h += bagianBanding(t.banding);
  h += `<h2>Per sub-kategori</h2><div class="kartu">${tabel(t.sub_kategori)}</div>`;
  if (t.suhu) {
    h += `<h2>Panas vs dingin</h2><div class="kartu">${tabel(t.suhu)}
      <p class="catatan">Dari kata di nama menu (panas/hot, dingin/es/ice) dan daftar per menu di Pengaturan.${
        t.suhu_tidak_diketahui.length ? " Belum diketahui: " + esc(t.suhu_tidak_diketahui.join(", ")) + "." : ""}</p></div>`;
  }
  h += `<h2>10 menu teratas (omzet)</h2><div class="kartu">${tabelMenu(t.top)}</div>`;
  if (t.bottom.length) h += `<h2>10 menu terbawah (omzet)</h2><div class="kartu">${tabelMenu(t.bottom)}</div>`;
  h += bagianOpsional("Menu naik / turun", t.naik_turun, (x) =>
    `<h3 class="sub-judul">Naik</h3>${x.naik.length ? tabel(x.naik) : "<p class='catatan'>Tidak ada.</p>"}
     <h3 class="sub-judul">Turun</h3>${x.turun.length ? tabel(x.turun) : "<p class='catatan'>Tidak ada.</p>"}
     <p class="catatan">${esc(x.catatan)}</p>`);
  h += bagianOpsional("Perubahan harga", t.harga, (x) =>
    `${x.baris.length ? tabel(x.baris) : "<p class='catatan'>Tidak ada perubahan harga.</p>"}<p class="catatan">${esc(x.catatan)}</p>`);
  h += bagianOpsional("Menu baru (belum pernah terjual sebelumnya)", t.baru_hilang.baru, (x) =>
    `${x.baris.length ? tabel(x.baris) : "<p class='catatan'>Tidak ada.</p>"}<p class="catatan">${esc(x.dasar)}.</p>`);
  h += bagianOpsional("Menu yang hilang", t.baru_hilang.hilang, (x) =>
    `${x.baris.length ? tabel(x.baris) : "<p class='catatan'>Tidak ada.</p>"}<p class="catatan">${esc(x.dasar)}.</p>`);
  if (t.menu_baru_pengaturan.length) {
    h += `<h2>Menu baru yang dipantau (dari Pengaturan)</h2><div class="kartu">${tabel(t.menu_baru_pengaturan)}
      <p class="catatan">Penjualan sejak tanggal mulai sampai akhir periode yang sedang dilihat.</p></div>`;
  }
  h += `<h2>Semua menu (${t.menu.length})</h2><div class="kartu"><details><summary>Lihat tabel lengkap</summary>${tabelMenu(t.menu)}</details></div>`;
  t.tambahan.forEach((x) => {
    h += `<h2>${esc(x.judul)}</h2><div class="kartu"><p class="catatan" style="padding:0">Omzet ${esc(x.omzet)} · qty ${esc(x.qty)}</p>${tabelMenu(x.menu)}</div>`;
  });
  h += `<ul class="catatan">${t.catatan.map((c) => `<li>${esc(c)}</li>`).join("")}
    <li>Margin = omzet bersih − COGS, hanya baris ber-HPP dan bukan salah input resep (HPP/unit &gt; 1,5× harga).</li></ul>`;
  return { html: h, setelah: () => {} };
}

// ---------------------------------------------------------------- kualitas data
function panelKualitas(d) {
  const q = d.kualitas;
  const ul = (xs) => `<ul class="catatan">${xs.map((x) => `<li>${x}</li>`).join("")}</ul>`;
  return `<h2>Kualitas data periode ini</h2><div class="kartu">
    ${tabel(q.file.map((f) => ({ File: f.file, Status: f.status, Keterangan: f.keterangan })))}
    <h3 class="sub-judul">Rekonsiliasi unggahan</h3>
    ${q.rekonsiliasi.length ? tabel(q.rekonsiliasi.map((r) => ({ Periode: r.unggahan, File: r.file, Rekonsiliasi: r.status }))) : "<p class='catatan'>Tidak ada unggahan di periode ini.</p>"}
    <h3 class="sub-judul">Hari</h3>
    ${q.hari.length ? tabel(q.hari.map((x) => ({ Keadaan: x.jenis, Tanggal: x.tanggal }))) : "<p class='catatan'>Semua hari ada datanya; tidak ada hari tutup atau parsial.</p>"}
    <h3 class="sub-judul">Baris dikeluarkan &amp; data HPP</h3>
    ${ul([
      ...q.baris_dikeluarkan.map((b) => `${esc(b.hal)}: <b>${b.jumlah}</b>`),
      `Menu tanpa data HPP: <b>${q.tanpa_hpp.menu}</b> menu, ${q.tanpa_hpp.baris} baris, omzet ${esc(q.tanpa_hpp.omzet)} (tidak ikut margin)`,
      q.kategori_belum_dipetakan.length ? `Kategori belum dipetakan: ${esc(q.kategori_belum_dipetakan.join("; "))}` : "Semua kategori menu sudah dipetakan.",
      q.hari_libur_terverifikasi ? "Daftar hari libur sudah diverifikasi." :
        "<b>Daftar hari libur 2026 masih isi awal dan belum diverifikasi</b> dengan SKB 3 Menteri (lihat Pengaturan).",
    ])}
    ${q.tanpa_hpp.daftar.length ? `<details><summary>Daftar menu tanpa HPP</summary>${ul(q.tanpa_hpp.daftar.map(esc))}</details>` : ""}
  </div>`;
}

// ---------------------------------------------------------------- muat & render
function urlDashboard() {
  const p = new URLSearchParams({ cabang: keadaan.cabang, bulan: keadaan.bulan, pilih: keadaan.pilih, tab: keadaan.tab });
  return `#dashboard?${p}`;
}

async function isiDaftarBulan() {
  const sel = document.getElementById("dash-bulan");
  const { bulan } = await api("/api/dashboard/bulan");
  const h = new Date();
  const kini = `${h.getFullYear()}-${String(h.getMonth() + 1).padStart(2, "0")}`;
  const semua = [...new Set([...bulan, kini])].sort().reverse();
  sel.innerHTML = semua.map((b) => {
    const [y, m] = b.split("-").map(Number);
    return `<option value="${b}">${NAMA_BULAN[m - 1]} ${y}${bulan.includes(b) ? "" : " (belum ada data)"}</option>`;
  }).join("");
  return bulan;
}

async function bukaDashboard(query) {
  const p = new URLSearchParams(query || "");
  const no = ++nomorMuat;
  document.getElementById("dash-isi").innerHTML = `<div class="kartu kosong">Menghitung…</div>`;
  const adaBulan = await isiDaftarBulan();
  if (no !== nomorMuat) return;
  keadaan.cabang = p.get("cabang") || keadaan.cabang;
  keadaan.bulan = p.get("bulan") || keadaan.bulan || adaBulan[adaBulan.length - 1] ||
    document.getElementById("dash-bulan").value;
  keadaan.pilih = p.get("pilih") || keadaan.pilih;
  keadaan.tab = p.get("tab") || keadaan.tab;
  document.getElementById("dash-cabang").value = keadaan.cabang;
  document.getElementById("dash-bulan").value = keadaan.bulan;
  await muat();
}

// Pemilih bisa diklik cepat berturut-turut. Hanya jawaban permintaan
// terakhir yang boleh tampil, supaya angka periode lama tidak menimpa yang baru.
let nomorMuat = 0;

async function muat() {
  const no = ++nomorMuat;
  const isi = document.getElementById("dash-isi");
  isi.innerHTML = `<div class="kartu kosong">Menghitung…</div>`;
  document.getElementById("dash-kualitas").innerHTML = "";
  let data;
  try {
    data = await api(`/api/dashboard?cabang=${encodeURIComponent(keadaan.cabang)}&bulan=${encodeURIComponent(keadaan.bulan)}&pilih=${encodeURIComponent(keadaan.pilih)}`);
  } catch (e) {
    if (no === nomorMuat) isi.innerHTML = `<div class="pesan galat">${esc(e.message)}</div>`;
    return;
  }
  if (no !== nomorMuat) return;
  keadaan.data = data;
  keadaan.pilih = data.pilih;
  render();
}

function render() {
  const d = keadaan.data;
  grafik.splice(0).forEach((g) => g.destroy());
  asalTerdaftar.length = 0;
  history.replaceState(null, "", urlDashboard());

  document.getElementById("dash-minggu").innerHTML = d.tombol.map((t) =>
    `<button role="tab" data-pilih="${esc(t.kode)}" aria-selected="${t.kode === d.pilih}" class="${t.ada_data ? "" : "kosong"}">
      ${esc(t.label)}<small>${esc(t.status)}</small></button>`).join("");
  document.getElementById("dash-judul").textContent = `${d.cabang} · ${d.periode.label}`;
  document.getElementById("dash-sub").textContent =
    `${tgl(d.periode.awal)} – ${tgl(d.periode.akhir)} · data ${d.periode.hari_data} dari ${d.periode.hari_rentang} hari` +
    (d.periode.ada_data && !d.periode.lengkap ? ` · parsial (${d.periode.hari_data} hari): perbandingan memakai rata-rata per hari buka` : "");
  document.getElementById("dash-peringatan").innerHTML = d.peringatan_merah
    ? `<div class="pesan galat">⚠ Sebagian data periode ini disimpan walau rekonsiliasi tidak cocok. Semua angka di bawah bisa salah.</div>` : "";
  document.getElementById("dash-tab").innerHTML = TAB.map(([k, n]) =>
    `<button data-tab="${k}" aria-selected="${k === keadaan.tab}">${esc(n)}</button>`).join("");

  let hasil;
  if (keadaan.tab === "overview") hasil = tabOverview(d);
  else if (keadaan.tab === "foot") hasil = tabFoot(d);
  else if (["makanan", "kudapan", "minuman"].includes(keadaan.tab)) hasil = tabMenu(d, keadaan.tab);
  else {
    const m = d.menyusul.find((x) => x.kode === keadaan.tab);
    hasil = { html: `<div class="kartu kosong">${esc(m ? m.nama : "Tab ini")} dibangun di tahap ${m ? m.tahap : "berikutnya"}.</div>`, setelah: () => {} };
  }
  document.getElementById("dash-isi").innerHTML = hasil.html;
  document.getElementById("dash-kualitas").innerHTML = panelKualitas(d);
  hasil.setelah();
}

document.getElementById("dash-minggu").addEventListener("click", (e) => {
  const b = e.target.closest("[data-pilih]");
  if (b) { keadaan.pilih = b.dataset.pilih; muat(); }
});
document.getElementById("dash-tab").addEventListener("click", (e) => {
  const b = e.target.closest("[data-tab]");
  if (b) { keadaan.tab = b.dataset.tab; render(); }
});
document.getElementById("dash-isi").addEventListener("click", (e) => {
  const b = e.target.closest("[data-asal]");
  if (b) bukaAsal(Number(b.dataset.asal));
});
document.getElementById("dash-cabang").addEventListener("change", (e) => { keadaan.cabang = e.target.value; muat(); });
document.getElementById("dash-bulan").addEventListener("change", (e) => { keadaan.bulan = e.target.value; keadaan.pilih = "bulan"; muat(); });

window.bukaDashboard = bukaDashboard;
if (location.hash.startsWith("#dashboard")) bukaDashboard(location.hash.split("?")[1]);
