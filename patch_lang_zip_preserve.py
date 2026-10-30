#!/usr/bin/env python3
# Patch one file inside a ZIP while preserving every other local record and
# compressed payload byte-for-byte for untouched entries. Updates CRC/sizes/offsets and the custom
# 0x4B46 "MD5" central-directory extra field when present.
import os, sys, struct, zlib, binascii, hashlib, shutil
from pathlib import Path

LOCAL_SIG = b'PK\x03\x04'
CENTRAL_SIG = b'PK\x01\x02'
EOCD_SIG = b'PK\x05\x06'


def find_eocd(data):
    start = max(0, len(data) - (65535 + 22))
    pos = data.rfind(EOCD_SIG, start)
    if pos < 0:
        raise ValueError('Tidak menemukan EOCD ZIP. ZIP64 atau arsip tidak standar belum didukung.')
    if pos + 22 > len(data):
        raise ValueError('EOCD ZIP terpotong.')
    sig, disk, cd_disk, disk_entries, total_entries, cd_size, cd_offset, comment_len = struct.unpack_from('<IHHHHIIH', data, pos)
    if disk or cd_disk or disk_entries != total_entries:
        raise ValueError('ZIP multi-disk tidak didukung.')
    if total_entries == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        raise ValueError('ZIP64 belum didukung oleh skrip ini.')
    if pos + 22 + comment_len != len(data):
        raise ValueError('Panjang komentar/EOCD tidak valid; arsip mungkin memiliki data tambahan di akhir.')
    return pos, total_entries, cd_size, cd_offset, data[pos+22:pos+22+comment_len]


def parse_central(data, cd_offset, cd_size, total_entries):
    entries = []
    p = cd_offset
    cd_end = cd_offset + cd_size
    for i in range(total_entries):
        if data[p:p+4] != CENTRAL_SIG:
            raise ValueError(f'Central directory rusak pada entri {i}.')
        vals = struct.unpack_from('<IHHHHHHIIIHHHHHII', data, p)
        # fixed 46 bytes
        name_len, extra_len, comment_len = vals[10], vals[11], vals[12]
        end = p + 46 + name_len + extra_len + comment_len
        if end > cd_end:
            raise ValueError('Central directory entry terpotong.')
        entries.append({
            'raw': bytearray(data[p:end]), 'name_bytes': data[p+46:p+46+name_len],
            'name': data[p+46:p+46+name_len].decode('utf-8' if vals[ flag_index := 3] & 0x800 else 'cp437', errors='replace'),
            'flags': vals[3], 'method': vals[4], 'crc': vals[7], 'csize': vals[8], 'usize': vals[9],
            'extra_len': extra_len, 'comment_len': comment_len, 'local_offset': vals[16],
            'version_made': vals[1], 'version_needed': vals[2], 'mod_time': vals[5], 'mod_date': vals[6],
        })
        p = end
    if p != cd_end:
        raise ValueError('Ada data central-directory yang tidak terjelaskan; dibatalkan demi keamanan.')
    return entries


def parse_extra(extra):
    fields=[]; p=0
    while p < len(extra):
        if p+4 > len(extra):
            raise ValueError('Extra field ZIP rusak.')
        tag, size = struct.unpack_from('<HH', extra, p)
        end = p+4+size
        if end > len(extra): raise ValueError('Panjang extra field ZIP tidak valid.')
        fields.append((tag, extra[p+4:end]))
        p=end
    return fields


def patch_extra(extra, md5_bytes):
    out=bytearray(); found=False
    for tag, payload in parse_extra(extra):
        if tag == 0x464B and payload[:3] == b'MD5' and len(payload) >= 19:
            payload = b'MD5' + md5_bytes + payload[19:]
            found=True
        out += struct.pack('<HH', tag, len(payload)) + payload
    return bytes(out), found


def raw_deflate(data, level=6):
    c = zlib.compressobj(level, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def build(input_zip, entry_name, replacement_path, output_zip):
    original = Path(input_zip).read_bytes()
    eocd_pos, total, cd_size, cd_offset, comment = find_eocd(original)
    entries = parse_central(original, cd_offset, cd_size, total)
    matches = [e for e in entries if e['name'].replace('\\','/') == entry_name.replace('\\','/')]
    if len(matches) != 1:
        raise ValueError(f'Nama entri harus cocok tepat satu kali; ditemukan {len(matches)}: {entry_name}')
    target = matches[0]
    if target['method'] not in (0, 8):
        raise ValueError(f'Metode kompresi target {target["method"]} tidak didukung (hanya STORE/DEFLATE).')
    if target['flags'] & 0x1:
        raise ValueError('Entri terenkripsi tidak didukung.')
    new_data = Path(replacement_path).read_bytes()
    # If replacement is byte-identical to the current entry, preserve its compressed
    # stream and local record exactly. This makes a no-change test a true control.
    with __import__('zipfile').ZipFile(input_zip, 'r') as _zf:
        original_target_data = _zf.read(entry_name)
    unchanged_payload = (new_data == original_target_data)
    if unchanged_payload:
        new_comp = None  # use the exact original compressed bytes below
    elif target['method'] == 0:
        new_comp = new_data
    else:
        # Compress the replacement bytes themselves. Never reuse a stale .bin stream:
        # a stream made from different bytes causes Bad CRC-32 on extraction.
        new_comp = raw_deflate(new_data, level=9)
    new_crc = binascii.crc32(new_data) & 0xFFFFFFFF
    new_md5 = hashlib.md5(new_data).digest()

    # Original local records in physical offset order. Preserve all unchanged spans exactly.
    by_offset = sorted(entries, key=lambda e: e['local_offset'])
    if len({e['local_offset'] for e in by_offset}) != len(by_offset):
        raise ValueError('Offset local header duplikat; dibatalkan.')
    local_prefix = original[:by_offset[0]['local_offset']] if by_offset else original[:cd_offset]
    out = bytearray(local_prefix)
    new_offsets = {}
    for idx, e in enumerate(by_offset):
        start = e['local_offset']
        next_start = by_offset[idx+1]['local_offset'] if idx+1 < len(by_offset) else cd_offset
        if start + 30 > len(original) or original[start:start+4] != LOCAL_SIG:
            raise ValueError(f'Local header tidak valid untuk {e["name"]}')
        vals = struct.unpack_from('<IHHHHHIIIHH', original, start)
        name_len, extra_len = vals[9], vals[10]
        data_start = start + 30 + name_len + extra_len
        data_end = data_start + e['csize']
        if e is target and unchanged_payload:
            new_offsets[id(e)] = len(out)
            out += original[start:next_start]
            continue
        descriptor_len = 0
        if e['flags'] & 0x8:
            # Data descriptor follows compressed bytes. Signature is optional; CRC+sizes are 12 or 16 bytes.
            if original[data_end:data_end+4] == b'PK\x07\x08': descriptor_len = 16
            else: descriptor_len = 12
        record_end = data_end + descriptor_len
        if record_end > next_start or next_start > cd_offset:
            raise ValueError(f'Batas record lokal tidak valid untuk {e["name"]}')
        raw_record = original[start:record_end]
        suffix_gap = original[record_end:next_start]
        new_offsets[id(e)] = len(out)
        if e is not target:
            out += raw_record
        else:
            # Keep original local header metadata, filename and local extra; update CRC/sizes.
            name_extra = original[start+30:data_start]
            local_header = bytearray(original[start:start+30])
            struct.pack_into('<III', local_header, 14, new_crc, len(new_comp), len(new_data))
            out += local_header + name_extra + new_comp
            # If the old target had a descriptor, write a matching descriptor of the same style.
            if e['flags'] & 0x8:
                has_sig = original[data_end:data_end+4] == b'PK\x07\x08'
                if has_sig: out += struct.pack('<IIII', 0x08074b50, new_crc, len(new_comp), len(new_data))
                else: out += struct.pack('<III', new_crc, len(new_comp), len(new_data))
        out += suffix_gap

    new_cd_offset = len(out)
    # Central directory remains in original order; patch target metadata and all local offsets.
    for e in entries:
        raw = bytearray(e['raw'])
        # central fixed fields: CRC@16, compressed size@20, uncompressed size@24, name len@28, extra len@30, comment len@32, local offset@42
        if e is target and not unchanged_payload:
            struct.pack_into('<III', raw, 16, new_crc, len(new_comp), len(new_data))
            name_len = struct.unpack_from('<H', raw, 28)[0]
            extra_len = struct.unpack_from('<H', raw, 30)[0]
            extra_start = 46 + name_len
            extra = bytes(raw[extra_start:extra_start+extra_len])
            updated_extra, found = patch_extra(extra, new_md5)
            if len(updated_extra) != extra_len:
                raise ValueError('Panjang extra field berubah; tidak aman untuk mempertahankan struktur.')
            raw[extra_start:extra_start+extra_len] = updated_extra
            if not found:
                print('PERINGATAN: metadata MD5 khusus 0x464B tidak ditemukan pada target.')
        struct.pack_into('<I', raw, 42, new_offsets[id(e)])
        out += raw
    new_cd_size = len(out) - new_cd_offset
    if new_cd_offset > 0xFFFFFFFF or new_cd_size > 0xFFFFFFFF:
        raise ValueError('Hasil membutuhkan ZIP64, tidak didukung.')
    # Update central directory size/offset. Rebuild the ZIP comment to make the
    # final archive exactly the same byte size as the reference ZIP.
    eocd = bytearray(original[eocd_pos:eocd_pos+22])
    struct.pack_into('<II', eocd, 12, new_cd_size, new_cd_offset)
    struct.pack_into('<H', eocd, 20, 0)
    out += eocd

    target_zip_size = len(original)
    difference = target_zip_size - len(out)
    if difference < 0:
        raise ValueError(
            f'ZIP hasil masih lebih besar {abs(difference):,} byte dari ZIP asli. '
            'Kompresi baru tidak muat dalam ukuran target; file tidak disimpan.'
        )
    if difference > 65535:
        raise ValueError(
            f'Selisih {difference:,} byte terlalu besar untuk komentar ZIP. '
            'File tidak disimpan.'
        )
    # A ZIP comment is legal metadata; this adds exactly `difference` bytes.
    struct.pack_into('<H', out, len(out)-2, difference)
    out += b' ' * difference
    if len(out) != target_zip_size:
        raise ValueError('Internal error: ukuran output tidak sama dengan ZIP asli.')
    Path(output_zip).write_bytes(out)

    # Validate output archive and every unchanged uncompressed file against original.
    import zipfile
    with zipfile.ZipFile(input_zip, 'r') as za, zipfile.ZipFile(output_zip, 'r') as zb:
        if za.namelist() != zb.namelist(): raise ValueError('Validasi gagal: urutan/nama entri berubah.')
        for name in za.namelist():
            a, b = za.read(name), zb.read(name)
            expected = new_data if name == entry_name else a
            if b != expected: raise ValueError(f'Validasi isi gagal: {name}')
        for a, b in zip(za.infolist(), zb.infolist()):
            if a.filename != b.filename or a.compress_type != b.compress_type:
                raise ValueError(f'Validasi metadata dasar gagal: {a.filename}')
    print('Selesai dan lolos validasi ZIP.')
    print(f'Entri diganti : {entry_name}')
    print(f'Ukuran baru   : {len(new_data):,} byte')
    print(f'MD5 baru      : {new_md5.hex()}')
    print(f'ZIP output    : {output_zip}')
    print(f'Ukuran ZIP    : {len(out):,} byte')
    print('Semua entri selain target disalin dengan compressed data aslinya.')
    if unchanged_payload: print('Target identik: compressed stream dan local record target juga dipertahankan persis.')


def main():
    print('Toy Story 3 - ZIP single-entry patcher')
    print('Mempertahankan compressed data dan metadata entri lain.')
    inp = input('Path ZIP asli: ').strip().strip('"')
    if not os.path.isfile(inp): raise SystemExit('File ZIP asli tidak ditemukan.')
    entry = input('Nama file di dalam ZIP (mis. english_pal_win32.dct): ').strip().replace('\\','/')
    repl = input('Path file pengganti: ').strip().strip('"')
    if not os.path.isfile(repl): raise SystemExit('File pengganti tidak ditemukan.')
    out = input('Path ZIP hasil (mis. lang_test.zip): ').strip().strip('"')
    if not out: raise SystemExit('Path output wajib diisi.')
    if os.path.abspath(out) == os.path.abspath(inp): raise SystemExit('Output tidak boleh menimpa ZIP asli.')
    build(inp, entry, repl, out)
    input('Tekan Enter untuk keluar...')

if __name__ == '__main__':
    try: main()
    except Exception as ex:
        print(f'GAGAL: {ex}')
        input('Tekan Enter untuk keluar...')
        sys.exit(1)
