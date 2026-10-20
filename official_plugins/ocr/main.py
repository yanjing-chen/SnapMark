"""SnapMark official OCR plugin 0.1.9, official PP-OCRv6 tiny ONNX models.

Setup is available only through explicit Preferences confirmation; it never
writes to Local AI Runtime or system Python. Translation is an optional separate SnapMark plugin.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import importlib.util

from gi.repository import Adw, Gio, GLib, Gtk, Pango

ROOT = Path(__file__).resolve().parent
MODELS = json.loads((ROOT / 'models.json').read_text(encoding='utf-8'))
MODEL_LABELS = tuple(MODELS)
_spec = importlib.util.spec_from_file_location(__name__ + '_catalog', ROOT / 'catalog.py')
_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_catalog)
lightweight_available = _catalog.lightweight_available
fetch_runtime_models = _catalog.fetch_runtime_models
_setup_spec = importlib.util.spec_from_file_location(__name__ + '_manager_c2b', ROOT / 'manager_c2b.py')
_setup = importlib.util.module_from_spec(_setup_spec)
_setup_spec.loader.exec_module(_setup)
_onnx_spec = importlib.util.spec_from_file_location(__name__ + '_onnx_c2', ROOT / 'onnx_c2.py')
_onnx = importlib.util.module_from_spec(_onnx_spec)
_onnx_spec.loader.exec_module(_onnx)


def _config_path():
    base = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return base / 'snapmark' / 'ocr.json'


def _model_root():
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    return data / 'snapmark' / 'ocr-models'


def _default_settings():
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    return {
        'python': str(data / 'snapmark' / 'ocr-venv' / 'bin' / 'python'),
        'models_root': str(_model_root()),
        'model': 'PP-OCRv6 small',
        'mode': 'lightweight',
        'registered_lightweight': [],
    }


def _read_settings():
    state = _default_settings()
    try:
        saved = json.loads(_config_path().read_text(encoding='utf-8'))
        if isinstance(saved, dict):
            for key in ('python', 'models_root', 'model', 'mode'):
                if isinstance(saved.get(key), str) and saved[key]:
                    state[key] = saved[key]
            entries = saved.get('registered_lightweight')
            if isinstance(entries, list):
                state['registered_lightweight'] = [x for x in entries if isinstance(x, str) and x in MODELS]
    except (ValueError, OSError):
        pass
    if state['mode'] not in ('lightweight', 'high_performance'):
        state['mode'] = 'lightweight'
    if not isinstance(state['model'], str):
        state['model'] = ''
    return state


def _atomic_save(data):
    path = _config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix='.ocr-',
                                     encoding='utf-8', delete=False) as f:
        temporary = Path(f.name)
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class OCRController:
    def __init__(self, editor):
        self.editor = editor
        self.settings = _read_settings()
        self.textview = None
        self.status = None
        self.timer = None
        self.model_dropdown = None
        self.model_ids = []
        self._catalog_generation = 0
        self.run_button = None
        self.started_at = None
        self.running = False
        self.generation = 0
        self.proc = None
        self.proc_lock = threading.Lock()
        self.source_image = None
        editor.connect('close-request', self._on_close)

    def _on_close(self, *_args):
        self.cancel()
        return False

    def build_panel(self, _editor):
        """OCR selection and Run above, editable text, elapsed time + 3 actions below."""
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        for setter in ('set_margin_top', 'set_margin_bottom', 'set_margin_start', 'set_margin_end'):
            getattr(root, setter)(8)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        model_icon = Gtk.Image.new_from_icon_name('edit-find-symbolic')
        model_icon.set_tooltip_text('OCR model')
        header.append(model_icon)
        combo = Gtk.DropDown.new_from_strings([''])
        combo.set_sensitive(False)
        combo.set_hexpand(False)
        combo.set_halign(Gtk.Align.START)
        combo.set_size_request(152, -1)
        combo.set_tooltip_text('Select registered OCR model (configured in Preferences)')
        combo.connect('notify::selected', self._model_selected)
        self.model_dropdown = combo
        header.append(combo)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)
        run = Gtk.Button(label='Run OCR')
        run.add_css_class('suggested-action')
        run.connect('clicked', lambda _button: self.run_whole())
        run.set_tooltip_text('OCR the complete original screenshot, without annotations')
        self.run_button = run
        header.append(run)
        root.append(header)

        self.status = Gtk.Label(label='', xalign=0)
        self.status.add_css_class('dim-label')
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        root.append(self.status)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_min_content_height(110)
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
        self.timer.set_tooltip_text('Elapsed time for current or most recent OCR')
        actions.append(self.timer)
        right_spacer = Gtk.Box()
        right_spacer.set_hexpand(True)
        actions.append(right_spacer)
        for caption, action in (
            ('Copy text', self.copy_text),
            ('Clear text', self.clear_text),
            ('Save as TXT', self.save_text),
        ):
            button = Gtk.Button(label=caption)
            button.connect('clicked', lambda _button, cb=action: cb())
            actions.append(button)
        root.append(actions)
        self._refresh_models()
        return root

    def _apply_models(self, items, generation, failure=None):
        if generation != self._catalog_generation or self.model_dropdown is None:
            return False
        self.model_ids = items
        self.model_dropdown.set_model(Gtk.StringList.new(items or ['']))
        self.model_dropdown.set_sensitive(bool(items))
        if items:
            selected = self.settings.get('model')
            self.model_dropdown.set_selected(items.index(selected) if selected in items else 0)
            self.settings['model'] = items[self.model_dropdown.get_selected()]
        else:
            self.settings['model'] = ''
            self._status('', toast=False)
        return False

    def _refresh_models(self):
        self._catalog_generation += 1
        generation = self._catalog_generation
        if self.settings['mode'] == 'lightweight':
            items = list(_onnx.available_models())
            items.extend(lightweight_available(self.settings, MODELS))
            self._apply_models(items, generation)
            return
        def job():
            try:
                items = fetch_runtime_models('ocr')
                error = None
            except Exception as exc:
                items, error = [], 'Runtime OCR catalog unavailable: ' + str(exc)
            GLib.idle_add(self._apply_models, items, generation, error)
        threading.Thread(target=job, daemon=True).start()

    def build_preferences(self, _editor):
        """Compact mode-switched OCR preferences, no local Paddle installation.

        Hosted ONNX runtime and user-approved models are a separate distribution
        track. Until its engine/model integration is verified, the download
        control stays unavailable rather than silently installing Paddle locally.
        """
        page = Adw.PreferencesPage()
        intro = Adw.PreferencesGroup(title='OCR', description=(
            'Choose lightweight OCR or higher-performance OCR through Local AI Runtime. '
            'Model installation and registration belong in Preferences, not the editor.'))
        page.add(intro)

        switch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        switch.add_css_class('linked')
        switch.set_hexpand(True)
        light_button = Gtk.ToggleButton(label='Lightweight · PP-OCR')
        advanced_button = Gtk.ToggleButton(label='Advanced · Local AI Runtime')
        advanced_button.set_group(light_button)
        for button in (light_button, advanced_button):
            button.set_hexpand(True)
            switch.append(button)
        intro.add(switch)

        lightweight = Adw.PreferencesGroup(title='Lightweight engine', description=(
            'PP-OCRv6 tiny models downloaded exclusively from PaddlePaddle official sources. '
            'No Python, PaddlePaddle or local compilation is required.'))
        page.add(lightweight)
        language = Adw.ActionRow(title='Language', subtitle='Automatically recognized by the selected model')
        language.add_suffix(Gtk.Label(label='Auto'))
        lightweight.add(language)
        inference = Adw.ActionRow(title='Inference', subtitle='CPU · packaged engine (GitHub Actions)')
        lightweight.add(inference)
        registered = Adw.ActionRow(title='Models')
        lightweight.add(registered)
        online_row = Adw.ActionRow(title='Official model catalog', subtitle=(
            'SnapMark-maintained list · all weights downloaded from PaddlePaddle only'))
        refresh = Gtk.Button(label='Refresh models')
        refresh.set_valign(Gtk.Align.CENTER)
        online_row.add_suffix(refresh)
        lightweight.add(online_row)
        select_model = Adw.ComboRow(title='Available OCR models')
        lightweight.add(select_model)
        models_row = Adw.ActionRow(title='Selected model')
        download = Gtk.Button(label='Download official models…')
        download.set_valign(Gtk.Align.CENTER)
        models_row.add_suffix(download)
        lightweight.add(models_row)
        catalog_entries = []
        busy = False

        def redraw_catalog():
            nonlocal catalog_entries
            catalog_entries = _onnx.catalog_models()
            old_label = selected_label() if select_model.get_model() and select_model.get_model().get_n_items() else _onnx.LABEL
            select_model.set_model(Gtk.StringList.new([m['label'] for m in catalog_entries]))
            labels = [m['label'] for m in catalog_entries]
            select_model.set_selected(labels.index(old_label) if old_label in labels else 0)
            refresh_status()

        def selected_label():
            index = select_model.get_selected()
            if index >= len(catalog_entries):
                return None
            return catalog_entries[index]['label']

        def refresh_status(*_args):
            model = catalog_entries[select_model.get_selected()] if select_model.get_selected() < len(catalog_entries) else None
            if model is None:
                models_row.set_subtitle('No official models in catalog')
                download.set_sensitive(False)
                return
            if not _onnx.model_compatible(model):
                models_row.set_subtitle('Requires a newer engine or model verification · not available for download')
                download.set_sensitive(False)
            elif _onnx.installed_label(model['label']):
                models_row.set_subtitle('Installed · official PaddlePaddle · SHA256 verified')
                download.set_sensitive(False)
            elif _onnx.engine_ready():
                models_row.set_subtitle('Ready to download from PaddlePaddle official repositories')
                download.set_sensitive(not busy)
            else:
                models_row.set_subtitle('Prebuilt CPU engine not installed · keep using OCR 0.1.8')
                download.set_sensitive(False)
        select_model.connect('notify::selected', refresh_status)

        def refresh_clicked(_button):
            nonlocal busy
            if busy:return
            busy = True
            refresh.set_sensitive(False)
            download.set_sensitive(False)
            online_row.set_subtitle('Refreshing SnapMark catalog…')
            def job():
                try:
                    catalog = _onnx.refresh_catalog()
                    message, error = f"Catalog refreshed · {len(catalog['models'])} official models", None
                except Exception as exc:
                    message,error=None,str(exc)
                def done():
                    nonlocal busy
                    busy = False
                    refresh.set_sensitive(True)
                    if error:
                        online_row.set_subtitle('Offline catalog retained · refresh failed')
                        self.editor._notice('Official OCR catalog: '+error[:230])
                    else:
                        online_row.set_subtitle(message)
                    redraw_catalog()
                    return False
                GLib.idle_add(done)
            threading.Thread(target=job,daemon=True).start()
        refresh.connect('clicked', refresh_clicked)

        def install_onnx_clicked(_button):
            label = selected_label()
            if not label or busy:return
            model = next((m for m in catalog_entries if m['label'] == label), None)
            if model is None or not _onnx.model_compatible(model):return
            confirm = Adw.AlertDialog(
                heading='Download official PaddlePaddle OCR model?',
                body=('Model: '+label+'\n\nDownload only from PaddlePaddle official Hugging Face '
                      'and PaddleOCR GitHub, with file verification. No existing model, '
                      'OCR engine, or Local AI Runtime will be overwritten.'))
            confirm.add_response('cancel','Cancel')
            confirm.add_response('confirm','Download')
            confirm.set_default_response('cancel')
            confirm.set_close_response('cancel')
            def responded(_dialog, response):
                nonlocal busy
                if response!='confirm' or busy:return
                busy=True
                refresh.set_sensitive(False)
                download.set_sensitive(False)
                models_row.set_subtitle('Downloading and verifying official models…')
                def job():
                    try:
                        message,error=_onnx.install_label(label,confirmed=True),None
                    except Exception as exc:
                        message,error=None,str(exc)
                    def done():
                        nonlocal busy
                        busy=False
                        refresh.set_sensitive(True)
                        refresh_status()
                        if error:
                            self.editor._notice('Official OCR download: '+error[:250])
                        else:
                            proposed=dict(self.settings,model=label)
                            try:
                                _atomic_save(proposed)
                                self.settings=proposed
                            except OSError as exc:
                                self.editor._notice('Cannot save OCR selection: '+str(exc))
                            self._refresh_models()
                            self.editor._notice(message)
                        return False
                    GLib.idle_add(done)
                threading.Thread(target=job,daemon=True).start()
            confirm.connect('response',responded)
            confirm.present(download.get_root())
        download.connect('clicked',install_onnx_clicked)
        redraw_catalog()
        test_light = Gtk.Button(label='Test OCR')
        test_light.add_css_class('suggested-action')
        test_light.set_valign(Gtk.Align.CENTER)
        light_test_row = Adw.ActionRow(title='Test OCR', subtitle='Recognize the current screenshot')
        light_test_row.add_suffix(test_light)
        lightweight.add(light_test_row)
        test_light.connect('clicked', lambda _button: self.editor._notice(
            'Open the OCR panel, select PP-OCRv6 tiny (ONNX CPU), then click Run OCR'))

        # Keep the standard OCR page compact. Registration of existing legacy
        # lightweight model folders remains available behind a collapsed row,
        # rather than installing PaddlePaddle on the user's machine.
        existing = Adw.ExpanderRow(title='Manage previously installed OCR models',
            subtitle='Optional · register existing local model files')
        lightweight.add(existing)
        existing_python = Adw.EntryRow(title='Existing Python interpreter')
        existing_python.set_text(self.settings['python'])
        existing.add_row(existing_python)
        existing_models = Adw.EntryRow(title='Existing model directory')
        existing_models.set_text(self.settings['models_root'])
        existing.add_row(existing_models)
        existing_choice = Adw.ComboRow(title='Existing model')
        existing_choice.set_model(Gtk.StringList.new(list(MODEL_LABELS)))
        existing.add_row(existing_choice)

        registration_status = Adw.ActionRow(title='Registered lightweight OCR models',
            subtitle=', '.join(self.settings['registered_lightweight']) or 'None')
        existing.add_row(registration_status)
        register_existing = Gtk.Button(label='Register selected installed model')
        register_existing.set_valign(Gtk.Align.CENTER)
        register_row = Adw.ActionRow(title='Register this existing model')
        register_row.add_suffix(register_existing)
        existing.add_row(register_row)
        unregister_existing = Gtk.Button(label='Unregister selected model')
        unregister_existing.set_valign(Gtk.Align.CENTER)
        unregister_row = Adw.ActionRow(title='Remove model registration (keep files)')
        unregister_row.add_suffix(unregister_existing)
        existing.add_row(unregister_row)

        def change_existing_registration(add):
            try:
                candidate = dict(self.settings)
                candidate['python'] = existing_python.get_text().strip()
                candidate['models_root'] = existing_models.get_text().strip()
                if not (Path(candidate['python']).is_absolute()
                        and Path(candidate['models_root']).is_absolute()):
                    raise ValueError('Python and model paths must be absolute')
                name = MODEL_LABELS[existing_choice.get_selected()]
                available = lightweight_available(
                    dict(candidate, registered_lightweight=[name]), MODELS)
                if add and name not in available:
                    raise ValueError('Existing model files or OCR environment not ready')
                old = candidate['registered_lightweight']
                candidate['registered_lightweight'] = (
                    list(dict.fromkeys([*old, name])) if add else
                    [item for item in old if item != name])
                _atomic_save(candidate)
                self.settings = candidate
                registration_status.set_subtitle(
                    ', '.join(candidate['registered_lightweight']) or 'None')
                self._refresh_models()
                refresh_registered()
            except (OSError, ValueError, IndexError) as exc:
                self.editor._notice('OCR model registration: ' + str(exc))

        register_existing.connect('clicked',
            lambda _button: change_existing_registration(True))
        unregister_existing.connect('clicked',
            lambda _button: change_existing_registration(False))

        advanced = Adw.PreferencesGroup(title='Runtime connection', description=(
            'High-performance Runtime OCR uses your existing Local AI Runtime. '
            'Only installed models explicitly registered for OCR are eligible.'))
        page.add(advanced)
        endpoint = Adw.ActionRow(title='Endpoint', subtitle='http://127.0.0.1:8111')
        endpoint_state = Gtk.Label(label='Not checked')
        endpoint.add_suffix(endpoint_state)
        advanced.add(endpoint)
        runtime_model = Adw.ComboRow(title='Model', subtitle='Registered OCR models only')
        runtime_model.set_model(Gtk.StringList.new([]))
        advanced.add(runtime_model)
        check = Gtk.Button(label='Refresh')
        check.set_valign(Gtk.Align.CENTER)
        check_row = Adw.ActionRow(title='Refresh connection and registered models')
        check_row.add_suffix(check)
        advanced.add(check_row)
        acceleration = Adw.ActionRow(title='Acceleration', subtitle='Managed by Runtime · Auto / Vulkan / CUDA')
        advanced.add(acceleration)
        runtime_test = Gtk.Button(label='Test OCR')
        runtime_test.set_sensitive(False)
        runtime_test.set_tooltip_text('High-performance OCR inference is not yet implemented')
        runtime_test.add_css_class('suggested-action')
        runtime_test_row = Adw.ActionRow(title='Test OCR', subtitle='Available after Runtime image inference integration')
        runtime_test_row.add_suffix(runtime_test)
        advanced.add(runtime_test_row)

        def refresh_registered():
            names = list(_onnx.available_models())
            names.extend(lightweight_available(self.settings, MODELS))
            registered.set_subtitle(', '.join(names) if names else 'Not installed')

        def switch_mode():
            selected = 'lightweight' if light_button.get_active() else 'high_performance'
            lightweight.set_visible(selected == 'lightweight')
            advanced.set_visible(selected == 'high_performance')
            if self.settings['mode'] != selected:
                proposed = dict(self.settings, mode=selected)
                try:
                    _atomic_save(proposed)
                    self.settings = proposed
                    self._refresh_models()
                except OSError as exc:
                    self.editor._notice('Could not save OCR mode: ' + str(exc))
            refresh_registered()

        def on_mode_changed(button, _pspec):
            if button.get_active():
                switch_mode()
        light_button.connect('notify::active', on_mode_changed)
        advanced_button.connect('notify::active', on_mode_changed)

        def refresh_runtime(_button):
            check.set_sensitive(False)
            endpoint_state.set_text('Checking…')
            def job():
                try:
                    items = fetch_runtime_models('ocr')
                    error = None
                except Exception as exc:
                    items, error = [], str(exc)
                def done():
                    check.set_sensitive(True)
                    if error:
                        endpoint_state.set_text('Unavailable')
                        self.editor._notice('OCR Runtime catalog: ' + error[:160])
                    else:
                        endpoint_state.set_text('Connected')
                    runtime_model.set_model(Gtk.StringList.new(items))
                    return False
                GLib.idle_add(done)
            threading.Thread(target=job, daemon=True).start()
        check.connect('clicked', refresh_runtime)

        if self.settings['mode'] == 'lightweight':
            light_button.set_active(True)
        else:
            advanced_button.set_active(True)
        refresh_registered()
        switch_mode()
        return page

    def _model_selected(self, dropdown, _pspec):
        index = dropdown.get_selected()
        if index >= len(self.model_ids):
            return
        selected = self.model_ids[index]
        self.settings['model'] = selected
        try:
            _atomic_save(self.settings)
        except OSError as exc:
            self._status(f'Cannot save OCR model choice: {exc}')

    def _status(self, text, *, toast=False):
        message = str(text)
        if self.status is not None:
            self.status.set_text(message)
            self.status.set_tooltip_text(message)
        if toast or self.status is None:
            self.editor._notice(message)

    def _error_dialog(self, reason):
        """Make missing OCR dependencies discoverable even if result pane is hidden."""
        self._status(f'OCR unavailable: {reason}', toast=True)
        dialog = Adw.AlertDialog(
            heading='OCR is not ready',
            body=f'{reason}\n\nConfigure Preferences → OCR. No models will be downloaded automatically.',
        )
        dialog.add_response('ok', 'OK')
        dialog.set_default_response('ok')
        dialog.present(self.editor)

    def _check_ready(self):
        """Fast read-only preflight on the GTK thread (worker validates again)."""
        cfg = self.settings
        if cfg['model'] not in self.model_ids:
            return 'No installed OCR-registered model in the selected mode. Configure Preferences → OCR.'
        if cfg['mode'] == 'high_performance':
            return ('High-performance OCR execution is not yet integrated. '
                    'The OCR model catalog can be browsed now; no model will be run.')
        if cfg['model'] in _onnx.available_models():
            return None if _onnx.installed_label(cfg['model']) else 'Prebuilt ONNX OCR model is not installed'
        interpreter = Path(cfg['python']).expanduser()
        if not interpreter.is_absolute() or not interpreter.is_file() or not os.access(interpreter, os.X_OK):
            return f"OCR Python environment missing or not executable: {interpreter}"
        models = Path(cfg['models_root']).expanduser()
        if not models.is_absolute() or not models.is_dir():
            return f"OCR model directory missing: {models}"
        try:
            folders = MODELS[cfg['model']]
        except KeyError:
            return 'Unsupported OCR model selection'
        for name in folders:
            folder = models / name
            if not folder.is_dir() or not any(item.is_file() for item in folder.iterdir()):
                return f"Local OCR model is missing: {folder}"
        return None

    def _buffer(self):
        return self.textview.get_buffer()

    def _get_text(self):
        buf = self._buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    def run_whole(self):
        if self.running:
            self.cancel()
            return
        reason = self._check_ready()
        if reason:
            self._error_dialog(reason)
            return
        try:
            image = self.editor.original_png_for_ocr()
        except ValueError as exc:
            self._error_dialog(str(exc))
            return
        self._run(image)

    def on_toolbar(self):
        # The toolbar only toggles visibility; Run OCR inside the panel executes.
        return None

    def _tick(self, generation):
        if generation != self.generation or not self.running or self.started_at is None:
            return False
        if self.timer is not None:
            self.timer.set_text(f'Time: {time.perf_counter() - self.started_at:.2f} s')
        return True

    def _run(self, image):
        if self.running:
            self._status('OCR is already running', toast=True)
            return
        if self.textview is None or self.timer is None:
            self.editor._notice('OCR panel is not ready')
            return
        reason = self._check_ready()
        if reason:
            self._error_dialog(reason)
            return
        self.source_image = self.editor.pixbuf
        self.generation += 1
        generation = self.generation
        cfg = dict(self.settings)
        self.running = True
        self.started_at = time.perf_counter()
        self.run_button.set_label('Cancel OCR')
        self._status(f"Recognizing with {cfg['model']} (local CPU)…", toast=True)
        self.timer.set_text('Time: 0.00 s')
        GLib.timeout_add(100, self._tick, generation)

        def job():
            start = time.perf_counter()
            try:
                is_onnx = cfg['model'] in _onnx.available_models()
                if not is_onnx:
                    interpreter = Path(cfg['python']).expanduser()
                    if not interpreter.is_absolute() or not interpreter.is_file():
                        raise ValueError('OCR Python environment missing; configure it in Preferences → OCR')
                with tempfile.TemporaryDirectory(prefix='snapmark-ocr-') as temp:
                    root = Path(temp)
                    (root / 'input.png').write_bytes(image)
                    (root / 'request.json').write_text(json.dumps({
                        'models_root': cfg['models_root'], 'model': cfg['model'],
                        'image_path': str(root / 'input.png'),
                    }), encoding='utf-8')
                    if is_onnx:
                        command = _onnx.command(root / 'input.png', cfg['model'])
                    else:
                        command = [str(interpreter), str(ROOT / 'worker.py'),
                                   '--request', str(root / 'request.json'),
                                   '--result', str(root / 'result.json')]
                    with self.proc_lock:
                        if generation != self.generation:
                            return
                        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                                stdout=(subprocess.PIPE if is_onnx else subprocess.DEVNULL),
                                                stderr=subprocess.PIPE)
                        self.proc = proc
                    try:
                        _out, error = proc.communicate(timeout=180)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()
                        raise TimeoutError('OCR exceeded 180 seconds')
                    if proc.returncode:
                        raise RuntimeError((error.decode('utf-8', 'replace')[-2400:] or
                                            f'OCR subprocess returned {proc.returncode}').strip())
                    if is_onnx:
                        if not _out or len(_out) > 8 * 1024 * 1024:
                            raise ValueError('ONNX OCR returned an empty or oversized response')
                        result = json.loads(_out.decode('utf-8'))
                        if result.get('ok') is not True:
                            raise ValueError('ONNX OCR returned an unsuccessful result')
                    else:
                        result = json.loads((root / 'result.json').read_text('utf-8'))
                    value = result.get('text')
                    if not isinstance(value, str):
                        raise ValueError('OCR worker returned no text field')
                output, err = value, None
            except Exception as exc:
                output, err = None, str(exc)
            elapsed = time.perf_counter() - start
            GLib.idle_add(self._done, generation, output, err, elapsed)

        threading.Thread(target=job, daemon=True).start()

    def _done(self, generation, output, err, elapsed):
        if generation != self.generation:
            return False
        self.proc = None
        self.running = False
        self.started_at = None
        self.run_button.set_label('Run OCR')
        self.timer.set_text(f'Time: {elapsed:.2f} s')
        if self.editor.pixbuf is not self.source_image:
            self._status('Image changed; stale OCR output was discarded', toast=True)
        elif err:
            self._error_dialog(str(err)[:600])
        else:
            # Append by default: never overwrite user-corrected/pasted text on re-OCR.
            buffer = self._buffer()
            before = self._get_text()
            suffix = ('\n' if before.endswith('\n') else '\n\n') if before else ''
            buffer.insert(buffer.get_end_iter(), suffix + output)
            self._status(f'OCR completed; {len(output)} text characters, editable', toast=True)
        return False

    def cancel(self):
        if self.running:
            self.generation += 1
            self.running = False
            self.started_at = None
            if self.run_button is not None:
                self.run_button.set_label('Run OCR')
            with self.proc_lock:
                proc = self.proc
                if proc is not None and proc.poll() is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                self.proc = None
            self._status('OCR cancelled', toast=True)
            self.timer.set_text('Time: cancelled')

    def clear_text(self):
        if not self._get_text():
            return
        dialog = Adw.AlertDialog(heading='Clear OCR text?',
                                 body='This deletes your edits and recognized text from the result pane.')
        dialog.add_response('cancel', 'Keep text')
        dialog.add_response('clear', 'Clear text')
        dialog.set_response_appearance('clear', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', lambda _d, code:
                       self._buffer().set_text('') if code == 'clear' else None)
        dialog.present(self.editor)

    def copy_text(self):
        if not self._get_text():
            self._status('No OCR text to copy')
            return
        self.editor.get_display().get_clipboard().set(self._get_text())
        self._status('OCR text copied')

    def save_text(self):
        if not self._get_text():
            self._status('No OCR text to save')
            return
        dialog = Gtk.FileDialog(title='Save OCR text')
        name = self.editor.filename.stem if self.editor.filename else 'screenshot'
        dialog.set_initial_name(name + '-ocr.txt')
        dialog.save(self.editor, None, self._save_done)

    def _save_done(self, dialog, response):
        try:
            target = dialog.save_finish(response)
            if target:
                data = self._get_text().encode('utf-8')
                target.replace_contents(data, None, False,
                                        Gio.FileCreateFlags.REPLACE_DESTINATION, None)
                self._status('OCR text saved')
        except GLib.Error as exc:
            if not (exc.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED)):
                self._status(f'Cannot save OCR text: {exc.message}')
        except Exception as exc:
            self._status(f'Cannot save OCR text: {exc}')


def register(host):
    controller = OCRController(host.editor)
    host.register_text_provider('ocr', controller._get_text)
    host.register_result_panel('ocr', 'OCR result', controller.build_panel)
    host.register_preferences_page('ocr', 'OCR', controller.build_preferences)
    host.register_toolbar_action('ocr', 'OCR', controller.on_toolbar)
