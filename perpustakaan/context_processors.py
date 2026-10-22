from .models import Notifikasi


def jumlah_notifikasi_belum_dibaca(request):
    if not request.user.is_authenticated:
        return {"jumlah_notifikasi_belum_dibaca": 0}
    return {
        "jumlah_notifikasi_belum_dibaca": Notifikasi.objects.filter(
            user=request.user, dibaca=False
        ).count()
    }
