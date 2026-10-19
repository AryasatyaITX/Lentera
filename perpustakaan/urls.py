from django.urls import path
from . import views
from . import views_admin

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Katalog + detail buku
    path('katalog/', views.katalog_view, name='katalog'),
    path('buku/<str:olid>/', views.buku_detail, name='buku_detail'),
    path('baca/<str:olid>/', views.baca_buku, name='baca_buku'),
    path('api/waktu-baca/', views.waktu_baca, name='waktu_baca'),
    path('buku/<str:olid>/pinjam/', views.pinjam_buku, name='pinjam_buku'),
    path('buku/<str:olid>/bookmark/', views.toggle_bookmark, name='toggle_bookmark'),

    path('ejournal/', views.ejournal_view, name='ejournal'),
    path('jurnal/<str:jurnal_id>/baca/', views.baca_jurnal, name='baca_jurnal'),
    path('peminjaman/', views.peminjaman_view, name='peminjaman'),
    path('kembalikan/<int:pinjaman_id>/', views.kembalikan_buku, name='kembalikan_buku'),
    path('perpanjang/<int:pinjaman_id>/', views.perpanjang_buku, name='perpanjang_buku'),
    path('bookmarks/', views.bookmarks_view, name='bookmarks'),
    path('hapus-bookmark/<int:bookmark_id>/', views.hapus_bookmark_api, name='hapus_bookmark'),
    path('riwayat/', views.riwayat_view, name='riwayat'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    path('profil/', views.profil_view, name='profil'),
    path('achievement/', views.achievement_view, name='achievement'),
    
    # Perbaikan nama URL di sini:
    path('profil/<str:username>/', views.profil_user_detail_view, name='profil_user_detail'),
    # tambah
    path("dashboard-admin/", views_admin.dashboard_admin, name="dashboard_admin"),
    path("dashboard-admin/buku/", views_admin.kelola_buku, name="kelola_buku",),
    path("dashboard-admin/buku/hapus/<str:id_item>/", views_admin.hapus_buku, name="hapus_buku",),
    path("dashboard-admin/jurnal/", views_admin.kelola_jurnal, name="kelola_jurnal",),
    path("dashboard-admin/jurnal/hapus/<str:id_item>/", views_admin.hapus_jurnal, name="hapus_jurnal",),

    # Kelola anggota, peminjaman, laporan (admin)
    path("dashboard-admin/anggota/", views_admin.kelola_anggota, name="kelola_anggota"),
    path("dashboard-admin/anggota/<str:pk>/edit/", views_admin.edit_anggota, name="edit_anggota"),
    path("dashboard-admin/anggota/<str:pk>/hapus/", views_admin.hapus_anggota, name="hapus_anggota"),
    path("dashboard-admin/anggota/<str:pk>/aktifkan/", views_admin.aktifkan_anggota, name="aktifkan_anggota"),
    path("dashboard-admin/peminjaman/", views_admin.peminjaman_admin, name="peminjaman_admin"),
    path("dashboard-admin/laporan/", views_admin.laporan, name="laporan_peminjaman"),
    path("dashboard-admin/laporan/unduh/", views_admin.unduh_laporan, name="unduh_laporan"),
]