"""SnapMark optional Translation plugin 0.1.5; source-language auto detection.

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
from snapmark.i18n import plugin_gettext
from snapmark.stream_preview_c3 import StreamingPreview

def _(message):
    return plugin_gettext('translation', message, Path(__file__).resolve().parent)

from gi.repository import Adw, Gio, GLib, Gtk, Pango

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(__name__ + '_runtime', ROOT / 'runtime_client.py')
if spec is None or spec.loader is None:
    raise RuntimeError('Translation runtime client missing')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
config_spec = importlib.util.spec_from_file_location(__name__ + '_settings_c2e', ROOT / 'settings_c2e.py')
if config_spec is None or config_spec.loader is None:
    raise RuntimeError('Missing Translation C2-E settings')
config_c2e = importlib.util.module_from_spec(config_spec)
config_spec.loader.exec_module(config_c2e)
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
            previous = {}
            try:
                previous = json.loads(path.read_text('utf-8'))
            except (OSError, ValueError):
                pass
            if not isinstance(previous, dict):
                previous = {}
            previous.update({'target_language': target, 'model': model})
            json.dump(previous, stream, ensure_ascii=False, indent=2)
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
        self.preview = None
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
        model_icon.set_tooltip_text(_('Translation model'))
        header.append(model_icon)
        selector = Gtk.DropDown.new_from_strings([''])
        selector.set_sensitive(False)
        selector.set_hexpand(False)
        selector.set_size_request(110, -1)
        selector.set_tooltip_text(_('Registered translation model'))
        selector.connect('notify::selected', self._model_changed)
        self.model_dropdown = selector
        header.append(selector)
        language_icon = Gtk.Image.new_from_icon_name('preferences-desktop-locale-symbolic')
        language_icon.set_tooltip_text(_('Target language; source detected automatically'))
        header.append(language_icon)
        dropdown = Gtk.DropDown.new_from_strings([_(name) for name, _code in LANGUAGES])
        dropdown.set_selected([code for _label, code in LANGUAGES].index(self.target))
        dropdown.set_hexpand(False)
        dropdown.set_size_request(138, -1)
        dropdown.set_tooltip_text(_('Select target language'))
        dropdown.connect('notify::selected', self._target_changed)
        header.append(dropdown)
        # Grow into spare header space so Translate stays at the far-right edge.
        # Leave the dropdowns at their compact, fixed requested sizes.
        translate_spacer = Gtk.Box()
        translate_spacer.set_hexpand(True)
        header.append(translate_spacer)
        run = Gtk.Button(label='Translate')
        run.set_label(_('Translate'))
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
        result_stack = Gtk.Stack()
        result_stack.set_vexpand(True)
        result_stack.add_named(scroll, 'result')
        self.preview = StreamingPreview(result_stack)
        result_stack.set_visible_child_name('result')
        root.append(result_stack)
        self.textview = tv

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions.set_homogeneous(False)
        actions.set_halign(Gtk.Align.FILL)
        actions.set_hexpand(True)
        actions.set_valign(Gtk.Align.END)
        self.timer = Gtk.Label(label='Time: Not run')
        self.timer.set_label(_('Time: Not run'))
        self.timer.set_tooltip_text(_('Elapsed time for translation'))
        actions.append(self.timer)
        right_spacer = Gtk.Box()
        right_spacer.set_hexpand(True)
        actions.append(right_spacer)
        for label, callback in (
            ('Clear translation', self.clear_translation),
            ('Copy text', self.copy_text),
            ('Save as TXT', self.save_text),
        ):
            button = Gtk.Button(label=_(label))
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
            self.timer.set_text(_('Time: {seconds:.2f} s').format(seconds=time.perf_counter() - self.started_at))
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
        dialog = Adw.AlertDialog(heading=_('Translation unavailable'), body=str(message))
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

    def build_preferences(self, _editor):
        """Optional per-model presets, sampling, and safe streaming controls."""
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title=_('Translation prompt'),
            description=_('The translation instructions can be edited. Technical placeholder validation is always enforced.'))
        page.add(group)
        model_name = self.selected_model or '__default__'
        profile = config_c2e.read_profile(model_name)
        row = Adw.ActionRow(title=_('Preset'))
        presets = list(config_c2e.PRESETS) + ['Custom']
        selection = Gtk.DropDown.new_from_strings([_(name) for name in presets])
        selection.set_valign(Gtk.Align.CENTER)
        selection.set_selected(presets.index(profile['preset']))
        row.add_suffix(selection)
        group.add(row)
        prompt_view = Gtk.TextView()
        prompt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        prompt_view.set_top_margin(10)
        prompt_view.set_bottom_margin(10)
        prompt_view.set_left_margin(10)
        prompt_view.set_right_margin(10)
        prompt_view.get_buffer().set_text(profile['prompt'])
        scroller = Gtk.ScrolledWindow()
        scroller.set_min_content_height(150)
        scroller.set_child(prompt_view)
        group.add(scroller)
        def use_preset(drop, _pspec):
            name = presets[drop.get_selected()]
            if name in config_c2e.PRESETS:
                prompt_view.get_buffer().set_text(config_c2e.PRESETS[name])
        selection.connect('notify::selected', use_preset)
        params = Adw.PreferencesGroup(title=_('Inference parameters'),
            description=_('Preferences are saved per translation model. Unsupported reasoning switches are not sent to Runtime.'))
        page.add(params)
        temperature_row = Adw.ActionRow(title=_('Temperature'), subtitle=_('0.0 keeps the existing deterministic default'))
        temperature = Gtk.SpinButton.new_with_range(0.0, 1.0, 0.1)
        temperature.set_digits(1)
        temperature.set_value(profile['temperature'])
        temperature.set_valign(Gtk.Align.CENTER)
        temperature_row.add_suffix(temperature)
        params.add(temperature_row)
        stream = Adw.SwitchRow(title=_('Streaming preview'),
            subtitle=_('Preview is not selectable or saveable; the final text is displayed only after technical validation'))
        stream.set_active(profile['streaming'])
        params.add(stream)
        tokens_row = Adw.ActionRow(title=_('Maximum output tokens'))
        options = ['Model default', '1024', '2048', '4096', '8192']
        token_selector = Gtk.DropDown.new_from_strings([_(name) if name == 'Model default' else name for name in options])
        token_selector.set_valign(Gtk.Align.CENTER)
        current = str(profile['max_tokens']) if profile['max_tokens'] else 'Model default'
        token_selector.set_selected(options.index(current))
        tokens_row.add_suffix(token_selector)
        params.add(tokens_row)
        reason = Adw.ActionRow(title=_('Thinking mode'),
            subtitle=_('Automatic (model default). Explicit controls require verified Runtime/model support.'))
        params.add(reason)
        save_row = Adw.ActionRow(title=_('Save model settings'),
            subtitle=_('Does not install models or change Local AI Runtime.'))
        save_button = Gtk.Button(label=_('Save settings'))
        save_button.add_css_class('suggested-action')
        save_button.set_valign(Gtk.Align.CENTER)
        save_row.add_suffix(save_button)
        params.add(save_row)
        def do_save(_button):
            buf = prompt_view.get_buffer()
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            try:
                config_c2e.save_profile(model_name, {
                    'preset': presets[selection.get_selected()],
                    'prompt': text,
                    'temperature': temperature.get_value(),
                    'streaming': stream.get_active(),
                    'max_tokens': None if token_selector.get_selected() == 0 else int(options[token_selector.get_selected()]),
                    'thinking': 'auto',
                })
                self.editor._notice(_('Translation settings saved'))
            except (OSError, ValueError) as exc:
                self.editor._notice('Cannot save translation settings: ' + str(exc))
        save_button.connect('clicked', do_save)
        return page

    def _partial(self, generation, text):
        if generation == self.generation and self.running and self.preview is not None:
            # Unverified content stays outside the editable/saveable result.
            # Never reveal guarded technical placeholders even mid-token.
            import re
            safe = re.sub(r'\[\[SMTECH_\d{0,5}\]?\]?', '[protected]', text)
            self.preview.set_text(safe)
            self.preview.set_visible(True)
            self._status(_('Unverified streaming preview: '))
        return False

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
        profile = config_c2e.read_profile(model_id)
        if self.preview is not None:
            self.preview.start() if profile.get('streaming') else self.preview.set_visible(False)
        self.started_at = time.perf_counter()
        self.timer.set_text(_('Time: {seconds:.2f} s').format(seconds=0.0))
        GLib.timeout_add(100, self._tick, generation)
        self.translate_button.set_sensitive(False)
        self._status(_('Translating locally; identifying source language…'))
        before = self._text()

        def job():
            try:
                def partial(value):
                    GLib.idle_add(self._partial, generation, value)
                translation, model = translate(source, target, model_id=model_id,
                                               settings=profile, on_partial=partial)
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
        if self.preview is not None:
            self.preview.set_visible(False)
        self.started_at = None
        self.timer.set_text(_('Time: {seconds:.2f} s').format(seconds=elapsed))
        self.translate_button.set_sensitive(True)
        if error:
            self._error(error)
            return False
        if self._text() != previous or self.source_getter() != source or self.target != target or self.selected_model != model_id:
            self._status(_('Source, target language, or translation was edited during inference; stale result discarded'), notify=True)
            return False
        self.textview.get_buffer().set_text(result)
        self._status(_('Translated into {target} with {model}').format(target=target, model=model), notify=True)
        return False

    def clear_translation(self):
        if not self._text():
            return
        dialog = Adw.AlertDialog(heading=_('Clear translation?'),
                                 body=_('This deletes the translation and your edits in the right pane only.'))
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
        dialog = Gtk.FileDialog(title=_('Save translation'))
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
    host.register_preferences_page('translation', 'Translation', controller.build_preferences)
    host.register_toolbar_action('translation', 'Translation', lambda: None)
