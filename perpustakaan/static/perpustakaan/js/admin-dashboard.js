/* =====================================================================
   admin-dashboard.js — satu file JavaScript untuk:
     1. Sidebar admin (desktop: buka/tutup, tablet/HP: drawer)
     2. Modal (buka/tutup lewat atribut data-*)
     3. Halaman Kelola Buku, Jurnal & Achievement (konfirmasi hapus, edit, hapus terpilih,
        pratinjau gambar unggahan)
     4. Dashboard admin (grafik 7 hari, bar buku terpopuler)
     5. Halaman Login & Register (kartu kaca, slider, OTP, petunjuk password)

   Setiap bagian hanya jalan kalau elemennya ada di halaman, jadi file ini
   aman dimuat di semua halaman.
   ===================================================================== */
(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var byId = function (id) { return document.getElementById(id); };

  var mobileMq = window.matchMedia("(max-width: 900px)");
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Kunci scroll halaman saat drawer sidebar (HP) atau modal sedang terbuka */
  function refreshLock() {
    var layout = byId("app-layout");
    var drawer = !!layout && layout.classList.contains("sidebar-open") && mobileMq.matches;
    var modal = !!$(".kelola-modal.open");
    document.body.classList.toggle("adm-lock", drawer || modal);
  }

  /* ===================================================================
     1. SIDEBAR ADMIN
     Desktop : pilihan buka/tutup disimpan di browser (localStorage).
     Tablet/HP (<= 900px): sidebar menjadi drawer, selalu mulai tertutup,
     dan pilihan di layar kecil tidak menimpa pilihan desktop.
     =================================================================== */
  function initSidebar() {
    var layout = byId("app-layout");
    var btn = byId("menu-button");
    if (!layout || !btn) return;

    var backdrop = byId("sidebarBackdrop");
    var KEY = "lentera-admin-sidebar";

    function baca() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
    function simpan(v) { try { localStorage.setItem(KEY, v); } catch (e) { /* abaikan */ } }

    function set(open) {
      layout.classList.toggle("sidebar-open", open);
      btn.setAttribute("aria-expanded", String(open));
      refreshLock();
    }
    function keadaanAwal() { set(mobileMq.matches ? false : baca() !== "closed"); }

    keadaanAwal();
    requestAnimationFrame(function () { layout.classList.remove("no-anim"); });

    btn.addEventListener("click", function () {
      var open = !layout.classList.contains("sidebar-open");
      set(open);
      if (!mobileMq.matches) simpan(open ? "open" : "closed");
    });

    if (backdrop) backdrop.addEventListener("click", function () { set(false); });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && mobileMq.matches && layout.classList.contains("sidebar-open")) set(false);
    });

    $$(".adm-sidebar .sidebar-menu a").forEach(function (a) {
      a.addEventListener("click", function () { if (mobileMq.matches) set(false); });
    });

    /* Layar diputar / jendela diubah ukurannya melewati batas tablet */
    if (mobileMq.addEventListener) mobileMq.addEventListener("change", keadaanAwal);
    else if (mobileMq.addListener) mobileMq.addListener(keadaanAwal);
  }

  /* ===================================================================
     2. MODAL
     Buka   : <button data-modal-open="idModal">
     Tutup  : <button data-modal-close>, klik area gelap, atau tombol Esc
     =================================================================== */
  var pembukaTerakhir = null;

  function bukaModal(id) {
    var m = byId(id);
    if (!m) return;
    m.classList.add("open");
    refreshLock();
  }
  function tutupModal(m) {
    if (!m) return;
    m.classList.remove("open");
    refreshLock();
    if (pembukaTerakhir && document.contains(pembukaTerakhir)) {
      try { pembukaTerakhir.focus(); } catch (e) { /* abaikan */ }
    }
    pembukaTerakhir = null;
  }

  function initModals() {
    document.addEventListener("click", function (e) {
      var buka = e.target.closest("[data-modal-open]");
      if (buka) {
        pembukaTerakhir = buka;
        bukaModal(buka.getAttribute("data-modal-open"));
        return;
      }
      var tutup = e.target.closest("[data-modal-close]");
      if (tutup) {
        tutupModal(tutup.closest(".kelola-modal"));
        return;
      }
      if (e.target.classList && e.target.classList.contains("kelola-modal")) tutupModal(e.target);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      var terbuka = $$(".kelola-modal.open");
      if (terbuka.length) tutupModal(terbuka[terbuka.length - 1]);
    });
  }

  /* ===================================================================
     3. HALAMAN KELOLA BUKU & JURNAL
     =================================================================== */
  function initKelola() {
    /* ---- 3a. Konfirmasi hapus satuan: <form data-confirm-delete> ---- */
    var modalHapus = byId("modalHapus");
    if (modalHapus) {
      var targetHapus = null;
      var namaEl = byId("hapusNama");

      document.addEventListener("submit", function (e) {
        var form = e.target;
        if (!form.matches || !form.matches("[data-confirm-delete]")) return;
        e.preventDefault();
        targetHapus = form;
        var baris = form.closest("tr");
        var judul = baris && baris.querySelector(".t");
        namaEl.textContent = judul ? "\u201C" + judul.textContent.trim() + "\u201D" : "Item ini";
        bukaModal("modalHapus");
      });

      byId("hapusYa").addEventListener("click", function () {
        if (targetHapus) targetHapus.submit();   // submit() tidak memicu event lagi
      });
      modalHapus.addEventListener("click", function (e) {
        if (e.target.closest("[data-modal-close]")) targetHapus = null;
      });
    }

    /* ---- 3b. Edit: isi form dari atribut data-* tombol pensil ---- */
    var formEdit = byId("formEdit");
    if (formEdit) {
      document.addEventListener("click", function (e) {
        var btn = e.target.closest(".btn-edit");
        if (!btn) return;
        pembukaTerakhir = btn;
        formEdit.reset();
        Object.keys(btn.dataset).forEach(function (key) {
          if (key === "url") { formEdit.action = btn.dataset.url; return; }
          var el = formEdit.elements[key];
          if (!el) return;
          if (el.type === "file") {            // input file tidak bisa diisi: tampilkan gambar lama sebagai pratinjau
            var pembungkus = el.closest(".acv-upload");
            var kotak = pembungkus && $(".acv-upload-box", pembungkus);
            if (kotak) { kotak.dataset.asli = btn.dataset[key]; setPreview(kotak, btn.dataset[key]); }
            return;
          }
          var nilai = btn.dataset[key];
          if (el.tagName === "SELECT" && nilai &&
              !Array.prototype.some.call(el.options, function (o) { return o.value === nilai; })) {
            el.add(new Option(nilai, nilai));   // kategori lama yang tidak ada di daftar
          }
          el.value = nilai;
        });
        bukaModal("modalEdit");
      });
    }

    /* ---- 3c. Pilih banyak + hapus terpilih ---- */
    var semua = byId("checkAll");
    var bar = byId("bulkBar");
    if (semua && bar) {
      var hitung = byId("bulkCount");

      var barisCek = function () { return $$(".row-check"); };
      var segarkan = function () {
        var cek = barisCek();
        var n = cek.filter(function (c) { return c.checked; }).length;
        bar.classList.toggle("show", n > 0);
        hitung.textContent = n;
        semua.checked = n > 0 && n === cek.length;
        semua.indeterminate = n > 0 && n < cek.length;
      };

      semua.addEventListener("change", function () {
        barisCek().forEach(function (c) { c.checked = semua.checked; });
        segarkan();
      });
      barisCek().forEach(function (c) { c.addEventListener("change", segarkan); });

      byId("bulkClear").addEventListener("click", function () {
        barisCek().forEach(function (c) { c.checked = false; });
        segarkan();
      });
      byId("bulkDel").addEventListener("click", function () {
        pembukaTerakhir = byId("bulkDel");
        byId("massalJumlah").textContent = hitung.textContent + " " + bar.dataset.satuan;
        bukaModal("modalHapusMassal");
      });
      byId("massalYa").addEventListener("click", function () {
        byId("formHapusMassal").submit();
      });
      segarkan();
    }
  }

  /* ===================================================================
     3b. PRATINJAU GAMBAR UNGGAHAN (Kelola Achievement)
     =================================================================== */
  function setPreview(kotak, src) {
    var img = $(".acv-preview", kotak);
    var ikon = $(".acv-ph", kotak);
    if (!img) return;
    if (src) {
      img.src = src;
      img.classList.remove("is-hidden");
      if (ikon) ikon.classList.add("is-hidden");
    } else {
      img.removeAttribute("src");
      img.classList.add("is-hidden");
      if (ikon) ikon.classList.remove("is-hidden");
    }
  }

  function initUploadPreview() {
    document.addEventListener("change", function (e) {
      var input = e.target;
      if (!input.matches || !input.matches(".acv-upload input[type=file]")) return;
      var kotak = $(".acv-upload-box", input.closest(".acv-upload"));
      if (!kotak) return;
      if (input._url) { URL.revokeObjectURL(input._url); input._url = null; }
      var berkas = input.files && input.files[0];
      if (berkas) {
        input._url = URL.createObjectURL(berkas);
        setPreview(kotak, input._url);
      } else {
        setPreview(kotak, kotak.dataset.asli || "");   // dibatalkan: kembali ke gambar lama
      }
    });
  }

  /* ===================================================================
     4. DASHBOARD ADMIN
     =================================================================== */
  function initDashboard() {
    /* Lebar bar buku terpopuler (nilai dari server lewat data-width) */
    $$(".adm-bar span[data-width]").forEach(function (el) {
      el.style.setProperty("--width", el.getAttribute("data-width") + "%");
    });

    /* Grafik 7 hari */
    var canvas = byId("chart-aktivitas");
    var dataEl = byId("data-grafik");
    if (!canvas || !dataEl || typeof Chart === "undefined") return;

    var d = JSON.parse(dataEl.textContent);
    var kecil = window.matchMedia("(max-width: 600px)").matches;   // HP: huruf & titik lebih kecil

    function garis(label, data, warna) {
      return {
        label: label,
        data: data,
        borderColor: warna,
        backgroundColor: warna,
        borderWidth: 2,
        tension: 0.35,
        pointRadius: kecil ? 2 : 3,
        pointHoverRadius: 5
      };
    }

    new Chart(canvas, {
      type: "line",
      data: {
        labels: d.labels,
        datasets: [
          garis("Peminjaman", d.pinjam, "#F2C94C"),
          garis("Pengembalian", d.kembali, "#173C3A")
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: reduceMotion ? false : { duration: 600 },
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#8A8A7A", font: { size: kecil ? 10 : 11 }, autoSkip: true, maxRotation: 0 }
          },
          y: {
            beginAtZero: true,
            ticks: { precision: 0, color: "#8A8A7A", font: { size: kecil ? 10 : 11 } },
            grid: { color: "#F0F0E6" }
          }
        }
      }
    });
  }

  /* ===================================================================
     5. HALAMAN LOGIN & REGISTER
     =================================================================== */
  /* Centang otomatis syarat password saat mengetik */
  function initPwRules(inputId, listId) {
    var input = byId(inputId);
    var items = $$("#" + listId + " li");
    if (!input || !items.length) return;

    function cek() {
      var v = input.value;
      var ok = {
        len: v.length >= 8 && v.length <= 20,
        upper: /[A-Z]/.test(v),
        special: /[^A-Za-z0-9]/.test(v)
      };
      items.forEach(function (li) { li.classList.toggle("ok", !!ok[li.dataset.rule]); });
    }
    input.addEventListener("input", cek);
    cek();
  }

  function initAuth() {
    if (!document.body.classList.contains("auth-body")) return;

    /* Logo gagal dimuat -> tampilkan ikon cadangan */
    var logo = $(".brand-logo img");
    var cadangan = $(".fallback-icon");
    if (logo && cadangan) {
      logo.addEventListener("error", function () {
        logo.classList.add("is-hidden");
        cadangan.classList.remove("is-hidden");
      });
    }

    /* Mata: tampilkan / sembunyikan password */
    function togglePass(icon) {
      var input = byId(icon.getAttribute("data-target"));
      if (!input) return;
      input.setAttribute("type", input.getAttribute("type") === "password" ? "text" : "password");
      icon.classList.toggle("fa-eye");
      icon.classList.toggle("fa-eye-slash");
    }
    document.addEventListener("click", function (e) {
      var icon = e.target.closest(".toggle-password");
      if (icon) togglePass(icon);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var icon = e.target.closest && e.target.closest(".toggle-password");
      if (icon) { e.preventDefault(); togglePass(icon); }
    });

    /* Beralih dari form login ke Pemulihan Akun */
    var loginBox = byId("loginFormBox");
    var forgotBox = byId("forgotFormBox");
    var lupa = $("[data-action='show-forgot']");
    if (lupa && loginBox && forgotBox) {
      lupa.addEventListener("click", function (e) {
        e.preventDefault();
        loginBox.classList.add("is-hidden");
        forgotBox.classList.remove("is-hidden");
        var email = byId("resetEmail");
        if (email && !mobileMq.matches) email.focus();
      });
    }

    /* Login: dashboard admin dimulai dengan sidebar tertutup */
    var loginForm = byId("loginForm");
    if (loginForm) {
      loginForm.addEventListener("submit", function () {
        try { localStorage.setItem("lentera-admin-sidebar", "closed"); } catch (e) { /* abaikan */ }
      });
    }

    /* Ingat Saya (menyimpan NIM di browser) */
    var usernameInput = byId("usernameInput");
    var ingat = byId("rememberMeCheckbox");
    if (loginForm && usernameInput && ingat) {
      var tersimpan = null;
      try { tersimpan = localStorage.getItem("lentera_remembered_username"); } catch (e) { /* abaikan */ }
      if (tersimpan) {
        usernameInput.value = tersimpan;
        ingat.checked = true;
      }
      loginForm.addEventListener("submit", function () {
        try {
          if (ingat.checked) localStorage.setItem("lentera_remembered_username", usernameInput.value);
          else localStorage.removeItem("lentera_remembered_username");
        } catch (e) { /* abaikan */ }
      });
    }

    /* Petunjuk password (reset password & register) */
    initPwRules("newPassword", "resetPwRules");
    initPwRules("regPassword", "regPwRules");

    /* Hitung mundur tombol "Kirim ulang kode" */
    var resendBtn = byId("resendBtn");
    if (resendBtn) {
      var sisa = parseInt(resendBtn.dataset.jeda, 10) || 0;
      var asli = resendBtn.textContent;
      if (sisa > 0) {
        resendBtn.disabled = true;
        resendBtn.textContent = asli + " (" + sisa + ")";
        var timer = setInterval(function () {
          sisa--;
          if (sisa <= 0) {
            clearInterval(timer);
            resendBtn.disabled = false;
            resendBtn.textContent = asli;
          } else {
            resendBtn.textContent = asli + " (" + sisa + ")";
          }
        }, 1000);
      }
    }

    /* Slider foto & kutipan di panel kiri */
    var slides = $$(".slide-item");
    var quotes = $$(".quote-content");
    var dots = $$(".dot");
    if (slides.length && quotes.length === slides.length) {
      var sekarang = 0;
      var setSlide = function (i) {
        [slides, quotes, dots].forEach(function (daftar) {
          if (daftar[sekarang]) daftar[sekarang].classList.remove("active");
          if (daftar[i]) daftar[i].classList.add("active");
        });
        sekarang = i;
      };
      dots.forEach(function (dot, i) {
        dot.addEventListener("click", function () { setSlide(i); });
      });
      if (!reduceMotion) {
        setInterval(function () { setSlide((sekarang + 1) % slides.length); }, 4500);
      }
    }
  }

  /* ===================================================================
     MULAI
     =================================================================== */
  function init() {
    initSidebar();
    initModals();
    initKelola();
    initUploadPreview();
    initDashboard();
    initAuth();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();