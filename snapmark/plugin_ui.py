"""GTK4 / libadwaita Preferences page for official plugin releases.

Network and unzip operations happen on worker threads; GTK runs on main loop.
"""
from __future__ import annotations

import threading

from gi.repository import Adw, GLib, Gtk

from .plugins import (PLUGIN_IDS, PluginError, PluginManager,
                      available_releases, install_release)


class PluginPreferences:
    def __init__(self, window, stack, on_changed=None):
        self.window = window
        self.stack = stack
        self.manager = PluginManager()
        self.on_changed = on_changed or (lambda: None)
        self.widgets = {}
        page = Adw.PreferencesPage()
        stack.add_titled(page, 'plugins', 'Plugins')
        intro = Adw.PreferencesGroup(title='Official Plugins', description=(
            'OCR and Translation are optional. Plugins are executable code: '
            'install only verified releases published by yanjing-chen/SnapMark. '
            'After changing plugins, reopen SnapMark to reload their interfaces.'))
        page.add(intro)
        for ident, heading in (('ocr', 'OCR'), ('translation', 'Translation')):
            group = Adw.PreferencesGroup(title=heading)
            page.add(group)
            active = Adw.ActionRow(title='Installed version', subtitle='Not installed')
            select = Gtk.DropDown.new_from_strings(['No versions installed'])
            select.set_valign(Gtk.Align.CENTER)
            active.add_suffix(select)
            group.add(active)

            controls = Adw.ActionRow(title='Activate selected version', subtitle='Disabled by default')
            activate = Gtk.Button(label='Use Version')
            activate.set_valign(Gtk.Align.CENTER)
            toggle = Gtk.Switch()
            toggle.set_valign(Gtk.Align.CENTER)
            controls.add_suffix(activate)
            controls.add_suffix(toggle)
            group.add(controls)

            remote = Adw.ActionRow(title='Official GitHub Releases', subtitle='Refresh to check available versions')
            remote_select = Gtk.DropDown.new_from_strings(['Click Refresh'])
            remote_select.set_valign(Gtk.Align.CENTER)
            refresh = Gtk.Button(icon_name='view-refresh-symbolic', tooltip_text='Refresh release versions')
            refresh.set_valign(Gtk.Align.CENTER)
            download = Gtk.Button(label='Install')
            download.set_sensitive(False)
            download.set_valign(Gtk.Align.CENTER)
            remote.add_suffix(remote_select)
            remote.add_suffix(refresh)
            remote.add_suffix(download)
            group.add(remote)

            remove_row = Adw.ActionRow(title='Remove selected installed version',
                                       subtitle='Does not delete downloaded AI models')
            remove = Gtk.Button(label='Uninstall')
            remove.set_valign(Gtk.Align.CENTER)
            remove.add_css_class('destructive-action')
            remove_row.add_suffix(remove)
            group.add(remove_row)

            self.widgets[ident] = dict(active=active, select=select, controls=controls,
                                       activate=activate, toggle=toggle, remote=remote,
                                       remote_select=remote_select, refresh=refresh,
                                       download=download, remove=remove, releases=[])
            activate.connect('clicked', self._activate, ident)
            toggle.connect('notify::active', self._toggle, ident)
            refresh.connect('clicked', self._refresh, ident)
            download.connect('clicked', self._download, ident)
            remove.connect('clicked', self._remove, ident)
        self._syncing = False
        self.refresh_installed()

    def _message(self, title, detail=''):
        dialog = Adw.MessageDialog(transient_for=self.window, heading=title, body=str(detail))
        dialog.add_response('ok', 'OK')
        dialog.present()

    def _changed(self):
        self.refresh_installed()
        self.on_changed()

    def refresh_installed(self):
        self._syncing = True
        try:
            for ident in PLUGIN_IDS:
                ui = self.widgets[ident]
                versions = self.manager.versions(ident)
                selected = self.manager.selected(ident)
                ui['select'].set_model(Gtk.StringList.new(versions or ['No versions installed']))
                if selected in versions:
                    ui['select'].set_selected(versions.index(selected))
                ui['active'].set_subtitle(f'Active: v{selected}' if selected else 'Not installed / inactive')
                ui['controls'].set_subtitle(('Enabled' if self.manager.is_available(ident) else
                    'Dependency not enabled' if self.manager.is_enabled(ident) else 'Disabled'))
                ui['toggle'].set_active(self.manager.is_enabled(ident))
                for action in ('select', 'activate', 'toggle', 'remove'):
                    ui[action].set_sensitive(bool(versions))
        finally:
            self._syncing = False

    def _selected_installed(self, ident):
        ui = self.widgets[ident]
        versions = self.manager.versions(ident)
        index = ui['select'].get_selected()
        return versions[index] if index < len(versions) else None

    def _activate(self, _button, ident):
        version = self._selected_installed(ident)
        if not version:
            return
        try:
            self.manager.select(ident, version, True)
            self._changed()
        except PluginError as exc:
            self._message('Cannot enable plugin', str(exc))

    def _toggle(self, switch, _pspec, ident):
        if self._syncing:
            return
        try:
            self.manager.set_enabled(ident, switch.get_active())
            self._changed()
        except PluginError as exc:
            self._message('Cannot change plugin state', str(exc))
            self.refresh_installed()

    def _run_worker(self, worker, callback):
        def go():
            try:
                value, error = worker(), None
            except Exception as exc:
                value, error = None, str(exc)
            GLib.idle_add(callback, value, error)
        threading.Thread(target=go, daemon=True).start()

    def _refresh(self, _button, ident):
        ui = self.widgets[ident]
        ui['refresh'].set_sensitive(False)
        ui['remote'].set_subtitle('Checking official GitHub Releases…')
        self._run_worker(lambda: available_releases(ident),
                         lambda result, error: self._refresh_done(ident, result, error))

    def _refresh_done(self, ident, releases, error):
        ui = self.widgets[ident]
        ui['refresh'].set_sensitive(True)
        if error:
            ui['remote'].set_subtitle('Release check failed; try again')
            self._message('Cannot check releases', error)
        else:
            ui['releases'] = releases
            ui['remote_select'].set_model(Gtk.StringList.new(
                [f"v{r['version']}" for r in releases] or ['No plugin releases published']))
            ui['remote'].set_subtitle(f'{len(releases)} official release version(s)')
        ui['download'].set_sensitive(bool(ui['releases']))
        return False

    def _download(self, _button, ident):
        ui = self.widgets[ident]
        options = ui['releases']
        index = ui['remote_select'].get_selected()
        if index >= len(options):
            return
        release = options[index]
        ui['download'].set_sensitive(False)
        ui['remote'].set_subtitle(f"Downloading v{release['version']}…")
        self._run_worker(lambda: install_release(self.manager, release),
                         lambda manifest, error: self._download_done(ident, manifest, error))

    def _download_done(self, ident, manifest, error):
        self.widgets[ident]['download'].set_sensitive(True)
        if error:
            self._message('Plugin installation failed', error)
        else:
            self._changed()
            self._message('Plugin downloaded', f"Installed {ident} v{manifest['version']}. "
                          'Choose Use Version to activate it, then reopen SnapMark.')
        return False

    def _remove(self, _button, ident):
        version = self._selected_installed(ident)
        if not version:
            return
        dialog = Adw.MessageDialog(transient_for=self.window, heading='Uninstall plugin version?',
                                   body=f'Remove {ident} v{version}? Other versions and AI models remain.')
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('uninstall', 'Uninstall')
        dialog.set_response_appearance('uninstall', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        def on_response(d, result):
            if result == 'uninstall':
                try:
                    self.manager.uninstall(ident, version)
                    self._changed()
                except PluginError as exc:
                    self._message('Cannot uninstall plugin', str(exc))
        dialog.connect('response', on_response)
        dialog.present()
