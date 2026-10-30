#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Toy Story 3 DCT Safe Translator - GUI
- Extract NUL-separated string pool to CSV.
- Import only exact-byte-length translations; never shifts offsets or pads spaces.
- Patch a DCT entry into an existing ZIP while preserving other entries.
Python 3.x, standard library only.
"""
from pathlib import Path
import csv
import hashlib
import importlib.util
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

POOL_START = 0x229B9
CSV_FIELDS = [
    "index", "file_offset_hex", "byte_length", "translatable_candidate",
    "text_or_escaped_bytes", "raw_hex", "translation"
]

def is_text(raw: bytes) -> bool:
    if not raw:
        return False
    for enc in ("utf-8", "cp1252"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            s = None
    if s is None:
        return False
    good = sum(ch.isprintable() or ch in "\r\n\t" for ch in s)
    return good / max(1, len(s)) >= 0.75

def display_bytes(raw: bytes) -> str:
    for enc in ("utf-8", "cp1252"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            s = None
    if s is None:
        return "".join(f"\\x{b:02X}" for b in raw)
    out = []
    for ch in s:
        n = ord(ch)
        if ch == "\\": out.append("\\\\")
        elif ch == "\r": out.append("\\r")
        elif ch == "\n": out.append("\\n")
        elif ch == "\t": out.append("\\t")
        elif n < 32 or n == 127: out.append(f"\\x{n:02X}")
        else: out.append(ch)
    return "".join(out)

def unescape_text(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] != "\\":
            out.append(s[i]); i += 1; continue
        if i + 1 >= len(s):
            out.append("\\"); i += 1; continue
        c = s[i+1]
        if c == "\\": out.append("\\"); i += 2
        elif c == "n": out.append("\n"); i += 2
        elif c == "r": out.append("\r"); i += 2
        elif c == "t": out.append("\t"); i += 2
        elif c == "x" and i + 3 < len(s):
            try:
                out.append(chr(int(s[i+2:i+4], 16))); i += 4
            except ValueError:
                out.extend(s[i:i+2]); i += 2
        else:
            out.extend(s[i:i+2]); i += 2
    return "".join(out)

def extract_csv(dct_path: Path, csv_path: Path):
    data = dct_path.read_bytes()
    if data[:4] != b"DICT":
        raise ValueError("Header DICT tidak ditemukan. Pilih file .dct yang benar.")
    if len(data) <= POOL_START:
        raise ValueError(f"File terlalu kecil untuk pool yang dikenali (offset 0x{POOL_START:X}).")
    # Keep every NUL-delimited segment and its original byte offset.
    offset = POOL_START
    segments = data[POOL_START:].split(b"\x00")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for idx, raw in enumerate(segments):
            candidate = bool(raw) and is_text(raw)
            w.writerow({
                "index": idx,
                "file_offset_hex": f"0x{offset:08X}",
                "byte_length": len(raw),
                "translatable_candidate": "YES" if candidate else "NO",
                "text_or_escaped_bytes": display_bytes(raw),
                "raw_hex": raw.hex(),
                "translation": ""
            })
            offset += len(raw) + 1
    return len(segments), sum(bool(x) and is_text(x) for x in segments), len(data)

def import_csv(source_path: Path, csv_path: Path, output_path: Path, encoding: str):
    original = source_path.read_bytes()
    if original[:4] != b"DICT":
        raise ValueError("Header DICT tidak ditemukan pada DCT sumber.")
    if output_path.resolve() == source_path.resolve():
        raise ValueError("File output harus berbeda dari file sumber asli.")
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV tidak memiliki header.")
        required = {"index", "file_offset_hex", "byte_length", "raw_hex", "translation"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError("Kolom CSV hilang: " + ", ".join(sorted(missing)))
        rows = list(reader)

    out = bytearray(original)
    changed, skipped = 0, 0
    errors = []
    seen_offsets = set()
    for line_no, row in enumerate(rows, start=2):
        translation = row.get("translation") or ""
        if translation == "":
            skipped += 1
            continue
        try:
            idx = int(row["index"])
            offset = int(row["file_offset_hex"], 16)
            length = int(row["byte_length"])
            expected = bytes.fromhex(row["raw_hex"])
            if offset in seen_offsets:
                raise ValueError("offset duplikat")
            seen_offsets.add(offset)
            if len(expected) != length:
                raise ValueError("byte_length tidak cocok dengan raw_hex")
            if offset < POOL_START or offset + length >= len(original):
                raise ValueError("offset di luar file")
            if original[offset:offset+length] != expected:
                raise ValueError("raw_hex tidak cocok dengan DCT sumber; CSV mungkin berasal dari file lain")
            if original[offset+length] != 0:
                raise ValueError("terminator NUL asli tidak ditemukan")
            decoded = unescape_text(translation)
            encoded = decoded.encode(encoding, errors="strict")
            if b"\x00" in encoded:
                raise ValueError("terjemahan mengandung byte NUL")
            if len(encoded) != length:
                raise ValueError(
                    f"panjang {len(encoded)} byte, harus tepat {length} byte. "
                    "Tidak ada padding otomatis karena dapat membuat subtitle bermasalah."
                )
            out[offset:offset+length] = encoded
            changed += 1
        except Exception as exc:
            errors.append(f"CSV baris {line_no}, index {row.get('index','?')}: {exc}")
            if len(errors) >= 30:
                errors.append("Berhenti menampilkan error setelah 30 masalah.")
                break
    if errors:
        raise ValueError("Import dibatalkan; file output tidak dibuat.\n\n" + "\n".join(errors))
    if len(out) != len(original):
        raise AssertionError("Ukuran file berubah, operasi dibatalkan.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(out)
    return changed, skipped, len(original), hashlib.md5(out).hexdigest()

def patch_zip(zip_path: Path, entry_name: str, replacement_path: Path, output_zip: Path):
    helper_path = Path(__file__).with_name("patch_lang_zip_preserve.py")
    if not helper_path.exists():
        raise FileNotFoundError(
            "File patch_lang_zip_preserve.py tidak ditemukan. "
            "Pastikan file ini berada satu folder dengan tool."
        )
    if output_zip.resolve() == zip_path.resolve():
        raise ValueError("ZIP output harus berbeda dari ZIP sumber.")
    spec = importlib.util.spec_from_file_location("lang_zip_patcher", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Tidak dapat memuat modul patch ZIP.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build(str(zip_path), entry_name, str(replacement_path), str(output_zip))
    return output_zip.stat().st_size, hashlib.md5(output_zip.read_bytes()).hexdigest()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Toy Story 3 - DCT Safe Translator")
        self.geometry("850x610")
        self.minsize(760, 560)
        self.configure(padx=12, pady=10)
        title = ttk.Label(self, text="Toy Story 3 — DCT Safe Translator", font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w")
        ttk.Label(
            self,
            text="Ekspor CSV • Impor dengan panjang byte yang sama persis • Patch ZIP tanpa membangun ulang seluruh arsip",
            wraplength=800
        ).pack(anchor="w", pady=(2, 10))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.tab_extract = ttk.Frame(nb, padding=12)
        self.tab_import = ttk.Frame(nb, padding=12)
        self.tab_zip = ttk.Frame(nb, padding=12)
        self.tab_help = ttk.Frame(nb, padding=12)
        nb.add(self.tab_extract, text="1. Ekspor CSV")
        nb.add(self.tab_import, text="2. Impor DCT")
        nb.add(self.tab_zip, text="3. Patch ZIP")
        nb.add(self.tab_help, text="Panduan")
        self._build_extract()
        self._build_import()
        self._build_zip()
        self._build_help()
        self.status = tk.StringVar(value="Siap.")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", pady=(8, 0))

    def _file_row(self, parent, label, var, command, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(parent, text="Pilih...", command=command).grid(row=row, column=2, pady=6)
        parent.columnconfigure(1, weight=1)

    def _build_extract(self):
        p = self.tab_extract
        self.ex_src = tk.StringVar()
        self.ex_csv = tk.StringVar()
        self._file_row(p, "DCT sumber:", self.ex_src, self.pick_ex_src, 0)
        self._file_row(p, "CSV output:", self.ex_csv, self.pick_ex_csv, 1)
        ttk.Label(
            p,
            text="CSV berisi seluruh segmen string setelah offset pool 0x229B9. Kolom translation sengaja dikosongkan. "
                 "Edit hanya kolom translation; jangan mengubah index, offset, byte_length, atau raw_hex.",
            wraplength=760
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 8))
        ttk.Button(p, text="Ekspor ke CSV", command=self.do_extract).grid(row=3, column=1, sticky="e", pady=10)

    def pick_ex_src(self):
        f = filedialog.askopenfilename(title="Pilih DCT sumber", filetypes=[("DCT/DIC files", "*.dct *.dict *.dic"), ("Semua file", "*.*")])
        if f:
            self.ex_src.set(f)
            if not self.ex_csv.get():
                self.ex_csv.set(str(Path(f).with_name(Path(f).stem + "_translation.csv")))

    def pick_ex_csv(self):
        f = filedialog.asksaveasfilename(title="Simpan CSV", defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if f: self.ex_csv.set(f)

    def do_extract(self):
        try:
            if not self.ex_src.get() or not self.ex_csv.get():
                raise ValueError("Pilih DCT sumber dan lokasi CSV output.")
            n, candidates, size = extract_csv(Path(self.ex_src.get()), Path(self.ex_csv.get()))
            msg = f"Ekspor selesai.\nSegmen: {n:,}\nKandidat teks: {candidates:,}\nUkuran DCT: {size:,} byte\n\nCSV: {self.ex_csv.get()}"
            self.status.set("Ekspor CSV selesai.")
            messagebox.showinfo("Selesai", msg)
        except Exception as e:
            messagebox.showerror("Ekspor gagal", str(e))
            self.status.set("Ekspor gagal.")

    def _build_import(self):
        p = self.tab_import
        self.im_src = tk.StringVar()
        self.im_csv = tk.StringVar()
        self.im_out = tk.StringVar()
        self.im_enc = tk.StringVar(value="cp1252")
        self._file_row(p, "DCT asli (basis):", self.im_src, self.pick_im_src, 0)
        self._file_row(p, "CSV terjemahan:", self.im_csv, self.pick_im_csv, 1)
        self._file_row(p, "DCT output:", self.im_out, self.pick_im_out, 2)
        ttk.Label(p, text="Encoding teks:").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Combobox(p, textvariable=self.im_enc, values=["cp1252", "utf-8", "latin-1"], state="readonly", width=18).grid(row=3, column=1, sticky="w", padx=8, pady=6)
        ttk.Label(
            p,
            text="PENTING: teks terjemahan harus memiliki jumlah BYTE yang persis sama dengan string asli. "
                 "Tool tidak menambah spasi otomatis dan tidak menggeser data. Jika ada satu string saja tidak cocok, "
                 "seluruh import dibatalkan agar tidak menghasilkan DCT setengah jadi.",
            wraplength=760
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 8))
        ttk.Button(p, text="Impor & Validasi", command=self.do_import).grid(row=5, column=1, sticky="e", pady=10)

    def pick_im_src(self):
        f = filedialog.askopenfilename(title="Pilih DCT asli", filetypes=[("DCT/DIC files", "*.dct *.dict *.dic"), ("Semua file", "*.*")])
        if f:
            self.im_src.set(f)
            if not self.im_out.get():
                path = Path(f)
                self.im_out.set(str(path.with_name(path.stem + "_ID_SAFE" + path.suffix)))

    def pick_im_csv(self):
        f = filedialog.askopenfilename(title="Pilih CSV terjemahan", filetypes=[("CSV", "*.csv"), ("Semua file", "*.*")])
        if f: self.im_csv.set(f)

    def pick_im_out(self):
        f = filedialog.asksaveasfilename(title="Simpan DCT output", defaultextension=".dct", filetypes=[("DCT", "*.dct"), ("Semua file", "*.*")])
        if f: self.im_out.set(f)

    def do_import(self):
        try:
            if not all([self.im_src.get(), self.im_csv.get(), self.im_out.get()]):
                raise ValueError("Pilih DCT asli, CSV terjemahan, dan DCT output.")
            changed, skipped, size, md5 = import_csv(Path(self.im_src.get()), Path(self.im_csv.get()), Path(self.im_out.get()), self.im_enc.get())
            msg = f"Import berhasil.\nString diubah: {changed:,}\nString dilewati: {skipped:,}\nUkuran: {size:,} byte (tetap)\nMD5: {md5}\n\nOutput: {self.im_out.get()}"
            self.status.set("Import DCT selesai.")
            messagebox.showinfo("Import berhasil", msg)
        except Exception as e:
            messagebox.showerror("Import dibatalkan", str(e))
            self.status.set("Import dibatalkan; periksa pesan error.")

    def _build_zip(self):
        p = self.tab_zip
        self.z_src = tk.StringVar()
        self.z_entry = tk.StringVar(value="english_ntsc_win32.dct")
        self.z_dct = tk.StringVar()
        self.z_out = tk.StringVar()
        self._file_row(p, "ZIP asli:", self.z_src, self.pick_z_src, 0)
        ttk.Label(p, text="Nama entri di ZIP:").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(p, textvariable=self.z_entry).grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        ttk.Label(p, text="DCT pengganti:",).grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(p, textvariable=self.z_dct).grid(row=2, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(p, text="Pilih...", command=self.pick_z_dct).grid(row=2, column=2, pady=6)
        ttk.Label(p, text="ZIP output:").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(p, textvariable=self.z_out).grid(row=3, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(p, text="Pilih...", command=self.pick_z_out).grid(row=3, column=2, pady=6)
        p.columnconfigure(1, weight=1)
        ttk.Label(
            p,
            text="Pilih ZIP asli yang bisa dijalankan game. Tool mengganti hanya satu entri DCT dan memvalidasi isi seluruh entri. "
                 "Jangan pilih ZIP yang sudah pernah dipatch sebagai sumber jika ingin memulai dari arsip bersih.",
            wraplength=760
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 8))
        ttk.Button(p, text="Buat ZIP hasil", command=self.do_zip).grid(row=5, column=1, sticky="e", pady=10)

    def pick_z_src(self):
        f = filedialog.askopenfilename(title="Pilih ZIP asli", filetypes=[("ZIP", "*.zip"), ("Semua file", "*.*")])
        if f:
            self.z_src.set(f)
            if not self.z_out.get():
                path = Path(f)
                self.z_out.set(str(path.with_name(path.stem + "_translated.zip")))

    def pick_z_dct(self):
        f = filedialog.askopenfilename(title="Pilih DCT pengganti", filetypes=[("DCT", "*.dct"), ("Semua file", "*.*")])
        if f:
            self.z_dct.set(f)
            # Infer the target entry name from file name if possible.
            self.z_entry.set(Path(f).name)

    def pick_z_out(self):
        f = filedialog.asksaveasfilename(title="Simpan ZIP output", defaultextension=".zip", filetypes=[("ZIP", "*.zip"), ("Semua file", "*.*")])
        if f: self.z_out.set(f)

    def do_zip(self):
        try:
            if not all([self.z_src.get(), self.z_entry.get(), self.z_dct.get(), self.z_out.get()]):
                raise ValueError("Lengkapi ZIP asli, nama entri, DCT pengganti, dan ZIP output.")
            size, md5 = patch_zip(Path(self.z_src.get()), self.z_entry.get(), Path(self.z_dct.get()), Path(self.z_out.get()))
            msg = f"ZIP berhasil dibuat dan divalidasi.\nUkuran: {size:,} byte\nMD5: {md5}\n\nOutput: {self.z_out.get()}"
            self.status.set("Patch ZIP selesai.")
            messagebox.showinfo("ZIP berhasil", msg)
        except Exception as e:
            messagebox.showerror("Patch ZIP gagal", str(e))
            self.status.set("Patch ZIP gagal.")

    def _build_help(self):
        p = self.tab_help
        text = (
            "ALUR KERJA YANG DISARANKAN\n\n"
            "1. Gunakan ZIP asli yang sudah terbukti bisa dijalankan.\n"
            "2. Ekspor DCT yang sesuai (NTSC atau PAL) ke CSV.\n"
            "3. Edit kolom translation saja. Biarkan kosong untuk tidak mengubah string.\n"
            "4. Jangan mengubah index, file_offset_hex, byte_length, atau raw_hex.\n"
            "5. Pilih encoding yang cocok. Untuk teks Indonesia biasa, cp1252 paling kompatibel dengan ASCII; "
            "karakter yang tidak tersedia dalam cp1252 akan ditolak.\n"
            "6. Import memakai DCT asli yang sama persis dengan sumber CSV.\n"
            "7. Panjang terjemahan harus tepat sama dalam byte, bukan jumlah karakter. Tidak boleh lebih pendek atau panjang.\n"
            "8. Patch DCT hasil ke ZIP asli dengan tab Patch ZIP.\n"
            "9. Simpan ZIP hasil dengan nama berbeda; cadangkan file asli.\n\n"
            "CATATAN\n"
            "• Tool tidak mengubah ukuran DCT dan tidak menggeser data setelah string.\n"
            "• Jika teks terjemahan lebih pendek, tambahkan karakter pengisi yang memang ingin tampil (misalnya tanda baca) "
            "sampai jumlah byte sama. Jangan mengandalkan spasi padding otomatis.\n"
            "• Jika teks lebih panjang, ringkas terjemahan. Tool sengaja menolak import jika panjang byte tidak persis cocok.\n"
            "• CSV dapat diedit dengan Notepad++ atau spreadsheet, tetapi gunakan UTF-8 CSV dan jangan mengubah metadata.\n"
            "• Tool tidak menguji game secara otomatis; selalu uji ZIP hasil dan simpan cadangan.\n"
        )
        box = tk.Text(p, wrap="word", height=22, width=90)
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True)

if __name__ == "__main__":
    App().mainloop()
