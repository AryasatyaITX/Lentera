from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Bookmark, BukuDigital, CustomUser, Peminjaman

# [PEWARISAN] Class tes mewarisi django.test.TestCase, yang menyediakan
# client dan database tes. setUp() ditimpa (overriding) untuk menyiapkan
# data awal tiap tes.
class LocalCatalogLoanFlowTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='catalog-test',
            password='test-password',
        )
        self.book = BukuDigital.objects.create(
            id_item='OL1234567W',
            judul='Buku Tes Lokal',
            penulis='Penulis Tes',
            tahun_terbit='2020',
        )
        self.client.force_login(self.user)

    def test_saved_book_can_be_borrowed_and_returned_without_open_library(self):
        catalog = self.client.get(reverse('katalog'))
        self.assertContains(catalog, 'buku-lokal')
        self.assertContains(catalog, 'Buku Tes Lokal')

        borrow = self.client.post(reverse('pinjam_buku', args=[self.book.id_item]))
        self.assertRedirects(borrow, reverse('peminjaman'))
        loan = Peminjaman.objects.get(user=self.user, buku_digital=self.book)
        self.assertEqual(loan.status, 'Dibaca')

        returned = self.client.get(reverse('kembalikan_buku', args=[loan.id]))
        self.assertRedirects(returned, reverse('peminjaman'))
        loan.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(loan.status, 'Selesai')
        self.assertEqual(loan.progress_baca, 100)
        self.assertIsNotNone(loan.tanggal_kembali)
        self.assertEqual(self.user.exp, 50)

        history = self.client.get(reverse('riwayat'))
        self.assertContains(history, 'Buku Tes Lokal')
        self.assertContains(history, 'Dikembalikan')

    def test_catalog_lists_the_ten_prodi_without_machine_category(self):
        catalog = self.client.get(reverse("katalog"))
        self.assertEqual(
            [label for _, label in catalog.context["kategori_list"]],
            [
                "Teknik Elektro",
                "Teknik Sipil",
                "Teknik Industri",
                "Teknik Pertambangan",
                "Teknik Kimia",
                "Teknik Geologi",
                "Arsitektur",
                "Informatika",
                "Sistem Informasi",
                "Teknik Lingkungan",
            ],
        )
        self.assertNotContains(catalog, "teknik_mesin")

    def test_catalog_categories_scroll_and_card_category_sits_by_bookmark(self):
        self.book.kategori = "teknik_sipil"
        self.book.save(update_fields=["kategori"])

        catalog = self.client.get(reverse("katalog"))

        self.assertContains(catalog, 'data-scroll-kategori="-1"')
        self.assertContains(catalog, 'data-scroll-kategori="1"')
        self.assertContains(catalog, '<div class="catalog-card-footer">')
        self.assertContains(catalog, '<span class="genre-chip">Teknik Sipil</span>')
        self.assertContains(catalog, 'class="catalog-bookmark"')

    def test_catalog_category_filter_matches_admin_value_and_legacy_label(self):
        current_category_book = BukuDigital.objects.create(
            id_item='OL1234568W',
            judul='Buku Computer Science',
            penulis='Penulis Tes',
            kategori='computer_science',
        )
        legacy_category_book = BukuDigital.objects.create(
            id_item='OL1234569W',
            judul='Buku Computer Science Lama',
            penulis='Penulis Tes',
            kategori='Computer Science',
        )
        BukuDigital.objects.create(
            id_item='OL1234570W',
            judul='Buku Sejarah',
            penulis='Penulis Tes',
            kategori='sejarah',
        )

        catalog = self.client.get(
            reverse('katalog'), {'kategori': 'computer_science'}
        )

        self.assertEqual(
            {book['olid'] for book in catalog.context['buku_lokal']},
            {current_category_book.id_item, legacy_category_book.id_item},
        )


class CollectionPaginationTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='pagination-test',
            password='test-password',
        )
        self.client.force_login(self.user)

    def test_bookmarks_are_paginated_and_show_no_fake_statistics(self):
        books = [
            BukuDigital.objects.create(
                id_item=f'OL12345{index}W',
                judul=f'Buku Bookmark {index}',
                penulis='Penulis Tes',
            )
            for index in range(12)
        ]
        Bookmark.objects.bulk_create([
            Bookmark(user=self.user, buku_digital=book)
            for book in books
        ])

        first_page = self.client.get(reverse('bookmarks'))
        self.assertEqual(first_page.context['bookmarks'].paginator.count, 12)
        self.assertEqual(len(first_page.context['bookmarks']), 10)
        self.assertContains(first_page, 'Halaman 1 dari 2')
        self.assertContains(first_page, 'Filter kategori buku')
        self.assertNotContains(first_page, 'bookmark-counter')
        self.assertNotIn('total_tersimpan', first_page.context)
        self.assertContains(first_page, 'data-bookmark-stats', count=10)
        self.assertNotContains(first_page, '4.8')
        self.assertNotContains(first_page, 'fa-eye')

        second_page = self.client.get(reverse('bookmarks'), {'page': 2})
        self.assertEqual(len(second_page.context['bookmarks']), 2)
        self.assertContains(second_page, 'Halaman 2 dari 2')

    def test_bookmarks_can_be_filtered_by_catalog_category(self):
        matching = BukuDigital.objects.create(
            id_item='OL7654322W',
            judul='Buku Sistem Informasi',
            penulis='Penulis Tes',
            kategori='sistem_informasi',
        )
        other = BukuDigital.objects.create(
            id_item='OL7654323W',
            judul='Buku Informatika',
            penulis='Penulis Tes',
            kategori='informatika',
        )
        Bookmark.objects.create(user=self.user, buku_digital=matching)
        Bookmark.objects.create(user=self.user, buku_digital=other)

        response = self.client.get(
            reverse('bookmarks'), {'kategori': 'sistem_informasi'}
        )

        self.assertEqual(response.context['bookmarks'].paginator.count, 1)
        self.assertContains(response, 'Buku Sistem Informasi')
        self.assertNotContains(response, 'Buku Informatika')
        self.assertContains(response, 'Sistem Informasi')

    def test_history_is_paginated(self):
        book = BukuDigital.objects.create(
            id_item='OL7654321W',
            judul='Buku Riwayat',
            penulis='Penulis Tes',
        )
        Peminjaman.objects.bulk_create([
            Peminjaman(user=self.user, buku_digital=book)
            for _ in range(12)
        ])

        first_page = self.client.get(reverse('riwayat'))
        self.assertEqual(first_page.context['page_obj'].paginator.count, 12)
        self.assertEqual(len(first_page.context['riwayat_list']), 10)
        self.assertContains(first_page, 'Halaman 1 dari 2')

        second_page = self.client.get(reverse('riwayat'), {'page': 2})
        self.assertEqual(len(second_page.context['riwayat_list']), 2)
        self.assertContains(second_page, 'Halaman 2 dari 2')


class DailyReadingGoalTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='daily-goal-test',
            password='test-password',
        )
        self.client.force_login(self.user)

    def send_reading_time(self, seconds):
        session = self.client.session
        session['ring_terakhir'] = 0
        session.save()
        return self.client.post(reverse('waktu_baca'), {'detik': seconds})

    def test_daily_reading_and_streak_stop_at_thirty_minutes(self):
        self.send_reading_time(1800)
        self.send_reading_time(300)

        self.user.refresh_from_db()
        self.assertEqual(self.user.detik_baca_hari_ini, 1800)
        self.assertEqual(self.user.streak_days, 1)

        dashboard = self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard.context['menit_hari_ini'], 30)
        self.assertEqual(dashboard.context['persen_target'], 100)

    def test_streak_resets_after_a_missed_reading_day(self):
        self.user.streak_days = 4
        self.user.last_read_date = timezone.localdate() - timedelta(days=2)
        self.user.save(update_fields=['streak_days', 'last_read_date'])

        dashboard = self.client.get(reverse('dashboard'))

        self.user.refresh_from_db()
        self.assertEqual(self.user.streak_days, 0)
        self.assertEqual(dashboard.context['streak_hari'], 0)


class ProfileAndAdminRegressionTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="real-name-user",
            password="test-password",
            nama_tampilan="Nama Asli",
        )
        self.book = BukuDigital.objects.create(
            id_item="OL9876543W",
            judul="Buku Statistik",
            penulis="Penulis",
            kategori="sistem_informasi",
        )

    def test_profile_and_achievement_pages_render(self):
        self.client.force_login(self.user)
        profile = self.client.get(reverse("profil"))
        self.assertEqual(profile.status_code, 200)

        admin = CustomUser.objects.create_user(
            username="achievement-admin",
            password="test-password",
            is_admin=True,
        )
        self.client.force_login(admin)
        achievements = self.client.get(reverse("kelola_achievement"))
        self.assertEqual(achievements.status_code, 200)

    def test_book_detail_counts_reads_and_bookmark_toggle_persists(self):
        self.client.force_login(self.user)
        detail = self.client.get(reverse("buku_detail", args=[self.book.id_item]))
        self.assertEqual(detail.context["jumlah_dibaca"], 0)
        self.assertContains(detail, "fa-eye")
        self.assertContains(detail, "0x Dibaca")

        Peminjaman.objects.create(user=self.user, buku_digital=self.book)
        detail = self.client.get(reverse("buku_detail", args=[self.book.id_item]))
        self.assertEqual(detail.context["jumlah_dibaca"], 1)
        self.assertContains(detail, "1x Dibaca")

        bookmark_url = reverse("toggle_bookmark", args=[self.book.id_item])
        saved = self.client.post(bookmark_url)
        self.assertJSONEqual(saved.content, {"bookmarked": True})
        self.assertTrue(Bookmark.objects.filter(user=self.user, buku_digital=self.book).exists())
        bookmark_list = self.client.get(reverse("bookmarks"))
        self.assertContains(bookmark_list, "Buku Statistik")

        Bookmark.objects.create(user=self.user, buku_digital=self.book)
        removed = self.client.post(bookmark_url)
        self.assertJSONEqual(removed.content, {"bookmarked": False})
        self.assertFalse(Bookmark.objects.filter(user=self.user, buku_digital=self.book).exists())

    def test_admin_report_excludes_admin_loans(self):
        admin = CustomUser.objects.create_user(
            username="report-admin",
            password="test-password",
            is_admin=True,
        )
        Peminjaman.objects.create(user=self.user, buku_digital=self.book)
        Peminjaman.objects.create(user=admin, buku_digital=self.book)

        self.client.force_login(admin)
        report = self.client.get(reverse("laporan_peminjaman"))
        self.assertEqual(report.context["peminjaman_bulan_ini"], 1)
        self.assertEqual(report.context["anggota_aktif"], 1)
        self.assertEqual(report.context["total_pembaca"], 1)
        self.assertEqual(
            report.context["kategori_list"],
            [{"nama": "Sistem Informasi", "jumlah": 1, "persen": 100}],
        )

    def test_leaderboard_assigns_rank_one_to_highest_exp(self):
        first = CustomUser.objects.create_user(
            username="leader-first",
            password="test-password",
            nama_tampilan="Reader First",
            exp=500,
        )
        CustomUser.objects.create_user(
            username="leader-second",
            password="test-password",
            nama_tampilan="Reader Second",
            exp=250,
        )
        self.client.force_login(self.user)

        leaderboard = self.client.get(reverse("leaderboard"))

        self.assertEqual(leaderboard.context["podium"]["rank1"], first)
        self.assertContains(leaderboard, "podium-avatar-initial")