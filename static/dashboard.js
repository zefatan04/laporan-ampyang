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

const keadaan = { cabang: "Rungkut", bulan: null, pilih: "bulan", tab: "overview", khusus: false, data: null };
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
    <p class="catatan">Jam dari Sales In Time; batas akhir inklusif sampai menit :59. ${khusus(keadaan.data) ? "" : "Jendela yang punya keterangan tidak dipakai untuk membandingkan antar cabang."}</p></div>`;
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

// ---------------------------------------------------------------- tab Promo
const WARNA_LABEL = { "Menambah omzet": "lulus", "Netral": "tidak_bisa", "Mengurangi omzet": "gagal", "Belum bisa disimpulkan": "peringatan" };

function kartuPromo(e) {
  const k = e.kesimpulan;
  const bp = e.bill_promo ? tabel([e.bill_promo]) : `<p class="catatan">Angka bill promo: Tidak diketahui — ${esc(e.bill_promo_alasan)}.</p>`;
  const banding = e.banding && e.hari_dibandingkan === 0
    ? `<p class="catatan">Perbandingan dengan pembanding: Tidak diketahui — belum ada hari promo yang punya pembanding hari yang sama (lihat alasan di atas).</p>`
    : e.banding ? `<h3 class="sub-judul">Dibanding pembanding (rata-rata hari yang sama dalam seminggu)</h3>
    ${tabel(e.banding.map((r) => ({ Metrik: r.metrik, "A: 4 minggu sebelum": r.A, "B: 4 minggu sebelum + 4 minggu sesudah": r.B })))}
    <ul class="catatan">
      <li>${e.hari_dibandingkan} hari promo dibandingkan.${e.hari_tanpa_pembanding.length ? " Tanpa pembanding hari yang sama: " + esc(e.hari_tanpa_pembanding.join(", ")) + "." : ""}</li>
      ${e.libur_dikeluarkan.length ? `<li>Hari libur/Ramadan dikeluarkan: ${esc(e.libur_dikeluarkan.join(", "))}.</li>` : ""}
      <li>Sampel pembanding A per hari: ${esc(Object.entries(e.sampel_a).map(([h, n]) => `${h} ${n}`).join(", ") || "-")}.</li>
    </ul>` : "";
  const rata = e.rata_bill ? `<li>Rata-rata bill F&amp;B selama promo ${esc(e.rata_bill.selama)} vs sebelum ${esc(e.rata_bill.sebelum)}
      (<span class="${esc(e.rata_bill.selisih.arah)}">${esc(e.rata_bill.selisih.persen)}</span>).</li>` : "";
  const setelah = e.setelah ? `<li>Efek setelah promo: ${esc(e.setelah.teks)}${e.setelah_menu ? "; " + esc(e.setelah_menu.teks) : ""}.</li>` : "";
  return `<div class="kartu cek ${WARNA_LABEL[k.label] || ""}">
    <div class="cek-judul"><span class="lencana ${esc(WARNA_LABEL[k.label] || "tidak_bisa")}">${esc(k.label)}</span>
      <span>${esc(e.nama)}</span><span class="cek-file">${esc(e.periode)} · ${esc(e.data_promo)}</span></div>
    <ul class="catatan">${k.alasan.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
    <h3 class="sub-judul">Bill yang memakai promo (nama di ESB: ${esc(e.promotion_esb.join(", ") || "belum diisi")})</h3>${bp}
    ${banding}
    <ul class="catatan">${rata}${setelah}
      <li>Pembanding A: ${esc(e.pembanding_a)}. Pembanding B: ${esc(e.pembanding_b)}.</li>
      <li>Menu promo: ${esc(e.menu_promo.join(", ") || "belum diisi di Pengaturan")}.</li></ul>
  </div>`;
}

function tabPromo(d) {
  const p = d.promo;
  let h = "";
  h += `<h2>Promo terdaftar</h2>`;
  if (!p.jumlah_terdaftar) {
    h += `<div class="kartu kosong">Belum ada promo yang didaftarkan. Isi daftar promo (nama, periode, cabang, nama di ESB, menu promo) di
      <a href="#pengaturan">Pengaturan</a> supaya bisa dinilai Menambah omzet / Netral / Mengurangi omzet.</div>`;
  } else if (!p.terdaftar.length) {
    h += `<div class="kartu kosong">Tidak ada promo terdaftar yang berjalan di periode ini (atau selesai ≤ 4 minggu sebelumnya) untuk cabang ini.</div>`;
  } else {
    h += p.terdaftar.map(kartuPromo).join("");
  }
  h += `<h2>Promo tercatat di ESB periode ini</h2>`;
  if (!p.esb.tersedia) h += `<div class="kartu kosong">Tidak diketahui — ${esc(p.esb.alasan)}.</div>`;
  else {
    h += `<div class="kartu">${p.esb.baris.length ? tabel(p.esb.baris) : "<p class='catatan'>Tidak ada bill yang memakai promo.</p>"}
      <p class="catatan">Bill tanpa promo: ${p.esb.tanpa_promo.bill}, rata-rata bill F&amp;B ${esc(p.esb.tanpa_promo.rata_bill_fnb)}.</p>
      <ul class="catatan">${p.esb.catatan.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>`;
  }
  h += `<h2>Paket</h2>`;
  const pk = p.paket;
  if (!pk.tersedia) h += `<div class="kartu kosong">Tidak diketahui — ${esc(pk.alasan)}.</div>`;
  else if (!pk.baris.length) h += `<div class="kartu kosong">${esc(pk.catatan[0])}</div>`;
  else {
    h += `<div class="kartu">${tabel(pk.baris)}
      <p class="catatan">Bill paket saja (tanpa item berbayar lain): ${pk.paket_saja} dari ${pk.bill_paket} bill paket, ${esc(pk.paket_saja_per_hari)} per hari buka.</p>
      <h3 class="sub-judul">Isi paket yang paling sering</h3>${tabel(pk.isi)}
      <h3 class="sub-judul">Sebaran bill paket per hari</h3>${tabel(pk.per_hari)}
      <h3 class="sub-judul">Sebaran per jendela waktu</h3>${tabel(pk.per_jendela)}
      <ul class="catatan">${pk.catatan.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>`;
  }
  h += `<ul class="catatan"><li>Kesimpulan memakai sisi pesimis dari dua pembanding; ambang netral ±${esc(p.ambang)}% (Pengaturan).</li>
    <li>Pembanding tidak memakai hari libur, Ramadan, hari tutup, hari parsial, atau hari tanpa data.</li></ul>`;
  return { html: h, setelah: () => {} };
}

// ---------------------------------------------------------------- tab Membership
function tabMembership(d) {
  const m = d.membership;
  if (!m.tersedia) {
    return { html: `<div class="kartu kosong">Tidak diketahui — ${esc(m.alasan)}. Unggah CSV ekspor web loyalty di <a href="#upload">Upload</a>.</div>`, setelah: () => {} };
  }
  const k = m.kartu;
  let h = `<h2>Member (potret Rekap Pelanggan)</h2><div class="kisi-kartu">
    ${kartuAngka("Total member (semua cabang)", k.total_member)}
    ${kartuAngka("Terverifikasi OTP", k.terverifikasi)}
    ${kartuAngka("Member baru terverifikasi", k.terverifikasi_baru)}
    ${kartuAngka(`Pernah transaksi di ${d.cabang}`, k.pernah_transaksi)}
    ${kartuAngka("Repeat sejak bergabung (≥2 transaksi)", k.repeat_sejak_gabung)}
  </div>`;
  if (!m.berkala) return { html: h + `<div class="kartu kosong">Data loyalty berkala (transaksi, rekap harian, klaim, log) belum ada untuk periode ini.</div>`, setelah: () => {} };
  h += `<h2>Periode ini</h2><div class="kisi-kartu">
    ${kartuAngka("Member baru (semua cabang)", k.member_baru)}
    ${kartuAngka("Member baru didaftarkan kasir cabang ini", k.member_baru_cabang)}
    ${kartuAngka("Member bertransaksi", k.member_aktif)}
    ${kartuAngka("Member repeat (≥2 transaksi di periode)", k.repeat)}
    ${kartuAngka("Bill lewat member", k.bill_member)}
    ${kartuAngka("Omzet lewat member", k.omzet_member, "Basis Grand Total")}
    ${kartuAngka("Porsi bill member dari total bill", k.porsi_bill)}
    ${kartuAngka("Porsi omzet member dari total omzet", k.porsi_omzet)}
    ${kartuAngka("Stempel diberikan", k.stempel)}
    ${kartuAngka("Klaim hadiah", k.klaim)}
  </div>`;
  if (m.rata_bill) {
    const r = m.rata_bill;
    h += `<h2>Rata-rata bill F&amp;B: member vs non-member</h2><div class="kisi-kartu">
      ${kartuAngka(`Member (${r.n_member} bill)`, r.member)}
      ${kartuAngka(`Non-member (${r.n_non} bill)`, r.non_member)}
    </div><p class="catatan">Selisih <span class="${esc(r.selisih.arah)}">${esc(r.selisih.teks)} (${esc(r.selisih.persen)})</span>.
      ${r.sampel_kecil ? "<b>Sampel member kecil (&lt; 10 bill); jangan disimpulkan.</b>" : ""}
      Bill member = bill ESB yang tercocokkan dengan transaksi loyalty.</p>`;
  }
  h += bagianBanding(m.banding);
  h += `<h2>Kualitas pendaftaran &amp; pencatatan</h2><div class="kartu">`;
  const q = m.kualitas;
  if (!q.tersedia) h += `<p class="catatan">Log Aktivitas belum diunggah; tanda pendaftaran tidak diketahui.</p>`;
  else {
    h += `<p>${q.daftar} pendaftaran tercatat di log cabang ini · tanda <b>beruntun ${q.beruntun}</b> · tanda <b>janggal ${q.janggal}</b>.</p>
      ${q.rincian.length ? tabel(q.rincian) : ""}`;
  }
  h += `<h3 class="sub-judul">Transaksi member tanpa pasangan bill ESB (${q.tanpa_esb.length})</h3>
    ${!q.esb_ada ? "<p class='catatan'>Tidak bisa dicek: data ESB periode ini belum ada.</p>" : q.tanpa_esb.length ? tabel(q.tanpa_esb) : "<p class='catatan'>Semua transaksi member punya pasangan bill ESB.</p>"}
    <h3 class="sub-judul">Kemungkinan dicatat ganda (${q.ganda.length})</h3>
    ${q.ganda.length ? tabel(q.ganda) : "<p class='catatan'>Tidak ada.</p>"}
    <ul class="catatan">${q.catatan.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>`;
  h += `<h2>Rincian per kasir</h2><div class="kartu">${m.per_kasir.length ? tabel(m.per_kasir) : "<p class='catatan'>Tidak ada aktivitas kasir.</p>"}</div>`;
  h += `<h2>Klaim hadiah &amp; promo eksklusif</h2><div class="kartu">${m.hadiah.length ? tabel(m.hadiah) : "<p class='catatan'>Tidak ada klaim hadiah.</p>"}
    <p class="catatan">Promo eksklusif member (dari Log Aktivitas): ${m.eksklusif.klaim} klaim, ${m.eksklusif.diserahkan} diserahkan.</p></div>`;
  h += `<h2>Harian</h2><div class="kartu">${tabel(m.harian)}</div>`;
  h += `<h2>Customer Data Report ESB</h2><div class="kartu kosong">${esc(m.customer_data_esb.alasan)}</div>`;
  h += `<ul class="catatan"><li>Nomor WA tidak disimpan di aplikasi ini; yang disimpan hanya sidik (hash) untuk menghitung member berulang.</li>
    <li>Nominal Bill di web loyalty terbukti memakai basis Grand Total ESB.</li></ul>`;
  return { html: h, setelah: () => {} };
}

// ---------------------------------------------------------------- tab Sosmed & Campaign
const METRIK_IG = [["tayangan", "Tayangan"], ["jangkauan", "Jangkauan"], ["interaksi", "Interaksi konten"],
  ["kunjungan", "Kunjungan profil"], ["klik", "Klik tautan"], ["pengikut", "Pengikut baru"]];
const daftarCatatan = (xs) => (xs && xs.length ? `<ul class="catatan">${xs.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : "");

function titikIg(harian, kode) {
  return harian.map((h) => {
    const [, , dd] = h.tanggal.split("-").map(Number);
    const st = h[`${kode}_status`];
    const ket = [st === "ada" ? "" : st, h.libur ? `Libur: ${h.libur}` : "", h.konten.length ? `Konten: ${h.konten.join("; ")}` : ""]
      .filter(Boolean).join(" · ");
    return { ...h, label_pendek: `${dd}${h.libur ? "*" : ""}`, label_panjang: h.label, keterangan: ket };
  });
}

function grafikIg(i, harian, kode) {
  const el = document.getElementById(`g-ig-${i}`);
  if (!el) return;
  const lama = Chart.getChart(el);
  if (lama) { grafik.splice(grafik.indexOf(lama), 1); lama.destroy(); }
  const nama = METRIK_IG.find(([k]) => k === kode)[1];
  grafikBatang(`g-ig-${i}`, nama, titikIg(harian, kode), (t) => t[kode],
    (v) => (v == null ? "tidak ada data" : Number(v).toLocaleString("id-ID")));
}

function kartuKampanye(k) {
  const dt = k.deteksi;
  const deteksi = !dt.tersedia ? `<p class="catatan">Tidak diketahui — ${esc(dt.alasan)}.</p>` : `
    <p>Terdeteksi dari klik tautan &gt; 0: <b>${esc(dt.terdeteksi)}</b> · tanggal isian: <b>${esc(dt.isian)}</b>
      ${dt.cocok ? `<span class="lencana lulus">cocok</span>` : `<span class="lencana peringatan">beda</span>`}</p>
    ${dt.peringatan.map((p) => `<p class="awas">⚠ ${esc(p)}</p>`).join("")}${daftarCatatan(dt.catatan)}`;
  const mi = k.metrik_ig;
  const metrik = !mi.tersedia ? `<p class="catatan">Tidak diketahui — ${esc(mi.alasan)}.</p>` : `${tabel(mi.baris)}${daftarCatatan(mi.catatan)}`;
  return `<div class="kartu cek ${dt.tersedia && !dt.cocok ? "peringatan" : ""}">
    <div class="cek-judul"><span>${esc(k.nama)}</span>
      <span class="cek-file">${esc(k.periode)} · sasaran ${esc(k.cabang)} · akun IG ${esc(k.akun)} · anggaran ${esc(k.anggaran)}</span></div>
    <p class="catatan" style="padding:0">Platform: ${esc(k.platform)} · tujuan: ${esc(k.tujuan)} · menu promo: ${esc(k.menu_promo.join(", ") || "-")}</p>
    <h3 class="sub-judul">Tanggal iklan: data vs isian</h3>${deteksi}
    <h3 class="sub-judul">Metrik Instagram selama kampanye vs pembanding</h3>${metrik}
    <h3 class="sub-judul">Biaya per hasil Instagram</h3>
    <div class="kisi-kartu">${k.biaya_ig.map((b) => kartuAngka(b.judul, b.n)).join("")}</div>
    <h3 class="sub-judul">Tambahan bill di cabang sasaran vs pembanding</h3>${tabel(k.tambahan_bill)}
    <h3 class="sub-judul">Biaya iklan per bill tambahan</h3>${tabel(k.biaya_bill)}
    <h3 class="sub-judul">Korelasi klik harian vs tambahan bill harian</h3>${tabel(k.korelasi)}
    ${daftarCatatan(k.catatan)}
  </div>`;
}

function tabSosmed(d) {
  const s = d.sosmed;
  let h = "";
  const pasang = [];
  s.akun.forEach((a, i) => {
    h += `<h2>Instagram akun ${esc(a.akun)}${a.akun === "Brand" && !khusus(d) ? " (dipakai kedua cabang)" : ""}</h2>`;
    if (!a.ada) {
      h += `<div class="kartu kosong">Tidak diketahui — data Instagram akun ${esc(a.akun)} periode ini tidak diunggah.
        Data ini opsional: unggah CSV Instagram Insights di <a href="#upload">Upload</a>, atau isi total mingguan di
        <a href="#pengaturan">Pengaturan → Input manual Instagram</a>.</div>`;
      return;
    }
    if (a.manual) h += `<div class="pesan info">Angka akun ini dari <b>input manual</b> mingguan; tanpa rincian harian.</div>`;
    h += `<div class="kisi-kartu">${a.kartu.map((k) => kartuAngka(k.judul, k.n)).join("")}</div>`;
    if (a.harian) {
      const kp = a.klik_positif;
      h += `<div class="kartu">
        <div class="pilih-metrik" data-ig="${i}" role="tablist" aria-label="Pilih metrik">${METRIK_IG.map(([k, n], j) =>
          `<button data-metrik="${k}" aria-selected="${j === 0}">${esc(n)}</button>`).join("")}</div>
        <div class="grafik"><canvas id="g-ig-${i}"></canvas></div>
        <p class="catatan">Hari dengan klik tautan &gt; 0: ${esc(kp.hari || "tidak ada")} (dari ${kp.cakupan} hari yang ada data klik).
          ${kp.tanpa_kampanye ? `<b>Tidak ada kampanye terdaftar untuk akun ini pada ${esc(kp.tanpa_kampanye)}</b>; bila itu iklan, isi di Pengaturan.` : ""}
          * = hari libur. Batang kosong = tidak tercatat / tidak diunggah.</p>
        <details><summary>Lihat tabel harian</summary>${tabel(a.harian.map((x) => {
          const r = { Tanggal: x.label };
          METRIK_IG.forEach(([k, n]) => {
            r[n] = x[`${k}_status`] === "ada" ? Number(x[k]).toLocaleString("id-ID") : x[`${k}_status`];
          });
          r.Konten = x.konten.join("; ") || "-";
          r.Libur = x.libur || "-";
          return r;
        }))}</details></div>`;
      pasang.push([i, a.harian]);
    } else {
      h += `<p class="catatan">Grafik harian: Tidak diketahui — ${esc(a.harian_alasan)}.</p>`;
    }
    h += bagianBanding(a.banding);
    if (a.manual_vs_harian.length) {
      h += `<h3 class="sub-judul">Input manual vs CSV harian (minggu yang punya keduanya)</h3><div class="kartu">${tabel(a.manual_vs_harian)}</div>`;
    }
  });

  h += `<h2>Kampanye</h2>`;
  const km = s.kampanye;
  if (!km.jumlah_terdaftar) {
    h += `<div class="kartu kosong">Belum ada kampanye terdaftar. Isi nama, tanggal, cabang sasaran, anggaran, dan akun Instagram di
      <a href="#pengaturan">Pengaturan → Kampanye iklan</a> supaya biaya per klik dan per bill tambahan bisa dihitung.</div>`;
  } else if (!km.daftar.length) {
    h += `<div class="kartu kosong">Tidak ada kampanye untuk ${esc(d.cabang)} yang berjalan di periode ini (atau selesai ≤ 4 minggu sebelumnya).</div>`;
  } else {
    h += km.daftar.map(kartuKampanye).join("");
  }

  h += `<h2>Konten periode ini</h2>`;
  h += s.konten.length ? `<div class="kartu">${tabel(s.konten)}</div>` : `<div class="kartu kosong">${s.jumlah_konten
    ? "Tidak ada konten terdaftar di periode ini untuk akun cabang ini atau Brand."
    : 'Belum ada daftar konten. Isi di <a href="#pengaturan">Pengaturan → Daftar konten</a> (opsional).'}</div>`;
  h += daftarCatatan(s.catatan);
  return { html: h, setelah: () => pasang.forEach(([i, harian]) => grafikIg(i, harian, "tayangan")) };
}

document.getElementById("dash-isi").addEventListener("click", (e) => {
  const b = e.target.closest("[data-metrik]");
  if (!b) return;
  const wadah = b.closest("[data-ig]");
  const i = Number(wadah.dataset.ig);
  wadah.querySelectorAll("button").forEach((x) => x.setAttribute("aria-selected", x === b));
  grafikIg(i, keadaan.data.sosmed.akun[i].harian, b.dataset.metrik);
});

// ---------------------------------------------------------------- narasi (Claude)
// Mode ekspor: file HTML mandiri membawa datanya sendiri (window.DATA_EKSPOR), tanpa server.
const EKSPOR = window.DATA_EKSPOR || null;
// Dugaan & saran sudah diawali "Dugaan:"/"Saran:" di teksnya, jadi tidak diberi lencana lagi.
const LABEL_JENIS = { belum_bisa_disimpulkan: ["peringatan", "belum bisa disimpulkan"] };
const paramPeriode = (d) => ({ cabang: d.cabang, bulan: `${d.tahun}-${String(d.bulan).padStart(2, "0")}`, pilih: d.pilih,
  lingkup: d.lingkup === "khusus" ? "khusus" : "lengkap" });
const khusus = (d) => d.lingkup === "khusus";

function panelNarasi(d, tab) {
  const n = d.narasi;
  const x = n && n.tab[tab];
  if (!x) return "";
  if (EKSPOR && x.status === "belum") return "";
  const tombol = EKSPOR ? "" : `<div class="aksi" style="margin:0">
      <button class="tombol" data-paket>Unduh paket untuk Claude</button>
      <button class="tombol" data-tempel>Tempel jawaban Claude</button>
      ${n.aktif ? `<button class="tombol" data-narasi="${esc(tab)}">Buat lewat API</button>` : ""}</div>`;
  const kepala = (lencana) => `<div class="narasi-kepala"><h2 class="tanpa-jarak">Temuan</h2>${lencana}</div>`;
  if (x.status === "belum") {
    return `<div class="kartu narasi">${kepala("")}
      <ol class="catatan langkah">
        <li><b>Unduh paket untuk Claude</b>: satu file berisi angka kedelapan tab periode ini dan instruksi analisa.</li>
        <li>Buka Claude (claude.ai), unggah file itu (atau salin isinya), lalu kirim.</li>
        <li>Salin seluruh jawaban Claude, tekan <b>Tempel jawaban Claude</b>. Setiap angka di jawabannya dicocokkan ke data;
          kalimat dengan angka yang tidak ada di data dibuang.</li>
      </ol>${tombol}</div>`;
  }
  const lencana = x.status === "ada"
    ? `<span class="lencana lulus">narasi terverifikasi</span>`
    : `<span class="lencana peringatan">data berubah sejak narasi dibuat — buat ulang</span>`;
  const daftar = x.temuan.length ? `<ul class="temuan">${x.temuan.map((t) => {
    const j = LABEL_JENIS[t.jenis];
    return `<li class="${esc(t.jenis)}">${j ? `<span class="lencana ${j[0]}">${esc(j[1])}</span> ` : ""}${esc(t.teks)}</li>`;
  }).join("")}</ul>` : `<p class="catatan">Semua kalimat narasi tab ini dibuang karena memuat angka yang tidak ada di data.</p>`;
  const buang = x.dibuang.length ? `<details><summary>${x.dibuang.length} kalimat dibuang karena angkanya tidak ditemukan di data</summary>
    ${tabel(x.dibuang.map((b) => ({ Kalimat: b.kalimat, "Angka tidak ditemukan": b.angka_tidak_ditemukan.join(", ") })))}</details>` : "";
  return `<div class="kartu narasi">${kepala(lencana)}${daftar}${buang}
    <p class="catatan">Dibuat ${esc(x.waktu.replace("T", " "))} · ${esc(x.model)}. Setiap angka di teks sudah dicocokkan ke data tab ini;
      kalimat yang angkanya tidak ditemukan dibuang. "Dugaan" = kemungkinan penjelasan, bukan fakta dari data. "Saran" = usulan tindakan.</p>
    ${tombol}</div>`;
}

function unduhPaket() {
  location.href = `/api/paket-claude?${new URLSearchParams(paramPeriode(keadaan.data))}`;
}

function bukaTempel() {
  const dlg = document.getElementById("dialog-tempel");
  document.getElementById("tempel-isi").value = "";
  document.getElementById("tempel-hasil").innerHTML = "";
  dlg.showModal();
}

async function kirimTempel() {
  const d = keadaan.data;
  const tombol = document.getElementById("tempel-kirim");
  const out = document.getElementById("tempel-hasil");
  const teks = document.getElementById("tempel-isi").value;
  if (!teks.trim()) { out.innerHTML = `<div class="pesan galat">Tempel jawaban Claude dulu.</div>`; return; }
  tombol.disabled = true;
  try {
    const r = await api("/api/narasi/tempel", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...paramPeriode(d), teks }),
    });
    if (r.galat) throw new Error(r.galat);
    const baris = Object.entries(r.tab).map(([t, v]) => ({ Tab: t, "Temuan disimpan": v.temuan, "Kalimat dibuang": v.dibuang }));
    out.innerHTML = `<div class="pesan sukses">Tersimpan untuk ${baris.length} tab.</div>${tabel(baris)}
      ${r.catatan.length ? `<ul class="catatan">${r.catatan.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}`;
    if (keadaan.data === d) await muat();
  } catch (err) {
    out.innerHTML = `<div class="pesan galat">${esc(err.message)}</div>`;
  } finally {
    tombol.disabled = false;
  }
}

if (!EKSPOR) {
  document.getElementById("dash-isi").addEventListener("click", async (e) => {
    if (e.target.closest("[data-paket]")) { unduhPaket(); return; }
    if (e.target.closest("[data-tempel]")) { bukaTempel(); return; }
    const b = e.target.closest("[data-narasi]");
    if (!b) return;
    const d = keadaan.data;
    const tab = b.dataset.narasi;
    b.disabled = true;
    b.textContent = "Menulis… (bisa sampai 1 menit)";
    try {
      const hasil = await api("/api/narasi", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...paramPeriode(d), tab }),
      });
      if (hasil.galat) throw new Error(hasil.galat);
      d.narasi.tab[tab] = hasil;
      if (keadaan.data === d) render();
    } catch (err) {
      b.disabled = false;
      b.textContent = "Coba lagi";
      b.insertAdjacentHTML("afterend", `<span class="turun">${esc(err.message)}</span>`);
    }
  });
  document.getElementById("tempel-kirim").addEventListener("click", kirimTempel);
  document.getElementById("tempel-tutup").addEventListener("click", () => document.getElementById("dialog-tempel").close());
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
  if (keadaan.khusus) p.set("khusus", "1");
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
  if (p.has("cabang")) keadaan.khusus = p.get("khusus") === "1";
  document.getElementById("dash-khusus").checked = keadaan.khusus;
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
    data = await api(`/api/dashboard?cabang=${encodeURIComponent(keadaan.cabang)}&bulan=${encodeURIComponent(keadaan.bulan)}&pilih=${encodeURIComponent(keadaan.pilih)}&lingkup=${keadaan.khusus ? "khusus" : "lengkap"}`);
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
  if (!EKSPOR) history.replaceState(null, "", urlDashboard());

  document.getElementById("dash-minggu").innerHTML = EKSPOR ? "" : d.tombol.map((t) =>
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
  else if (keadaan.tab === "promo") hasil = tabPromo(d);
  else if (keadaan.tab === "membership") hasil = tabMembership(d);
  else hasil = tabSosmed(d);
  document.getElementById("dash-isi").innerHTML = panelNarasi(d, keadaan.tab) + hasil.html;
  document.getElementById("dash-kualitas").innerHTML = panelKualitas(d);
  hasil.setelah();
}

document.getElementById("dash-minggu").addEventListener("click", (e) => {
  const b = e.target.closest("[data-pilih]");
  if (b && !EKSPOR) { keadaan.pilih = b.dataset.pilih; muat(); }
});
document.getElementById("dash-tab").addEventListener("click", (e) => {
  const b = e.target.closest("[data-tab]");
  if (b) { keadaan.tab = b.dataset.tab; render(); }
});
document.getElementById("dash-isi").addEventListener("click", (e) => {
  const b = e.target.closest("[data-asal]");
  if (b) bukaAsal(Number(b.dataset.asal));
});
if (EKSPOR) {
  keadaan.data = EKSPOR;
  keadaan.pilih = EKSPOR.pilih;
  render();
} else {
  document.getElementById("dash-cabang").addEventListener("change", (e) => { keadaan.cabang = e.target.value; muat(); });
  document.getElementById("dash-bulan").addEventListener("change", (e) => { keadaan.bulan = e.target.value; keadaan.pilih = "bulan"; muat(); });
  document.getElementById("dash-khusus").addEventListener("change", (e) => { keadaan.khusus = e.target.checked; muat(); });
  document.getElementById("dash-unduh").addEventListener("click", () => {
    location.href = `/api/ekspor?${new URLSearchParams(paramPeriode(keadaan.data))}`;
  });
  window.bukaDashboard = bukaDashboard;
  if (location.hash.startsWith("#dashboard")) bukaDashboard(location.hash.split("?")[1]);
}
