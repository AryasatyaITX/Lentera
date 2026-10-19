// (Dashboard & katalog sekarang menggunakan database lokal)
function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// 2. FUNGSI KONFIRMASI PENGEMBALIAN BUKU
function confirmReturn(event, bookTitle) {
    event.preventDefault(); // Hentikan aksi klik sementara
    const url = event.currentTarget.getAttribute('href'); // Ambil link tujuan
    
    // Tampilkan Pop Up Konfirmasi bawaan browser
    if (confirm(`Apakah Anda yakin ingin mengembalikan buku "${bookTitle}"?`)) {
        window.location.href = url; // Lanjutkan jika pilih OK
    }
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