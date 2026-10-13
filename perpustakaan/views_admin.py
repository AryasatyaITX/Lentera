from datetime import timedelta
import uuid
from django.core.files.storage import FileSystemStorage
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from .models import Bookmark, BukuDigital, CustomUser, Jurnal, Peminjaman

BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember",
]
HARI_SINGKAT = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


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

        BukuDigital.objects.create(
            id_item=id_item,
            judul=judul,
            penulis=penulis,
            kategori=kategori,
            tahun_terbit=tahun_terbit,
            cover=cover_url,
            deskripsi=deskripsi,
            link_unduh=link_unduh,
            ukuran_file=ukuran_mb,
            format_file="PDF",
        )
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


# ==========================================
# KELOLA JURNAL (ADMIN)
# ==========================================
@user_passes_test(_boleh_admin, login_url="login")
def kelola_jurnal(request):
    if request.method == "POST":
        judul = request.POST.get("judul")
        penulis = request.POST.get("penulis")
        kategori="", 
        bidang_ilmu = request.POST.get("bidang_ilmu", "")
        volume = request.POST.get("volume", "")
        tahun_terbit = request.POST.get("tahun_terbit", "")
        cover_url = request.POST.get("cover", "")
        link_akses = request.POST.get("link_akses", "")

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

        Jurnal.objects.create(
            id_item=id_item,
            judul=judul,
            penulis=penulis,
            bidang_ilmu=bidang_ilmu,
            volume=volume,
            tahun_terbit=tahun_terbit,
            cover=cover_url,
            link_akses=link_akses,
        )
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
def hapus_jurnal(request, id_item):
    if request.method == "POST":
        jurnal = get_object_or_404(Jurnal, id_item=id_item)
        jurnal.delete()
    return redirect("kelola_jurnal")
