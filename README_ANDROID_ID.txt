Toy Story 3 Safe Translator — Android APK project
=================================================

Ini adalah proyek sumber Android yang mengadaptasi HANYA isi Safe_Translator.zip yang diunggah pengguna.
Fitur: ekspor DCT ke CSV, impor CSV ke DCT dengan panjang byte harus sama, dan patch satu entri dalam ZIP dengan validasi CRC/isi.

Batasan penting:
- APK belum dibangun atau diuji di perangkat nyata.
- Build perlu dilakukan di Linux/WSL dengan Buildozer, Java, Android SDK/NDK.
- Pilih file lewat file chooser. Android versi baru mungkin membatasi akses file; uji permission/akses di perangkat target.
- Import memakai cp1252 sesuai default tool Windows yang diunggah. Jangan ubah metadata CSV.
- Gunakan file output terpisah; file sumber tidak ditimpa.

Build (Linux):
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip buildozer cython
  buildozer android debug

APK debug jika build berhasil biasanya berada di bin/.

Build APK tanpa memasang toolchain di perangkat:
1. Buat repository GitHub baru melalui browser dan upload seluruh isi folder proyek ini (termasuk .github/workflows/build-apk.yml).
2. Buka tab Actions di repository, pilih "Build Safe Translator APK", lalu tekan "Run workflow" jika belum berjalan otomatis.
3. Tunggu sampai workflow hijau. Buka hasil run dan unduh artifact "Safe-Translator-Android-APK".
4. Ekstrak artifact ZIP di Android lalu pasang APK. Android mungkin meminta izin memasang aplikasi dari browser/file manager.

Catatan: build cloud tetap perlu diuji; jika workflow gagal, kirim log error agar konfigurasi bisa diperbaiki.
