from datetime import timedelta

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


def _aktivitas_terbaru(batas=4):
    """Gabungkan beberapa jenis aktivitas, urutkan dari yang terbaru."""
    events = []

    for u in CustomUser.objects.filter(is_member=True).order_by(
        "-date_joined"
    )[:batas]:
        events.append(
            {
                "jenis": "anggota",
                "judul": "Anggota baru bergabung",
                "deskripsi": u.nama_tampilan or u.username,
                "waktu": u.date_joined,
            }
        )

    pinjam_qs = Peminjaman.objects.select_related(
        "user", "buku_digital", "jurnal"
    )
    for p in pinjam_qs.order_by("-tanggal_pinjam")[:batas]:
        events.append(
            {
                "jenis": "pinjam",
                "judul": "Buku dipinjam",
                "deskripsi": _judul_item(p),
                "waktu": p.tanggal_pinjam,
            }
        )

    kembali_qs = pinjam_qs.filter(
        status="Selesai", tanggal_kembali__isnull=False
    )
    for p in kembali_qs.order_by("-tanggal_kembali")[:batas]:
        events.append(
            {
                "jenis": "kembali",
                "judul": "Buku dikembalikan",
                "deskripsi": _judul_item(p),
                "waktu": p.tanggal_kembali,
            }
        )

    bm_qs = Bookmark.objects.select_related("buku_digital", "jurnal")
    for b in bm_qs.order_by("-tanggal_disimpan")[:batas]:
        item = b.buku_digital or b.jurnal
        events.append(
            {
                "jenis": "bookmark",
                "judul": "Item disimpan",
                "deskripsi": item.judul if item else "Item sudah dihapus",
                "waktu": b.tanggal_disimpan,
            }
        )

    events.sort(key=lambda e: e["waktu"], reverse=True)
    events = events[:batas]
    for e in events:
        e["waktu_lalu"] = _waktu_lalu(e["waktu"])
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