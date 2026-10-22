from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('perpustakaan', '0016_remove_bukudigital_ia_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notifikasi',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jenis', models.CharField(choices=[('katalog', 'Katalog'), ('pengumuman', 'Pengumuman'), ('peminjaman', 'Peminjaman'), ('tenggat', 'Tenggat'), ('gamifikasi', 'Gamifikasi')], default='pengumuman', max_length=20)),
                ('judul', models.CharField(max_length=180)),
                ('isi', models.TextField()),
                ('url', models.CharField(blank=True, max_length=500)),
                ('dibuat', models.DateTimeField(default=django.utils.timezone.now)),
                ('dibaca', models.BooleanField(default=False)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifikasi', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-dibuat', '-pk']},
        ),
    ]
