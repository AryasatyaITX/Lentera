import os
import uuid
from datetime import date, timedelta
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

KATEGORI_PRODI = [
    ("teknik_elektro", "Teknik Elektro"),
    ("teknik_sipil", "Teknik Sipil"),
    ("teknik_industri", "Teknik Industri"),
    ("teknik_pertambangan", "Teknik Pertambangan"),
    ("teknik_kimia", "Teknik Kimia"),
    ("teknik_geologi", "Teknik Geologi"),
    ("arsitektur", "Arsitektur"),
    ("informatika", "Informatika"),
    ("sistem_informasi", "Sistem Informasi"),
    ("teknik_lingkungan", "Teknik Lingkungan"),
]

TARGET_HARIAN_DETIK = 30 * 60


def label_kategori(kategori):
    label = dict(KATEGORI_PRODI).get(kategori)
    return label or (kategori or "").replace("_", " ").title()


# [ABSTRAKSI] ItemKatalog adalah abstract base class (Meta.abstract = True).
# Class ini hanya cetak biru atribut umum item katalog dan tidak membuat tabel
# sendiri. Objek langsung dari ItemKatalog tidak bisa dibuat, hanya subclass-nya.
class ItemKatalog(models.Model):
    # ENKAPSULASI: atribut data item dikelompokkan sebagai field class model.
    # Setiap object ItemKatalog turunannya memiliki nilai field masing-masing.
    id_item = models.CharField(max_length=20, unique=True, primary_key=True)
    judul = models.CharField(max_length=255)
    penulis = models.CharField(max_length=255)
    tahun_terbit = models.CharField(max_length=4, blank=True)
    cover = models.URLField(blank=True, null=True)  # URL gambar sampul
    tanggal_ditambahkan = models.DateTimeField(default=timezone.now) 

    class Meta:
        abstract = True

# [PEWARISAN] BukuDigital adalah subclass ItemKatalog (is-a). Ia mewarisi
# judul, penulis, tahun_terbit, cover, dan tanggal_ditambahkan, lalu menambah
# atribut khusus buku digital seperti ISBN, link_unduh, dan format_file.
class BukuDigital(ItemKatalog):
    kategori = models.CharField(max_length=50, default="", blank=True)
    isbn = models.CharField(max_length=20, blank=True, default="") 
    link_unduh = models.URLField(default="https://example.com")
    ukuran_file = models.FloatField(default=2.5, help_text="dalam MB")
    format_file = models.CharField(max_length=10, default="PDF")
    deskripsi = models.TextField(blank=True, default="")

    @property
    def kategori_label(self):
        return label_kategori(self.kategori)

    # [POLIMORFISME - overriding] Menimpa __str__ bawaan Model.
    def __str__(self):
        return f"[Digital] {self.judul}"


# [PEWARISAN] Jurnal juga subclass ItemKatalog, sehingga berbagi atribut
# dasar dengan BukuDigital. Atribut khususnya: ISSN, volume, bidang_ilmu,
# dan link_akses.
class Jurnal(ItemKatalog):
    kategori = models.CharField(max_length=50, default="", blank=True)
    issn = models.CharField(max_length=9, blank=True, default="")
    volume = models.CharField(max_length=50, blank=True)
    bidang_ilmu = models.CharField(max_length=100, blank=True)
    link_akses = models.URLField(default="https://example.com")

    # [POLIMORFISME - overriding] Menimpa __str__ bawaan Model.
    def __str__(self):
        return f"[Jurnal] {self.judul}"


# [ASOSIASI ANTAROBJEK] Peminjaman menghubungkan satu CustomUser dengan satu
# BukuDigital atau Jurnal lewat ForeignKey. Objek terkait diakses lewat
# relasi, bukan disalin datanya.
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
    waktu_baca_detik = models.IntegerField(default=0)  # BARU: detik membaca untuk peminjaman ini
    perpanjangan = models.PositiveIntegerField(default=0)

    # [POLIMORFISME - overriding] Menimpa __str__ bawaan Model.
    def __str__(self):
        item = self.buku_digital or self.jurnal
        return f"{self.user.username} {item} ({self.status})"


# ASOSIASI ANTAROBJECT: Bookmark menghubungkan user dengan item katalog yang
# disimpan. ForeignKey mengelola relasi dan perilaku penghapusan datanya.
class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    buku_digital = models.ForeignKey(
        BukuDigital, null=True, blank=True, on_delete=models.CASCADE
    )
    jurnal = models.ForeignKey(
        Jurnal, null=True, blank=True, on_delete=models.CASCADE
    )
    tanggal_disimpan = models.DateTimeField(auto_now_add=True)

    # [POLIMORFISME - overriding] Menimpa __str__ bawaan Model.
    def __str__(self):
        item = self.buku_digital or self.jurnal
        return f"{self.user.username} saved {item}"


# ====================== ACHIEVEMENT & KATEGORI ======================
class Achievement(models.Model):
    KATEGORI_CHOICES = [
        ('Umum', 'Umum'),
        ('Langka', 'Langka'),
        ('Epik', 'Epik'),
    ]
    
    nama = models.CharField(max_length=100)
    deskripsi = models.TextField(blank=True)
    kategori = models.CharField(max_length=20, choices=KATEGORI_CHOICES, default='Umum')
    ikon = models.CharField(max_length=50, default='fa-trophy') # Kelas icon FontAwesome/Material
    syarat = models.CharField(max_length=255, blank=True)

    # [POLIMORFISME - overriding] Menimpa __str__ bawaan Model.
    def __str__(self):
        return f"[{self.kategori}] {self.nama}"


class UserAchievement(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_achievements')
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    tanggal_didapat = models.DateTimeField(auto_now_add=True)

    # [POLIMORFISME - overriding] Menimpa __str__ bawaan Model.
    def __str__(self):
        return f"{self.user.username} {self.achievement.nama}"


class Notifikasi(models.Model):
    JENIS = [(key, key.replace("_", " ").title()) for key in (
        "katalog", "pengumuman", "peminjaman", "tenggat", "gamifikasi"
    )]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifikasi")
    jenis = models.CharField(max_length=20, choices=JENIS, default="pengumuman")
    judul = models.CharField(max_length=180)
    isi = models.TextField()
    url = models.CharField(max_length=500, blank=True)
    dibuat = models.DateTimeField(default=timezone.now)
    dibaca = models.BooleanField(default=False)

    class Meta:
        ordering = ["-dibuat", "-pk"]

    def __str__(self):
        return f"{self.user.username}: {self.judul}"


# PEWARISAN: CustomUser memperluas class AbstractUser dari Django dengan
# atribut dan perilaku khusus aplikasi Lentera.
class CustomUser(AbstractUser):
    is_admin = models.BooleanField(default=False)
    is_member = models.BooleanField(default=True)

    # --- FITUR PROFIL KUSTOM ---
    nama_tampilan = models.CharField(max_length=100)
    foto_profil = models.ImageField(upload_to="profil/", blank=True, null=True)
    foto_background = models.ImageField(
        upload_to="backgrounds/", null=True, blank=True
    )

    # Tambahan untuk OTP dan Reset Password (email sudah bawaan AbstractUser)
    email = models.EmailField(blank=True, null=True)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)

    exp = models.IntegerField(default=0)
    waktu_baca_detik = models.IntegerField(default=0)
    detik_baca_hari_ini = models.PositiveIntegerField(default=0)
    tanggal_baca_harian = models.DateField(null=True, blank=True)
    streak_days = models.IntegerField(default=0)
    last_read_date = models.DateField(null=True, blank=True)
    max_loans = models.IntegerField(default=5)

    # BARU: Field untuk menyimpan custom achievement yang dipilih/disematkan di profil (maksimal 3)
    pinned_achievements = models.TextField(blank=True, default="")

    # POLIMORFISME (method overriding): save() mengganti/menambahkan perilaku
    # penyimpanan bawaan tanpa menghasilkan nama tampilan dari NIM.
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @property
    def nama_asli(self):
        nama_lengkap = self.get_full_name().strip()
        if nama_lengkap:
            return nama_lengkap
        nama = (self.nama_tampilan or "").strip()
        if nama.startswith("User_") and nama[5:].isdigit():
            return self.username
        return nama or self.username

    # ENKAPSULASI PERILAKU: operasi perubahan EXP diletakkan pada object user,
    # sehingga aturan perubahan state tidak perlu ditulis ulang pemanggilnya.
    def add_exp(self, points):
        self.exp += points
        self.save()

    def update_streak(self):
        """Perbarui streak setelah target baca harian tercapai."""
        today = timezone.localdate()
        if (
            self.tanggal_baca_harian != today
            or self.detik_baca_hari_ini < TARGET_HARIAN_DETIK
            or self.last_read_date == today
        ):
            return

        if self.last_read_date == today - timedelta(days=1):
            self.streak_days += 1
        elif not self.last_read_date or self.last_read_date < today - timedelta(
            days=1
        ):
            self.streak_days = 1  # Reset atau mulai baru

        self.last_read_date = today
        self.save()

    def reset_streak_if_expired(self):
        """Hapus streak yang sudah melewatkan satu hari tanpa target baca."""
        today = timezone.localdate()
        if (
            self.streak_days
            and self.last_read_date
            and self.last_read_date < today - timedelta(days=1)
        ):
            self.streak_days = 0
            self.save(update_fields=["streak_days"])

    # [POLIMORFISME - overriding] Menimpa __str__ bawaan Model.
    def __str__(self):
        return self.username


class Pengaturan(models.Model):
    masa_pinjam_hari = models.PositiveIntegerField(default=14)

    class Meta:
        verbose_name_plural = "Pengaturan"

    # [POLIMORFISME - overriding] Menimpa __str__ bawaan Model.
    def __str__(self):
        return f"Masa pinjam: {self.masa_pinjam_hari} hari"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def muat(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def path_gambar_terkunci(instance, filename):
    return f"achievement/terkunci/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"

def path_gambar_terbuka(instance, filename):
    return f"achievement/terbuka/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"
class AchievementGambar(models.Model):
    KATEGORI_CHOICES = [("Umum", "Umum"), ("Langka", "Langka"), ("Epik", "Epik")]

    TIPE_SYARAT_CHOICES = [
        ("buku_selesai", "Jumlah buku yang diselesaikan"),
        ("buku_dimulai", "Jumlah judul buku berbeda yang dibaca"),
        ("genre", "Jumlah genre berbeda yang dibaca"),
        ("pinjam_total", "Total peminjaman"),
        ("pinjam_selesai", "Peminjaman yang diselesaikan"),
        ("bookmark", "Jumlah bookmark"),
        ("exp", "Total EXP"),
        ("streak", "Hari beruntun membaca (streak)"),
    ]

    nama = models.CharField(max_length=100, unique=True)
    kategori = models.CharField(max_length=10, choices=KATEGORI_CHOICES, default="Umum")
    deskripsi = models.TextField(blank=True, default="")
    gambar_terkunci = models.ImageField(upload_to=path_gambar_terkunci)
    gambar_terbuka = models.ImageField(upload_to=path_gambar_terbuka)
    tipe_syarat = models.CharField(max_length=20, choices=TIPE_SYARAT_CHOICES, blank=True, default="")
    target = models.PositiveIntegerField(default=1)
    dibuat = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ["-dibuat", "-id"]

    def __str__(self):
        return f"[{self.kategori}] {self.nama}"
