"""First-level AI Runtime Preferences page; intentionally read-only to Runtime."""
from __future__ import annotations

import threading
from gi.repository import Adw, Gio, GLib, Gtk

from .ai_runtime import (BACKEND_PREFERENCES, RUNTIME_PROJECT, RuntimeSettings,
                         RuntimeIntegrationError, probe_runtime)


class AIRuntimePreferences:
    def __init__(self, window, stack):
        self.window = window
        self.settings = RuntimeSettings()
        self.config = self.settings.load()
        self.generation = 0
        self.model_rows = []
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
        effective = Adw.ActionRow(title='Runtime-reported backend', subtitle='Not checked')
        group.add(effective)
        self.widgets['effective'] = effective

        models = Adw.PreferencesGroup(title='Registered Models', description=(
            'Only models reported by the connected Runtime are listed. '
            'No model is downloaded or loaded by this page.'))
        page.add(models)
        placeholder = Adw.ActionRow(title='No models checked yet')
        models.add(placeholder)
        self.widgets['models_group'] = models
        self.widgets['models_placeholder'] = placeholder

        install = Adw.PreferencesGroup(title='Install or add models', description=(
            'Runtime installation and local-model registration require verified release '
            'and API compatibility; one-click operations are planned for v0.6.0-B2.'))
        page.add(install)
        guide = Adw.ActionRow(title='Local AI Runtime project',
                              subtitle='Open the official source and installation instructions')
        open_guide = Gtk.Button(label='View instructions…')
        open_guide.set_valign(Gtk.Align.CENTER)
        guide.add_suffix(open_guide)
        install.add(guide)
        models_info = Adw.ActionRow(title='Add a local model',
                                    subtitle='Pending verification of the Runtime registration API')
        install.add(models_info)

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
            return False
        self.widgets['status'].set_subtitle('Connected · ' + result.health)
        self.widgets['effective'].set_subtitle(result.backend + (
            ' (query unavailable)' if result.backend_error else ''))
        self._set_models(result.models)
        if result.models_error:
            self.widgets['models_placeholder'].set_title('Model query unavailable')
            self.widgets['models_placeholder'].set_subtitle(result.models_error[:180])
        return False

    def _set_models(self, names):
        group = self.widgets['models_group']
        for row in self.model_rows:
            group.remove(row)
        self.model_rows = []
        placeholder = self.widgets['models_placeholder']
        placeholder.set_title('No models reported')
        placeholder.set_subtitle('')
        placeholder.set_visible(not names)
        for name in names:
            row = Adw.ActionRow(title=name)
            group.add(row)
            self.model_rows.append(row)

    def _open_instructions(self, _button):
        try:
            Gio.AppInfo.launch_default_for_uri(RUNTIME_PROJECT, None)
        except GLib.Error as exc:
            self._message('Could not open Runtime instructions', exc)
