Toy Story 3 - DCT Safe Translator
=================================

Isi:
- Toy_Story3_DCT_Safe_Translator.py : GUI Tkinter untuk ekspor CSV, impor DCT, dan patch ZIP.
- patch_lang_zip_preserve.py         : patcher ZIP yang mempertahankan entri lain.

Persyaratan:
- Windows dengan Python 3.10+.
- Tidak perlu memasang paket tambahan.
- Tkinter biasanya sudah disertakan pada installer resmi Python untuk Windows.

Cara menjalankan:
1. Ekstrak semua file dari ZIP ini ke satu folder.
2. Klik dua kali Toy_Story3_DCT_Safe_Translator.py, atau jalankan:
   py Toy_Story3_DCT_Safe_Translator.py
3. Tab Ekspor CSV: pilih DCT asli dan simpan CSV.
4. Edit kolom translation saja. Kosong = tidak diubah.
5. Tab Impor DCT: pilih DCT asli yang sama, CSV, dan nama output baru.
6. Tab Patch ZIP: pilih ZIP asli yang bisa berjalan, nama entri DCT di dalam ZIP,
   DCT output, dan nama ZIP output.

Aturan keselamatan:
- Importer hanya menerima terjemahan yang panjang BYTE-nya persis sama dengan string sumber.
- Tidak ada padding spasi otomatis.
- Jika satu terjemahan tidak cocok, seluruh impor dibatalkan dan file output tidak dibuat.
- Jangan mengubah kolom metadata CSV: index, file_offset_hex, byte_length, raw_hex.
- Selalu mulai dari DCT dan ZIP asli yang bisa berjalan.
- Uji game setelah patch dan simpan cadangan.

Encoding:
- Default cp1252; gunakan ASCII untuk teks paling aman.
- UTF-8 dapat dipilih jika file/game memang menggunakan UTF-8 untuk string pool.
- Jika terjemahan memiliki karakter yang tidak bisa dikodekan dengan pilihan encoding, import akan dibatalkan.

Penting:
Tool ini memakai offset string pool 0x229B9 yang terdeteksi pada DCT Toy Story 3 yang dianalisis.
Jika file versi lain memiliki struktur berbeda, ekspor/impor tidak boleh diasumsikan kompatibel.


Perbaikan build Android (30 Oktober 2026)
-----------------------------------------
- Workflow GitHub Actions mengunci Buildozer 1.5.0 dan Cython 0.29.36.
- buildozer.spec mengunci Python-for-Android ke tag v2024.01.21, bukan master.
- Ini menghindari resep CPython 3.14.2 yang pada log sebelumnya gagal saat kompilasi
  remote_debugging.c karena deklarasi preadv/pwritev tidak tersedia untuk target API 23.
- Build APK harus dijalankan ulang lewat GitHub Actions; file ZIP ini bukan APK.
- Jika build berikutnya gagal pada tahap berbeda, kirim log baru karena toolchain yang
  dipin masih perlu diverifikasi oleh build nyata di GitHub Actions.
