(function () {
  // ---------- Sidebar: memakai class .sidebar-open dari style.css ----------
  var layout = document.getElementById("app-layout");
  var btn = document.getElementById("menu-button");

  if (layout && btn) {
    btn.addEventListener("click", function () {
      var open = layout.classList.toggle("sidebar-open");
      btn.setAttribute("aria-expanded", String(open));
    });
  }

  // ---------- Grafik 7 hari ----------
  var canvas = document.getElementById("chart-aktivitas");
  var dataEl = document.getElementById("data-grafik");
  if (!canvas || !dataEl || typeof Chart === "undefined") return;

  var d = JSON.parse(dataEl.textContent);
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function garis(label, data, warna) {
    return {
      label: label,
      data: data,
      borderColor: warna,
      backgroundColor: warna,
      borderWidth: 2,
      tension: 0.35,
      pointRadius: 3,
      pointHoverRadius: 5,
    };
  }

  new Chart(canvas, {
    type: "line",
    data: {
      labels: d.labels,
      datasets: [
        garis("Peminjaman", d.pinjam, "#F2C94C"),
        garis("Pengembalian", d.kembali, "#173C3A"),
      ],
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
          ticks: { color: "#8A8A7A", font: { size: 11 } },
        },
        y: {
          beginAtZero: true,
          ticks: { precision: 0, color: "#8A8A7A", font: { size: 11 } },
          grid: { color: "#F0F0E6" },
        },
      },
    },
  });
})();