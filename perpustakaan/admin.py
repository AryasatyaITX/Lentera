from django.contrib import admin
from django.utils.html import format_html
from .models import (
    CustomUser, BukuDigital, Jurnal, Peminjaman, Notifikasi,
    Bookmark, Pengaturan, Achievement, AchievementGambar, UserAchievement,
)

admin.site.register(CustomUser)
admin.site.register(BukuDigital)
admin.site.register(Jurnal)
admin.site.register(Peminjaman)
admin.site.register(Notifikasi)
admin.site.register(Bookmark)
admin.site.register(Achievement)
admin.site.register(UserAchievement)
admin.site.register(Pengaturan)

@admin.register(AchievementGambar)
class AchievementGambarAdmin(admin.ModelAdmin):
    list_display = ("nama", "kategori", "tipe_syarat", "target",
                    "preview_terkunci", "preview_terbuka")
    list_filter = ("kategori", "tipe_syarat")
    search_fields = ("nama", "deskripsi")

    class Media:
        css = {"all": ("perpustakaan/css/admin.css",)}

    @admin.display(description="Gambar terkunci")
    def preview_terkunci(self, obj):
        return self._preview(obj, terbuka=False)

    @admin.display(description="Gambar terbuka")
    def preview_terbuka(self, obj):
        return self._preview(obj, terbuka=True)

    def _ikon(self, obj, terbuka):
        """Ikon dari obj.ikon_tampil (field ikon, lalu kamus nama), fallback gembok."""
        gembok = "fa-lock-open" if terbuka else "fa-lock"
        ikon = obj.ikon_tampil
        if ikon:
            return format_html('<i class="fas {}"></i>', ikon)
        return format_html('<i class="fas {}" title="nama tidak dikenal: {}"></i>', gembok, obj.nama)

        # 1) Ikon yang diisi admin di form (sumber paling sahih)
        if obj.ikon:
            ikon = obj.ikon.strip()
            if ikon:
                return format_html('<i class="fas {}"></i>', ikon)

        # 2) Kamus nama -> ikon (toleran huruf besar/kecil & spasi)
        kunci = (obj.nama or "").strip().casefold()
        if kunci in IKON_ACHIEVEMENT_BERSIH:
            return format_html('<i class="fas {}"></i>', IKON_ACHIEVEMENT_BERSIH[kunci])

        # 3) Tidak ketemu -> gembok
        return format_html('<i class="fas {}" title="nama tidak dikenal: {}"></i>', gembok, obj.nama)

    def _preview(self, obj, terbuka):
        # 1) Gambar asli yang diupload admin -> thumbnail
        berkas = obj.gambar_terbuka if terbuka else obj.gambar_terkunci
        if berkas:
            kelas = "acv-thumb terbuka" if terbuka else "acv-thumb terkunci"
            return format_html(
                '<img src="{}" class="{}" width="44" height="44">', berkas.url, kelas
            )
        # 2) Placeholder: icon achievement + warna kategori (terkunci = hitam putih)
        ikon_html = self._ikon(obj, terbuka)
        warna = {"umum": "#22C55E", "langka": "#3B82F6", "epik": "#8B5CF6"}.get(
            (obj.kategori or "umum").lower(), "#22C55E"
        )
        if terbuka:
            return format_html(
                '<span class="acv-admin-ik terbuka" style="background:{};">{}</span>',
                warna, ikon_html,
            )
        return format_html('<span class="acv-admin-ik terkunci">{}</span>', ikon_html)