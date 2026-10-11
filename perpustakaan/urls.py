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
    path('buku/<str:olid>/pinjam/', views.pinjam_buku, name='pinjam_buku'),
    path('buku/<str:olid>/bookmark/', views.toggle_bookmark, name='toggle_bookmark'),

    path('ejournal/', views.ejournal_view, name='ejournal'),
    path('peminjaman/', views.peminjaman_view, name='peminjaman'),
    path('kembalikan/<int:pinjaman_id>/', views.kembalikan_buku, name='kembalikan_buku'),
    path('bookmarks/', views.bookmarks_view, name='bookmarks'),
    path('hapus-bookmark/<int:bookmark_id>/', views.hapus_bookmark_api, name='hapus_bookmark'),
    path('riwayat/', views.riwayat_view, name='riwayat'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    path('profil/', views.profil_view, name='profil'),
    
    # Perbaikan nama URL di sini:
    path('profil/<str:username>/', views.profil_user_detail_view, name='profil_user_detail'),

    path("dashboard-admin/", views_admin.dashboard_admin, name="dashboard_admin"),
]