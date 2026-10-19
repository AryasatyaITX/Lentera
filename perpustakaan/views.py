from datetime import timedelta, date
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.timesince import timesince
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from .models import CustomUser, BukuDigital, Jurnal, Peminjaman, Bookmark, Pengaturan, Achievement, UserAchievement
from django.db.models import Count, Q
import json
import os
import random
import re
import time
from urllib.parse import urlparse
from django.conf import settings

MASA_PINJAM_HARI = 14
RING_DETIK_PENUH = 120   # 2 menit membaca aktif
RING_EXP = 10            # EXP tiap cincin penuh
RING_BEAT_MAKS = 15      # batas detik yang boleh dilaporkan per kiriman
PAGINATION_PAGE_SIZE = 10
ITEM_ID_RE = re.compile(r'^[\w-]+$')
COVER_PREFIX = 'https://covers.openlibrary.org/'

KATEGORI = [
    ("engineering", "Engineering"),
    ("computer science", "Computer Science"),
    ("mathematics", "Matematika"),
    ("physics", "Fisika"),
    ("business", "Bisnis"),
    ("fiction", "Fiksi"),
    ("history", "Sejarah"),
]
DEFAULT_KATEGORI = "engineering"
BAHASA = [("", "Semua bahasa"), ("ind", "Indonesia"), ("eng", "Inggris")]


def is_admin(user):
    return user.is_authenticated and (user.is_admin or user.is_staff)


def login_view(request):
    if request.user.is_authenticated:
        if is_admin(request.user):
            return redirect("dashboard_admin")
        return redirect("dashboard")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "reset_password":
            username_input = request.POST.get("username")
            email_input = request.POST.get("email")
            new_password = request.POST.get("new_password")
            confirm_password = request.POST.get("confirm_password")

            if new_password != confirm_password:
                messages.error(request, "Konfirmasi password baru tidak cocok!")
            else:
                user = CustomUser.objects.filter(username=username_input, email=email_input).first()
                if user:
                    user.set_password(new_password)
                    user.save()
                    messages.success(request, "Password berhasil diubah! Silakan login dengan password baru.")
                else:
                    messages.error(request, "Username/NIM atau Email terdaftar tidak ditemukan!")
        else:
            username_input = request.POST.get("username")
            password_input = request.POST.get("password")
            remember_me = request.POST.get("remember_me")

            user = authenticate(request, username=username_input, password=password_input)

            if user is not None:
                login(request, user)
                if not remember_me:
                    request.session.set_expiry(0)
                else:
                    request.session.set_expiry(1209600)

                if is_admin(user):
                    return redirect("dashboard_admin")
                return redirect("dashboard")
            else:
                messages.error(request, "Username atau Password Salah. Silahkan Coba Lagi")

    return render(request, "perpustakaan/login.html")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if password != confirm_password:
            messages.error(request, "Konfirmasi password tidak cocok!")
            return render(request, "perpustakaan/register.html")

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username/NIM sudah terdaftar!")
            return render(request, "perpustakaan/register.html")

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_member=True,
            is_admin=False,
        )
        login(request, user)
        messages.success(request, "Registrasi berhasil!")
        return redirect("dashboard")

    return render(request, "perpustakaan/register.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required(login_url="login")
def dashboard(request):
    user = request.user

    sedang_dipinjam = Peminjaman.objects.filter(user=user, status="Dibaca").count()
    total_dibaca = Peminjaman.objects.filter(user=user, status="Selesai").count()

    User = get_user_model()
    peringkat = User.objects.filter(exp__gt=user.exp).count() + 1

    peminjaman_terakhir = (
        Peminjaman.objects
        .filter(user=user, status="Dibaca", buku_digital__isnull=False)
        .select_related("buku_digital")
        .order_by("-tanggal_pinjam", "-id")
        .first()
    )

    def teks_terakhir(dttm):
        if not dttm:
            return ""
        menit = int((timezone.now() - dttm).total_seconds() // 60)
        if menit < 1:
            return "Terakhir dibaca baru saja"
        if menit < 60:
            return f"Terakhir dibaca {menit} menit lalu"
        if menit < 1440:
            return f"Terakhir dibaca {menit // 60} jam lalu"
        return f"Terakhir dibaca {menit // 1440} hari lalu"

    bacaan_terakhir = None
    if peminjaman_terakhir:
        p = peminjaman_terakhir
        buku = p.buku_digital

        if not p.tanggal_kembali:
            p.tanggal_kembali = timezone.now() + timedelta(days=MASA_PINJAM_HARI)
            p.save(update_fields=["tanggal_kembali"])

        sisa_hari = (timezone.localtime(p.tanggal_kembali).date() - timezone.localdate()).days
        if sisa_hari < 0:
            sisa_hari = 0

        bacaan_terakhir = {
            "buku_digital": buku,
            "progress_baca": p.progress_baca,
            "kategori_label": str(buku.kategori) if buku.kategori else "",
            "sisa_hari": sisa_hari,
            "terakhir_teks": teks_terakhir(p.tanggal_pinjam),
        }

    TARGET_HARIAN_DETIK = 1800
    detik_hari_ini = user.detik_baca_hari_ini if user.tanggal_baca_harian == timezone.localdate() else 0
    menit_hari_ini = detik_hari_ini // 60
    target_menit = TARGET_HARIAN_DETIK // 60
    persen_target = min(100, round(detik_hari_ini / TARGET_HARIAN_DETIK * 100)) if detik_hari_ini else 0

    context = {
        "user": user,
        "sedang_dipinjam": sedang_dipinjam,
        "total_dibaca": total_dibaca,
        "bookmarks": Bookmark.objects.filter(user=user).count(),
        "bacaan_terakhir": bacaan_terakhir,
        "peringkat": peringkat,
        "streak_hari": user.streak_days, 
        "menit_hari_ini": menit_hari_ini,
        "target_menit": target_menit,
        "persen_target": persen_target,
    }
    return render(request, "perpustakaan/dashboard.html", context)


@login_required(login_url="login")
@ensure_csrf_cookie
def katalog_view(request):
    kategori_pilihan = request.GET.get("kategori", "").strip()
    search_query = request.GET.get("q", "").strip()
    
    buku_queryset = BukuDigital.objects.all().distinct()

    aktif_kategori = kategori_pilihan
    if search_query and (not kategori_pilihan or kategori_pilihan.lower() == "semua"):
        for nilai_kat, label_kat in KATEGORI:
            if search_query.lower() in nilai_kat.lower() or search_query.lower() in label_kat.lower():
                aktif_kategori = nilai_kat
                break

    if aktif_kategori and aktif_kategori.lower() != "semua":
        buku_queryset = buku_queryset.filter(
            Q(kategori__icontains=aktif_kategori) |
            Q(kategori__iexact=aktif_kategori)
        )

    if search_query:
        buku_queryset = buku_queryset.filter(
            Q(judul__icontains=search_query) |
            Q(penulis__icontains=search_query) |
            Q(kategori__icontains=search_query) |
            Q(deskripsi__icontains=search_query)
        ).distinct()

    context = {
        "user": request.user,
        "kategori_list": KATEGORI,
        "bahasa_list": BAHASA,
        "default_kategori": aktif_kategori if aktif_kategori else "semua",
        "search_query": search_query,
        "tersimpan_ids": list(
            Bookmark.objects.filter(
                user=request.user, buku_digital__isnull=False
            ).values_list("buku_digital_id", flat=True)
        ),
        'buku_lokal': [
            {
                'olid': buku.id_item,
                'judul': buku.judul,
                'penulis': buku.penulis,
                'tahun': buku.tahun_terbit,
                'cover': buku.cover or '',
                'cover_besar': buku.cover or '',
                'rating': None,
                'want': None,
                'ia': buku.ia_id,
                'ia_semua': [],
                'akses': '',
                'deskripsi': buku.deskripsi,
                'subjek': [buku.kategori] if buku.kategori else [],
            }
            for buku in buku_queryset.order_by('judul')
        ],
    }
    return render(request, "perpustakaan/katalog.html", context)


def _bersih(teks, panjang):
    return (teks or "").strip()[:panjang]


def _pastikan_buku(request, olid):
    d = request.POST
    buku = BukuDigital.objects.filter(pk=olid).first()
    if buku:
        deskripsi = _bersih(d.get("deskripsi"), 20000)
        if deskripsi and not buku.deskripsi:
            buku.deskripsi = deskripsi
            buku.save(update_fields=["deskripsi"])
        return buku

    judul = _bersih(d.get("judul"), 255)
    if not judul:
        return None

    cover = _bersih(d.get("cover"), 200)
    ia = _bersih(d.get("ia"), 100)
    tahun = "".join(ch for ch in _bersih(d.get("tahun"), 10) if ch.isdigit())[:4]

    link_baca = _bersih(d.get("link_baca"), 500)
    if not link_baca:
        link_baca = f"https://archive.org/details/{ia}" if ia else f"https://openlibrary.org/works/{olid}"

    return BukuDigital.objects.create(
        id_item=olid,
        judul=judul,
        penulis=_bersih(d.get("penulis"), 255) or "Unknown",
        tahun_terbit=tahun,
        cover=cover or None,
        deskripsi=_bersih(d.get("deskripsi"), 20000),
        ia_id=ia,
        link_unduh=link_baca,
    )

@login_required(login_url="login")
@ensure_csrf_cookie
def buku_detail(request, olid):
    if not ITEM_ID_RE.match(olid):
        raise Http404

    user = request.user
    buku_db = BukuDigital.objects.filter(pk=olid).first()
    pinjam_aktif = Peminjaman.objects.filter(user=user, buku_digital_id=olid, status="Dibaca").first()
    jumlah_aktif = Peminjaman.objects.filter(user=user, status="Dibaca").count()
    context = {
        "user": user,
        "olid": olid,
        "buku_db": (
            {
                "olid": buku_db.id_item,
                "judul": buku_db.judul,
                "penulis": buku_db.penulis,
                "tahun": buku_db.tahun_terbit,
                "cover": buku_db.cover or "",
                "cover_besar": buku_db.cover or "",
                "ia": buku_db.ia_id,
                "deskripsi": buku_db.deskripsi,
                "subjek": [],
                "rating": None,
                "want": 0,
            }
            if buku_db
            else None
        ),
        "bookmarked": Bookmark.objects.filter(user=user, buku_digital_id=olid).exists(),
        "pinjam_aktif": pinjam_aktif,
        "jatuh_tempo": (
            pinjam_aktif.tanggal_pinjam + timedelta(days=MASA_PINJAM_HARI)
            if pinjam_aktif
            else None
        ),
        "jumlah_aktif": jumlah_aktif,
        "max_loans": user.max_loans,
        "slot_penuh": jumlah_aktif >= user.max_loans,
        "masa_pinjam": MASA_PINJAM_HARI,
    }
    return render(request, "perpustakaan/buku_detail.html", context)


@login_required(login_url="login")
def baca_buku(request, olid):
    buku = get_object_or_404(BukuDigital, id_item=olid)

    peminjaman, baru_dibuat = Peminjaman.objects.get_or_create(
        user=request.user,
        buku_digital=buku,
        status="Dibaca",
        defaults={
            "tanggal_kembali": timezone.now() + timedelta(days=MASA_PINJAM_HARI),
        },
    )

    peminjaman.tanggal_pinjam = timezone.now()
    peminjaman.save(update_fields=["tanggal_pinjam"])

    request.user.update_streak()

    context = {
        "buku": buku,
        "pinjam": peminjaman,
        "user": request.user,
    }
    return render(request, "perpustakaan/baca.html", context)


@login_required(login_url="login")
@require_POST
def simpan_progress(request, olid):
    if not ITEM_ID_RE.match(olid):
        raise Http404
    pinjam = Peminjaman.objects.filter(user=request.user, buku_digital_id=olid, status="Dibaca").first()
    if not pinjam:
        return JsonResponse({"error": "Peminjaman tidak ditemukan."}, status=404)
    try:
        persen = int(request.POST.get("progress", 0))
    except ValueError:
        return JsonResponse({"error": "Nilai tidak valid."}, status=400)
    persen = max(0, min(persen, 100))
    pinjam.progress_baca = persen
    pinjam.save(update_fields=["progress_baca"])
        
    return JsonResponse({"progress": pinjam.progress_baca})


@login_required(login_url="login")
@require_POST
def pinjam_buku(request, olid):
    if not ITEM_ID_RE.match(olid):
        raise Http404
    user = request.user

    if Peminjaman.objects.filter(user=user, buku_digital_id=olid, status="Dibaca").exists():
        messages.info(request, "Buku ini sudah ada di daftar pinjamanmu.")
        return redirect("buku_detail", olid=olid)

    if Peminjaman.objects.filter(user=user, status="Dibaca").count() >= user.max_loans:
        messages.error(request, f"Batas pinjam {user.max_loans} buku tercapai. Kembalikan satu buku dulu.")
        return redirect("buku_detail", olid=olid)

    buku = _pastikan_buku(request, olid)
    if buku is None:
        messages.error(request, "Data buku belum selesai dimuat. Tunggu sebentar, lalu coba lagi.")
        return redirect("buku_detail", olid=olid)

    Peminjaman.objects.create(user=user, buku_digital=buku)
    messages.success(request, f'"{buku.judul}" berhasil dipinjam selama {MASA_PINJAM_HARI} hari.')
    return redirect("peminjaman")


@login_required(login_url="login")
@require_POST
def toggle_bookmark(request, olid):
    if not ITEM_ID_RE.match(olid):
        raise Http404
    ada = Bookmark.objects.filter(user=request.user, buku_digital_id=olid).first()
    if ada:
        ada.delete()
        return JsonResponse({"bookmarked": False})
    buku = _pastikan_buku(request, olid)
    if buku is None:
        return JsonResponse({"error": "Data buku belum dimuat."}, status=400)
    Bookmark.objects.create(user=request.user, buku_digital=buku)
    return JsonResponse({"bookmarked": True})


@login_required(login_url="login")
def ejournal_view(request):
    jurnal_harian = []

    for jurnal in Jurnal.objects.order_by("judul", "id_item"):
        jurnal_harian.append({
            "id": jurnal.id_item,
            "judul": jurnal.judul,
            "penulis": jurnal.penulis,
            "tahun": jurnal.tahun_terbit,
            "nama_jurnal": jurnal.bidang_ilmu or "Koleksi Lentera",
            "cover": jurnal.cover,
            "baca_url": f"/jurnal/{jurnal.id_item}/baca/",
        })

    file_json = settings.BASE_DIR / "jurnal_teknik.json"
    if file_json.exists():
        try:
            with file_json.open(encoding="utf-8") as file:
                jurnal_json = json.load(file)
            for index, jurnal in enumerate(jurnal_json):
                jurnal_harian.append({
                    "id": f"JSON-{index}",
                    "judul": jurnal.get("judul", "Tanpa judul"),
                    "penulis": jurnal.get("penulis", "Penulis tidak diketahui"),
                    "tahun": jurnal.get("tahun", "-"),
                    "nama_jurnal": jurnal.get("jurnal", ""),
                    "cover": jurnal.get("cover_url", ""),
                    "baca_url": f"/jurnal/JSON-{index}/baca/",
                })
        except (OSError, json.JSONDecodeError):
            pass

    query = request.GET.get("q", "").strip()
    if query:
        query_lower = query.casefold()
        jurnal_harian = [
            jurnal for jurnal in jurnal_harian
            if query_lower in jurnal["judul"].casefold()
            or query_lower in jurnal["penulis"].casefold()
            or query_lower in jurnal["nama_jurnal"].casefold()
        ]

    if jurnal_harian:
        offset = timezone.localdate().toordinal() % len(jurnal_harian)
        jurnal_harian = jurnal_harian[offset:] + jurnal_harian[:offset]
    jurnal_harian = jurnal_harian[:6]

    return render(request, "perpustakaan/ejournal.html", {
        "user": request.user,
        "jurnal_list": jurnal_harian,
        "search_query": query,
        "tanggal_jurnal": timezone.localdate(),
    })


@login_required(login_url="login")
@ensure_csrf_cookie
def baca_jurnal(request, jurnal_id):
    if jurnal_id.startswith("JSON-"):
        try:
            index = int(jurnal_id[5:])
            with (settings.BASE_DIR / "jurnal_teknik.json").open(encoding="utf-8") as file:
                semua_jurnal = json.load(file)
            if index < 0:
                raise IndexError
            jurnal = semua_jurnal[index]
        except (ValueError, IndexError, OSError, json.JSONDecodeError):
            raise Http404("Jurnal tidak ditemukan")
        judul = jurnal.get("judul", "Tanpa judul")
        penulis = jurnal.get("penulis", "Penulis tidak diketahui")
        reader_url = jurnal.get("pdf_url") or ""
        sumber_url = jurnal.get("sumber_url") or jurnal.get("doi_url") or ""
    else:
        jurnal = get_object_or_404(Jurnal, pk=jurnal_id)
        judul = jurnal.judul
        penulis = jurnal.penulis
        reader_url = jurnal.link_akses or ""
        sumber_url = reader_url

    is_pdf = urlparse(reader_url).path.lower().endswith(".pdf")
    return render(request, "perpustakaan/baca_jurnal.html", {
        "user": request.user,
        "judul": judul,
        "penulis": penulis,
        "reader_url": reader_url,
        "sumber_url": sumber_url,
        "is_pdf": is_pdf,
    })


@login_required(login_url="login")
def peminjaman_view(request):
    daftar_pinjaman = Peminjaman.objects.filter(
        user=request.user, status="Dibaca"
    ).order_by("-tanggal_pinjam")

    for pinjaman in daftar_pinjaman:
        pinjaman.jatuh_tempo = pinjaman.tanggal_pinjam + timedelta(days=MASA_PINJAM_HARI)

    batas_pinjam = request.user.max_loans
    jumlah_aktif = Peminjaman.objects.filter(user=request.user, status="Dibaca").count()
    sisa_slot = max(batas_pinjam - jumlah_aktif, 0)

    context = {
        "user": request.user,
        "daftar_pinjaman": daftar_pinjaman,
        "total_pinjaman": daftar_pinjaman.count(),
        "batas_pinjam": batas_pinjam,
        "jumlah_aktif": jumlah_aktif,
        "sisa_slot": sisa_slot,
        "slot_range": range(batas_pinjam),
    }
    return render(request, "perpustakaan/peminjaman.html", context)


@login_required(login_url="login")
def kembalikan_buku(request, pinjaman_id):
    pinjaman = get_object_or_404(Peminjaman, id=pinjaman_id, user=request.user)

    if pinjaman.status == "Dibaca":
        pinjaman.status = "Selesai"
        pinjaman.progress_baca = 100
        pinjaman.tanggal_kembali = timezone.now()
        pinjaman.save()

    return redirect("peminjaman")


@login_required(login_url="login")
def bookmarks_view(request):
    daftar_bookmark = (
        Bookmark.objects.filter(user=request.user)
        .select_related('buku_digital', 'jurnal')
        .order_by('-tanggal_disimpan', '-pk')
    )
    page_obj = Paginator(daftar_bookmark, PAGINATION_PAGE_SIZE).get_page(request.GET.get('page'))
    context = {
        'user': request.user,
        'bookmarks': page_obj,
        'page_obj': page_obj,
        'total_tersimpan': page_obj.paginator.count,
    }
    return render(request, "perpustakaan/bookmarks.html", context)


@login_required(login_url="login")
def hapus_bookmark_api(request, bookmark_id):
    try:
        bookmark = Bookmark.objects.get(id=bookmark_id, user=request.user)
        bookmark.delete()
        return JsonResponse({"status": "success"})
    except Bookmark.DoesNotExist:
        return JsonResponse({"status": "error"}, status=404)


@login_required(login_url="login")
def riwayat_view(request):
    riwayat_list = Peminjaman.objects.filter(user=request.user).order_by("-tanggal_pinjam")
    masa = Pengaturan.muat().masa_pinjam_hari
    for p in riwayat_list:
        p.jatuh_tempo = p.tanggal_kembali or (p.tanggal_pinjam + timedelta(days=masa))

    context = {
        "daftar_riwayat": riwayat_list,
    }
    return render(request, "perpustakaan/riwayat.html", context)

@login_required(login_url="login")
def leaderboard_view(request):
    semua_user = CustomUser.objects.filter(is_member=True, is_admin=False, is_staff=False).order_by("-exp")
    top_3 = semua_user[:3]
    other_users = semua_user[3:10]
    max_exp = top_3[0].exp if top_3 else 1

    list_users = []
    for index, u in enumerate(other_users, start=4):
        percentage = (u.exp / max_exp) * 100 if max_exp > 0 else 0
        list_users.append({"rank": index, "user": u, "percentage": percentage})

    podium = {
        "rank2": top_3[1] if len(top_3) > 1 else None,
        "rank1": top_3[0] if len(top_3) > 0 else None,
        "rank3": top_3[2] if len(top_3) > 2 else None,
    }

    context = {
        "user": request.user,
        "podium": podium,
        "list_users": list_users,
    }
    return render(request, "perpustakaan/leaderboard.html", context)


@login_required(login_url="login")
def profil_view(request):
    user = request.user
    total_dibaca = Peminjaman.objects.filter(user=user, status="Selesai").count()
    semua_achievement = _achievements(user)

    if request.method == "POST":
        nama_baru = request.POST.get("nama_tampilan")
        email_baru = request.POST.get("email")
        pass_lama = request.POST.get("password_lama")
        pass_baru = request.POST.get("password_baru")

        foto_profil = request.FILES.get("foto_profil")
        foto_bg = request.FILES.get("foto_background")

        hapus_foto_profil = request.POST.get("hapus_foto_profil")
        hapus_foto_bg = request.POST.get("hapus_foto_background")

        pinned_list = request.POST.getlist("pinned_achievements")
        if len(pinned_list) > 3:
            pinned_list = pinned_list[:3]

        perubahan_terjadi = False

        if nama_baru and nama_baru != user.nama_tampilan:
            user.nama_tampilan = nama_baru
            perubahan_terjadi = True

        if email_baru is not None and email_baru != user.email:
            user.email = email_baru
            perubahan_terjadi = True

        new_pinned_str = ",".join(pinned_list)
        if new_pinned_str != user.pinned_achievements:
            user.pinned_achievements = new_pinned_str
            perubahan_terjadi = True

        if hapus_foto_profil and user.foto_profil:
            if user.foto_profil.storage.exists(user.foto_profil.name):
                user.foto_profil.delete(save=False)
            user.foto_profil = None
            perubahan_terjadi = True

        if foto_profil:
            if foto_profil.size > 2 * 1024 * 1024:
                messages.error(request, "Gagal: Ukuran foto profil maksimal 2 MB!")
                return redirect("profil")
            if user.foto_profil and user.foto_profil.storage.exists(user.foto_profil.name):
                user.foto_profil.delete(save=False)
            user.foto_profil = foto_profil
            perubahan_terjadi = True

        if hapus_foto_bg and user.foto_background:
            if user.foto_background.storage.exists(user.foto_background.name):
                user.foto_background.delete(save=False)
            user.foto_background = None
            perubahan_terjadi = True

        if foto_bg:
            if foto_bg.size > 2 * 1024 * 1024:
                messages.error(request, "Gagal: Ukuran background maksimal 2 MB!")
                return redirect("profil")
            if user.foto_background and user.foto_background.storage.exists(user.foto_background.name):
                user.foto_background.delete(save=False)
            user.foto_background = foto_bg
            perubahan_terjadi = True

        if perubahan_terjadi:
            user.save()
            messages.success(request, "Profil berhasil diperbarui!")

        if pass_lama and pass_baru:
            if user.check_password(pass_lama):
                user.set_password(pass_baru)
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password berhasil diubah!")
            else:
                messages.error(request, "Gagal: Password lama salah!")

        return redirect("profil")

    selesai = Peminjaman.objects.filter(user=user, status="Selesai", buku_digital__isnull=False)
    total_buku = selesai.values("buku_digital_id").distinct().count()
    peringkat = CustomUser.objects.filter(is_member=True, exp__gt=user.exp).count() + 1
    level = user.exp // LEVEL_EXP + 1
    exp_di_level = user.exp % LEVEL_EXP
    persen_level = exp_di_level * 100 // LEVEL_EXP
    
    pinned_names = [name.strip() for name in user.pinned_achievements.split(",") if name.strip()]
    achievements_dict = {a["nama"]: a for a in semua_achievement}
    
    display_achievements = []
    for name in pinned_names:
        if name in achievements_dict:
            display_achievements.append(achievements_dict[name])
            
    if not display_achievements:
        display_achievements = [a for a in semua_achievement if a["didapat"]][:3]

    context = {
        "user": user,
        "total_dibaca": total_dibaca,
        "peringkat": peringkat,
        "level": level,
        "exp_di_level": exp_di_level,
        "exp_per_level": LEVEL_EXP,
        "persen_level": persen_level,
        "achievements": display_achievements,
        "semua_achievement": semua_achievement,
        "pinned_names": pinned_names,
        "achievement_terbuka": sum(1 for a in semua_achievement if a["didapat"]),
        "achievement_total": len(semua_achievement),
    }
    return render(request, "perpustakaan/profil.html", context)


LEVEL_EXP = 100

def _achievements(user):
    peminjaman = Peminjaman.objects.filter(user=user)
    buku = peminjaman.filter(buku_digital__isnull=False)

    pinjam_total = peminjaman.count()
    pinjam_selesai = peminjaman.filter(status="Selesai").count()
    buku_selesai = buku.filter(status="Selesai").values("buku_digital_id").distinct().count()
    buku_dimulai = buku.values("buku_digital_id").distinct().count()
    genre = buku.exclude(buku_digital__kategori="").values("buku_digital__kategori").distinct().count()
    bookmark = Bookmark.objects.filter(user=user).count()
    exp = user.exp
    hari = user.streak_days

    def kategori_selesai(*kata):
        q = Q()
        for k in kata:
            q |= Q(buku_digital__kategori__icontains=k)
        return buku.filter(q, status="Selesai").values("buku_digital_id").distinct().count()

    def item(nama, ikon, syarat, nilai, target, kategori="Umum"):
        nilai = min(nilai, target)
        return {
            "nama": nama,
            "ikon": ikon,
            "syarat": syarat,
            "nilai": nilai,
            "target": target,
            "didapat": nilai >= target,
            "persen": round(nilai / target * 100) if target > 0 else 100,
            "kategori": kategori,
        }

    return [
        item("Halaman Pertama", "fa-book-open", "Selesaikan sesi baca buku pertamamu.", 0, 1, "Umum"),
        item("Tunas Literasi", "fa-seedling", "Selesaikan 5 sesi baca buku.", 0, 5, "Umum"),
        item("Rak Mulai Terisi", "fa-leaf", "Selesaikan 10 sesi baca buku.", 0, 10, "Umum"),
        item("Pembaca Tekun", "fa-tree", "Selesaikan 25 sesi baca buku.", 0, 25, "Langka"),
        item("Penjaga Cerita", "fa-shield-halved", "Selesaikan 50 sesi baca buku.", 0, 50, "Epik"),
        item("Sampul Terakhir", "fa-flag-checkered", "Tuntaskan satu buku sampai bagian terakhir.", buku_selesai, 1, "Umum"),
        item("Tiga Cerita", "fa-medal", "Tuntaskan tiga buku.", buku_selesai, 3, "Umum"),
        item("Kolektor Kisah", "fa-layer-group", "Tuntaskan lima buku.", buku_selesai, 5, "Langka"),
        item("Penjelajah Rak", "fa-compass", "Mulai membaca lima judul buku berbeda.", buku_dimulai, 5, "Langka"),
        item("Rak Pribadi", "fa-book", "Mulai membaca tujuh judul buku berbeda.", buku_dimulai, 7, "Langka"),
        item("Misteri Terurai", "fa-magnifying-glass", "Selesaikan sesi baca buku berkategori Misteri.", kategori_selesai("misteri", "mystery"), 1, "Umum"),
        item("Dunia Ajaib", "fa-wand-magic-sparkles", "Selesaikan sesi baca buku berkategori Fantasi.", kategori_selesai("fantasi", "fantasy"), 1, "Umum"),
        item("Hati di Halaman", "fa-heart", "Selesaikan sesi baca buku berkategori Romansa.", kategori_selesai("romansa", "romance"), 1, "Umum"),
        item("Langkah Bertumbuh", "fa-arrow-trend-up", "Selesaikan sesi baca buku Pengembangan Diri.", kategori_selesai("pengembangan", "self"), 1, "Umum"),
        item("Pencari Ilmu", "fa-graduation-cap", "Selesaikan sesi baca buku berkategori Pendidikan.", kategori_selesai("pendidikan", "education"), 1, "Umum"),
        item("Sang Pencinta Sastra", "fa-feather-pointed", "Selesaikan sesi baca buku berkategori Sastra.", kategori_selesai("sastra", "literature"), 1, "Umum"),
        item("Lintas Genre", "fa-shuffle", "Baca buku dari 3 genre yang berbeda.", genre, 3, "Langka"),
        item("Pustaka Berwarna", "fa-palette", "Baca buku dari 5 genre yang berbeda.", genre, 5, "Epik"),
        item("Percikan Pertama", "fa-bolt", "Kumpulkan 25 EXP dari ikon membaca.", exp, 25, "Umum"),
        item("Bintang Pembaca", "fa-star", "Kumpulkan 100 EXP.", exp, 100, "Umum"),
        item("Cahaya Lentera", "fa-lightbulb", "Kumpulkan 250 EXP.", exp, 250, "Langka"),
        item("Lentera Emas", "fa-crown", "Kumpulkan 500 EXP.", exp, 500, "Epik"),
        item("Penanda Cerita", "fa-bookmark", "Buat bookmark pertamamu.", bookmark, 1, "Umum"),
        item("Penjaga Halaman", "fa-book-bookmark", "Simpan 5 bookmark buku atau bab.", bookmark, 5, "Langka"),
        item("Peminjam Pertama", "fa-handshake", "Ajukan peminjaman buku pertamamu.", pinjam_total, 1, "Umum"),
        item("Sahabat Perpustakaan", "fa-user-group", "Selesaikan 5 transaksi peminjaman.", pinjam_selesai, 5, "Langka"),
        item("Pembaca Jurnal", "fa-newspaper", "Selesaikan satu bagian jurnal.", 0, 1, "Umum"),
        item("Penjelajah Wacana", "fa-scroll", "Selesaikan 5 bagian jurnal.", 0, 5, "Langka"),
        item("Hadir Membaca", "fa-sun", "Dapatkan EXP pada satu hari membaca.", hari, 1, "Umum"),
        item("Ritme Membaca", "fa-chart-line", "Dapatkan EXP pada 3 hari berbeda.", hari, 3, "Umum"),
        item("Kebiasaan Terbentuk", "fa-calendar-check", "Dapatkan EXP pada 7 hari berbeda.", hari, 7, "Langka"),
        item("Rak Kesayangan", "fa-heart-circle-check", "Simpan 3 judul ke koleksi favorit.", bookmark, 3, "Umum"),
        item("Saldo Pertama", "fa-coins", "Lakukan simulasi top up Reader pertamamu.", 0, 1, "Umum"),
        item("Poin Terkumpul", "fa-gem", "Simulasikan top up minimal 50 kredit total.", 0, 50, "Langka"),
        item("Pinjam dan Kembali", "fa-rotate-left", "Kembalikan setidaknya satu buku pinjaman.", pinjam_selesai, 1, "Umum"),
        item("Bagian demi Bagian", "fa-puzzle-piece", "Selesaikan 15 bagian buku dan jurnal.", 0, 15, "Epik"),
    ]


@login_required(login_url="login")
def profil_user_detail_view(request, username):
    target = get_object_or_404(CustomUser, username=username)
    if target.pk == request.user.pk:
        return redirect("profil")

    selesai = Peminjaman.objects.filter(user=target, status="Selesai", buku_digital__isnull=False)
    total_buku = selesai.values("buku_digital_id").distinct().count()

    buku_terbaru, terlihat = [], set()
    for p in selesai.select_related("buku_digital").order_by("-tanggal_kembali", "-pk")[:30]:
        if p.buku_digital_id in terlihat:
            continue
        terlihat.add(p.buku_digital_id)
        buku_terbaru.append(p.buku_digital)
        if len(buku_terbaru) == 6:
            break

    favorit = [
        row["buku_digital__kategori"].replace("_", " ").capitalize()
        for row in (
            selesai.exclude(buku_digital__kategori="")
            .order_by()
            .values("buku_digital__kategori")
            .annotate(n=Count("id"))
            .order_by("-n")[:2]
        )
    ]

    peringkat = CustomUser.objects.filter(is_member=True, exp__gt=target.exp).count() + 1
    level = target.exp // LEVEL_EXP + 1
    level_sisa = target.exp % LEVEL_EXP
    selisih = target.exp - request.user.exp

    semua_achievement_target = _achievements(target)
    pinned_names = [name.strip() for name in target.pinned_achievements.split(",") if name.strip()]
    achievements_dict = {a["nama"]: a for a in semua_achievement_target}
    
    pinned_achievements = []
    for name in pinned_names:
        if name in achievements_dict:
            pinned_achievements.append(achievements_dict[name])
            
    if not pinned_achievements:
        pinned_achievements = [a for a in semua_achievement_target if a["didapat"]][:3]

    context = {
        "user": request.user,
        "profile_user": target,
        "total_buku": total_buku,
        "peringkat": peringkat,
        "level": level,
        "level_sisa": level_sisa,
        "level_exp": LEVEL_EXP,
        "level_persen": round(level_sisa / LEVEL_EXP * 100),
        "buku_terbaru": buku_terbaru,
        "favorit": favorit,
        "achievements": [a for a in semua_achievement_target if a["didapat"]],
        "pinned_achievements": pinned_achievements,
        "selisih": selisih,
        "selisih_abs": abs(selisih),
    }
    return render(request, "perpustakaan/profil_publik.html", context)


@login_required(login_url="login")
@require_POST
def waktu_baca(request):
    try:
        klaim = int(request.POST.get('detik', 0) or 0)
    except ValueError:
        klaim = 0
    klaim = max(0, klaim)

    sekarang = time.time()
    terakhir = request.session.get("ring_terakhir")
    request.session["ring_terakhir"] = sekarang
    if terakhir is not None:
        klaim = min(klaim, int(sekarang - terakhir) + 1)

    if klaim <= 0:
        user = request.user
        return JsonResponse({"detik": user.waktu_baca_detik, "exp_gain": 0, "exp": user.exp})

    pinjam_id = request.POST.get('pinjam')
    if pinjam_id:
        p = Peminjaman.objects.filter(id=pinjam_id, user=request.user).first()
        if p:
            p.waktu_baca_detik += klaim
            p.save(update_fields=['waktu_baca_detik'])

    user = request.user
    pool = user.waktu_baca_detik + klaim
    exp_gain = 0
    while pool >= RING_DETIK_PENUH:
        pool -= RING_DETIK_PENUH
        exp_gain += RING_EXP

    user.waktu_baca_detik = pool
    if exp_gain:
        user.exp += exp_gain

    hari_ini = timezone.localdate()
    if user.tanggal_baca_harian != hari_ini:
        user.detik_baca_hari_ini = 0
        user.tanggal_baca_harian = hari_ini
    user.detik_baca_hari_ini += klaim

    user.save(update_fields=["waktu_baca_detik", "exp", "detik_baca_hari_ini", "tanggal_baca_harian"])

    return JsonResponse({"detik": pool, "exp_gain": exp_gain, "exp": user.exp})


@login_required(login_url="login")
def achievement_view(request):
    daftar = _achievements(request.user)
    pinned_names = [name.strip() for name in request.user.pinned_achievements.split(",") if name.strip()]
    
    context = {
        "user": request.user,
        "achievements": daftar,
        "pinned_names": pinned_names,
        "terbuka": sum(1 for a in daftar if a["didapat"]),
        "total": len(daftar),
    }
    return render(request, "perpustakaan/achievement.html", context)


@login_required(login_url="login")
@require_POST
def update_pinned_achievement_api(request):
    try:
        data = json.loads(request.body)
        pinned_list = data.get("pinned_achievements", [])
        
        if not isinstance(pinned_list, list):
            return JsonResponse({"status": "error", "message": "Format data tidak valid."}, status=400)
            
        if len(pinned_list) > 3:
            pinned_list = pinned_list[:3]
            
        request.user.pinned_achievements = ",".join(pinned_list)
        request.user.save(update_fields=["pinned_achievements"])
        
        return JsonResponse({"status": "success", "pinned": pinned_list})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required(login_url="login")
@user_passes_test(is_admin, login_url="login")
def dashboard_admin(request):
    total_pengguna = CustomUser.objects.filter(is_member=True).count()
    total_buku = BukuDigital.objects.count()
    total_peminjaman = Peminjaman.objects.filter(status="Dibaca").count()
    
    context = {
        "user": request.user,
        "total_pengguna": total_pengguna,
        "total_buku": total_buku,
        "total_peminjaman": total_peminjaman,
    }
    return render(request, "perpustakaan/admin/dashboard.html", context)


@login_required(login_url="login")
@user_passes_test(is_admin, login_url="login")
def kelola_buku_admin(request):
    buku_list = BukuDigital.objects.all().order_by('-id')
    context = {
        "user": request.user,
        "buku_list": buku_list,
    }
    return render(request, "perpustakaan/admin/kelola_buku.html", context)