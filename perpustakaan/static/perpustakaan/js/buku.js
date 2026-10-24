// Katalog (infinite scroll), halaman detail, halaman baca, dan bookmark.
// Data buku Open Library diambil LANGSUNG dari browser. Django hanya menyimpan
// pinjam/bookmark. Dibungkus IIFE supaya tidak bentrok dengan nama di script.js.
(function () {
    'use strict';

    // CSS pembaca PDF disuntikkan oleh JS sendiri, jadi tidak bergantung pada baca.html.
    const PV_CSS = `
.reader-stage.pdf-mode{display:flex!important;flex-direction:column!important;align-items:stretch!important;justify-content:flex-start!important;background:#F3F4EE!important;overflow:hidden!important;min-height:0}
.pv-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:14px 20px 0;padding:10px 14px;background:#fff;border:1px solid #E4E6DC;border-radius:16px;flex:none}
.pv-group{display:flex;align-items:center;gap:8px;padding:4px 12px;background:#fff;border:1px solid #ECEEE4;border-radius:999px}
.pv-group button{width:36px;height:36px;border:0;border-radius:50%;background:transparent;color:#121824;font-size:16px;cursor:pointer;transition:.2s}
.pv-group button:hover:not(:disabled){background:#D4F838}
.pv-group button:disabled{opacity:.3;cursor:default}
.pv-group input[type=range]{width:130px;accent-color:#1a3c3c}
.pv-pct{min-width:46px;text-align:center;font-weight:700;font-size:14px;color:#121824}
.pv-pageinfo{display:flex;align-items:center;gap:6px;font-weight:700;font-size:14px;color:#121824}
.pv-pageinfo input{width:52px;height:32px;text-align:center;border:1px solid #E4E6DC;border-radius:8px;font:700 14px 'Plus Jakarta Sans',sans-serif;color:#121824;background:#fff}
.pv-read{font-size:13px;font-weight:600;color:#6A6A5C;padding:0 6px;white-space:nowrap}
.pv-progress{height:3px;margin:12px 20px 0;background:#E4E6DC;border-radius:3px;overflow:hidden;flex:none}
.pv-progress div{height:100%;width:0;background:#D4F838;transition:width .3s}
.pv-scroll{overflow:auto;position:relative;padding:20px 24px 60px;flex:none}
.pv-pages{display:flex;flex-direction:column;align-items:center;gap:16px;width:max-content;min-width:100%}
.pv-page{flex:none;background:#fff;box-shadow:0 6px 24px rgba(18,24,36,.14);overflow:hidden}
.pv-page canvas{display:block;width:100%;height:100%}
.pv-toast{position:fixed;right:24px;bottom:104px;background:#D4F838;color:#121824;font:700 14px 'Plus Jakarta Sans',sans-serif;padding:12px 18px;border-radius:999px;box-shadow:0 8px 24px rgba(18,24,36,.25);opacity:0;transform:translateY(12px);transition:.3s;z-index:50;pointer-events:none}
.pv-toast.show{opacity:1;transform:none}
.pv-group button.pv-mode{width:auto;padding:0 14px;border-radius:999px;display:flex;align-items:center;gap:8px;font:700 13px 'Plus Jakarta Sans',sans-serif}
.pv-single .pv-page{display:none}
.pv-single .pv-page.cur{display:block}
.pv-single.pv-pages{justify-content:center;min-height:100%}
`;
    function injectPdfStyles() {
        if (document.getElementById('pv-style')) return;
        const st = document.createElement('style');
        st.id = 'pv-style';
        st.textContent = PV_CSS;
        document.head.appendChild(st);
    }

    // ---------- Util ----------
    function escHtml(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
            ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }
    function getCookie(name) {
        const m = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
        return m ? decodeURIComponent(m[1]) : '';
    }
    function readJson(id) {
        const el = document.getElementById(id);
        try { return el ? JSON.parse(el.textContent) : null; } catch (e) { return null; }
    }
    async function postForm(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            body: new URLSearchParams(data || {}),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
    }

    // ---------- Klien Open Library ----------
    function coverUrl(id, size) {
        return id ? `https://covers.openlibrary.org/b/id/${id}-${size}.jpg` : '';
    }
    function normalize(doc) {
        return {
            olid: (doc.key || '').split('/').pop(),
            judul: doc.title || 'Tanpa judul',
            penulis: (doc.author_name || ['Unknown']).slice(0, 2).join(', '),
            tahun: doc.first_publish_year || '',
            cover: coverUrl(doc.cover_i, 'M'),
            cover_besar: coverUrl(doc.cover_i, 'L'),
            rating: typeof doc.ratings_average === 'number' && Number.isFinite(doc.ratings_average)
                ? Math.round(doc.ratings_average * 10) / 10
                : null,
            want: typeof doc.want_to_read_count === 'number' && Number.isFinite(doc.want_to_read_count)
                ? doc.want_to_read_count
                : null,
            akses: doc.ebook_access || '',          // 'public' = bisa dibaca gratis
            deskripsi: '',
            subjek: [],
        };
    }
    // Hasil dicache di sessionStorage (15 menit); permintaan yang menggantung > 15 detik dibatalkan.
    const CACHE_TTL = 15 * 60 * 1000;
    async function olGet(path, params) {
        const qs = new URLSearchParams(params).toString();
        const key = 'ol:' + path + '?' + qs;
        try {
            const raw = sessionStorage.getItem(key);
            if (raw) {
                const o = JSON.parse(raw);
                if (Date.now() - o.t < CACHE_TTL) return o.d;
            }
        } catch (e) { /* cache rusak: abaikan */ }

        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 15000);
        let data;
        try {
            const res = await fetch(`${OL}${path}?${qs}`, { signal: ctrl.signal });
            if (!res.ok) throw new Error('Open Library HTTP ' + res.status);
            data = await res.json();
        } finally {
            clearTimeout(timer);
        }
        try { sessionStorage.setItem(key, JSON.stringify({ t: Date.now(), d: data })); } catch (e) { /* penuh: abaikan */ }
        return data;
    }
    async function olSearch(q, page, limit, sort) {
        const params = { q, fields: FIELDS, limit, page };
        if (sort) params.sort = sort;
        const data = await olGet('/search.json', params);
        const books = (data.docs || []).map(normalize).filter(b => /^OL\d+W$/.test(b.olid));
        const total = data.numFound || data.num_found || 0;
        return { books, total, hasMore: page * limit < total };
    }
    function cleanDescription(d) {
        if (d && typeof d === 'object') d = d.value;
        if (typeof d !== 'string') return '';
        return d.split('----------')[0]
            .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
            .replace(/\(\[source\]\[\d+\]\)/g, '')
            .trim();
    }
    async function olBook(olid) {
        const r = await olSearch(`key:/works/${olid}`, 1, 1);
        if (!r.books.length) { const e = new Error('notfound'); e.notfound = true; throw e; }
        const book = r.books[0];
        try {
            const work = await olGet(`/works/${olid}.json`, {});
            book.deskripsi = cleanDescription(work.description);
            book.subjek = (work.subjects || []).filter(s => typeof s === 'string').slice(0, 8);
        } catch (e) { /* detail tetap tampil tanpa deskripsi */ }
        return book;
    }

    async function hydrateBookmarkStats() {
        const cards = Array.from(document.querySelectorAll('[data-bookmark-stats]'));
        await Promise.all(cards.map(async (card) => {
            const ratingEl = card.querySelector('[data-book-rating]');
            const wantEl = card.querySelector('[data-book-want]');
            try {
                const result = await olSearch(`key:/works/${card.dataset.olid}`, 1, 1);
                const book = result.books.find(item => item.olid === card.dataset.olid);
                if (!book) throw new Error('Book not found in Open Library response');

                ratingEl.textContent = book.rating === null ? 'Belum ada rating' : book.rating.toFixed(1);
                wantEl.textContent = book.want === null
                    ? ' • Jumlah ingin membaca tidak tersedia'
                    : ` • ${new Intl.NumberFormat('id-ID').format(book.want)} ingin membaca`;
            } catch (error) {
                ratingEl.textContent = 'Data tidak tersedia';
                wantEl.textContent = '';
            }
        }));
    }
    hydrateBookmarkStats();

    // ---------- Bookmark ----------
    const bookCache = new Map();                    // olid -> data buku, dikirim ke Django saat bookmark
    const tersimpan = new Set(readJson('tersimpan-ids') || []);

    function bookPayload(b) {
        return { judul: b.judul, penulis: b.penulis, tahun: b.tahun, cover: b.cover, deskripsi: b.deskripsi || '' };
    }
    function setHeart(el, on) {
        el.classList.toggle('active', on);
        el.classList.toggle('fas', on);
        el.classList.toggle('far', !on);
        el.title = on ? 'Hapus dari bookmark' : 'Simpan ke bookmark';
    }
    async function toggleHeart(el) {
        if (el.dataset.busy) return;
        el.dataset.busy = '1';
        const olid = el.closest('[data-olid]').dataset.olid;
        try {
            const data = await postForm(`/buku/${olid}/bookmark/`, bookPayload(bookCache.get(olid) || {}));
            setHeart(el, data.bookmarked);
            if (data.bookmarked) tersimpan.add(olid); else tersimpan.delete(olid);
        } catch (e) {
            alert('Bookmark gagal disimpan. Coba lagi sebentar lagi.');
        } finally {
            delete el.dataset.busy;
        }
    }

    // ---------- Klik kartu -> detail; klik hati -> bookmark ----------
    document.addEventListener('click', (e) => {
        const heart = e.target.closest('.heart[data-toggle-bookmark]');
        if (heart) { e.preventDefault(); e.stopPropagation(); toggleHeart(heart); return; }
        if (e.target.closest('.heart')) return; // hati lama (halaman bookmarks) punya handler sendiri
        const card = e.target.closest('.book-card[data-olid]');
        if (!card) return;
        const url = `/buku/${card.dataset.olid}/`;
        if (e.ctrlKey || e.metaKey) window.open(url, '_blank'); else window.location.href = url;
    });
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        const card = e.target.closest && e.target.closest('.book-card[data-olid]');
        if (card && e.target === card) window.location.href = `/buku/${card.dataset.olid}/`;
    });

    function cardHtml(b, withHeart) {
        const rating = b.rating === null ? '-' : b.rating.toFixed(1);
        const want = b.want === null ? '—' : new Intl.NumberFormat('id-ID').format(b.want);
        const tahun = b.tahun ? ` • ${escHtml(b.tahun)}` : '';
        const on = tersimpan.has(b.olid);
        return `
        <div class="book-card" data-olid="${escHtml(b.olid)}" tabindex="0" role="link" aria-label="${escHtml(b.judul)}">
            <img src="${escHtml(b.cover || NO_COVER)}" alt="Sampul ${escHtml(b.judul)}" class="book-cover" loading="lazy"
                onerror="this.onerror=null;this.src='${NO_COVER}'">
            <div class="book-info">
                <p class="type">Buku Digital${b.akses === 'public' ? ' <span class="badge-free">Bisa dibaca</span>' : ''}</p>
                <h3>${escHtml(b.judul)}</h3>
                <p class="author">${escHtml(b.penulis)}${tahun}</p>
                <span class="book-rating"><i class="fas fa-star"></i> ${rating} • <i class="fas fa-bookmark"></i> ${want}</span>
                ${withHeart ? `<i class="${on ? 'fas active' : 'far'} fa-heart heart" data-toggle-bookmark title="${on ? 'Hapus dari bookmark' : 'Simpan ke bookmark'}"></i>` : ''}
            </div>
        </div>`;
    }

    // ---------- Halaman detail ----------
    const page = document.getElementById('bd-page');
    if (page) initDetail(page.dataset.olid);

    function initDetail(olid) {
        const $ = (id) => document.getElementById(id);
        // Setter aman: tidak error kalau elemennya tidak ada di template.
        const setText = (id, text) => { const el = $(id); if (el) el.textContent = text; };
        let current = null;

        // Buku manual dari admin (BK-xxxx) bukan ID Open Library, jadi jangan dicari ke sana.
        const isOpenLibraryId = /^OL\d+W$/.test(olid);

        const bmBtn = $('bm-btn');
        if (bmBtn) bmBtn.addEventListener('click', async () => {
            if (bmBtn.disabled) return;
            const aktif = bmBtn.classList.contains('active');
            if (!aktif && !current) { alert('Tunggu data buku selesai dimuat.'); return; }
            bmBtn.disabled = true;
            try {
                const data = await postForm(`/buku/${olid}/bookmark/`, current ? bookPayload(current) : {});
                bmBtn.classList.toggle('active', data.bookmarked);
                bmBtn.querySelector('i').className = (data.bookmarked ? 'fas' : 'far') + ' fa-heart';
                bmBtn.querySelector('span').textContent = data.bookmarked ? 'Tersimpan' : 'Simpan';
            } catch (e) {
                alert('Bookmark gagal disimpan. Coba lagi sebentar lagi.');
            } finally { bmBtn.disabled = false; }
        });

        function render(b) {
            current = b;
            document.title = b.judul;
            setText('bd-title', b.judul);
            setText('bd-author', b.penulis + (b.tahun ? `, pertama terbit ${b.tahun}` : ''));

            const cover = $('bd-cover');
            if (cover) {
                cover.alt = 'Sampul ' + b.judul;
                const src = b.cover_besar || b.cover;
                if (src) { cover.onerror = () => { cover.onerror = null; cover.src = NO_COVER; }; cover.src = src; }
            }

            const stats = $('bd-stats');
            if (stats) {
                const count = Number(stats.dataset.readCount || 0);
                stats.innerHTML =
                    `<span><i class="fas fa-eye"></i> ${new Intl.NumberFormat('id-ID').format(count)}x Dibaca</span>`;
            }

            const desc = $('bd-desc');
            if (desc) {
                if (b.deskripsi) { desc.textContent = b.deskripsi; desc.style.whiteSpace = 'pre-line'; desc.classList.remove('bd-muted'); }
                else { desc.textContent = isOpenLibraryId ? 'Open Library belum punya deskripsi untuk buku ini.' : 'Belum ada deskripsi untuk buku ini.'; }
            }

            setText('bd-dl-author', b.penulis);
            setText('bd-dl-year', b.tahun || '-');

            const tags = $('bd-tags'), tagsWrap = $('bd-subjects-wrap');
            if (tags && tagsWrap && b.subjek && b.subjek.length) {
                tags.innerHTML = b.subjek.map(s => `<span>${escHtml(s)}</span>`).join('');
                tagsWrap.hidden = false;
            }

            const form = $('pinjam-form');
            if (form) {
                const p = bookPayload(b);
                Object.keys(p).forEach(k => { if (form.elements[k]) form.elements[k].value = p[k] == null ? '' : p[k]; });
                const btn = $('pinjam-btn');
                if (btn) btn.disabled = false;
            }
        }

        async function loadRelated(b) {
            if (!b.subjek || !b.subjek.length) return;
            try {
                const subject = b.subjek[0].replace(/"/g, '');
                const r = await olSearch(`subject:"${subject}"`, 1, 6, 'rating');
                const list = r.books.filter(x => x.olid !== b.olid).slice(0, 5);
                if (!list.length) return;
                list.forEach(x => bookCache.set(x.olid, x));
                const grid = $('bd-related-grid'), wrap = $('bd-related');
                if (!grid || !wrap) return;
                grid.innerHTML = list.map(x => cardHtml(x, false)).join('');
                wrap.hidden = false;
            } catch (e) { /* buku terkait hanya pelengkap */ }
        }

        (async () => {
            const db = readJson('buku-db');
            let book = null;

            if (!isOpenLibraryId && db) {
                // Buku manual: pakai data dari database sendiri, tanpa pesan error.
                book = db;
            } else {
                try {
                    book = await olBook(olid);
                } catch (e) {
                    if (db) {
                        book = db;
                        const err = $('bd-error');
                        if (err) {
                            err.textContent = 'Data terbaru dari Open Library belum bisa dimuat. Menampilkan data yang tersimpan.';
                            err.hidden = false;
                        }
                    } else {
                        setText('bd-title', e.notfound ? 'Buku tidak ditemukan' : 'Buku tidak bisa dimuat');
                        setText('bd-author', '');
                        setText('bd-desc', e.notfound
                            ? 'Open Library tidak punya buku dengan ID ini.'
                            : 'Open Library belum bisa dihubungi dari browsermu. Muat ulang halaman ini beberapa saat lagi.');
                        return;
                    }
                }
            }
            render(book);
            loadRelated(book);
        })();
    }

    // ---------- Halaman baca ----------
    const stage = document.getElementById('reader-stage');
    if (stage) initReader(stage);

    // Notifikasi kecil "+N EXP" saat progres baca menambah EXP.
    function showExpToast(n) {
        const t = document.createElement('div');
        t.className = 'pv-toast';
        t.innerHTML = `<i class="fas fa-bolt"></i> +${n} EXP`;
        document.body.appendChild(t);
        requestAnimationFrame(() => t.classList.add('show'));
        setTimeout(() => {
            t.classList.remove('show');
            setTimeout(() => t.remove(), 300);
        }, 2500);
    }

    // Pembaca PDF bawaan website (PDF.js): scroll bersambung, slider zoom, progres tersimpan.
    async function initPdfReader(stage, url, olid, savedProgress, progressUrl, progressKey) {
        pdfjsLib.GlobalWorkerOptions.workerSrc =
            'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

        injectPdfStyles();
        document.body.style.overflow = 'hidden';
        stage.classList.add('pdf-mode');
        stage.innerHTML = `
            <div class="pv-toolbar">
                <div class="pv-group">
                    <button type="button" id="pv-out" title="Perkecil"><i class="fas fa-magnifying-glass-minus"></i></button>
                    <input type="range" id="pv-slider" min="30" max="250" step="5" value="100" aria-label="Zoom">
                    <span class="pv-pct" id="pv-zoom">100%</span>
                    <button type="button" id="pv-in" title="Perbesar"><i class="fas fa-magnifying-glass-plus"></i></button>
                </div>
                <div class="pv-group">
                    <button type="button" id="pv-prev" title="Halaman sebelumnya"><i class="fas fa-chevron-left"></i></button>
                    <span class="pv-pageinfo"><input id="pv-page" type="number" min="1" value="1" aria-label="Nomor halaman"> / <span id="pv-total">-</span></span>
                    <button type="button" id="pv-next" title="Halaman berikutnya"><i class="fas fa-chevron-right"></i></button>
                </div>
                <div class="pv-group">
                    <span class="pv-read" id="pv-read">0% dibaca</span>
                    <button type="button" id="pv-mode" class="pv-mode" title="Ganti mode baca"><i class="fas fa-arrows-up-down"></i><span>Gulir</span></button>
                    <button type="button" id="pv-full" title="Layar penuh"><i class="fas fa-expand"></i></button>
                </div>
            </div>
            <div class="pv-progress"><div id="pv-bar"></div></div>
            <div class="pv-scroll" id="pv-scroll">
                <div class="pv-pages" id="pv-pages"><div class="reader-msg"><span class="spinner"></span> Memuat buku...</div></div>
            </div>`;

        const $ = (id) => document.getElementById(id);
        const scroller = $('pv-scroll');
        const pagesBox = $('pv-pages');
        const backUrl = stage.dataset.backUrl || `/buku/${olid}/`;

        // Batasi tinggi area scroll sampai dasar layar, supaya pasti bisa di-scroll.
        function fitHeight() {
            const top = scroller.getBoundingClientRect().top;
            scroller.style.height = Math.max(240, window.innerHeight - top) + 'px';
        }
        fitHeight();
        window.addEventListener('resize', fitHeight);
        document.addEventListener('fullscreenchange', () => setTimeout(fitHeight, 50));
        const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

        let pdf;
        try {
            pdf = await pdfjsLib.getDocument(url).promise;
        } catch (e) {
            console.error('Gagal memuat PDF:', e);
            stage.classList.remove('pdf-mode');
            stage.innerHTML = `<div class="reader-msg">Gagal memuat file PDF.<br>
                <a class="btn-kembali" href="${escHtml(backUrl)}">Kembali</a></div>`;
            return;
        }
        const total = pdf.numPages;
        $('pv-total').textContent = total;
        $('pv-page').max = total;

        // Ukuran halaman 1 jadi patokan sebelum halaman lain dirender.
        const first = await pdf.getPage(1);
        const base = first.getViewport({ scale: 1 });
        const sizes = new Array(total + 1).fill(null);
        sizes[1] = { w: base.width, h: base.height };
        const sizeOf = (n) => sizes[n] || sizes[1];

        function fitZoom() {
            const width = scroller.clientWidth || window.innerWidth;
            return clamp(Math.floor(Math.min(width - 48, 900) / base.width * 100), 30, 250);
        }
        let zoom = fitZoom();

        // Kerangka semua halaman (kosong dulu, diisi saat terlihat)
        pagesBox.innerHTML = '';
        const pageEls = [];
        for (let n = 1; n <= total; n++) {
            const d = document.createElement('div');
            d.className = 'pv-page';
            d.dataset.n = n;
            pagesBox.appendChild(d);
            pageEls.push(d);
        }
        function layout() {
            pageEls.forEach((el, i) => {
                const s = sizeOf(i + 1);
                el.style.width = Math.round(s.w * zoom / 100) + 'px';
                el.style.height = Math.round(s.h * zoom / 100) + 'px';
            });
        }
        layout();

        // Render halaman hanya saat mendekati layar, dibuang lagi kalau jauh (hemat memori)
        const visible = new Set();
        const tasks = new Map();
        const rendered = new Map();

        async function renderPage(n) {
            if (rendered.get(n) === zoom) return;
            const old = tasks.get(n);
            if (old) { try { old.cancel(); } catch (e) { /* abaikan */ } }
            const myZoom = zoom;
            try {
                const page = await pdf.getPage(n);
                if (!visible.has(n) || myZoom !== zoom) return;
                const v1 = page.getViewport({ scale: 1 });
                sizes[n] = { w: v1.width, h: v1.height };
                const vp = page.getViewport({ scale: myZoom / 100 });
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                const c = document.createElement('canvas');
                c.width = Math.floor(vp.width * dpr);
                c.height = Math.floor(vp.height * dpr);
                const task = page.render({
                    canvasContext: c.getContext('2d'),
                    viewport: vp,
                    transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null,
                });
                tasks.set(n, task);
                await task.promise;
                if (myZoom !== zoom) return;
                const el = pageEls[n - 1];
                el.style.width = Math.round(vp.width) + 'px';
                el.style.height = Math.round(vp.height) + 'px';
                el.replaceChildren(c);
                rendered.set(n, myZoom);
            } catch (e) { /* render dibatalkan: normal */ }
        }
        function release(n) {
            const t = tasks.get(n);
            if (t) { try { t.cancel(); } catch (e) { /* abaikan */ } tasks.delete(n); }
            rendered.delete(n);
            pageEls[n - 1].replaceChildren();
        }
        const io = new IntersectionObserver((entries) => {
            entries.forEach((en) => {
                const n = Number(en.target.dataset.n);
                if (en.isIntersecting) { visible.add(n); renderPage(n); }
                else { visible.delete(n); release(n); }
            });
        }, { root: scroller, rootMargin: '800px 0px' });
        pageEls.forEach((el) => io.observe(el));

        // Halaman aktif + progres
        const MODE_KEY = 'lentera-mode-baca';
        function loadMode() {
            try { return localStorage.getItem(MODE_KEY) === 'page' ? 'page' : 'scroll'; } catch (e) { return 'scroll'; }
        }
        let mode = loadMode();   // 'scroll' (bawaan) atau 'page'
        let cur = 1, bestPct = savedProgress || 0, saveTimer, ticking = false;

        function pageAtScroll() {
            const y = scroller.scrollTop + scroller.clientHeight * 0.35;
            let lo = 0, hi = total - 1;
            while (lo < hi) {
                const mid = (lo + hi + 1) >> 1;
                if (pageEls[mid].offsetTop <= y) lo = mid; else hi = mid - 1;
            }
            return lo + 1;
        }
        function scheduleSave(pct) {
            clearTimeout(saveTimer);
            saveTimer = setTimeout(() => {
                if (progressUrl) {
                    postForm(progressUrl, { progress: pct })
                        .then((r) => { if (r && r.exp_gain > 0) showExpToast(r.exp_gain); })
                        .catch(() => {});
                } else if (progressKey) {
                    try { localStorage.setItem(progressKey, String(pct)); } catch (e) { /* penyimpanan lokal opsional */ }
                }
            }, 1500);
        }
        function updateUi() {
            const input = $('pv-page');
            if (document.activeElement !== input) input.value = cur;
            $('pv-prev').disabled = cur <= 1;
            $('pv-next').disabled = cur >= total;
            $('pv-zoom').textContent = zoom + '%';
            $('pv-slider').value = zoom;
            const pct = Math.round(cur / total * 100);
            $('pv-bar').style.width = pct + '%';
            $('pv-read').textContent = pct + '% dibaca';
            if (pct !== bestPct) { bestPct = pct; scheduleSave(pct); }
        }
        scroller.addEventListener('scroll', () => {
            if (mode !== 'scroll' || ticking) return;
            ticking = true;
            requestAnimationFrame(() => { ticking = false; cur = pageAtScroll(); updateUi(); });
        });

        function updateModeBtn() {
            const b = $('pv-mode');
            b.innerHTML = mode === 'page'
                ? '<i class="fas fa-book-open"></i><span>Halaman</span>'
                : '<i class="fas fa-arrows-up-down"></i><span>Gulir</span>';
            b.title = mode === 'page'
                ? 'Mode Halaman. Klik untuk ganti ke Gulir'
                : 'Mode Gulir. Klik untuk ganti ke Halaman';
        }
        // Terapkan mode saat ini: gulir = semua halaman berurutan, halaman = satu halaman saja.
        function applyMode() {
            pagesBox.classList.toggle('pv-single', mode === 'page');
            const old = pagesBox.querySelector('.pv-page.cur');
            if (old) old.classList.remove('cur');
            if (mode === 'page') {
                pageEls[cur - 1].classList.add('cur');
                scroller.scrollTop = 0;
            } else {
                scroller.scrollTop = pageEls[cur - 1].offsetTop - 12;
            }
            updateModeBtn();
            updateUi();
        }
        function go(n) {
            n = clamp(n, 1, total);
            if (mode === 'page') {
                if (n === cur) return;
                cur = n;
                applyMode();
                return;
            }
            scroller.scrollTo({ top: pageEls[n - 1].offsetTop - 12 });
        }

        let zoomTimer;
        function setZoom(z) {
            z = clamp(Math.round(z), 30, 250);
            if (z === zoom) return;
            const el = pageEls[cur - 1];
            const frac = (scroller.scrollTop - el.offsetTop) / (el.offsetHeight || 1);
            zoom = z;
            layout();
            const el2 = pageEls[cur - 1];
            scroller.scrollTop = el2.offsetTop + frac * el2.offsetHeight;
            updateUi();
            clearTimeout(zoomTimer);
            zoomTimer = setTimeout(() => {
                rendered.clear();
                visible.forEach((n) => renderPage(n));
            }, 150);
        }

        $('pv-prev').onclick = () => go(cur - 1);
        $('pv-next').onclick = () => go(cur + 1);
        $('pv-page').onchange = (e) => go(parseInt(e.target.value, 10) || cur);
        $('pv-in').onclick = () => setZoom(zoom + 10);
        $('pv-out').onclick = () => setZoom(zoom - 10);
        $('pv-slider').oninput = (e) => setZoom(parseInt(e.target.value, 10));
        $('pv-mode').onclick = () => {
            mode = mode === 'page' ? 'scroll' : 'page';
            try { localStorage.setItem(MODE_KEY, mode); } catch (e) { /* abaikan */ }
            applyMode();
        };
        // Mode halaman di HP: geser kiri/kanan untuk pindah halaman
        let tx = 0, ty = 0;
        scroller.addEventListener('touchstart', (e) => { tx = e.touches[0].clientX; ty = e.touches[0].clientY; }, { passive: true });
        scroller.addEventListener('touchend', (e) => {
            if (mode !== 'page') return;
            if (scroller.scrollWidth > scroller.clientWidth + 2) return;   // sedang zoom besar: biarkan geser biasa
            const t = e.changedTouches[0];
            const dx = t.clientX - tx, dy = t.clientY - ty;
            if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) go(cur + (dx < 0 ? 1 : -1));
        }, { passive: true });
        $('pv-full').onclick = () => {
            if (document.fullscreenElement) document.exitFullscreen();
            else if (stage.requestFullscreen) stage.requestFullscreen();
        };
        scroller.addEventListener('wheel', (e) => {
            if (!e.ctrlKey) return;
            e.preventDefault();
            setZoom(zoom + (e.deltaY < 0 ? 10 : -10));
        }, { passive: false });
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;
            if (e.key === 'ArrowRight') go(cur + 1);
            if (e.key === 'ArrowLeft') go(cur - 1);
        });

        // Lanjut dari halaman terakhir yang dibaca
        if (savedProgress > 0) cur = clamp(Math.round(savedProgress / 100 * total), 1, total);
        if (mode === 'page') applyMode();
        else {
            updateModeBtn();
            if (savedProgress > 0) go(cur);
            updateUi();
        }
    }

    function initReader(stage) {
        const olid = stage.dataset.olid;
        const directLink = stage.dataset.link || '';
        const progressUrl = stage.dataset.progressUrl || '';
        const progressKey = stage.dataset.progressKey || '';
        let savedProgress = parseInt(stage.dataset.progress || '0', 10) || 0;
        if (progressKey) {
            try {
                savedProgress = parseInt(localStorage.getItem(progressKey) || '', 10) || savedProgress;
            } catch (e) { /* progres lokal opsional */ }
        }

        const show = (html) => { stage.innerHTML = `<div class="reader-msg">${html}</div>`; };
        const backUrl = stage.dataset.backUrl || `/buku/${olid}/`;
        const backLinks = `<br><br><a class="btn-kembali" href="${escHtml(backUrl)}">Kembali</a>`;

        // JALUR 0: PDF yang diupload manual oleh admin -> pembaca bawaan website (PDF.js)
        const isPdf = directLink.split(/[?#]/)[0].toLowerCase().endsWith('.pdf');
        if (isPdf) {
            if (window.pdfjsLib) {
                initPdfReader(stage, directLink, olid, savedProgress, progressUrl, progressKey);
            } else {
                // PDF.js gagal dimuat (offline / diblokir): pakai pembaca bawaan browser.
                stage.innerHTML = `<iframe src="${escHtml(directLink)}#view=FitH" title="Pembaca PDF" style="width:100%; height:100%; border:none;"></iframe>`;
            }
            return;
        }

        show(`
            <div style="text-align: center; padding: 40px; color: #121824;">
                <i class="fas fa-file-pdf fa-3x" style="color: #8A8A7A; margin-bottom: 15px;"></i>
                <h2>File PDF belum tersedia</h2>
                <p style="color: #6A6A5C; margin: 10px 0 20px;">PDF belum tersedia untuk dibaca di perpustakaan.</p>
                ${backLinks}
            </div>
        `);
    }

    // ---------- Halaman katalog ----------
    const grid = document.getElementById('katalog-grid');
    if (!grid) return;

    const statusEl = document.getElementById('grid-status');
    const titleEl = document.getElementById('grid-title');
    const sentinel = document.getElementById('grid-sentinel');
    const searchEl = document.getElementById('katalog-search');
    const chips = Array.from(document.querySelectorAll('#chip-row .chip'));
    const DEFAULT_KAT = grid.dataset.defaultKategori;
    const LIMIT = 20;
    const localBooks = readJson('buku-lokal') || [];

    const state = { q: '', kategori: DEFAULT_KAT, page: 1, loading: false, done: false, failed: false };
    let token = 0; // naik setiap filter berubah, supaya respons lama diabaikan

    function buildQuery() {
        const parts = [];
        if (state.q) parts.push(state.q);
        if (state.kategori) parts.push(`subject:"${state.kategori.replace(/"/g, '')}"`);
        return parts.join(' ');
    }
    const SKELETON = Array(8).fill(
        '<div class="book-card sk-card" aria-hidden="true"><div class="sk-cover"></div>' +
        '<div class="book-info"><div class="sk-line"></div><div class="sk-line short"></div></div></div>').join('');
    function clearSkeleton() { if (grid.querySelector('.sk-card')) grid.innerHTML = ''; }
    function setStatus(html) { statusEl.innerHTML = html; }
    function updateTitle() {
        if (state.q) titleEl.textContent = `Hasil untuk "${state.q}"`;
        else {
            const active = chips.find(c => c.dataset.kategori === state.kategori);
            titleEl.textContent = active ? active.textContent : '';
        }
    }
    function nearBottom() { return sentinel.getBoundingClientRect().top < window.innerHeight + 500; }

    async function load(reset) {
        if (reset) {
            token++;
            state.page = 1; state.done = false; state.failed = false; state.loading = false;
            grid.innerHTML = SKELETON;
            updateTitle();
        }
        if (state.loading || state.done || state.failed) return;

        const mine = token;
        state.loading = true;
        setStatus('<span class="spinner"></span> Memuat buku...');
        try {
            // tanpa kata kunci = jelajah kategori, urutkan dari rating
            const r = await olSearch(buildQuery(), state.page, LIMIT, state.q ? null : 'rating');
            if (mine !== token) return;

            r.books.forEach(b => bookCache.set(b.olid, b));
            clearSkeleton();
            grid.insertAdjacentHTML('beforeend', r.books.map(b => cardHtml(b, true)).join(''));
            state.page += 1;
            state.done = !r.hasMore;

            if (!grid.children.length) setStatus('<strong>Buku tidak ditemukan.</strong><br>Coba kata kunci lain atau ganti kategori.');
            else if (state.done) setStatus('Semua hasil sudah ditampilkan.');
            else setStatus('');
        } catch (err) {
            if (mine !== token) return;
            clearSkeleton();
            state.failed = true;
            if (localBooks.length) {
                const q = state.q.toLocaleLowerCase();
                const available = localBooks.filter(b =>
                    !q || `${b.judul} ${b.penulis}`.toLocaleLowerCase().includes(q)
                );
                available.forEach(b => bookCache.set(b.olid, b));
                grid.insertAdjacentHTML('beforeend', available.map(b => cardHtml(b, true)).join(''));
                setStatus(
                    `<span>${available.length
                        ? 'Open Library sedang tidak bisa dihubungi. Menampilkan buku yang sudah tersimpan.'
                        : 'Tidak ada buku tersimpan yang cocok dengan pencarian ini. Hapus kata kunci untuk melihat semua buku lokal.'}</span> ` +
                    '<button type="button" class="link-btn" id="retry-btn">Coba lagi</button>'
                );
                const retry = document.getElementById('retry-btn');
                if (retry) retry.addEventListener('click', () => { state.failed = false; load(false); });
                return;
            }
            setStatus('Gagal memuat buku dari Open Library. <button type="button" class="link-btn" id="retry-btn">Coba lagi</button>');
            const retry = document.getElementById('retry-btn');
            if (retry) retry.addEventListener('click', () => { state.failed = false; load(false); });
        } finally {
            if (mine === token) {
                state.loading = false;
                setTimeout(() => { if (nearBottom()) load(false); }, 0); // layar belum penuh: muat lagi
            }
        }
    }

    new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) load(false);
    }, { rootMargin: '500px' }).observe(sentinel);

    chips.forEach(chip => chip.addEventListener('click', () => {
        searchEl.value = '';
        state.q = '';
        state.kategori = chip.dataset.kategori;
        chips.forEach(c => c.classList.toggle('active', c === chip));
        load(true);
    }));

    let timer;
    searchEl.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
            const q = searchEl.value.trim();
            if (q === state.q) return;
            state.q = q;
            if (q) {
                state.kategori = '';
                chips.forEach(c => c.classList.remove('active'));
            } else {
                state.kategori = DEFAULT_KAT;
                chips.forEach(c => c.classList.toggle('active', c.dataset.kategori === DEFAULT_KAT));
            }
            load(true);
        }, 400);
    });

    const awal = new URLSearchParams(window.location.search).get('q');
    if (awal && awal.trim()) {
        state.q = awal.trim();
        state.kategori = '';
        searchEl.value = state.q;
        chips.forEach(c => c.classList.remove('active'));
    }
    load(true);
})();