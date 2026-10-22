from django.test import TestCase
from django.urls import reverse

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
        self.assertContains(first_page, 'data-bookmark-stats', count=10)
        self.assertNotContains(first_page, '4.8')
        self.assertNotContains(first_page, 'fa-eye')

        second_page = self.client.get(reverse('bookmarks'), {'page': 2})
        self.assertEqual(len(second_page.context['bookmarks']), 2)
        self.assertContains(second_page, 'Halaman 2 dari 2')

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