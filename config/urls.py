from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from perpustakaan import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('buku/<str:olid>/progress/', views.simpan_progress, name='simpan_progress'),
    path('', include('perpustakaan.urls')),
]

# Layani file upload (PDF buku, foto profil) lewat /media/.
# static() otomatis tidak aktif kalau DEBUG = False.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)