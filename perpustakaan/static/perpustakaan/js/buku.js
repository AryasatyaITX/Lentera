// Katalog (infinite scroll), halaman detail, dan bookmark.
// Data buku diambil LANGSUNG dari browser ke Open Library. Django hanya menyimpan
// pinjam/bookmark. Dibungkus IIFE supaya tidak bentrok dengan nama di script.js.
(function () {
    'use strict';

    const OL = 'https://openlibrary.org';
    const FIELDS = 'key,title,author_name,first_publish_year,cover_i,ia,ratings_average,want_to_read_count,ebook_access';
    const NO_COVER = 'https://images.unsplash.com/photo-1532012197267-da84d127e765?w=300';

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
            ia: (doc.ia || [''])[0],
            ia_semua: (doc.ia || []).slice(0, 8),   // semua versi di Internet Archive (untuk halaman baca)
            akses: doc.ebook_access || '',          // 'public' = bisa dibaca gratis
            deskripsi: '',
            subjek: [],
        };
    }
    // Hasil dicache di sessionStorage (15 menit) supaya kategori/buku yang sudah dibuka muncul seketika,
    // dan permintaan yang menggantung lebih dari 15 detik dibatalkan (lalu muncul tombol "Coba lagi").
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
            data = await res.json(); // gagal kalau yang datang halaman verifikasi (HTML)
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
        return { judul: b.judul, penulis: b.penulis, tahun: b.tahun, cover: b.cover, ia: b.ia, deskripsi: b.deskripsi || '' };
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
        let current = null;

        const bmBtn = $('bm-btn');
        bmBtn.addEventListener('click', async () => {
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
            $('bd-title').textContent = b.judul;
            $('bd-author').textContent = b.penulis + (b.tahun ? `, pertama terbit ${b.tahun}` : '');
            const cover = $('bd-cover');
            cover.alt = 'Sampul ' + b.judul;
            if (b.cover_besar) { cover.onerror = () => { cover.onerror = null; cover.src = NO_COVER; }; cover.src = b.cover_besar; }

            $('bd-stats').innerHTML =
                `<span><i class="fas fa-star"></i> ${b.rating === null ? 'Belum ada rating' : b.rating}</span>` +
                `<span><i class="fas fa-bookmark"></i> ${b.want === null
                    ? 'Jumlah ingin membaca tidak tersedia'
                    : `${new Intl.NumberFormat('id-ID').format(b.want)} orang ingin membaca`}</span>` +
                (b.akses === 'public' ? '<span><i class="fas fa-book-open"></i> Bisa dibaca gratis</span>' : '');

            const desc = $('bd-desc');
            if (b.deskripsi) { desc.textContent = b.deskripsi; desc.style.whiteSpace = 'pre-line'; desc.classList.remove('bd-muted'); }
            else { desc.textContent = 'Open Library belum punya deskripsi untuk buku ini.'; }

            $('bd-dl-author').textContent = b.penulis;
            $('bd-dl-year').textContent = b.tahun || '-';

            if (b.subjek && b.subjek.length) {
                $('bd-tags').innerHTML = b.subjek.map(s => `<span>${escHtml(s)}</span>`).join('');
                $('bd-subjects-wrap').hidden = false;
            }
            if (b.ia && /^[A-Za-z0-9._-]+$/.test(b.ia)) {
                const a = $('bd-ia'); a.href = `https://archive.org/details/${b.ia}`; a.hidden = false;
            }

            const form = $('pinjam-form');
            if (form) {
                const p = bookPayload(b);
                Object.keys(p).forEach(k => { form.elements[k].value = p[k]; });
                $('pinjam-btn').disabled = false;
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
                $('bd-related-grid').innerHTML = list.map(x => cardHtml(x, false)).join('');
                $('bd-related').hidden = false;
            } catch (e) { /* buku terkait hanya pelengkap */ }
        }

        (async () => {
            let book = null;
            try {
                book = await olBook(olid);
            } catch (e) {
                const db = readJson('buku-db');
                if (db) {
                    book = db;
                    $('bd-error').textContent = 'Data terbaru dari Open Library belum bisa dimuat. Menampilkan data yang tersimpan.';
                    $('bd-error').hidden = false;
                } else {
                    $('bd-title').textContent = e.notfound ? 'Buku tidak ditemukan' : 'Buku tidak bisa dimuat';
                    $('bd-author').textContent = '';
                    $('bd-desc').textContent = e.notfound
                        ? 'Open Library tidak punya buku dengan ID ini.'
                        : 'Open Library belum bisa dihubungi dari browsermu. Muat ulang halaman ini beberapa saat lagi.';
                    return;
                }
            }
            render(book);
            loadRelated(book);
        })();
    }

    // ---------- Halaman baca ----------
    const stage = document.getElementById('reader-stage');
    if (stage) initReader(stage);

    async function archiveFree(id) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 8000);
        try {
            const res = await fetch(`https://archive.org/metadata/${id}/metadata`, { signal: ctrl.signal });
            if (!res.ok) return false;
            const m = (await res.json()).result || {};
            return m.mediatype === 'texts' && String(m['access-restricted-item']) !== 'true';
        } catch (e) { return false; } finally { clearTimeout(timer); }
    }

    // FUNGSI BARU: Cari Google Books API berdasarkan Judul + Penulis untuk Preview Bacaan
    async function getGoogleBooksReader(judul, penulis) {
        const query = encodeURIComponent(`intitle:${judul} inauthor:${penulis}`);
        const url = `https://www.googleapis.com/books/v1/volumes?q=${query}&limit=1`;
        try {
            const res = await fetch(url);
            const data = await res.json();
            if (data.items && data.items.length > 0) {
                const access = data.items[0].accessInfo;
                // Ambil link baca gratis Google
                return access.webReaderLink || data.items[0].volumeInfo.previewLink || null;
            }
        } catch(e) { return null; }
        return null;
    }

    async function initReader(stage) {
        const olid = stage.dataset.olid;
        const iaId = stage.dataset.ia;
        const judulBuku = stage.dataset.judul || "Buku";
        const penulisBuku = stage.dataset.penulis || "";
        const directLink = stage.dataset.link || "";

        const show = (html) => { stage.innerHTML = `<div class="reader-msg">${html}</div>`; };
        const archiveLink = (id) => `<a class="btn-selesai" style="background:#4A90E2; color:white; border:none;" href="https://archive.org/details/${id}" target="_blank" rel="noopener"><i class="fas fa-external-link-alt"></i> Buka di Internet Archive</a>`;
        const googleLink = (url) => `<a class="btn-selesai" style="background:#4285F4; color:white; border:none;" href="${url}" target="_blank" rel="noopener"><i class="fab fa-google"></i> Baca di Google Books</a>`;
        const backLinks = `<br><br><a class="btn-kembali" href="/buku/${olid}/">Detail buku</a> &nbsp;&middot;&nbsp; <a class="btn-kembali" href="/katalog/">Katalog</a>`;

        // ========================================================
        // ⚡ JALUR CEPAT 1: JIKA BUKU PUNYA ID ARCHIVE LANGSUNG
        // ========================================================
        if (iaId && iaId.trim() !== '') {
            stage.innerHTML = `<iframe src="https://archive.org/embed/${iaId}" title="Pembaca buku" allowfullscreen style="width:100%; height:100%; border:none;"></iframe>`;
            return;
        }

        // ========================================================
        // ⚡ JALUR CEPAT 2: JIKA SUDAH PUNYA LINK GOOGLE BOOKS
        // ========================================================
        if (directLink && directLink.includes('google.com')) {
            show(`
                <div style="text-align: center; padding: 40px; color: #121824;">
                    <i class="fab fa-google fa-3x" style="color: #4285F4; margin-bottom: 15px;"></i>
                    <h2>Buku Ditemukan di Google Books</h2>
                    <p style="color: #6A6A5C; margin: 10px 0 20px;">Silakan baca pratinjau buku ini melalui Google Web Reader.</p>
                    ${googleLink(directLink)}
                    ${backLinks}
                </div>
            `);
            return;
        }

        // ========================================================
        // ⏱️ JALUR API LAMBAT: DIBERI BATAS WAKTU MAKSIMAL 3 DETIK!
        // ========================================================
        show('<span class="spinner"></span> Menyiapkan pratinjau buku...');

        try {
            // Balapan: Jika API luar melebihi 3 detik, paksa lanjut ke fallback
            const gUrl = await Promise.race([
                getGoogleBooksReader(judulBuku, penulisBuku),
                new Promise(resolve => setTimeout(() => resolve(null), 3000)) // Timeout 3 detik
            ]);

            if (gUrl) {
                show(`
                    <div style="text-align: center; padding: 40px; color: #121824;">
                        <i class="fab fa-google fa-3x" style="color: #4285F4; margin-bottom: 15px;"></i>
                        <h2>Buku Ditemukan di Google Books</h2>
                        <p style="color: #6A6A5C; margin: 10px 0 20px;">Silakan klik tombol di bawah untuk membaca pratinjau buku.</p>
                        ${googleLink(gUrl)}
                        ${backLinks}
                    </div>
                `);
                return;
            }
        } catch (e) {
            console.warn("API check timed out/failed:", e);
        }

        // FALLBACK AMAN: Tampilkan tombol sumber jika API lemot
        show(`
            <div style="text-align: center; padding: 40px; color: #121824;">
                <i class="fas fa-book-open fa-3x" style="color: #8A8A7A; margin-bottom: 15px;"></i>
                <h2>Buku Berhak Cipta / Terproteksi</h2>
                <p style="color: #6A6A5C; margin: 10px 0 20px;">Pratinjau langsung tidak tersedia secara publik.</p>
                ${directLink ? `<a class="btn-selesai" style="background:#121824; color:white; border:none;" href="${directLink}" target="_blank"><i class="fas fa-external-link-alt"></i> Buka Sumber Buku</a>` : ''}
                ${backLinks}
            </div>
        `);
    }

    // ---------- Dashboard: rekomendasi + pencarian ----------
    const dash = document.getElementById('book-grid-container');
    if (dash) {
        olSearch('subject:"engineering"', 1, 4, 'rating').then(r => {
            r.books.forEach(b => bookCache.set(b.olid, b));
            dash.innerHTML = r.books.length
                ? r.books.map(b => cardHtml(b, false)).join('')
                : '<p>Buku tidak ditemukan.</p>';
        }).catch(() => {
            dash.innerHTML = '<p>Gagal memuat rekomendasi dari Open Library. Muat ulang halaman ini nanti.</p>';
        });
        const heroSearch = document.getElementById('hero-search');
        if (heroSearch) {
            heroSearch.addEventListener('keydown', (e) => {
                if (e.key !== 'Enter') return;
                const q = heroSearch.value.trim();
                if (q) window.location.href = '/katalog/?q=' + encodeURIComponent(q);
            });
        }
    }

    // ---------- Halaman katalog ----------
    const grid = document.getElementById('katalog-grid');
    if (!grid) return;

    const statusEl = document.getElementById('grid-status');
    const titleEl = document.getElementById('grid-title');
    const sentinel = document.getElementById('grid-sentinel');
    const searchEl = document.getElementById('katalog-search');
    const langEl = document.getElementById('filter-bahasa');
    const chips = Array.from(document.querySelectorAll('#chip-row .chip'));
    const DEFAULT_KAT = grid.dataset.defaultKategori;
    const LIMIT = 20;
    const localBooks = readJson('buku-lokal') || [];

    const state = { q: '', kategori: DEFAULT_KAT, bahasa: '', gratis: false, page: 1, loading: false, done: false, failed: false };
    let token = 0; // naik setiap filter berubah, supaya respons lama diabaikan

    function buildQuery() {
        const parts = [];
        if (state.q) parts.push(state.q);
        if (state.kategori) parts.push(`subject:"${state.kategori.replace(/"/g, '')}"`);
        if (state.bahasa) parts.push(`language:${state.bahasa}`);
        if (state.gratis) parts.push('public_scan_b:true');
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

    document.getElementById('btn-filter').addEventListener('click', (e) => {
        const open = document.getElementById('filter-panel').classList.toggle('open');
        e.currentTarget.setAttribute('aria-expanded', open);
    });
    langEl.addEventListener('change', () => { state.bahasa = langEl.value; load(true); });
    document.getElementById('filter-gratis').addEventListener('change', (e) => { state.gratis = e.target.checked; load(true); });

    const awal = new URLSearchParams(window.location.search).get('q');
    if (awal && awal.trim()) {
        state.q = awal.trim();
        state.kategori = '';
        searchEl.value = state.q;
        chips.forEach(c => c.classList.remove('active'));
    }
    load(true);
})();