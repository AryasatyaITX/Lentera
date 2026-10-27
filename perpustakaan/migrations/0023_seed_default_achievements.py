from django.db import migrations


ACHIEVEMENTS = [
    ("Halaman Pertama", "Umum", "Selesaikan sesi baca buku pertamamu.", "fa-book-open", "", 1),
    ("Tunas Literasi", "Umum", "Selesaikan 5 sesi baca buku.", "fa-seedling", "", 5),
    ("Rak Mulai Terisi", "Umum", "Selesaikan 10 sesi baca buku.", "fa-leaf", "", 10),
    ("Pembaca Tekun", "Langka", "Selesaikan 25 sesi baca buku.", "fa-tree", "", 25),
    ("Penjaga Cerita", "Epik", "Selesaikan 50 sesi baca buku.", "fa-shield-halved", "", 50),
    ("Sampul Terakhir", "Umum", "Tuntaskan satu buku sampai bagian terakhir.", "fa-flag-checkered", "buku_selesai", 1),
    ("Tiga Cerita", "Umum", "Tuntaskan tiga buku.", "fa-medal", "buku_selesai", 3),
    ("Kolektor Kisah", "Langka", "Tuntaskan lima buku.", "fa-layer-group", "buku_selesai", 5),
    ("Penjelajah Rak", "Langka", "Mulai membaca lima judul buku berbeda.", "fa-compass", "buku_dimulai", 5),
    ("Rak Pribadi", "Langka", "Mulai membaca tujuh judul buku berbeda.", "fa-book", "buku_dimulai", 7),
    ("Sistem Informasi Terurai", "Umum", "Selesaikan sesi baca buku berkategori Sistem Informasi.", "fa-magnifying-glass", "", 1),
    ("Dunia Elektro", "Umum", "Selesaikan sesi baca buku berkategori Teknik Elektro.", "fa-wand-magic-sparkles", "", 1),
    ("Hati di Lingkungan", "Umum", "Selesaikan sesi baca buku berkategori Teknik Lingkungan.", "fa-heart", "", 1),
    ("Langkah Pembangunan", "Umum", "Selesaikan sesi baca buku Arsitektur.", "fa-arrow-trend-up", "", 1),
    ("Pencari Ilmu Teknik", "Umum", "Selesaikan sesi baca buku berkategori Teknik Sipil.", "fa-graduation-cap", "", 1),
    ("Sang Pencinta IT", "Umum", "Selesaikan sesi baca buku berkategori Informatika.", "fa-feather-pointed", "", 1),
    ("Lintas Genre", "Langka", "Baca buku dari 3 genre yang berbeda.", "fa-shuffle", "genre", 3),
    ("Pustaka Berwarna", "Epik", "Baca buku dari 5 genre yang berbeda.", "fa-palette", "genre", 5),
    ("Percikan Pertama", "Umum", "Kumpulkan 25 EXP dari ikon membaca.", "fa-bolt", "exp", 25),
    ("Bintang Pembaca", "Umum", "Kumpulkan 100 EXP.", "fa-star", "exp", 100),
    ("Cahaya Lentera", "Langka", "Kumpulkan 250 EXP.", "fa-lightbulb", "exp", 250),
    ("Lentera Emas", "Epik", "Kumpulkan 500 EXP.", "fa-crown", "exp", 500),
    ("Penanda Cerita", "Umum", "Buat bookmark pertamamu.", "fa-bookmark", "bookmark", 1),
    ("Penjaga Halaman", "Langka", "Simpan 5 bookmark buku atau bab.", "fa-book-bookmark", "bookmark", 5),
    ("Peminjam Pertama", "Umum", "Ajukan peminjaman buku pertamamu.", "fa-handshake", "pinjam_total", 1),
    ("Sahabat Perpustakaan", "Langka", "Selesaikan 5 transaksi peminjaman.", "fa-user-group", "pinjam_selesai", 5),
    ("Pembaca Jurnal", "Umum", "Selesaikan satu bagian jurnal.", "fa-newspaper", "", 1),
    ("Penjelajah Wacana", "Langka", "Selesaikan 5 bagian jurnal.", "fa-scroll", "", 5),
    ("Hadir Membaca", "Umum", "Dapatkan EXP pada satu hari membaca.", "fa-sun", "streak", 1),
    ("Ritme Membaca", "Umum", "Dapatkan EXP pada 3 hari berbeda.", "fa-chart-line", "streak", 3),
    ("Kebiasaan Terbentuk", "Langka", "Dapatkan EXP pada 7 hari berbeda.", "fa-calendar-check", "streak", 7),
    ("Rak Kesayangan", "Umum", "Simpan 3 judul ke koleksi favorit.", "fa-heart-circle-check", "bookmark", 3),
    ("Saldo Pertama", "Umum", "Lakukan simulasi top up Reader pertamamu.", "fa-coins", "", 1),
    ("Poin Terkumpul", "Langka", "Simulasikan top up minimal 50 kredit total.", "fa-gem", "", 50),
    ("Pinjam dan Kembali", "Umum", "Kembalikan setidaknya satu buku pinjaman.", "fa-rotate-left", "pinjam_selesai", 1),
    ("Bagian demi Bagian", "Epik", "Selesaikan 15 bagian buku dan jurnal.", "fa-puzzle-piece", "", 15),
]


def seed_achievements(apps, schema_editor):
    AchievementGambar = apps.get_model("perpustakaan", "AchievementGambar")
    manager = AchievementGambar.objects.using(schema_editor.connection.alias)

    for nama, kategori, deskripsi, ikon, tipe_syarat, target in ACHIEVEMENTS:
        if manager.filter(nama__iexact=nama).exists():
            continue
        manager.create(
            nama=nama,
            kategori=kategori,
            deskripsi=deskripsi,
            ikon=ikon,
            tipe_syarat=tipe_syarat,
            target=target,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("perpustakaan", "0022_achievementgambar_ikon_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_achievements, migrations.RunPython.noop),
    ]
