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
