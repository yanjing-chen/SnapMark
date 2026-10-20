"""SnapMark optional Translation plugin 0.1.4; source-language auto detection.

GTK4 on main thread. Only explicit Translate sends locally editable OCR text
into Local AI Runtime (127.0.0.1:8111). No automatic inference or downloads.
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
import threading
from pathlib import Path
from gi.repository import Adw, Gio, GLib, Gtk, Pango

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(__name__ + '_runtime', ROOT / 'runtime_client.py')
if spec is None or spec.loader is None:
    raise RuntimeError('Translation runtime client missing')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
translate = module.translate
list_translation_models = module.list_translation_models

LANGUAGES = (
    ('Dutch (Nederlands)', 'Dutch'),
    ('Chinese (中文)', 'Simplified Chinese'),
    ('English', 'English'),
    ('German (Deutsch)', 'German'),
    ('French (Français)', 'French'),
    ('Spanish (Español)', 'Spanish'),
    ('Japanese (日本語)', 'Japanese'),
    ('Korean (한국어)', 'Korean'),
    ('Portuguese (Português)', 'Portuguese'),
    ('Italian (Italiano)', 'Italian'),
    ('Russian (Русский)', 'Russian'),
    ('Arabic (العربية)', 'Arabic'),
)


def _settings_file():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'snapmark' / 'translation.json'


def _saved_settings():
    state = {'target_language': 'Dutch', 'model': ''}
    try:
        obj = json.loads(_settings_file().read_text('utf-8'))
        if isinstance(obj, dict):
            if obj.get('target_language') in [code for _label, code in LANGUAGES]:
                state['target_language'] = obj['target_language']
            if isinstance(obj.get('model'), str):
                state['model'] = obj['model']
    except (OSError, ValueError):
        pass
    return state


def _save_settings(target, model):
    path = _settings_file()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         prefix='.translation-', delete=False) as stream:
            tmp = Path(stream.name)
            json.dump({'target_language': target, 'model': model}, stream)
            stream.write('\n')
        tmp.chmod(0o600)
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


class TranslationController:
    def __init__(self, editor, source_getter):
        self.editor = editor
        self.source_getter = source_getter
        saved = _saved_settings()
        self.target = saved['target_language']
        self.selected_model = saved['model']
        self.model_ids = []
        self.model_dropdown = None
        self.timer = None
        self.started_at = None
        self._catalog_generation = 0
        self.textview = None
        self.status = None
        self.translate_button = None
        self.generation = 0
        self.running = False
        editor.connect('close-request', self._on_close)

    def _on_close(self, *_args):
        self.generation += 1
        return False

    def build_panel(self, _editor):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        for setter in ('set_margin_top', 'set_margin_bottom', 'set_margin_start', 'set_margin_end'):
            getattr(root, setter)(8)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_hexpand(True)
        model_icon = Gtk.Image.new_from_icon_name('accessories-dictionary-symbolic')
        model_icon.set_tooltip_text('Translation model')
        header.append(model_icon)
        selector = Gtk.DropDown.new_from_strings([''])
        selector.set_sensitive(False)
        selector.set_hexpand(False)
        selector.set_size_request(110, -1)
        selector.set_tooltip_text('Registered translation model')
        selector.connect('notify::selected', self._model_changed)
        self.model_dropdown = selector
        header.append(selector)
        language_icon = Gtk.Image.new_from_icon_name('preferences-desktop-locale-symbolic')
        language_icon.set_tooltip_text('Target language; source detected automatically')
        header.append(language_icon)
        dropdown = Gtk.DropDown.new_from_strings([name for name, _code in LANGUAGES])
        dropdown.set_selected([code for _label, code in LANGUAGES].index(self.target))
        dropdown.set_hexpand(False)
        dropdown.set_size_request(138, -1)
        dropdown.set_tooltip_text('Select target language')
        dropdown.connect('notify::selected', self._target_changed)
        header.append(dropdown)
        # Grow into spare header space so Translate stays at the far-right edge.
        # Leave the dropdowns at their compact, fixed requested sizes.
        translate_spacer = Gtk.Box()
        translate_spacer.set_hexpand(True)
        header.append(translate_spacer)
        run = Gtk.Button(label='Translate')
        run.set_halign(Gtk.Align.END)
        run.set_hexpand(False)
        run.add_css_class('suggested-action')
        run.connect('clicked', self._run)
        self.translate_button = run
        header.append(run)
        root.append(header)

        self.status = Gtk.Label(label='', xalign=0)
        self.status.add_css_class('dim-label')
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        root.append(self.status)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(110)
        scroll.set_vexpand(True)
        tv = Gtk.TextView()
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        for setter in ('set_top_margin', 'set_bottom_margin', 'set_left_margin', 'set_right_margin'):
            getattr(tv, setter)(8)
        scroll.set_child(tv)
        root.append(scroll)
        self.textview = tv

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions.set_homogeneous(False)
        actions.set_halign(Gtk.Align.FILL)
        actions.set_hexpand(True)
        actions.set_valign(Gtk.Align.END)
        self.timer = Gtk.Label(label='Time: Not run')
        self.timer.set_tooltip_text('Elapsed time for translation')
        actions.append(self.timer)
        right_spacer = Gtk.Box()
        right_spacer.set_hexpand(True)
        actions.append(right_spacer)
        for label, callback in (
            ('Clear translation', self.clear_translation),
            ('Copy text', self.copy_text),
            ('Save as TXT', self.save_text),
        ):
            button = Gtk.Button(label=label)
            button.connect('clicked', lambda _button, cb=callback: cb())
            actions.append(button)
        root.append(actions)
        self._refresh_models()
        return root

    def _refresh_models(self):
        self._catalog_generation += 1
        generation = self._catalog_generation
        def job():
            try:
                result = list_translation_models()
                error = None
            except Exception as exc:
                result, error = [], str(exc)
            GLib.idle_add(self._apply_models, result, generation, error)
        threading.Thread(target=job, daemon=True).start()

    def _apply_models(self, names, generation, failure):
        if generation != self._catalog_generation:
            return False
        self.model_ids = names
        self.model_dropdown.set_model(Gtk.StringList.new(names or ['']))
        self.model_dropdown.set_sensitive(bool(names))
        if names:
            index = names.index(self.selected_model) if self.selected_model in names else 0
            self.model_dropdown.set_selected(index)
            self.selected_model = names[index]
        else:
            self.selected_model = ''
            self._status('')
        return False

    def _model_changed(self, dropdown, _pspec):
        index = dropdown.get_selected()
        if index >= len(self.model_ids):
            return
        self.selected_model = self.model_ids[index]
        try:
            _save_settings(self.target, self.selected_model)
        except OSError as exc:
            self._status(f'Cannot save translation model: {exc}', notify=True)

    def _tick(self, generation):
        if generation != self.generation or not self.running or self.started_at is None:
            return False
        if self.timer:
            self.timer.set_text(f'Time: {time.perf_counter() - self.started_at:.2f} s')
        return True

    def _text(self):
        buffer = self.textview.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)

    def _status(self, message, *, notify=False):
        if self.status is not None:
            self.status.set_label(message)
            self.status.set_tooltip_text(message)
        if notify:
            self.editor._notice(message)

    def _error(self, message):
        self._status('Translation failed: ' + str(message), notify=True)
        dialog = Adw.AlertDialog(heading='Translation unavailable', body=str(message))
        dialog.add_response('ok', 'OK')
        dialog.set_default_response('ok')
        dialog.present(self.editor)

    def _target_changed(self, dropdown, _pspec):
        choice = dropdown.get_selected()
        if choice >= len(LANGUAGES):
            return
        self.target = LANGUAGES[choice][1]
        try:
            _save_settings(self.target, self.selected_model)
        except OSError as exc:
            self._status(f'Cannot save target language: {exc}', notify=True)

    def _run(self, _button):
        if self.running:
            return
        source = self.source_getter()
        if not isinstance(source, str) or not source.strip():
            self._error('OCR text is empty. Run OCR or type text into the left pane first.')
            return
        if not self.selected_model or self.selected_model not in self.model_ids:
            self._error('No installed translation model is registered. Use Preferences → AI Runtime.')
            return
        self.running = True
        self.generation += 1
        generation = self.generation
        target = self.target
        model_id = self.selected_model
        self.started_at = time.perf_counter()
        self.timer.set_text('Time: 0.00 s')
        GLib.timeout_add(100, self._tick, generation)
        self.translate_button.set_sensitive(False)
        self._status('Translating locally; identifying source language…')
        before = self._text()

        def job():
            try:
                translation, model = translate(source, target, model_id=model_id)
                error = None
            except Exception as exc:
                translation, model, error = None, None, str(exc)
            elapsed = time.perf_counter() - self.started_at
            GLib.idle_add(self._complete, generation, translation, model, error, before, source, target, model_id, elapsed)

        threading.Thread(target=job, daemon=True).start()

    def _complete(self, generation, result, model, error, previous, source, target, model_id, elapsed):
        if generation != self.generation:
            return False
        self.running = False
        self.started_at = None
        self.timer.set_text(f'Time: {elapsed:.2f} s')
        self.translate_button.set_sensitive(True)
        if error:
            self._error(error)
            return False
        if self._text() != previous or self.source_getter() != source or self.target != target or self.selected_model != model_id:
            self._status('Source, target language, or translation was edited during inference; stale result discarded', notify=True)
            return False
        self.textview.get_buffer().set_text(result)
        self._status(f'Translated into {target} with {model}', notify=True)
        return False

    def clear_translation(self):
        if not self._text():
            return
        dialog = Adw.AlertDialog(heading='Clear translation?',
                                 body='This deletes the translation and your edits in the right pane only.')
        dialog.add_response('cancel', 'Keep translation')
        dialog.add_response('clear', 'Clear translation')
        dialog.set_response_appearance('clear', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', lambda _dialog, response:
                       self.textview.get_buffer().set_text('') if response == 'clear' else None)
        dialog.present(self.editor)

    def copy_text(self):
        text = self._text()
        if not text:
            self._status('No translation to copy')
            return
        self.editor.get_display().get_clipboard().set(text)
        self._status('Translation copied')

    def save_text(self):
        if not self._text():
            self._status('No translation to save')
            return
        dialog = Gtk.FileDialog(title='Save translation')
        name = self.editor.filename.stem if self.editor.filename else 'screenshot'
        dialog.set_initial_name(name + '-translation.txt')
        dialog.save(self.editor, None, self._save_done)

    def _save_done(self, dialog, response):
        try:
            target = dialog.save_finish(response)
            if target:
                target.replace_contents(self._text().encode('utf-8'), None, False,
                    Gio.FileCreateFlags.REPLACE_DESTINATION, None)
                self._status('Translation saved')
        except GLib.Error as exc:
            if not exc.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                self._status(f'Cannot save translation: {exc.message}', notify=True)
        except Exception as exc:
            self._status(f'Cannot save translation: {exc}', notify=True)


def register(host):
    getter = host.get_text_provider('ocr')
    if not callable(getter):
        raise RuntimeError('Translation needs the active OCR text provider')
    controller = TranslationController(host.editor, getter)
    host.register_result_panel('translation', 'Translation', controller.build_panel)
    host.register_toolbar_action('translation', 'Translation', lambda: None)
