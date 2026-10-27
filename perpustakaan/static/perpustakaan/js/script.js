// (Dashboard & katalog sekarang menggunakan database lokal)
function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// 5. FUNGSI HAPUS BOOKMARK DENGAN AJAX
async function removeBookmark(element) {
    const bookmarkId = element.dataset.id; // Ambil ID dari atribut data-id
    const bookCard = element.closest('.book-card');
    
    try {
        const response = await fetch(`/hapus-bookmark/${bookmarkId}/`);
        
        if (response.ok) {
            bookCard.style.transition = "opacity 0.3s, transform 0.3s";
            bookCard.style.opacity = "0";
            bookCard.style.transform = "scale(0.9)";
            
            setTimeout(() => {
                bookCard.remove();
                
                const countEl = document.getElementById('bookmark-counter');
                if (countEl) {
                    let current = parseInt(countEl.innerText);
                    countEl.innerText = Math.max(0, current - 1);
                }
            }, 300);
        }
    } catch (error) {
        console.error("Gagal menghapus bookmark", error);
    }
}

// 6. FUNGSI MODAL DETAIL RIWAYAT
function openDetailModal(element) {
    // Ambil semua data dari atribut data-* pada link yang diklik
    document.getElementById('modal-judul').innerText = element.dataset.judul;
    document.getElementById('modal-penulis').innerText = element.dataset.penulis;
    document.getElementById('modal-pinjam').innerText = element.dataset.pinjam;
    document.getElementById('modal-kembali').innerText = element.dataset.kembali;
    document.getElementById('modal-progress').innerText = element.dataset.progress + "%";
    document.getElementById('modal-exp').innerText = "+" + element.dataset.exp + " EXP";

    // Tampilkan modal
    document.getElementById('detail-modal').classList.add('show');
}

function closeDetailModal() {
    document.getElementById('detail-modal').classList.remove('show');
}

function getCsrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : '';
}

async function toggleCatalogBookmark(button) {
    if (!button || button.dataset.busy) return;
    button.dataset.busy = '1';
    try {
        const response = await fetch(button.dataset.url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': getCsrfToken() },
            body: new URLSearchParams({
                judul: button.dataset.judul || '',
                penulis: button.dataset.penulis || '',
                tahun: button.dataset.tahun || '',
                cover: button.dataset.cover || '',
                deskripsi: button.dataset.deskripsi || '',
            }),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const heart = button.querySelector('.fa-heart');
        heart.classList.toggle('active', data.bookmarked);
        heart.classList.toggle('fas', data.bookmarked);
        heart.classList.toggle('far', !data.bookmarked);
        button.style.color = data.bookmarked ? '#65a30d' : '#cbd5e1';
        button.title = data.bookmarked ? 'Hapus dari bookmark' : 'Simpan ke bookmark';
        button.setAttribute('aria-label', button.title);
    } catch (error) {
        alert('Bookmark gagal disimpan. Coba lagi sebentar lagi.');
    } finally {
        delete button.dataset.busy;
    }
}

// Tutup modal jika klik di area gelap di luar kotak
window.addEventListener('click', function(event) {
    const modal = document.getElementById('detail-modal');
    if (modal && event.target === modal) {
        closeDetailModal();
    }
});

// 6. FUNGSI TOGGLE LIHAT PASSWORD (Halaman Profil)
function togglePassword(inputId, iconElement) {
    const input = document.getElementById(inputId);
    if (input.type === "password") {
        input.type = "text";
        iconElement.classList.remove("fa-eye");
        iconElement.classList.add("fa-eye-slash");
    } else {
        input.type = "password";
        iconElement.classList.remove("fa-eye-slash");
        iconElement.classList.add("fa-eye");
    }
}

document.addEventListener("DOMContentLoaded", function () {
    const categoryStrip = document.getElementById("chip-scroll-area");
    const categoryButtons = document.querySelectorAll("[data-scroll-kategori]");

    function updateCategoryButtons() {
        if (!categoryStrip) return;
        const maxScroll = categoryStrip.scrollWidth - categoryStrip.clientWidth;
        categoryButtons.forEach(function (button) {
            const direction = Number(button.dataset.scrollKategori);
            button.disabled = direction < 0
                ? categoryStrip.scrollLeft <= 0
                : categoryStrip.scrollLeft >= maxScroll - 1;
        });
    }

    categoryButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            if (!categoryStrip) return;
            categoryStrip.scrollBy({
                left: categoryStrip.clientWidth * Number(button.dataset.scrollKategori) * 0.75,
                behavior: "smooth",
            });
        });
    });
    if (categoryStrip) {
        categoryStrip.addEventListener("scroll", updateCategoryButtons, { passive: true });
        window.addEventListener("resize", updateCategoryButtons);
        updateCategoryButtons();
    }

    const appLayout = document.getElementById("appLayout");
    const sidebar = appLayout && appLayout.querySelector(".sidebar");
    const mainContent = appLayout && appLayout.querySelector(".main-content");

    if (appLayout && sidebar && mainContent) {
        let menuButton = document.getElementById("menuButton");
        const mobileMenu = window.matchMedia("(max-width: 900px)");

        if (!menuButton) {
            menuButton = document.createElement("button");
            menuButton.id = "menuButton";
            menuButton.className = "menu-button";
            menuButton.type = "button";
            menuButton.setAttribute("aria-label", "Buka atau tutup menu");
            menuButton.innerHTML = '<i class="fas fa-bars" aria-hidden="true"></i>';

            let navTarget = mainContent.querySelector(".top-nav-left");
            if (!navTarget) {
                const topNav = mainContent.querySelector(".top-nav");
                if (topNav) {
                    navTarget = document.createElement("div");
                    navTarget.className = "top-nav-left";
                    topNav.insertBefore(navTarget, topNav.firstChild);
                }
            }
            if (navTarget) {
                navTarget.insertBefore(menuButton, navTarget.firstChild);
            } else {
                menuButton.classList.add("user-menu-trigger--standalone");
                mainContent.insertBefore(menuButton, mainContent.firstChild);
                appLayout.classList.add("has-standalone-menu");
            }
        }

        if (!sidebar.id) sidebar.id = "user-sidebar";
        menuButton.setAttribute("aria-controls", sidebar.id);

        let backdrop = appLayout.querySelector(".user-sidebar-backdrop");
        if (!backdrop) {
            backdrop = document.createElement("button");
            backdrop.type = "button";
            backdrop.className = "user-sidebar-backdrop";
            backdrop.setAttribute("aria-label", "Tutup menu");
            backdrop.tabIndex = -1;
            appLayout.appendChild(backdrop);
        }

        function setSidebarOpen(open) {
            appLayout.classList.toggle("sidebar-open", open);
            menuButton.setAttribute("aria-expanded", String(open));
            backdrop.setAttribute(
                "aria-hidden",
                String(!open || !mobileMenu.matches)
            );
            document.body.classList.toggle(
                "user-drawer-open",
                open && mobileMenu.matches
            );
        }

        function restoreSidebarState() {
            let open = false;
            if (!mobileMenu.matches) {
                try {
                    open = sessionStorage.getItem("sidebarOpen") === "1";
                } catch (error) {
                    open = false;
                }
            }
            setSidebarOpen(open);
        }

        restoreSidebarState();
        requestAnimationFrame(function () {
            appLayout.classList.remove("no-anim");
        });

        menuButton.addEventListener("click", function () {
            const open = !appLayout.classList.contains("sidebar-open");
            setSidebarOpen(open);
            if (!mobileMenu.matches) {
                try {
                    sessionStorage.setItem("sidebarOpen", open ? "1" : "0");
                } catch (error) {
                    // Storage may be unavailable in private browsing contexts.
                }
            }
        });

        backdrop.addEventListener("click", function () {
            setSidebarOpen(false);
            menuButton.focus();
        });

        sidebar.addEventListener("click", function (event) {
            if (mobileMenu.matches && event.target.closest("a")) {
                setSidebarOpen(false);
            }
        });

        document.addEventListener("keydown", function (event) {
            if (
                event.key === "Escape"
                && mobileMenu.matches
                && appLayout.classList.contains("sidebar-open")
            ) {
                setSidebarOpen(false);
                menuButton.focus();
            }
        });

        if (mobileMenu.addEventListener) {
            mobileMenu.addEventListener("change", restoreSidebarState);
        } else {
            mobileMenu.addListener(restoreSidebarState);
        }
    }
});