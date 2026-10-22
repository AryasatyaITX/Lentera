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
    const appLayout = document.getElementById("appLayout");
    const menuButton = document.getElementById("menuButton");

    if (!appLayout || !menuButton) {
        console.error("appLayout atau menuButton tidak ditemukan");
        return;
    }

    // Pulihkan status sidebar selama sesi ini (hilang saat tab/browser ditutup)
    try {
        if (sessionStorage.getItem("sidebarOpen") === "1") {
            appLayout.classList.add("sidebar-open");
        }
        localStorage.removeItem("sidebarOpen"); // bersihkan sisa versi lama
    } catch (e) {}

    menuButton.addEventListener("click", function () {
        appLayout.classList.toggle("sidebar-open");
        try {
            sessionStorage.setItem("sidebarOpen", appLayout.classList.contains("sidebar-open") ? "1" : "0");
        } catch (e) {}
    });
});