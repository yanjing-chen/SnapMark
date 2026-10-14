"""AI Runtime Preferences: read-only service inspection and local bundle preview."""
from __future__ import annotations

import threading
from gi.repository import Adw, Gio, GLib, Gtk

from .ai_runtime import (BACKEND_PREFERENCES, RUNTIME_PROJECT, RuntimeSettings,
                         RuntimeIntegrationError, probe_runtime)
from .model_bundle import ModelBundleError, inspect_gguf_files, inspect_gguf_folder


class AIRuntimePreferences:
    def __init__(self, window, stack):
        self.window = window
        self.settings = RuntimeSettings()
        self.config = self.settings.load()
        self.generation = 0
        self.model_rows = []
        self.preview_rows = []
        self.preview_generation = 0
        self.widgets = {}
        page = Adw.PreferencesPage()
        stack.add_titled(page, 'ai-runtime', 'AI Runtime')

        integration = Adw.PreferencesGroup(title='Local AI Runtime', description=(
            'Optional shared inference service. SnapMark never stops, installs models '
            'into, or changes the configuration of an existing Runtime.'))
        page.add(integration)
        enabled = Adw.SwitchRow(title='Enable AI Runtime integration',
                                subtitle='Off by default; affects SnapMark only')
        enabled.set_active(self.config['enabled'])
        integration.add(enabled)
        self.widgets['enabled'] = enabled

        connection = Adw.PreferencesGroup(title='Connection', description=(
            'Reuse an existing service where possible. Connection checks do not start Runtime.'))
        page.add(connection)
        endpoint = Adw.EntryRow(title='Endpoint')
        endpoint.set_text(self.config['endpoint'])
        connection.add(endpoint)
        self.widgets['endpoint'] = endpoint
        save = Gtk.Button(label='Save & Check')
        save.set_valign(Gtk.Align.CENTER)
        save.add_css_class('suggested-action')
        action = Adw.ActionRow(title='Use existing Runtime',
                               subtitle='Check health, registered models, and backend')
        action.add_suffix(save)
        connection.add(action)
        self.widgets['check'] = save
        status = Adw.ActionRow(title='Connection status',
                               subtitle='Integration disabled' if not self.config['enabled'] else 'Not checked')
        connection.add(status)
        self.widgets['status'] = status

        group = Adw.PreferencesGroup(title='Hardware acceleration', description=(
            'Auto is recommended. Runtime decides the effective CPU/Vulkan/CUDA backend. '
            'Manual preferences are saved for future model requests; this page does not '
            'override a shared running service.'))
        page.add(group)
        pref = Adw.ActionRow(title='Backend preference')
        options = Gtk.DropDown.new_from_strings(['Auto (recommended)', 'CPU', 'Vulkan', 'CUDA'])
        options.set_valign(Gtk.Align.CENTER)
        options.set_selected(BACKEND_PREFERENCES.index(self.config['backend_preference']))
        pref.add_suffix(options)
        group.add(pref)
        self.widgets['backend_preference'] = options
        effective = Adw.ActionRow(title='Backend reported by Runtime', subtitle='Not checked')
        group.add(effective)
        self.widgets['effective'] = effective
        service_pref = Adw.ActionRow(title='Runtime backend preference', subtitle='Not checked')
        group.add(service_pref)
        self.widgets['service_preference'] = service_pref
        actual = Adw.ActionRow(title='Active inference backend', subtitle='Not checked')
        group.add(actual)
        self.widgets['actual'] = actual
        loaded = Adw.ActionRow(title='Model loaded in memory', subtitle='Not checked')
        group.add(loaded)
        self.widgets['loaded'] = loaded

        models = Adw.PreferencesGroup(title='Registered Models', description=(
            'Only models reported by the connected Runtime are listed. '
            'No model is downloaded or loaded by this page.'))
        page.add(models)
        placeholder = Adw.ActionRow(title='No models checked yet')
        models.add(placeholder)
        self.widgets['models_group'] = models
        self.widgets['models_placeholder'] = placeholder

        install = Adw.PreferencesGroup(title='Runtime installation', description=(
            'Reuse your current installation. A verified one-click installer requires a '
            'confirmed release package and checksum; no installation is performed here.'))
        page.add(install)
        guide = Adw.ActionRow(title='Local AI Runtime project',
                              subtitle='Open the official source and installation instructions')
        open_guide = Gtk.Button(label='View instructions…')
        open_guide.set_valign(Gtk.Align.CENTER)
        guide.add_suffix(open_guide)
        install.add(guide)
        select = Adw.PreferencesGroup(title='Preview local GGUF model bundle', description=(
            'Select multiple GGUF files or a folder. SnapMark detects main weights, '
            'mmproj and split GGUF pieces together. This is a read-only preview: '
            'registration awaits verification of Runtime 0.8.0 write API.'))
        page.add(select)
        buttons_row = Adw.ActionRow(title='Choose model files', subtitle=(
            'Supports one main GGUF plus mmproj, and numbered GGUF shards.'))
        select_files = Gtk.Button(label='Select files…')
        select_files.set_valign(Gtk.Align.CENTER)
        select_files.connect('clicked', self._choose_files)
        buttons_row.add_suffix(select_files)
        select.add(buttons_row)
        folder_row = Adw.ActionRow(title='Choose model folder', subtitle=(
            'Inspects only the selected folder; never scans subfolders.'))
        select_folder = Gtk.Button(label='Select folder…')
        select_folder.set_valign(Gtk.Align.CENTER)
        select_folder.connect('clicked', self._choose_folder)
        folder_row.add_suffix(select_folder)
        select.add(folder_row)
        placeholder = Adw.ActionRow(title='No local models inspected yet')
        select.add(placeholder)
        self.widgets['preview_group'] = select
        self.widgets['preview_placeholder'] = placeholder

        self._enabled_handler = enabled.connect('notify::active', self._enabled_changed)
        self._backend_handler = options.connect('notify::selected', self._backend_changed)
        save.connect('clicked', self._check_clicked)
        open_guide.connect('clicked', self._open_instructions)
        self._set_available(self.config['enabled'])

    def _message(self, title, detail):
        dialog = Adw.MessageDialog(transient_for=self.window, heading=title, body=str(detail))
        dialog.add_response('ok', 'OK')
        dialog.present()

    def _set_available(self, available):
        for key in ('endpoint', 'check', 'backend_preference'):
            self.widgets[key].set_sensitive(available)

    def _enabled_changed(self, switch, _property):
        enabled = switch.get_active()
        try:
            self.config = self.settings.update(enabled=enabled)
        except (OSError, RuntimeIntegrationError) as exc:
            self._message('Cannot save AI Runtime setting', exc)
            switch.handler_block(self._enabled_handler)
            switch.set_active(self.config['enabled'])
            switch.handler_unblock(self._enabled_handler)
            return
        self.generation += 1
        self._set_available(enabled)
        self.widgets['status'].set_subtitle('Not checked' if enabled else 'Integration disabled')
        self.widgets['effective'].set_subtitle('Not checked')
        self.widgets['service_preference'].set_subtitle('Not checked')
        self.widgets['actual'].set_subtitle('Not checked')
        self.widgets['loaded'].set_subtitle('Not checked')
        self._set_models(())
        if enabled:
            self._start_probe(self.config['endpoint'])

    def _backend_changed(self, dropdown, _property):
        preference = BACKEND_PREFERENCES[dropdown.get_selected()]
        if preference == self.config['backend_preference']:
            return
        try:
            self.config = self.settings.update(backend_preference=preference)
        except (OSError, RuntimeIntegrationError) as exc:
            self._message('Cannot save backend preference', exc)
            dropdown.handler_block(self._backend_handler)
            dropdown.set_selected(BACKEND_PREFERENCES.index(self.config['backend_preference']))
            dropdown.handler_unblock(self._backend_handler)

    def _check_clicked(self, _button):
        if not self.config['enabled']:
            return
        endpoint = self.widgets['endpoint'].get_text()
        try:
            self.config = self.settings.update(endpoint=endpoint)
        except (OSError, RuntimeIntegrationError) as exc:
            self._message('Invalid Runtime endpoint', exc)
            return
        self._start_probe(self.config['endpoint'])

    def _start_probe(self, endpoint):
        self.generation += 1
        generation = self.generation
        self.widgets['status'].set_subtitle('Connecting…')
        self.widgets['check'].set_sensitive(False)
        self._set_models(())

        def work():
            try:
                outcome, error = probe_runtime(endpoint), None
            except (RuntimeIntegrationError, OSError) as exc:
                outcome, error = None, str(exc)
            GLib.idle_add(self._probe_done, generation, outcome, error)

        threading.Thread(target=work, daemon=True).start()

    def _probe_done(self, generation, result, error):
        if generation != self.generation or not self.config['enabled']:
            return False
        self.widgets['check'].set_sensitive(True)
        if error:
            self.widgets['status'].set_subtitle('Unavailable: ' + error[:180])
            self.widgets['effective'].set_subtitle('Not reported')
            self.widgets['service_preference'].set_subtitle('Not reported')
            self.widgets['actual'].set_subtitle('Not running')
            self.widgets['loaded'].set_subtitle('Not loaded')
            return False
        self.widgets['status'].set_subtitle('Connected · ' + result.health)
        self.widgets['effective'].set_subtitle(result.backend + (
            ' (query unavailable)' if result.backend_error else ''))
        self.widgets['service_preference'].set_subtitle(result.configured_backend or 'Not reported')
        self.widgets['actual'].set_subtitle(
            result.active_backend if result.active_backend else
            ('Running · backend unknown' if result.backend_running else 'Not running'))
        self.widgets['loaded'].set_subtitle(
            result.current_model if result.current_model else 'Not loaded')
        self._set_models(result.models, snapshot=result)
        if result.models_error:
            self.widgets['models_placeholder'].set_title('Model query unavailable')
            self.widgets['models_placeholder'].set_subtitle(result.models_error[:180])
        return False

    def _set_models(self, names, snapshot=None):
        group = self.widgets['models_group']
        for row in self.model_rows:
            group.remove(row)
        self.model_rows = []
        placeholder = self.widgets['models_placeholder']
        placeholder.set_title('No models reported')
        placeholder.set_subtitle('')
        placeholder.set_visible(not names)
        details = {item.identifier: item for item in snapshot.detailed_models} if snapshot else {}
        for name in names:
            entry = details.get(name)
            status = ('Installed' if entry.installed is True else
                      'Not installed' if entry.installed is False else 'Install status unknown') if entry else 'Install status unknown'
            if snapshot and snapshot.backend_running and snapshot.current_model == name:
                status += ' · Loaded'
            else:
                status += ' · Not loaded'
            capabilities = ', '.join(entry.capabilities) if entry else ''
            if capabilities:
                status += ' · ' + capabilities
            row = Adw.ActionRow(title=name, subtitle=status)
            group.add(row)
            self.model_rows.append(row)

    def _open_instructions(self, _button):
        try:
            Gio.AppInfo.launch_default_for_uri(RUNTIME_PROJECT, None)
        except GLib.Error as exc:
            self._message('Could not open Runtime instructions', exc)

    def _choose_files(self, _button):
        dialog = Gtk.FileDialog.new()
        dialog.set_title('Select GGUF model files (main, mmproj, or splits)')
        filt = Gtk.FileFilter()
        filt.set_name('GGUF models')
        filt.add_pattern('*.gguf')
        filt.add_pattern('*.GGUF')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filt)
        dialog.set_filters(filters)
        dialog.open_multiple(self.window, None, self._files_chosen)

    def _files_chosen(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:  # Includes the user cancelling the chooser.
            return
        paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
        if any(path is None for path in paths):
            self._message('Local files only', 'Please choose files on a local filesystem.')
            return
        self._preview_async(paths=paths)

    def _choose_folder(self, _button):
        dialog = Gtk.FileDialog.new()
        dialog.set_title('Select local GGUF model folder')
        dialog.select_folder(self.window, None, self._folder_chosen)

    def _folder_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result).get_path()
        except GLib.Error:
            return
        if not folder:
            self._message('Local folder only', 'Please choose a local directory.')
            return
        self._preview_async(folder=folder)

    def _preview_async(self, *, paths=None, folder=None):
        self.preview_generation += 1
        generation = self.preview_generation
        self.widgets['preview_placeholder'].set_visible(True)
        self.widgets['preview_placeholder'].set_title('Inspecting model files…')
        # Avoid blocking GNOME's UI on removable drives or network-mounted paths.
        def work():
            try:
                bundles = (inspect_gguf_files(paths) if paths is not None else
                           inspect_gguf_folder(folder))
                error = None
            except (ModelBundleError, OSError, ValueError) as exc:
                bundles, error = (), str(exc)
            GLib.idle_add(self._preview_ready, generation, bundles, error)
        threading.Thread(target=work, daemon=True).start()

    def _preview_ready(self, generation, bundles, error):
        if generation != self.preview_generation:
            return False
        group = self.widgets['preview_group']
        for row in self.preview_rows:
            group.remove(row)
        self.preview_rows = []
        placeholder = self.widgets['preview_placeholder']
        placeholder.set_visible(bool(error) or not bundles)
        placeholder.set_title('Cannot inspect model files' if error else 'No GGUF bundles found')
        placeholder.set_subtitle((error or '')[:240])
        for bundle in bundles:
            pieces = []
            if bundle.main:
                pieces.append('main: ' + bundle.main.name)
            if bundle.shards:
                pieces.append(f'{len(bundle.shards)} GGUF split parts')
            if bundle.projectors:
                pieces.append('mmproj: ' + ', '.join(p.name for p in bundle.projectors))
            pieces.append(f'{bundle.total_bytes / (1024 ** 3):.2f} GiB')
            for warning in bundle.warnings:
                pieces.append('Warning: ' + warning)
            row = Adw.ActionRow(title=bundle.name, subtitle=' · '.join(pieces))
            group.add(row)
            self.preview_rows.append(row)
        return False
