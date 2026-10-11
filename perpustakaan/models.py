from datetime import date, timedelta
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


# ABSTRACT CLASS
class ItemKatalog(models.Model):
    id_item = models.CharField(max_length=20, unique=True, primary_key=True)
    judul = models.CharField(max_length=255)
    penulis = models.CharField(max_length=255)
    tahun_terbit = models.CharField(max_length=4, blank=True)
    cover = models.URLField(blank=True, null=True)  # URL gambar sampul

    class Meta:
        abstract = True  # Pilar Abstraction OOP


# id_item diisi OLID dari Open Library (contoh: OL45883W)
class BukuDigital(ItemKatalog):
    link_unduh = models.URLField(default="https://example.com")
    ukuran_file = models.FloatField(default=2.5, help_text="dalam MB")
    format_file = models.CharField(max_length=10, default="PDF")
    deskripsi = models.TextField(blank=True, default="")
    ia_id = models.CharField(
        max_length=100, blank=True, default=""
    )  # ID archive.org, kalau ada

    def __str__(self):
        return f"[Digital] {self.judul}"


# ====================== JURNAL ======================
class Jurnal(ItemKatalog):
    volume = models.CharField(max_length=50, blank=True)
    bidang_ilmu = models.CharField(max_length=100, blank=True)
    link_akses = models.URLField(default="https://example.com")

    def __str__(self):
        return f"[Jurnal] {self.judul}"


class Peminjaman(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    buku_digital = models.ForeignKey(
        BukuDigital, null=True, blank=True, on_delete=models.SET_NULL
    )
    jurnal = models.ForeignKey(
        Jurnal, null=True, blank=True, on_delete=models.SET_NULL
    )

    tanggal_pinjam = models.DateTimeField(auto_now_add=True)
    tanggal_kembali = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, default="Dibaca"
    )  # Dibaca / Selesai
    progress_baca = models.IntegerField(default=0)  # 0 - 100%

    def __str__(self):
        item = self.buku_digital or self.jurnal
        return f"{self.user.username} - {item} ({self.status})"


class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    buku_digital = models.ForeignKey(
        BukuDigital, null=True, blank=True, on_delete=models.CASCADE
    )
    jurnal = models.ForeignKey(
        Jurnal, null=True, blank=True, on_delete=models.CASCADE
    )
    tanggal_disimpan = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        item = self.buku_digital or self.jurnal
        return f"{self.user.username} saved {item}"


class CustomUser(AbstractUser):
    is_admin = models.BooleanField(default=False)
    is_member = models.BooleanField(default=True)

    # --- FITUR PROFIL KUSTOM ---
    nama_tampilan = models.CharField(max_length=100)
    foto_profil = models.ImageField(upload_to="profil/", blank=True, null=True)
    foto_background = models.ImageField(
        upload_to="backgrounds/", null=True, blank=True
    )

    exp = models.IntegerField(default=0)
    streak_days = models.IntegerField(default=0)
    last_read_date = models.DateField(null=True, blank=True)
    max_loans = models.IntegerField(default=5)

    def save(self, *args, **kwargs):
        if not self.nama_tampilan and self.username:
            tiga_digit = (
                self.username[-3:] if len(self.username) >= 3 else self.username
            )
            self.nama_tampilan = f"User_{tiga_digit}"
        super().save(*args, **kwargs)

    def add_exp(self, points):
        self.exp += points
        self.save()

    def update_streak(self):
        """Logika otomatis memperbarui streak harian user"""
        today = timezone.localdate()
        if self.last_read_date == today:
            return  # Sudah dihitung hari ini

        if self.last_read_date == today - timedelta(days=1):
            self.streak_days += 1
        elif not self.last_read_date or self.last_read_date < today - timedelta(
            days=1
        ):
            self.streak_days = 1  # Reset atau mulai baru

        self.last_read_date = today
        self.save()

    def __str__(self):
        return self.username