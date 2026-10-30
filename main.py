# -*- coding: utf-8 -*-
"""Android Kivy front-end for the uploaded Safe Translator tool."""
import os
from pathlib import Path
from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.utils import platform

from safe_translator_core import extract_csv, import_csv, patch_zip

DEFAULT_DIR = '/storage/emulated/0/Download'

class SafeTranslatorApp(App):
    title = 'Safe Translator'

    def build(self):
        self.rootbox = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        self.rootbox.add_widget(Label(text='Toy Story 3 — Safe Translator', size_hint_y=None, height=dp(42), font_size='20sp', bold=True))
        self.rootbox.add_widget(Label(text='DCT → CSV  •  CSV → DCT  •  Patch ZIP\nPanjang byte wajib sama; file asli tidak ditimpa.', size_hint_y=None, height=dp(48), font_size='13sp'))
        self.fields = {}
        self._field('DCT sumber', 'ex_src', '*.dct')
        self._field('CSV ekspor / CSV terjemahan', 'csv', '*.csv')
        self._field('DCT hasil impor', 'im_out', '*.dct')
        self._field('ZIP asli', 'zip_src', '*.zip')
        self._field('Nama entri di ZIP', 'entry', None, default='english_pal_win32.dct')
        self._field('DCT pengganti untuk ZIP', 'zip_dct', '*.dct')
        self._field('ZIP hasil', 'zip_out', '*.zip')

        buttons = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(126))
        for label, fn in [
            ('1. Ekspor DCT → CSV', self.do_extract),
            ('2. Impor CSV → DCT', self.do_import),
            ('3. Patch ZIP', self.do_patch),
            ('Bersihkan log', self.clear_log),
        ]:
            b = Button(text=label, size_hint_y=None, height=dp(54), font_size='14sp')
            b.bind(on_release=lambda inst, f=fn: f())
            buttons.add_widget(b)
        self.rootbox.add_widget(buttons)
        self.rootbox.add_widget(Label(text='Log proses', size_hint_y=None, height=dp(26), halign='left', text_size=(None, None)))
        sc = ScrollView(size_hint_y=None, height=dp(180))
        self.log = TextInput(text='Siap. Letakkan file di Download agar mudah dipilih.', readonly=True, multiline=True, size_hint_y=None, font_size='12sp')
        self.log.bind(minimum_height=self.log.setter('height'))
        self.log.height = dp(180)
        sc.add_widget(self.log)
        self.rootbox.add_widget(sc)
        self.rootbox.add_widget(Label(text='Penting: hanya edit kolom translation. Jangan ubah index, offset, byte_length, atau raw_hex.', size_hint_y=None, height=dp(44), font_size='11sp'))
        self.rootbox.size_hint_y = None
        self.rootbox.bind(minimum_height=self.rootbox.setter('height'))
        if platform == 'android':
            self._request_permissions()
        outer = ScrollView()
        outer.add_widget(self.rootbox)
        return outer

    def _request_permissions(self):
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
        except Exception as e:
            self.log_msg('Catatan izin penyimpanan: ' + str(e))

    def _field(self, label, key, pattern, default=''):
        row = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(64), spacing=dp(2))
        row.add_widget(Label(text=label, size_hint_y=None, height=dp(22), halign='left', valign='middle', font_size='12sp', text_size=(dp(330), None)))
        line = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(5))
        ti = TextInput(text=default, multiline=False, font_size='12sp', size_hint_x=0.78)
        line.add_widget(ti)
        self.fields[key] = ti
        if pattern:
            b = Button(text='Pilih', size_hint_x=0.22, font_size='12sp')
            b.bind(on_release=lambda inst, k=key, pat=pattern: self.choose_file(k, pat))
            line.add_widget(b)
        row.add_widget(line)
        self.rootbox.add_widget(row)

    def choose_file(self, key, pattern):
        start = DEFAULT_DIR if os.path.isdir(DEFAULT_DIR) else '/storage/emulated/0'
        chooser = FileChooserListView(path=start, filters=[pattern], dirselect=False)
        box = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(6))
        box.add_widget(chooser)
        controls = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        popup = Popup(title='Pilih file', content=box, size_hint=(0.96, 0.9))
        cancel = Button(text='Batal')
        select = Button(text='Gunakan file')
        cancel.bind(on_release=popup.dismiss)
        def accept(*_):
            if chooser.selection:
                self.fields[key].text = chooser.selection[0]
                popup.dismiss()
        select.bind(on_release=accept)
        controls.add_widget(cancel); controls.add_widget(select)
        box.add_widget(controls)
        popup.open()

    def log_msg(self, msg):
        self.log.text += ('\n' if self.log.text else '') + str(msg)
        self.log.cursor = (0, len(self.log.text.splitlines()))

    def clear_log(self):
        self.log.text = ''

    def val(self, key):
        return self.fields[key].text.strip().strip('"')

    def need(self, *keys):
        missing = [k for k in keys if not self.val(k)]
        if missing:
            self.log_msg('Isi atau pilih jalur file yang diperlukan terlebih dahulu.')
            return False
        for k in keys:
            if not os.path.isfile(self.val(k)) and k not in ('im_out', 'zip_out', 'csv'):
                self.log_msg('File tidak ditemukan: ' + self.val(k)); return False
        return True

    def do_extract(self):
        if not self.need('ex_src', 'csv'): return
        try:
            count, candidates, size = extract_csv(Path(self.val('ex_src')), Path(self.val('csv')))
            self.log_msg(f'Ekspor selesai: {count} segmen; {candidates} kandidat teks; DCT {size:,} byte.\nCSV: {self.val("csv")}')
        except Exception as e: self.log_msg('GAGAL ekspor: ' + str(e))

    def do_import(self):
        if not self.need('ex_src', 'csv', 'im_out'): return
        try:
            changed, skipped, size, md5 = import_csv(Path(self.val('ex_src')), Path(self.val('csv')), Path(self.val('im_out')), 'cp1252')
            self.log_msg(f'Impor selesai: {changed} diubah, {skipped} dilewati; ukuran {size:,} byte; MD5 {md5}\nOutput: {self.val("im_out")}')
        except Exception as e: self.log_msg('IMpor dibatalkan: ' + str(e))

    def do_patch(self):
        if not self.need('zip_src', 'entry', 'zip_dct', 'zip_out'): return
        try:
            size, md5 = patch_zip(Path(self.val('zip_src')), self.val('entry'), Path(self.val('zip_dct')), Path(self.val('zip_out')))
            self.log_msg(f'Patch ZIP selesai dan tervalidasi. Ukuran {size:,} byte; MD5 {md5}\nOutput: {self.val("zip_out")}')
        except Exception as e: self.log_msg('GAGAL patch ZIP: ' + str(e))

if __name__ == '__main__':
    SafeTranslatorApp().run()
