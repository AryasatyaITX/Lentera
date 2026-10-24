import csv
from datetime import timedelta
import uuid
from django import forms
from django.core.files.storage import FileSystemStorage, default_storage
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone
from .models import AchievementGambar, BukuDigital, CustomUser, Jurnal, Peminjaman, Notifikasi


BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember",
]
HARI_SINGKAT = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]

# Dipakai kalau model Peminjaman tidak punya field jatuh_tempo.
LAMA_PINJAM_HARI = 14

# Nama field di Peminjaman yang menunjuk ke CustomUser (otomatis terdeteksi).
_USER_FIELD = next(
    (
        f.name
        for f in Peminjaman._meta.fields
        if f.is_relation and f.related_model is CustomUser
    ),
    "user",
)

def _boleh_admin(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.is_admin
    )

def _waktu_lalu(dt):
    detik = int((timezone.now() - dt).total_seconds())
    menit = detik // 60
    if menit < 1:
        return "baru saja"
    if menit < 60:
        return f"{menit} menit yang lalu"
    jam = menit // 60
    if jam < 24:
        return f"{jam} jam yang lalu"
    return f"{jam // 24} hari yang lalu"

# [POLIMORFISME lewat pewarisan] BukuDigital dan Jurnal sama-sama mewarisi
# atribut judul dari ItemKatalog, jadi item.judul bisa dipakai untuk
# keduanya tanpa memeriksa tipenya.
def _judul_item(obj):
    item = obj.buku_digital or obj.jurnal
    return item.judul if item else "Item sudah dihapus"

def _aktivitas_terbaru():
    """Selalu empat kartu: buku, jurnal, anggota, dikembalikan."""
    events = []

    b = BukuDigital.objects.order_by("-tanggal_ditambahkan").first()
    events.append({
        "jenis": "buku",
        "judul": "Buku baru ditambahkan",
        "deskripsi": b.judul if b else "Belum ada buku",
        "waktu_lalu": _waktu_lalu(b.tanggal_ditambahkan) if b else "-",
    })

    j = Jurnal.objects.order_by("-tanggal_ditambahkan").first()
    events.append({
        "jenis": "jurnal",
        "judul": "E-journal baru terbit",
        "deskripsi": j.judul if j else "Belum ada jurnal",
        "waktu_lalu": _waktu_lalu(j.tanggal_ditambahkan) if j else "-",
    })

    u = (
        CustomUser.objects.filter(is_member=True)
        .order_by("-date_joined")
        .first()
    )
    events.append({
        "jenis": "anggota",
        "judul": "Anggota baru bergabung",
        "deskripsi": (u.nama_tampilan or u.username) if u else "Belum ada anggota",
        "waktu_lalu": _waktu_lalu(u.date_joined) if u else "-",
    })

    p = (
        Peminjaman.objects.select_related("buku_digital", "jurnal")
        .filter(status="Selesai", tanggal_kembali__isnull=False)
        .order_by("-tanggal_kembali")
        .first()
    )
    events.append({
        "jenis": "kembali",
        "judul": "Buku dikembalikan",
        "deskripsi": _judul_item(p) if p else "Belum ada pengembalian",
        "waktu_lalu": _waktu_lalu(p.tanggal_kembali) if p else "-",
    })

    return events


def _data_grafik_7_hari():
    hari_ini = timezone.localdate()
    mulai = hari_ini - timedelta(days=6)

    def per_hari(qs, field):
        rows = (
            qs.annotate(h=TruncDate(field))
            .order_by()
            .values_list("h")
            .annotate(n=Count("id"))
        )
        return {h: n for h, n in rows}

    dipinjam = per_hari(
        Peminjaman.objects.filter(tanggal_pinjam__date__gte=mulai),
        "tanggal_pinjam",
    )
    dikembalikan = per_hari(
        Peminjaman.objects.filter(
            tanggal_kembali__isnull=False, tanggal_kembali__date__gte=mulai
        ),
        "tanggal_kembali",
    )

    labels, pinjam, kembali = [], [], []
    for i in range(7):
        d = mulai + timedelta(days=i)
        labels.append(f"{HARI_SINGKAT[d.weekday()]} {d.day}")
        pinjam.append(dipinjam.get(d, 0))
        kembali.append(dikembalikan.get(d, 0))
    return {"labels": labels, "pinjam": pinjam, "kembali": kembali}


@user_passes_test(_boleh_admin, login_url="login")
def dashboard_admin(request):
    sekarang = timezone.now()
    hari_ini = timezone.localdate()
    awal_bulan = sekarang.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    anggota = CustomUser.objects.filter(is_member=True)
    populer = (
        BukuDigital.objects.annotate(jumlah=Count("peminjaman"))
        .filter(jumlah__gt=0)
        .order_by("-jumlah")[:5]
    )
    populer = list(populer)
    maks = populer[0].jumlah if populer else 1
    for b in populer:
        b.persen = round(b.jumlah / maks * 100)

    nama = request.user.nama_tampilan or request.user.username

    context = {
        "nama": nama,
        "inisial": nama[:2].upper(),
        "tanggal_teks": (
            f"{hari_ini.day:02d} {BULAN[hari_ini.month - 1]} {hari_ini.year}"
        ),
        "total_buku": BukuDigital.objects.count(),
        "total_jurnal": Jurnal.objects.count(),
        "total_anggota": anggota.count(),
        "anggota_baru": anggota.filter(date_joined__gte=awal_bulan).count(),
        "sedang_dipinjam": Peminjaman.objects.filter(status="Dibaca").count(),
        "dikembalikan_minggu": Peminjaman.objects.filter(
            status="Selesai",
            tanggal_kembali__gte=sekarang - timedelta(days=7),
        ).count(),
        "grafik": _data_grafik_7_hari(),
        "populer": populer,
        "aktivitas": _aktivitas_terbaru(),
    }
    return render(request, "perpustakaan/dashboard_admin.html", context)
# tambah



# ==========================================
# KELOLA BUKU DIGITAL (ADMIN)
# ==========================================
@user_passes_test(_boleh_admin, login_url="login")
def kelola_buku(request):
    if request.method == "POST":
        judul = request.POST.get("judul")
        penulis = request.POST.get("penulis")
        kategori = request.POST.get("kategori", "").strip()
        tahun_terbit = request.POST.get("tahun_terbit", "")
        cover_url = request.POST.get("cover", "")
        deskripsi = request.POST.get("deskripsi", "")
        isbn = request.POST.get("isbn", "").strip()

        id_item = f"BK-{uuid.uuid4().hex[:8].upper()}"

        link_unduh = "https://example.com"
        ukuran_mb = 2.5

        # Proses Upload File PDF
        if "file_pdf" in request.FILES:
            file_pdf = request.FILES["file_pdf"]
            fs = FileSystemStorage()
            filename = fs.save(f"buku_pdf/{file_pdf.name}", file_pdf)
            link_unduh = fs.url(filename)
            ukuran_mb = round(file_pdf.size / (1024 * 1024), 2)

        buku = BukuDigital.objects.create(
            id_item=id_item,
            judul=judul,
            penulis=penulis,
            kategori=kategori,
            isbn=isbn,
            tahun_terbit=tahun_terbit,
            cover=cover_url,
            deskripsi=deskripsi,
            link_unduh=link_unduh,
            ukuran_file=ukuran_mb,
            format_file="PDF",
        )
        judul_notif = f"Buku baru: {buku.judul}"
        for anggota in CustomUser.objects.filter(is_member=True, is_admin=False):
            Notifikasi.objects.create(user=anggota, jenis="katalog", judul=judul_notif,
                isi=f"Buku {buku.judul} baru masuk di kategori {buku.kategori or 'Umum'}.",
                url=f"/buku/{buku.id_item}/")
        return redirect("kelola_buku")

    q = request.GET.get("q", "")
    buku_qs = BukuDigital.objects.all()
    if q:
        buku_qs = buku_qs.filter(
            Q(judul__icontains=q) | Q(penulis__icontains=q)
        )

    buku_list = list(buku_qs)
    for b in buku_list:
        b.total_pembaca = Peminjaman.objects.filter(buku_digital=b).count()

    context = {
        "buku_list": buku_list,
        "search_query": q,
    }
    return render(request, "perpustakaan/kelola_buku.html", context)


@user_passes_test(_boleh_admin, login_url="login")
def hapus_buku(request, id_item):
    if request.method == "POST":
        buku = get_object_or_404(BukuDigital, id_item=id_item)
        buku.delete()
    return redirect("kelola_buku")

@user_passes_test(_boleh_admin, login_url="login")
def edit_buku(request, id_item):
    buku = get_object_or_404(BukuDigital, id_item=id_item)
    if request.method != "POST":
        return redirect("kelola_buku")

    judul = request.POST.get("judul", "").strip()
    penulis = request.POST.get("penulis", "").strip()
    if not judul or not penulis:
        messages.error(request, "Judul dan penulis tidak boleh kosong.")
        return redirect("kelola_buku")

    if "file_pdf" in request.FILES:
        file_pdf = request.FILES["file_pdf"]
        if not file_pdf.name.lower().endswith(".pdf"):
            messages.error(request, "File buku harus berformat PDF.")
            return redirect("kelola_buku")
        fs = FileSystemStorage()
        filename = fs.save(f"buku_pdf/{file_pdf.name}", file_pdf)
        buku.link_unduh = fs.url(filename)
        buku.ukuran_file = round(file_pdf.size / (1024 * 1024), 2)

    buku.judul = judul
    buku.penulis = penulis
    buku.isbn = request.POST.get("isbn", "").strip()
    buku.kategori = request.POST.get("kategori", "").strip()
    buku.tahun_terbit = request.POST.get("tahun_terbit", "").strip()
    buku.cover = request.POST.get("cover", "").strip()
    buku.deskripsi = request.POST.get("deskripsi", "")
    buku.save()
    messages.success(request, f"Buku '{buku.judul}' berhasil diperbarui.")
    return redirect("kelola_buku")

@user_passes_test(_boleh_admin, login_url="login")
def hapus_buku_massal(request):
    if request.method == "POST":
        qs = BukuDigital.objects.filter(id_item__in=request.POST.getlist("ids"))
        jumlah = qs.count()
        if jumlah:
            qs.delete()
            messages.success(request, f"{jumlah} buku berhasil dihapus.")
        else:
            messages.error(request, "Belum ada buku yang dipilih.")
    return redirect("kelola_buku")

# ==========================================
# KELOLA JURNAL (ADMIN)
# ==========================================
@user_passes_test(_boleh_admin, login_url="login")
def kelola_jurnal(request):
    if request.method == "POST":
        judul = request.POST.get("judul")
        penulis = request.POST.get("penulis")
        bidang_ilmu = request.POST.get("bidang_ilmu", "")
        volume = request.POST.get("volume", "")
        tahun_terbit = request.POST.get("tahun_terbit", "")
        cover_url = request.POST.get("cover", "")
        link_akses = request.POST.get("link_akses", "")
        issn = request.POST.get("issn", "").strip()

        id_item = f"JR-{uuid.uuid4().hex[:8].upper()}"

        # Proses Upload File PDF Jurnal
        if "file_pdf" in request.FILES:
            file_pdf = request.FILES["file_pdf"]
            if not file_pdf.name.lower().endswith(".pdf"):
                messages.error(request, "File jurnal harus berformat PDF.")
                return redirect("kelola_jurnal")
            fs = FileSystemStorage()
            filename = fs.save(f"jurnal_pdf/{file_pdf.name}", file_pdf)
            link_akses = fs.url(filename)

        if not link_akses:
            messages.error(request, "Isi tautan laman jurnal atau unggah file PDF.")
            return redirect("kelola_jurnal")

        jurnal = Jurnal.objects.create(
            id_item=id_item,
            judul=judul,
            penulis=penulis,\
            issn=issn,            
            bidang_ilmu=bidang_ilmu,
            volume=volume,
            tahun_terbit=tahun_terbit,
            cover=cover_url,
            link_akses=link_akses,
        )
        for anggota in CustomUser.objects.filter(is_member=True, is_admin=False):
            Notifikasi.objects.create(user=anggota, jenis="katalog", judul="E-journal baru",
                isi=f"E-journal {jurnal.judul} baru ditambahkan ke koleksi.",
                url=f"/jurnal/{jurnal.id_item}/baca/")
        return redirect("kelola_jurnal")

    q = request.GET.get("q", "")
    jurnal_qs = Jurnal.objects.all()
    if q:
        jurnal_qs = jurnal_qs.filter(
            Q(judul__icontains=q) | Q(penulis__icontains=q)
        )

    jurnal_list = list(jurnal_qs)
    for j in jurnal_list:
        j.total_pembaca = Peminjaman.objects.filter(jurnal=j).count()

    context = {
        "jurnal_list": jurnal_list,
        "search_query": q,
    }
    return render(request, "perpustakaan/kelola_jurnal.html", context)


@user_passes_test(_boleh_admin, login_url="login")
def buat_pengumuman(request):
    if request.method == "POST":
        jenis = request.POST.get("jenis", "pengumuman")
        judul = request.POST.get("judul", "").strip()
        isi = request.POST.get("isi", "").strip()
        if jenis not in ("pengumuman", "gamifikasi") or not judul or not isi:
            messages.error(request, "Jenis, judul, dan isi notifikasi wajib diisi.")
            return redirect("buat_pengumuman")
        if jenis == "gamifikasi":
            judul = f"Pilihan admin minggu ini: {judul}"
        anggota = CustomUser.objects.filter(is_member=True, is_admin=False)
        Notifikasi.objects.bulk_create([
            Notifikasi(user=user, jenis=jenis, judul=judul, isi=isi,
                       url=request.POST.get("url", "").strip())
            for user in anggota
        ])
        messages.success(request, f"Notifikasi terkirim ke {anggota.count()} anggota.")
        return redirect("buat_pengumuman")
    return render(request, "perpustakaan/admin/buat_pengumuman.html")


@user_passes_test(_boleh_admin, login_url="login")
def hapus_jurnal(request, id_item):
    if request.method == "POST":
        jurnal = get_object_or_404(Jurnal, id_item=id_item)
        jurnal.delete()
    return redirect("kelola_jurnal")

@user_passes_test(_boleh_admin, login_url="login")
def edit_jurnal(request, id_item):
    jurnal = get_object_or_404(Jurnal, id_item=id_item)
    if request.method != "POST":
        return redirect("kelola_jurnal")

    judul = request.POST.get("judul", "").strip()
    penulis = request.POST.get("penulis", "").strip()
    if not judul or not penulis:
        messages.error(request, "Judul dan penulis tidak boleh kosong.")
        return redirect("kelola_jurnal")

    link_akses = request.POST.get("link_akses", "").strip()
    if "file_pdf" in request.FILES:
        file_pdf = request.FILES["file_pdf"]
        if not file_pdf.name.lower().endswith(".pdf"):
            messages.error(request, "File jurnal harus berformat PDF.")
            return redirect("kelola_jurnal")
        fs = FileSystemStorage()
        filename = fs.save(f"jurnal_pdf/{file_pdf.name}", file_pdf)
        link_akses = fs.url(filename)

    jurnal.judul = judul
    jurnal.penulis = penulis
    jurnal.issn = request.POST.get("issn", "").strip()
    jurnal.bidang_ilmu = request.POST.get("bidang_ilmu", "").strip()
    jurnal.volume = request.POST.get("volume", "").strip()
    jurnal.tahun_terbit = request.POST.get("tahun_terbit", "").strip()
    jurnal.cover = request.POST.get("cover", "").strip()
    if link_akses:                      # kosong = pertahankan link lama
        jurnal.link_akses = link_akses
    jurnal.save()
    messages.success(request, f"Jurnal '{jurnal.judul}' berhasil diperbarui.")
    return redirect("kelola_jurnal")

@user_passes_test(_boleh_admin, login_url="login")
def hapus_jurnal_massal(request):
    if request.method == "POST":
        qs = Jurnal.objects.filter(id_item__in=request.POST.getlist("ids"))
        jumlah = qs.count()
        if jumlah:
            qs.delete()
            messages.success(request, f"{jumlah} jurnal berhasil dihapus.")
        else:
            messages.error(request, "Belum ada jurnal yang dipilih.")
    return redirect("kelola_jurnal")

# ==========================================
# KELOLA ACHIEVEMENT (ADMIN)
# ==========================================
BATAS_GAMBAR_MB = 2
KATEGORI_ACHIEVEMENT = ["Umum", "Langka", "Epik"]


class AchievementForm(forms.ModelForm):
    class Meta:
        model = AchievementGambar
        fields = ["nama", "kategori", "deskripsi", "gambar_terkunci", "gambar_terbuka"]
        labels = {
            "tipe_syarat": "Jenis syarat",   
            "target": "Target",   
            "nama": "Nama",
            "kategori": "Kategori",
            "deskripsi": "Deskripsi",
            "gambar_terkunci": "Gambar terkunci",
            "gambar_terbuka": "Gambar terbuka",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nama"].error_messages["required"] = "wajib diisi."
        self.fields["kategori"].error_messages["invalid_choice"] = "pilih Umum, Langka, atau Epik."
        for nama in ("gambar_terkunci", "gambar_terbuka"):
            self.fields[nama].error_messages["required"] = "wajib diunggah."
            self.fields[nama].error_messages["invalid_image"] = "harus berupa gambar (PNG, JPG, WEBP, atau GIF)."

    def clean_nama(self):
        nama = self.cleaned_data["nama"].strip()
        ada = AchievementGambar.objects.filter(nama__iexact=nama)
        if self.instance.pk:
            ada = ada.exclude(pk=self.instance.pk)
        if ada.exists():
            raise forms.ValidationError("sudah dipakai achievement lain.")
        return nama

    def clean_target(self):
        target = self.cleaned_data.get("target") or 0
        if target < 1:
            raise forms.ValidationError("minimal 1.")
        return target

    def _cek_ukuran(self, field):
        berkas = self.cleaned_data.get(field)
        # hanya file yang baru diunggah yang punya content_type
        if getattr(berkas, "content_type", None) and berkas.size > BATAS_GAMBAR_MB * 1024 * 1024:
            raise forms.ValidationError(f"maksimal {BATAS_GAMBAR_MB} MB.")
        return berkas

    def clean_gambar_terkunci(self):
        return self._cek_ukuran("gambar_terkunci")

    def clean_gambar_terbuka(self):
        return self._cek_ukuran("gambar_terbuka")


def _galat_form(form):
    teks = []
    for nama, daftar in form.errors.items():
        label = form.fields[nama].label if nama in form.fields else ""
        teks.append(f"{label} {' '.join(daftar)}".strip())
    return " · ".join(teks)


def _hapus_berkas(ach):
    for berkas in (ach.gambar_terkunci, ach.gambar_terbuka):
        if berkas:
            berkas.delete(save=False)


@user_passes_test(_boleh_admin, login_url="login")
def kelola_achievement(request):
    if request.method == "POST":
        form = AchievementForm(request.POST, request.FILES)
        if form.is_valid():
            ach = form.save()
            messages.success(request, f"Achievement '{ach.nama}' berhasil ditambahkan.")
        else:
            messages.error(request, _galat_form(form))
        return redirect("kelola_achievement")

    q = request.GET.get("q", "").strip()
    kategori = request.GET.get("kategori", "")
    if kategori not in KATEGORI_ACHIEVEMENT:
        kategori = ""

    qs = AchievementGambar.objects.all()
    if kategori:
        qs = qs.filter(kategori=kategori)
    if q:
        qs = qs.filter(Q(nama__icontains=q) | Q(deskripsi__icontains=q))

    hitung = dict(AchievementGambar.objects.values_list("kategori").annotate(Count("id")))
    context = {
        "achievement_list": qs,
        "search_query": q,
        "kategori_aktif": kategori,
        "total": sum(hitung.values()),
        "n_umum": hitung.get("Umum", 0),
        "n_langka": hitung.get("Langka", 0),
        "n_epik": hitung.get("Epik", 0),
    }
    return render(request, "perpustakaan/kelola_achievement.html", context)


@user_passes_test(_boleh_admin, login_url="login")
def edit_achievement(request, pk):
    ach = get_object_or_404(AchievementGambar, pk=pk)
    if request.method != "POST":
        return redirect("kelola_achievement")

    nama_lama = (ach.gambar_terkunci.name, ach.gambar_terbuka.name)
    form = AchievementForm(request.POST, request.FILES, instance=ach)
    if form.is_valid():
        ach = form.save()
        nama_baru = (ach.gambar_terkunci.name, ach.gambar_terbuka.name)
        for lama, baru in zip(nama_lama, nama_baru):
            if lama and lama != baru:          # gambar diganti: hapus file lama
                default_storage.delete(lama)
        messages.success(request, f"Achievement '{ach.nama}' berhasil diperbarui.")
    else:
        messages.error(request, _galat_form(form))
    return redirect("kelola_achievement")


@user_passes_test(_boleh_admin, login_url="login")
def hapus_achievement(request, pk):
    if request.method == "POST":
        ach = get_object_or_404(AchievementGambar, pk=pk)
        nama = ach.nama
        _hapus_berkas(ach)
        ach.delete()
        messages.success(request, f"Achievement '{nama}' berhasil dihapus.")
    return redirect("kelola_achievement")


@user_passes_test(_boleh_admin, login_url="login")
def hapus_achievement_massal(request):
    if request.method == "POST":
        ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
        daftar = list(AchievementGambar.objects.filter(pk__in=ids))
        if daftar:
            for ach in daftar:
                _hapus_berkas(ach)
                ach.delete()
            messages.success(request, f"{len(daftar)} achievement berhasil dihapus.")
        else:
            messages.error(request, "Belum ada achievement yang dipilih.")
    return redirect("kelola_achievement")

# ==========================================
# KELOLA ANGGOTA (ADMIN)
# ==========================================
def _pinjaman_per_user():
    """Dictionary {id_user: jumlah_peminjaman}."""
    rows = (
        Peminjaman.objects.order_by()
        .values(_USER_FIELD)
        .annotate(n=Count("id"))
    )
    return {r[_USER_FIELD]: r["n"] for r in rows}


def _cek_password(pw):
    """Kembalikan pesan error bila password tidak memenuhi syarat, else None."""
    import re
    if not (8 <= len(pw) <= 20):
        return "Password harus 8 - 20 karakter."
    if not re.search(r"[^A-Za-z0-9\s]", pw):
        return "Password harus memuat minimal 1 karakter unik (mis. ! @ # $)."
    if not re.search(r"[A-Z]", pw):
        return "Password harus memuat minimal 1 huruf besar."
    return None


def _queryset_anggota():
    """Hanya user biasa. Akun admin tidak ditampilkan / tidak bisa diubah di sini."""
    return (
        CustomUser.objects.filter(is_member=True)
        .exclude(is_admin=True)
        .exclude(is_staff=True)
        .exclude(is_superuser=True)
    )


@user_passes_test(_boleh_admin, login_url="login")
def kelola_anggota(request):
    # CREATE
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        nama = request.POST.get("nama_tampilan", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not username:
            messages.error(request, "Username wajib diisi.")
        elif _cek_password(password):
            messages.error(request, _cek_password(password))
        elif CustomUser.objects.filter(username__iexact=username).exists():
            messages.error(request, f"Username \u201c{username}\u201d sudah dipakai.")
        else:
            user = CustomUser(
                username=username,
                nama_tampilan=nama,
                email=email,
                is_member=True,
                is_active=True,
            )
            user.set_password(password)
            user.save()
            messages.success(request, f"Anggota \u201c{nama or username}\u201d berhasil ditambahkan.")
        return redirect("kelola_anggota")

    # READ
    anggota = list(_queryset_anggota().order_by("-date_joined"))
    jumlah = _pinjaman_per_user()
    for a in anggota:
        a.jumlah_pinjaman = jumlah.get(a.pk, 0)

    return render(
        request, "perpustakaan/kelola_anggota.html", {"anggota": anggota}
    )


@user_passes_test(_boleh_admin, login_url="login")
def edit_anggota(request, pk):
    """UPDATE data anggota."""
    user = get_object_or_404(_queryset_anggota(), pk=pk)
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        nama = request.POST.get("nama_tampilan", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        aktif = request.POST.get("is_active", "1") == "1"

        if not username:
            messages.error(request, "Username tidak boleh kosong.")
        elif CustomUser.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
            messages.error(request, f"Username \u201c{username}\u201d sudah dipakai.")
        elif password and _cek_password(password):
            messages.error(request, _cek_password(password))
        else:
            perubahan = []
            if user.nama_tampilan != nama:
                perubahan.append(f"nama tampilan menjadi {nama or username}")
            if user.username != username:
                perubahan.append("username diperbarui")
            if user.email != email:
                perubahan.append("alamat email diperbarui")
            if user.is_active != aktif:
                perubahan.append("status akun diaktifkan" if aktif else "status akun dinonaktifkan")
            if password:
                perubahan.append("kata sandi diperbarui")
            user.username = username
            user.nama_tampilan = nama
            user.email = email
            user.is_active = aktif
            if password:
                user.set_password(password)
            user.save()
            if perubahan:
                Notifikasi.objects.create(
                    user=user,
                    jenis="pengumuman",
                    judul="Informasi akun diperbarui oleh admin",
                    isi="Admin memperbarui " + ", ".join(perubahan) + ". Jika perubahan ini tidak kamu minta, hubungi admin perpustakaan.",
                    url="/profil/",
                )
            messages.success(request, "Data anggota berhasil diperbarui.")
    return redirect("kelola_anggota")


@user_passes_test(_boleh_admin, login_url="login")
def hapus_anggota(request, pk):
    """DELETE = nonaktifkan akun. Akun pindah ke tab Nonaktif, riwayat pinjam tetap ada."""
    if request.method == "POST":
        user = get_object_or_404(_queryset_anggota(), pk=pk)
        user.is_active = False
        user.save(update_fields=["is_active"])
        messages.success(
            request,
            f"Akun \u201c{user.nama_tampilan or user.username}\u201d dinonaktifkan.",
        )
    return redirect("kelola_anggota")


@user_passes_test(_boleh_admin, login_url="login")
def aktifkan_anggota(request, pk):
    if request.method == "POST":
        user = get_object_or_404(_queryset_anggota(), pk=pk)
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(
            request,
            f"Akun \u201c{user.nama_tampilan or user.username}\u201d diaktifkan kembali.",
        )
    return redirect("kelola_anggota")


# ==========================================
# PEMINJAMAN & PENGEMBALIAN (ADMIN)
# ==========================================
@user_passes_test(_boleh_admin, login_url="login")
def peminjaman_admin(request):
    hari_ini = timezone.localdate()
    daftar = list(
        Peminjaman.objects.select_related(_USER_FIELD, "buku_digital", "jurnal")
        .order_by("-tanggal_pinjam")
    )

    for p in daftar:
        p.pengguna = getattr(p, _USER_FIELD)
        p.item = p.buku_digital or p.jurnal
        p.is_kembali = p.status == "Selesai"

        jatuh_tempo = getattr(p, "jatuh_tempo", None) or (
            p.tanggal_pinjam + timedelta(days=LAMA_PINJAM_HARI)
        )
        p.jatuh_tempo_tampil = jatuh_tempo
        tgl = jatuh_tempo.date() if hasattr(jatuh_tempo, "date") else jatuh_tempo
        p.is_telat = (not p.is_kembali) and tgl < hari_ini

    return render(
        request, "perpustakaan/peminjaman_admin.html", {"peminjaman": daftar}
    )


# ==========================================
# LAPORAN (ADMIN)
# ==========================================
@user_passes_test(_boleh_admin, login_url="login")
def laporan(request):
    sekarang = timezone.now()
    awal_bulan = sekarang.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    anggota = CustomUser.objects.filter(is_member=True)

    # Anggota aktif = anggota yang meminjam dalam 30 hari terakhir.
    id_aktif = (
        Peminjaman.objects.filter(
            tanggal_pinjam__gte=sekarang - timedelta(days=30)
        )
        .order_by()
        .values_list(_USER_FIELD, flat=True)
        .distinct()
    )

    # Buku per kategori
    rows = list(
        BukuDigital.objects.values("kategori")
        .annotate(jumlah=Count("pk"))
        .order_by("-jumlah")
    )
    maks = rows[0]["jumlah"] if rows else 1
    kategori_list = [
        {
            "nama": (r["kategori"] or "Lainnya").replace("_", " ").title(),
            "jumlah": r["jumlah"],
            "persen": round(r["jumlah"] / maks * 100),
        }
        for r in rows
    ]

    grafik = _data_grafik_7_hari()

    context = {
        "peminjaman_bulan_ini": Peminjaman.objects.filter(
            tanggal_pinjam__gte=awal_bulan
        ).count(),
        "jurnal_tersedia": Jurnal.objects.count(),
        "anggota_aktif": anggota.filter(pk__in=id_aktif).count(),
        "total_pembaca": anggota.count(),
        "buku_tersedia": BukuDigital.objects.count(),
        "volume_labels": grafik["labels"],
        "volume_pinjam": grafik["pinjam"],
        "volume_kembali": grafik["kembali"],
        "kategori_list": kategori_list,
    }
    return render(request, "perpustakaan/laporan_peminjaman.html", context)


@user_passes_test(_boleh_admin, login_url="login")
def unduh_laporan(request):
    """Unduh seluruh data peminjaman sebagai CSV (bisa dibuka di Excel)."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="laporan-peminjaman.csv"'
    response.write("\ufeff")  # agar Excel membaca UTF-8 dengan benar

    writer = csv.writer(response)
    writer.writerow(["Buku/Jurnal", "Anggota", "Tanggal pinjam", "Tanggal kembali", "Status"])

    qs = Peminjaman.objects.select_related(
        _USER_FIELD, "buku_digital", "jurnal"
    ).order_by("-tanggal_pinjam")

    for p in qs:
        writer.writerow([
            _judul_item(p),
            getattr(p, _USER_FIELD).username,
            p.tanggal_pinjam.strftime("%Y-%m-%d"),
            p.tanggal_kembali.strftime("%Y-%m-%d") if p.tanggal_kembali else "-",
            "Dikembalikan" if p.status == "Selesai" else "Dipinjam",
        ])

    return response
