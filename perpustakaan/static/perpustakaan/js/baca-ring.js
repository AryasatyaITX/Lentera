// Lingkaran waktu baca (dipakai di halaman baca buku DAN jurnal).
// - Terisi hanya saat user aktif membaca (gulir / tombol / sentuh).
// - Berhenti kalau user diam terlalu lama atau tab disembunyikan.
// - Penuh = 2 menit membaca aktif -> +10 EXP. Server yang menghitung dan memvalidasi.
// Cara pakai: taruh <div id="read-ring" data-url=".." data-detik=".." data-total="120"></div>
// di halaman baca, lalu muat file ini. Komponen menggambar dirinya sendiri.
(function () {
    'use strict';

    const host = document.getElementById('read-ring');
    if (!host) return;

    const URL_BEAT = host.dataset.url;
    const TOTAL = parseInt(host.dataset.total || '120', 10);
    const IDLE_MS = 30000;      // diam lebih dari 30 detik -> lingkaran berhenti
    const BEAT_EVERY = 10;      // kirim ke server tiap 10 detik aktif

    let pool = Math.min(TOTAL, Math.max(0, parseInt(host.dataset.detik || '0', 10) || 0));
    let pending = 0;            // detik aktif yang belum dikirim
    let busy = false;
    let lastBeat = 0;           // kapan terakhir kirim ke server
    let lastAct = 0;            // 0 = belum ada aktivitas, mulai dalam keadaan berhenti
    let overFrame = false;      // kursor di atas iframe (aktivitas di dalam iframe tidak terdeteksi)

    // ---------- Tampilan ----------
    const R = 28;
    const C = 2 * Math.PI * R;
    const css = `
#read-ring{position:fixed;right:24px;bottom:24px;width:64px;height:64px;z-index:60;border-radius:50%;background:rgba(23,60,58,.94);box-shadow:0 8px 24px rgba(0,0,0,.3);display:flex;align-items:center;justify-content:center;transition:opacity .3s}
#read-ring svg.rr-ring{position:absolute;inset:0;width:100%;height:100%;transform:rotate(-90deg)}
#read-ring .rr-track{fill:none;stroke:rgba(212,248,56,.18);stroke-width:4}
#read-ring .rr-bar{fill:none;stroke:#D4F838;stroke-width:4;stroke-linecap:round;transition:stroke-dashoffset .9s linear,stroke .3s}
#read-ring .rr-book{position:relative;width:24px;height:24px;color:#D4F838;transition:color .3s}
#read-ring.rr-paused{opacity:.8}
#read-ring.rr-paused .rr-bar{stroke:#7F9A8F}
#read-ring.rr-paused .rr-book{color:#9FB3AB}
#read-ring.rr-active .rr-book{animation:rr-pulse 1.8s ease-in-out infinite}
@keyframes rr-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.14)}}
#read-ring .rr-tip{position:absolute;right:76px;top:50%;transform:translateY(-50%);white-space:nowrap;background:#173C3A;color:#fff;font:600 12px 'Plus Jakarta Sans',sans-serif;padding:8px 12px;border-radius:10px;opacity:0;pointer-events:none;transition:opacity .2s}
#read-ring:hover .rr-tip{opacity:1}
#read-ring .rr-gain{position:absolute;right:76px;top:50%;transform:translateY(-50%) scale(.9);white-space:nowrap;background:#D4F838;color:#121824;font:800 14px 'Plus Jakarta Sans',sans-serif;padding:10px 16px;border-radius:999px;box-shadow:0 8px 24px rgba(18,24,36,.3);opacity:0;pointer-events:none;transition:.3s}
#read-ring .rr-gain.show{opacity:1;transform:translateY(-50%) scale(1)}
`;
    const st = document.createElement('style');
    st.textContent = css;
    document.head.appendChild(st);

    host.innerHTML = `
        <svg class="rr-ring" viewBox="0 0 64 64" aria-hidden="true">
            <circle class="rr-track" cx="32" cy="32" r="${R}"></circle>
            <circle class="rr-bar" cx="32" cy="32" r="${R}" stroke-dasharray="${C}" stroke-dashoffset="${C}"></circle>
        </svg>
        <svg class="rr-book" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path>
            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path>
        </svg>
        <span class="rr-gain" id="rr-gain"></span>
        <span class="rr-tip" id="rr-tip"></span>`;
    host.classList.add('rr-paused');

    const bar = host.querySelector('.rr-bar');
    const tip = document.getElementById('rr-tip');
    const gainEl = document.getElementById('rr-gain');
    const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    let active = false;

    function draw() {
        bar.style.strokeDashoffset = String(C * (1 - pool / TOTAL));
        bar.style.opacity = pool > 0 ? '1' : '0';   // kosong benar-benar kosong (tanpa titik)
        tip.textContent = (active ? 'Sedang membaca' : 'Dijeda, gulir untuk lanjut')
            + ` • ${mmss(pool)} / ${mmss(TOTAL)} • +10 EXP`;
    }
    function setActive(on) {
        if (on === active) return;
        active = on;
        host.classList.toggle('rr-active', on);
        host.classList.toggle('rr-paused', !on);
        draw();
    }
    function showGain(n) {
        gainEl.textContent = `+${n} EXP`;
        gainEl.classList.add('show');
        setTimeout(() => gainEl.classList.remove('show'), 2800);
    }
    draw();

    // ---------- Deteksi aktivitas ----------
    const mark = () => { lastAct = Date.now(); };
    const EVENTS = ['scroll', 'wheel', 'keydown', 'touchstart', 'touchmove', 'pointerdown'];
    EVENTS.forEach((ev) => document.addEventListener(ev, mark, { capture: true, passive: true }));

    // Kursor di atas iframe: kejadian di dalam iframe tidak sampai ke halaman ini.
    document.addEventListener('mouseover', (e) => {
        overFrame = !!(e.target && e.target.tagName === 'IFRAME');
    }, true);

    // Iframe satu domain (mis. PDF di /media/): coba pasang pendeteksi di dalamnya juga.
    function hookIframe(f) {
        if (f.dataset.rrHook) return;
        f.dataset.rrHook = '1';
        const attach = () => {
            try {
                const doc = f.contentWindow && f.contentWindow.document;
                if (!doc) return;
                EVENTS.forEach((ev) => doc.addEventListener(ev, mark, { capture: true, passive: true }));
            } catch (e) { /* beda domain: tidak bisa, abaikan */ }
        };
        f.addEventListener('load', attach);
        attach();
    }

    function isActive() {
        if (document.hidden) return false;
        if (Date.now() - lastAct < IDLE_MS) return true;
        return overFrame;
    }

    // ---------- Server ----------
    function getCookie(name) {
        const m = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
        return m ? decodeURIComponent(m[1]) : '';
    }
    async function beat() {
        if (busy || pending <= 0) return;
        busy = true;
        lastBeat = Date.now();
        const send = pending;
        pending = 0;
        try {
            const res = await fetch(URL_BEAT, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
                body: new URLSearchParams({ detik: send }),
            });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const r = await res.json();
            pool = Math.min(TOTAL, (r.detik || 0) + pending);
            if (r.exp_gain > 0) {
                bar.style.transition = 'none';   // reset lingkaran tanpa animasi mundur
                draw();
                void bar.getBoundingClientRect();
                bar.style.transition = '';
                showGain(r.exp_gain);
            } else {
                draw();
            }
        } catch (e) {
            pending += send;                     // gagal kirim: coba lagi nanti
        } finally {
            busy = false;
        }
    }
    function flush() {
        // Dipanggil saat tab disembunyikan/ditutup agar sisa detik tidak hilang.
        if (pending <= 0 || !navigator.sendBeacon) return;
        const body = new URLSearchParams({ detik: pending, csrfmiddlewaretoken: getCookie('csrftoken') });
        if (navigator.sendBeacon(URL_BEAT, body)) pending = 0;
    }
    document.addEventListener('visibilitychange', () => { if (document.hidden) flush(); });
    window.addEventListener('pagehide', flush);

    // Saat mode layar penuh, pindahkan lingkaran ke dalam elemen layar penuh agar tetap terlihat.
    document.addEventListener('fullscreenchange', () => {
        (document.fullscreenElement || document.body).appendChild(host);
    });

    // ---------- Detak per detik ----------
    setInterval(() => {
        document.querySelectorAll('iframe').forEach(hookIframe);
        const on = isActive();
        setActive(on);
        if (!on) return;
        if (pool < TOTAL) pool += 1;
        pending += 1;
        draw();
        const penuh = pool >= TOTAL && Date.now() - lastBeat > 3000;   // jangan tunggu 10 detik saat sudah penuh
        if (pending >= BEAT_EVERY || penuh) beat();
    }, 1000);
})();