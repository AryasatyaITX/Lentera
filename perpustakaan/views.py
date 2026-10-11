from datetime import timedelta
from django.core.paginator import Paginator
from django.utils import timezone
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from .models import CustomUser, BukuDigital, Jurnal, Peminjaman, Bookmark
from django.contrib.auth import update_session_auth_hash
import re

MASA_PINJAM_HARI = 14
PAGINATION_PAGE_SIZE = 10
ITEM_ID_RE = re.compile(r'^[\w-]+$')
COVER_PREFIX = 'https://covers.openlibrary.org/'

# (nilai subject di Open Library, label yang tampil)
KATEGORI = [
    ('engineering', 'Engineering'),
    ('computer science', 'Computer Science'),
    ('mathematics', 'Matematika'),
    ('physics', 'Fisika'),
    ('business', 'Bisnis'),
    ('fiction', 'Fiksi'),
    ('history', 'Sejarah'),
]
DEFAULT_KATEGORI = 'engineering'
BAHASA = [('', 'Semua bahasa'), ('ind', 'Indonesia'), ('eng', 'Inggris')]


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username_input = request.POST.get('username')
        password_input = request.POST.get('password')
        user = authenticate(request, username=username_input, password=password_input)

        if user is not None:
            login(request, user)
            if user.is_staff or user.is_admin:
                return redirect('/admin/')
            return redirect('dashboard')
        else:
            messages.error(request, "Username/Email atau Password salah!")

    return render(request, 'perpustakaan/login.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, "Konfirmasi password tidak cocok!")
            return render(request, 'perpustakaan/register.html')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username/NIM sudah terdaftar!")
            return render(request, 'perpustakaan/register.html')

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_member=True,
            is_admin=False
        )
        login(request, user)
        messages.success(request, "Registrasi berhasil!")
        return redirect('dashboard')

    return render(request, 'perpustakaan/register.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def dashboard(request):
    user = request.user
    sedang_dipinjam = Peminjaman.objects.filter(user=user, status='Dibaca').count()
    total_dibaca = Peminjaman.objects.filter(user=user, status='Selesai').count()
    bacaan_terakhir = Peminjaman.objects.filter(user=user, status='Dibaca').last()

    context = {
        'user': user,
        'sedang_dipinjam': sedang_dipinjam,
        'total_dibaca': total_dibaca,
        'bookmarks': Bookmark.objects.filter(user=user).count(),
        'bacaan_terakhir': bacaan_terakhir,
    }
    return render(request, 'perpustakaan/dashboard.html', context)


@login_required(login_url='login')
@ensure_csrf_cookie
def katalog_view(request):

    context = {
        'user': request.user,
        'kategori_list': KATEGORI,
        'bahasa_list': BAHASA,
        'default_kategori': DEFAULT_KATEGORI,
        'tersimpan_ids': list(
            Bookmark.objects.filter(user=request.user, buku_digital__isnull=False)
            .values_list('buku_digital_id', flat=True)
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
                'subjek': [],
            }
            for buku in BukuDigital.objects.order_by('judul')
        ],
    }
    return render(request, 'perpustakaan/katalog.html', context)


def _bersih(teks, panjang):
    return (teks or '').strip()[:panjang]


def _pastikan_buku(request, olid):
    d = request.POST
    buku = BukuDigital.objects.filter(pk=olid).first()
    if buku:
        deskripsi = _bersih(d.get('deskripsi'), 20000)
        if deskripsi and not buku.deskripsi:
            buku.deskripsi = deskripsi
            buku.save(update_fields=['deskripsi'])
        return buku

    judul = _bersih(d.get('judul'), 255)
    if not judul:
        return None  

    cover = _bersih(d.get('cover'), 200)
    ia = _bersih(d.get('ia'), 100)
    tahun = ''.join(ch for ch in _bersih(d.get('tahun'), 10) if ch.isdigit())[:4]
    
    # PERUBAHAN: Tangkap link_baca yang dikirim dari JS Google Books
    link_baca = _bersih(d.get('link_baca'), 500)
    if not link_baca:
        # Cadangan jika dari Open Library
        link_baca = f'https://archive.org/details/{ia}' if ia else f'https://openlibrary.org/works/{olid}'

    return BukuDigital.objects.create(
        id_item=olid,
        judul=judul,
        penulis=_bersih(d.get('penulis'), 255) or 'Unknown',
        tahun_terbit=tahun,
        cover=cover or None,
        deskripsi=_bersih(d.get('deskripsi'), 20000),
        ia_id=ia,
        link_unduh=link_baca, # Menyimpan Link Web Reader Google di sini
    )


@login_required(login_url='login')
@ensure_csrf_cookie
def buku_detail(request, olid):
    """Kerangka halaman. Isi buku (judul, deskripsi, dll) diisi browser dari Open Library."""
    if not ITEM_ID_RE.match(olid):
        raise Http404

    user = request.user
    buku_db = BukuDigital.objects.filter(pk=olid).first()
    pinjam_aktif = Peminjaman.objects.filter(user=user, buku_digital_id=olid, status='Dibaca').first()
    jumlah_aktif = Peminjaman.objects.filter(user=user, status='Dibaca').count()
    context = {
        'user': user,
        'olid': olid,
        # cadangan kalau Open Library tidak terjangkau (hanya ada kalau buku pernah dipinjam/di-bookmark)
        'buku_db': {
            'olid': buku_db.id_item, 'judul': buku_db.judul, 'penulis': buku_db.penulis,
            'tahun': buku_db.tahun_terbit, 'cover': buku_db.cover or '', 'cover_besar': buku_db.cover or '',
            'ia': buku_db.ia_id, 'deskripsi': buku_db.deskripsi, 'subjek': [], 'rating': None, 'want': None,
        } if buku_db else None,
        'bookmarked': Bookmark.objects.filter(user=user, buku_digital_id=olid).exists(),
        'pinjam_aktif': pinjam_aktif,
        'jatuh_tempo': pinjam_aktif.tanggal_pinjam + timedelta(days=MASA_PINJAM_HARI) if pinjam_aktif else None,
        'jumlah_aktif': jumlah_aktif,
        'max_loans': user.max_loans,
        'slot_penuh': jumlah_aktif >= user.max_loans,
        'masa_pinjam': MASA_PINJAM_HARI,
    }
    return render(request, 'perpustakaan/buku_detail.html', context)


@login_required(login_url='login')
def baca_buku(request, olid):
    """Halaman baca. Hanya untuk buku yang sedang dipinjam user."""
    if not ITEM_ID_RE.match(olid):
        raise Http404
    pinjam = (Peminjaman.objects.filter(user=request.user, buku_digital_id=olid, status='Dibaca')
            .select_related('buku_digital').first())
    if not pinjam:
        messages.info(request, 'Pinjam buku ini dulu supaya bisa dibaca.')
        return redirect('buku_detail', olid=olid)
    return render(request, 'perpustakaan/baca.html', {
        'user': request.user,
        'pinjam': pinjam,
        'buku': pinjam.buku_digital,
        'jatuh_tempo': pinjam.tanggal_pinjam + timedelta(days=MASA_PINJAM_HARI),
    })


@login_required(login_url='login')
@require_POST
def pinjam_buku(request, olid):
    if not ITEM_ID_RE.match(olid):
        raise Http404
    user = request.user

    if Peminjaman.objects.filter(user=user, buku_digital_id=olid, status='Dibaca').exists():
        messages.info(request, 'Buku ini sudah ada di daftar pinjamanmu.')
        return redirect('buku_detail', olid=olid)

    if Peminjaman.objects.filter(user=user, status='Dibaca').count() >= user.max_loans:
        messages.error(request, f'Batas pinjam {user.max_loans} buku tercapai. Kembalikan satu buku dulu.')
        return redirect('buku_detail', olid=olid)

    buku = _pastikan_buku(request, olid)
    if buku is None:
        messages.error(request, 'Data buku belum selesai dimuat. Tunggu sebentar, lalu coba lagi.')
        return redirect('buku_detail', olid=olid)

    Peminjaman.objects.create(user=user, buku_digital=buku)
    messages.success(request, f'"{buku.judul}" berhasil dipinjam selama {MASA_PINJAM_HARI} hari.')
    return redirect('peminjaman')


@login_required(login_url='login')
@require_POST
def toggle_bookmark(request, olid):
    if not ITEM_ID_RE.match(olid):
        raise Http404
    ada = Bookmark.objects.filter(user=request.user, buku_digital_id=olid).first()
    if ada:
        ada.delete()
        return JsonResponse({'bookmarked': False})
    buku = _pastikan_buku(request, olid)
    if buku is None:
        return JsonResponse({'error': 'Data buku belum dimuat.'}, status=400)
    Bookmark.objects.create(user=request.user, buku_digital=buku)
    return JsonResponse({'bookmarked': True})


@login_required(login_url='login')
def ejournal_view(request):
    return render(request, 'perpustakaan/ejournal.html', {'user': request.user})


@login_required(login_url='login')
def peminjaman_view(request):
    daftar_pinjaman = Peminjaman.objects.filter(user=request.user, status='Dibaca').order_by('-tanggal_pinjam')
    
    for pinjaman in daftar_pinjaman:
        pinjaman.jatuh_tempo = pinjaman.tanggal_pinjam + timedelta(days=MASA_PINJAM_HARI)

    context = {
        'user': request.user,
        'daftar_pinjaman': daftar_pinjaman,
        'total_pinjaman': daftar_pinjaman.count(),
    }
    return render(request, 'perpustakaan/peminjaman.html', context)


@login_required(login_url='login')
def kembalikan_buku(request, pinjaman_id):
    pinjaman = get_object_or_404(Peminjaman, id=pinjaman_id, user=request.user)
    
    if pinjaman.status == 'Dibaca':
        pinjaman.status = 'Selesai'
        pinjaman.progress_baca = 100
        pinjaman.tanggal_kembali = timezone.now()
        pinjaman.save()
        request.user.add_exp(50)
        
    return redirect('peminjaman')


@login_required(login_url='login')
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
    return render(request, 'perpustakaan/bookmarks.html', context)


@login_required(login_url='login')
def hapus_bookmark_api(request, bookmark_id):
    try:
        bookmark = Bookmark.objects.get(id=bookmark_id, user=request.user)
        bookmark.delete()
        return JsonResponse({'status': 'success'})
    except Bookmark.DoesNotExist:
        return JsonResponse({'status': 'error'}, status=404)

@login_required(login_url='login')
def riwayat_view(request):
    riwayat_queryset = (
        Peminjaman.objects.filter(user=request.user)
        .select_related('buku_digital', 'jurnal')
        .order_by('-tanggal_pinjam', '-pk')
    )
    page_obj = Paginator(riwayat_queryset, PAGINATION_PAGE_SIZE).get_page(request.GET.get('page'))
    riwayat_list = page_obj.object_list
    
    for item in riwayat_list:
        if not item.tanggal_kembali:
            if item.status == 'Selesai':
                # Fallback untuk data lama yang dikembalikan sebelum perbaikan ini
                item.tanggal_kembali = item.tanggal_pinjam + timedelta(days=MASA_PINJAM_HARI)
            else:
                item.jatuh_tempo = item.tanggal_pinjam + timedelta(days=MASA_PINJAM_HARI)

    context = {
        'user': request.user,
        'riwayat_list': riwayat_list,
        'page_obj': page_obj,
        'total_aktivitas': page_obj.paginator.count,
    }
    return render(request, 'perpustakaan/riwayat.html', context)

@login_required(login_url='login')
def leaderboard_view(request):
    # Ambil semua member, urutkan berdasarkan EXP terbanyak
    semua_user = CustomUser.objects.filter(is_member=True).order_by('-exp')

    # Pisahkan Top 3 dan sisanya (Rank 4 sampai 10)
    top_3 = semua_user[:3]
    other_users = semua_user[3:10]

    # Cari EXP tertinggi untuk menghitung persentase Progress Bar di list bawah
    max_exp = top_3[0].exp if top_3 else 1 # Hindari pembagian dengan nol

    # Siapkan data untuk Rank 4 ke bawah
    list_users = []
    for index, u in enumerate(other_users, start=4):
        percentage = (u.exp / max_exp) * 100 if max_exp > 0 else 0
        list_users.append({
            'rank': index,
            'user': u,
            'percentage': percentage
        })

    # Susun urutan podium: Kiri (Rank 2), Tengah (Rank 1), Kanan (Rank 3)
    podium = {
        'rank2': top_3[1] if len(top_3) > 1 else None,
        'rank1': top_3[0] if len(top_3) > 0 else None,
        'rank3': top_3[2] if len(top_3) > 2 else None,
    }

    context = {
        'user': request.user,
        'podium': podium,
        'list_users': list_users,
    }
    return render(request, 'perpustakaan/leaderboard.html', context)

@login_required(login_url='login')
def profil_view(request):
    user = request.user
    total_dibaca = Peminjaman.objects.filter(user=user, status='Selesai').count()

    if request.method == 'POST':
        # Ambil data dari form HTML
        nama_baru = request.POST.get('nama_tampilan')
        email_baru = request.POST.get('email')
        pass_lama = request.POST.get('password_lama')
        pass_baru = request.POST.get('password_baru')
        
        # Ambil file upload gambar
        foto_profil = request.FILES.get('foto_profil')
        foto_bg = request.FILES.get('foto_background')

        perubahan_terjadi = False

        # Update Nama & Email
        if nama_baru and nama_baru != user.nama_tampilan:
            user.nama_tampilan = nama_baru
            perubahan_terjadi = True
        
        if email_baru and email_baru != user.email:
            user.email = email_baru
            perubahan_terjadi = True

        # Update Foto (Hanya jika ada file baru yang diupload)
        if foto_profil:
            user.foto_profil = foto_profil
            perubahan_terjadi = True
            
        if foto_bg:
            user.foto_background = foto_bg
            perubahan_terjadi = True

        # Simpan perubahan teks/foto
        if perubahan_terjadi:
            user.save()
            messages.success(request, "Perubahan Berhasil!")

        # Update Password Khusus
        if pass_lama and pass_baru:
            if user.check_password(pass_lama):
                user.set_password(pass_baru)
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Perubahan Berhasil! (Password diubah)")
            else:
                messages.error(request, "Gagal: Password lama salah!")
                
        return redirect('profil')

    context = {
        'user': user,
        'total_dibaca': total_dibaca,
    }
    return render(request, 'perpustakaan/profil.html', context)