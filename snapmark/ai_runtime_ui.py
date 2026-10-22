"""AI Runtime Preferences: safe status, consent-gated idle timeout and registration."""
from __future__ import annotations

from .i18n import _

import threading
from gi.repository import Adw, Gio, GLib, Gtk

from .ai_runtime import (BACKEND_PREFERENCES, RUNTIME_PROJECT, RUNTIME_RELEASES,
                         RuntimeSettings, RuntimeIntegrationError, probe_runtime,
                         describe_preload, describe_idle_unload)
from .model_bundle import ModelBundleError, inspect_gguf_files, inspect_gguf_folder
from .runtime_registration import inspect_registration, register_reviewed_model
from .runtime_idle import read_idle_capability, change_idle_seconds
from .runtime_manager_b3 import RuntimeManager, ManagementError
from .runtime_backends_b4 import (read_overview, change_preference,
                                  install_backend, rollback_backend, wait_install)
from .runtime_release_check import (RELEASE_URL, ReleaseCheckError,
                                    inspect_local_installation, compare_versions,
                                    fetch_official_release)


class AIRuntimePreferences:
    def __init__(self, window, stack):
        self.window = window
        self.settings = RuntimeSettings()
        self.config = self.settings.load()
        self.generation = 0
        self.model_rows = []
        self.preview_rows = []
        self.preview_generation = 0
        self.registration_generation = 0
        self.registration_in_progress = False
        self.idle_saving = False
        self.idle_verified_seconds = None
        self.idle_verified_endpoint = None
        self.release_probe_generation = 0
        self.release_checking = False
        self.runtime_manager = RuntimeManager()
        self.runtime_management_busy = False
        self.local_installation = inspect_local_installation()
        self.installed_runtime_version = ""
        self.backend_overview = None
        self.backend_overview_endpoint = None
        self.backend_busy = False
        self.backend_generation = 0
        self.widgets = {}
        page = Adw.PreferencesPage()
        stack.add_titled(page, 'ai-runtime', 'AI Runtime')
        stack.get_page(page).set_title(_('AI Runtime'))

        integration = Adw.PreferencesGroup(title=_('Local AI Runtime'), description=(
            _('Optional shared inference service. Connecting never changes it; '
            'only explicitly confirmed actions may modify shared Runtime settings.')))
        page.add(integration)
        enabled = Adw.SwitchRow(title=_('Enable AI Runtime integration'),
                                subtitle=_('Off by default; affects SnapMark only'))
        enabled.set_active(self.config['enabled'])
        integration.add(enabled)
        self.widgets['enabled'] = enabled

        connection = Adw.PreferencesGroup(title=_('Connection'), description=(
            _('Reuse an existing service where possible. Connection checks do not start Runtime.')))
        page.add(connection)
        endpoint = Adw.EntryRow(title=_('Endpoint'))
        endpoint.set_text(self.config['endpoint'])
        connection.add(endpoint)
        self.widgets['endpoint'] = endpoint
        save = Gtk.Button(label=_('Save & Check'))
        save.set_valign(Gtk.Align.CENTER)
        save.add_css_class('suggested-action')
        action = Adw.ActionRow(title=_('Use existing Runtime'),
                               subtitle=_('Check health, registered models, and backend'))
        action.add_suffix(save)
        connection.add(action)
        self.widgets['check'] = save
        status = Adw.ActionRow(title=_('Connection status'),
                               subtitle=_('Integration disabled') if not self.config['enabled'] else _('Not checked'))
        connection.add(status)
        self.widgets['status'] = status
        # Lightweight read-only summary stays on the main page. The existing
        # backend controls and service/model management remain intact below.
        version = Adw.ActionRow(title=_('Runtime version'), subtitle=_('Not checked'))
        connection.add(version)
        self.widgets['version_summary'] = version

        # Advanced preferences: collapsed by default. The nested groups are
        # ordinary Adw.PreferencesGroup widgets; no fragile GTK tree scanning.
        advanced = Adw.PreferencesGroup(title=_('Advanced settings'))
        page.add(advanced)
        advanced_action = Adw.ActionRow(title=_('Show advanced settings'),
            subtitle=_('Backend preference and shared idle timeout'))
        advanced_button = Gtk.ToggleButton(label=_('Show'))
        advanced_button.set_valign(Gtk.Align.CENTER)
        advanced_action.add_suffix(advanced_button)
        advanced.add(advanced_action)
        self.advanced_revealer = Gtk.Revealer()
        self.advanced_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.advanced_revealer.set_transition_duration(160)
        advanced_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        advanced_box.set_margin_top(12)
        self.advanced_revealer.set_child(advanced_box)
        advanced.add(self.advanced_revealer)
        advanced_button.connect('toggled', lambda b:
            self.advanced_revealer.set_reveal_child(b.get_active()))
        self.advanced_box = advanced_box
        self.widgets['advanced_toggle'] = advanced_button

        # Maintenance operations are kept in a separate on-demand window.
        # Importantly, opening either page NEVER starts/stops Runtime.
        maintenance_link = Adw.PreferencesGroup(title=_('Runtime maintenance'))
        page.add(maintenance_link)
        maintenance_row = Adw.ActionRow(title=_('Runtime maintenance tools'),
            subtitle=_('Installation, service, backend packages and model registration'))
        maintenance_button = Gtk.Button(label=_('Open maintenance tools…'))
        maintenance_button.set_valign(Gtk.Align.CENTER)
        maintenance_button.connect('clicked', self._open_maintenance)
        maintenance_row.add_suffix(maintenance_button)
        maintenance_link.add(maintenance_row)
        self.widgets['maintenance_button'] = maintenance_button

        self.maintenance_window = Adw.PreferencesWindow(title=_('Runtime maintenance tools'))
        self.maintenance_window.set_default_size(900, 670)
        self.maintenance_window.set_transient_for(self.window)
        self.maintenance_window.set_hide_on_close(True)
        self.maintenance_page = Adw.PreferencesPage()
        self.maintenance_window.add(self.maintenance_page)

        group = Adw.PreferencesGroup(title=_('Hardware acceleration'), description=(
            _('Auto is recommended. Runtime decides the effective CPU/Vulkan/CUDA backend. '
            'Manual preferences are saved for future model requests; this page does not '
            'override a shared running service.')))
        self.advanced_box.append(group)
        pref = Adw.ActionRow(title=_('Backend preference'))
        options = Gtk.DropDown.new_from_strings(['Auto (recommended)', 'CPU', 'Vulkan', 'CUDA'])
        options.set_model(Gtk.StringList.new([_('Auto (recommended)'), 'CPU', 'Vulkan', 'CUDA']))
        options.set_valign(Gtk.Align.CENTER)
        options.set_selected(BACKEND_PREFERENCES.index(self.config['backend_preference']))
        pref.add_suffix(options)
        group.add(pref)
        self.widgets['backend_preference'] = options
        effective = Adw.ActionRow(title=_('Backend reported by Runtime'), subtitle=_('Not checked'))
        connection.add(effective)
        self.widgets['effective'] = effective
        service_pref = Adw.ActionRow(title=_('Runtime backend preference'), subtitle=_('Not checked'))
        group.add(service_pref)
        self.widgets['service_preference'] = service_pref
        actual = Adw.ActionRow(title=_('Active inference backend'), subtitle=_('Not checked'))
        connection.add(actual)
        self.widgets['actual'] = actual
        loaded = Adw.ActionRow(title=_('Model loaded in memory'), subtitle=_('Not checked'))
        connection.add(loaded)
        self.widgets['loaded'] = loaded

        # B4 + C1: separate, shared Runtime backend state and management.
        # The earlier dropdown only saves SnapMark-local preference and is not
        # the selected preference in the shared Runtime service.
        packages = Adw.PreferencesGroup(title=_('Runtime backend packages and live state'),
            description=(_('CPU/Vulkan and CUDA are separate Runtime-managed packages. '
                         'Availability is not active inference. No operation occurs until '
                         'explicitly confirmed. Click Refresh backend status to read first.')))
        self.maintenance_page.add(packages)
        for key, title in (
            ('b4_llama', 'CPU / Vulkan package'),
            ('b4_cuda', 'CUDA package'),
            ('b4_available', 'Detected backend availability'),
            ('b4_active', 'Active backend / loaded model'),
            ('b4_fallback', 'Backend fallback'),
            ('b4_progress', 'Backend operation status')):
            row = Adw.ActionRow(title=_(title), subtitle=_('Not checked'))
            packages.add(row)
            self.widgets[key] = row
        # Keep dropdown and confirmation action on separate ActionRows.
        # Two wide suffix widgets previously squeezed the title into a column.
        shared_choice = Adw.ActionRow(
            title=_('Shared Runtime backend preference'),
            subtitle=_('Select the global Runtime preference (not SnapMark-only)'))
        shared_dropdown = Gtk.DropDown.new_from_strings(
            ['Auto (recommended)', 'CPU', 'Vulkan', 'CUDA'])
        shared_dropdown.set_model(Gtk.StringList.new([_('Auto (recommended)'), 'CPU', 'Vulkan', 'CUDA']))
        shared_dropdown.set_selected(0)
        shared_dropdown.set_valign(Gtk.Align.CENTER)
        shared_dropdown.set_sensitive(False)
        shared_choice.add_suffix(shared_dropdown)
        packages.add(shared_choice)

        apply_choice = Adw.ActionRow(
            title='Apply selected backend preference',
            subtitle=_('May unload the active model; requires confirmation'))
        apply_choice.set_title(_('Apply selected backend preference'))
        save_shared = Gtk.Button(label=_('Apply to Runtime…'))
        save_shared.set_valign(Gtk.Align.CENTER)
        save_shared.set_sensitive(False)
        save_shared.connect('clicked', self._b4_action, 'preference')
        apply_choice.add_suffix(save_shared)
        packages.add(apply_choice)
        self.widgets['b4_choice'] = shared_dropdown
        self.widgets['b4_save'] = save_shared
        action_rows = (
            ('refresh', 'Read current package and runtime status', 'Refresh backend status'),
            ('llama_install', 'Install or upgrade Runtime CPU and Vulkan package', 'Install CPU/Vulkan…'),
            ('llama_rollback', 'Roll back CPU and Vulkan package', 'Rollback CPU/Vulkan…'),
            ('cuda_install', 'Install or upgrade Runtime CUDA package', 'Install CUDA…'),
            ('cuda_rollback', 'Roll back CUDA package', 'Rollback CUDA…'),
        )
        for key, title, label in action_rows:
            row = Adw.ActionRow(title=_(title))
            button = Gtk.Button(label=_(label))
            button.set_valign(Gtk.Align.CENTER)
            button.set_sensitive(key == 'refresh' and self.config['enabled'])
            button.connect('clicked', self._b4_action, key)
            row.add_suffix(button)
            packages.add(row)
            self.widgets['b4_'+key] = button

        # Read-only service lifecycle state. Never call a Runtime mutation
        # endpoint or preload a model while constructing Settings.
        memory = Adw.PreferencesGroup(title=_('Model memory management'), description=(
            _('Model loading and idle unloading are managed by Local AI Runtime. '
            'SnapMark reads current settings and changes the shared idle interval only '
            'after an explicit confirmation on Runtime 1.0.0 or newer. '
            'Models are loaded when a later OCR or Translation request needs them.')))
        self.advanced_box.append(memory)
        preload_row = Adw.ActionRow(title=_('Startup model preload'), subtitle=_('Not checked'))
        memory.add(preload_row)
        self.widgets['preload'] = preload_row
        preload_state = Adw.ActionRow(title=_('Runtime preload status'), subtitle=_('Not checked'))
        memory.add(preload_state)
        self.widgets['preload_state'] = preload_state
        idle_row = Adw.ActionRow(title=_('Unload after inactivity'), subtitle=_('Not checked'))
        memory.add(idle_row)
        self.widgets['idle_unload'] = idle_row
        scope = Adw.ActionRow(title=_('Configuration scope'), subtitle=(
            _('Shared Runtime setting · view only until explicitly confirmed')))
        memory.add(scope)
        self.widgets['idle_scope'] = scope
        change_row = Adw.ActionRow(title=_('Custom idle timeout'), subtitle=(
            _('Seconds · 0 disables automatic unloading · 86400 = 24 hours')))
        spin = Gtk.SpinButton.new_with_range(0, 86400, 30)
        spin.set_numeric(True)
        spin.set_value(600)
        spin.set_width_chars(7)
        spin.set_valign(Gtk.Align.CENTER)
        spin.set_sensitive(False)
        change_row.add_suffix(spin)
        apply_idle = Gtk.Button(label=_('Save timeout…'))
        apply_idle.set_valign(Gtk.Align.CENTER)
        apply_idle.set_sensitive(False)
        apply_idle.connect('clicked', self._idle_save_clicked)
        change_row.add_suffix(apply_idle)
        memory.add(change_row)
        self.widgets['idle_spin'] = spin
        self.widgets['idle_save'] = apply_idle

        models = Adw.PreferencesGroup(title=_('Registered Models'), description=(
            _('Only models reported by the connected Runtime are listed. '
            'No model is downloaded or loaded by this page.')))
        self.maintenance_page.add(models)
        placeholder = Adw.ActionRow(title=_('No models checked yet'))
        models.add(placeholder)
        refresh_row = Adw.ActionRow(title=_('Refresh registered models'), subtitle=(
            _('Manually refresh model inventory (may take several seconds).')))
        refresh = Gtk.Button(label='Refresh Models')
        refresh.set_label(_('Refresh Models'))
        refresh.set_valign(Gtk.Align.CENTER)
        refresh.set_sensitive(False)
        refresh.connect('clicked', self._refresh_models_clicked)
        refresh_row.add_suffix(refresh)
        models.add(refresh_row)
        self.widgets['refresh_models'] = refresh
        self.widgets['models_group'] = models
        self.widgets['models_placeholder'] = placeholder

        install = Adw.PreferencesGroup(title=_('Runtime installation'), description=(
            _('Use verified official releases to install or upgrade Runtime. '
            'Destructive operations require confirmation and make backups.')))
        self.maintenance_page.add(install)
        guide = Adw.ActionRow(title=_('Local AI Runtime project'),
                              subtitle=_('Open the official source and installation instructions'))
        open_guide = Gtk.Button(label=_('View instructions…'))
        open_guide.set_valign(Gtk.Align.CENTER)
        guide.add_suffix(open_guide)
        install.add(guide)
        detection = Adw.ActionRow(title=_('Existing Runtime detection'), subtitle=(
            _('Integration disabled') if not self.config['enabled'] else _('Not checked')))
        install.add(detection)
        self.widgets['installation_status'] = detection
        releases_row = Adw.ActionRow(title=_('Official Runtime releases'), subtitle=(
            _('Review verified releases before installing; no automatic install yet')))
        open_releases = Gtk.Button(label=_('View releases…'))
        open_releases.set_valign(Gtk.Align.CENTER)
        open_releases.connect('clicked', self._open_releases)
        releases_row.add_suffix(open_releases)
        install.add(releases_row)
        local_row = Adw.ActionRow(title=_('Local user installation'), subtitle=(
            _('User installation files detected') if self.local_installation.complete else
            _('Partial user installation files detected') if self.local_installation.installed else
            _('No known user installation files found (remote service may still exist)')))
        install.add(local_row)
        self.widgets['local_install'] = local_row
        target = Adw.ActionRow(title=_('Runtime 1.0.0 release check'), subtitle=(
            _('Manual read-only GitHub lookup · archive not downloaded or verified')))
        check_release = Gtk.Button(label=_('Check 1.0.0'))
        check_release.set_valign(Gtk.Align.CENTER)
        check_release.connect('clicked', self._check_release_clicked)
        target.add_suffix(check_release)
        install.add(target)
        self.widgets['release_check'] = check_release
        self.widgets['release_status'] = target
        upgrade = Adw.ActionRow(title=_('Upgrade preflight'), subtitle=(
            _('Not checked · no install, restart, downgrade or uninstall is available yet')))
        install.add(upgrade)
        self.widgets['upgrade_preflight'] = upgrade
        management = Adw.PreferencesGroup(title=_('Runtime application management'), description=(
            _('Controls the local user service only, independently of the API endpoint. '
            'All actions are manual. Installing an application does not install models or GPU '
            'backends. Upgrades create a backup and do NOT restart a running service. '
            'Uninstall preserves model files, settings and backend packages by default.')))
        self.maintenance_page.add(management)
        self._management_row(management, 'download', 'Download & verify Runtime 1.0.0',
                             'Pinned GitHub asset and SHA256SUMS; download only',
                             'Download & verify')
        self._management_row(management, 'backup', 'Backup current application',
                             'Copies program, service unit and small settings; not GGUF files',
                             'Create backup')
        self._management_row(management, 'install', 'Install / upgrade Runtime',
                             'Requires verified application archive; creates automatic backup',
                             'Install / upgrade…')
        self._management_row(management, 'rollback', 'Rollback application files',
                             'Restore latest application backup; service restart is separate',
                             'Rollback…')
        self._management_row(management, 'start', 'Start user Runtime service',
                             'Explicitly start; no action on opening Preferences', 'Start…')
        self._management_row(management, 'stop', 'Stop user Runtime service',
                             'Stops shared Runtime and any current model', 'Stop…')
        self._management_row(management, 'restart', 'Restart user Runtime service',
                             'Interrupts users of this Runtime; use after an upgrade', 'Restart…')
        self._management_row(management, 'uninstall', 'Uninstall Runtime application',
                             'Stop and remove application/service; preserve models and GPU backends',
                             'Uninstall…')
        self._management_row(management, 'purge_config', 'Uninstall and delete settings',
                             'Remove three managed configuration files, but preserve all models and GPU backends',
                             'Remove settings…')
        progress = Adw.ActionRow(title=_('Runtime manager status'), subtitle=_('No operation requested'))
        management.add(progress)
        self.widgets['manager_status'] = progress
        self._refresh_manager_buttons()

        select = Adw.PreferencesGroup(title=_('Preview local GGUF model bundle'), description=(
            _('Select multiple GGUF files or a folder. SnapMark detects main weights, '
            'mmproj and split GGUF pieces together. Registration of one complete '
            'non-split bundle requires separate inspection and explicit confirmation.')))
        self.maintenance_page.add(select)
        buttons_row = Adw.ActionRow(title=_('Choose model files'), subtitle=(
            _('Supports one main GGUF plus mmproj, and numbered GGUF shards.')))
        select_files = Gtk.Button(label=_('Select files…'))
        select_files.set_valign(Gtk.Align.CENTER)
        select_files.connect('clicked', self._choose_files)
        buttons_row.add_suffix(select_files)
        select.add(buttons_row)
        folder_row = Adw.ActionRow(title=_('Choose model folder'), subtitle=(
            _('Inspects only the selected folder; never scans subfolders.')))
        select_folder = Gtk.Button(label=_('Select folder…'))
        select_folder.set_valign(Gtk.Align.CENTER)
        select_folder.connect('clicked', self._choose_folder)
        folder_row.add_suffix(select_folder)
        select.add(folder_row)
        placeholder = Adw.ActionRow(title=_('No local models inspected yet'))
        select.add(placeholder)
        self.widgets['preview_group'] = select
        self.widgets['preview_placeholder'] = placeholder

        self._enabled_handler = enabled.connect('notify::active', self._enabled_changed)
        self._backend_handler = options.connect('notify::selected', self._backend_changed)
        save.connect('clicked', self._check_clicked)
        open_guide.connect('clicked', self._open_instructions)
        self._set_available(self.config['enabled'])

    def _open_maintenance(self, _button):
        self.maintenance_window.present()
        return False

    def _b4_buttons(self):
        ready = bool(self.backend_overview and self.backend_overview_endpoint ==
                     self.config['endpoint'] and self.config['enabled'])
        self.widgets['b4_refresh'].set_sensitive(self.config['enabled'] and not self.backend_busy)
        for action in ('llama_install', 'llama_rollback', 'cuda_install', 'cuda_rollback'):
            family = 'cuda' if action.startswith('cuda') else 'llama'
            info = getattr(self.backend_overview, family, {}) if ready else {}
            operation = info.get('operation') or {}
            has_previous = bool(info.get('previous'))
            sensitive = (ready and not self.backend_busy and
                         operation.get('state') != 'running' and
                         (action.endswith('install') or has_previous))
            self.widgets['b4_'+action].set_sensitive(sensitive)
        self.widgets['b4_choice'].set_sensitive(ready and not self.backend_busy)
        self.widgets['b4_save'].set_sensitive(ready and not self.backend_busy)

    def _b4_action(self, _button, action):
        if not self.config['enabled'] or self.backend_busy:
            return
        if action == 'refresh':
            self._b4_read()
            return
        if not self.backend_overview or self.backend_overview_endpoint != self.config['endpoint']:
            self._message(_('Refresh backend status first'), _('A current Runtime 1.0.0+ status is required.'))
            return
        if action == 'preference':
            desired = BACKEND_PREFERENCES[self.widgets['b4_choice'].get_selected()]
            previous = self.backend_overview.preference
            if desired == previous:
                self._message(_('No change'), _('Runtime already uses this backend preference.'))
                return
            title = 'Change the shared Runtime backend preference?'
            body = (f'Change {previous} to {desired}. Runtime may unload the active model. '
                    'Future inference can use a fallback if the selected backend is unavailable. '
                    'This affects every client connected to the service.')
        else:
            family = 'cuda' if action.startswith('cuda_') else 'llama'
            title = ('Install / update' if action.endswith('install') else 'Rollback') + f' {family} backend?'
            body = ('This invokes the external Runtime 1.0.0 management API. '
                    'Installation downloads verified packages in the background. '
                    'Rollback may interrupt the active model, especially for CUDA. '
                    'This changes the shared service and affects other clients.')
        dialog = Adw.MessageDialog(transient_for=self.window, heading=title, body=body)
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('confirm', 'Confirm action')
        dialog.set_response_appearance('confirm', Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', self._b4_confirm, action)
        dialog.present()

    def _b4_confirm(self, _dialog, response, action):
        if response != 'confirm' or self.backend_busy:
            return
        if action == 'preference':
            desired = BACKEND_PREFERENCES[self.widgets['b4_choice'].get_selected()]
            expected = self.backend_overview.preference
        else:
            desired, expected = '', ''
        self._b4_work(action, desired, expected)

    def _b4_work(self, action, desired='', expected=''):
        self.backend_busy = True
        self.backend_generation += 1
        generation = self.backend_generation
        endpoint = self.config['endpoint']
        self._b4_buttons()
        self.widgets['b4_progress'].set_subtitle('Running ' + action + '…')

        def report(operation):
            phase = str(operation.get('phase') or operation.get('state') or 'working')
            GLib.idle_add(self._b4_progress, generation, endpoint, phase)

        def worker():
            try:
                if action == 'read':
                    result = read_overview(endpoint)
                elif action == 'preference':
                    change_preference(endpoint, desired, confirmed=True, expected=expected)
                    result = read_overview(endpoint)
                else:
                    family = 'cuda' if action.startswith('cuda') else 'llama'
                    if action.endswith('install'):
                        operation = install_backend(endpoint, family, confirmed=True)
                        wait_install(endpoint, family, operation['job_id'], progress=report)
                    else:
                        rollback_backend(endpoint, family, confirmed=True)
                    result = read_overview(endpoint)
                error = None
            except (RuntimeIntegrationError, OSError, ValueError) as exc:
                result, error = None, str(exc)
            GLib.idle_add(self._b4_done, generation, endpoint, result, error)
        threading.Thread(target=worker, daemon=True).start()

    def _b4_read(self):
        self._b4_work('read')

    def _b4_progress(self, generation, endpoint, phase):
        if generation == self.backend_generation and endpoint == self.config['endpoint']:
            self.widgets['b4_progress'].set_subtitle('Backend installation: ' + phase[:130])
        return False

    def _b4_done(self, generation, endpoint, result, error):
        if generation != self.backend_generation:
            return False
        self.backend_busy = False
        if endpoint != self.config['endpoint'] or not self.config['enabled']:
            self.backend_overview = None
            self.backend_overview_endpoint = None
            self._b4_buttons()
            return False
        if error:
            self.backend_overview = None
            self.backend_overview_endpoint = None
            self.widgets['b4_progress'].set_subtitle('Unavailable: ' + error[:220])
            self._b4_buttons()
            return False
        self.backend_overview = result
        self.backend_overview_endpoint = endpoint
        def pkg(info):
            current = str(info.get('current') or 'Not installed')
            previous = str(info.get('previous') or 'None')
            op = info.get('operation') or {}
            return f'Current: {current} · Previous: {previous} · Operation: {op.get("state", "unknown")}'
        self.widgets['b4_llama'].set_subtitle(GLib.markup_escape_text(pkg(result.llama)))
        self.widgets['b4_cuda'].set_subtitle(GLib.markup_escape_text(pkg(result.cuda)))
        availability = []
        for backend in ('cpu', 'vulkan', 'cuda'):
            info = result.available.get(backend) or {}
            availability.append(backend + ': ' + ('usable' if info.get('usable') is True else
                              'installed, unavailable' if info.get('installed') is True else 'not installed'))
        self.widgets['b4_available'].set_subtitle(' · '.join(availability))
        active = result.active_backend if result.backend_running else 'Not running'
        self.widgets['b4_active'].set_subtitle(
            f'{active} · Model: {result.model or "None"} · Healthy: {result.healthy}')
        self.widgets['b4_fallback'].set_subtitle(
            GLib.markup_escape_text(result.fallback or 'No fallback reported'))
        self.widgets['b4_progress'].set_subtitle('Ready · Runtime ' + result.runtime_version)
        if result.preference in BACKEND_PREFERENCES:
            self.widgets['b4_choice'].set_selected(BACKEND_PREFERENCES.index(result.preference))
        self._b4_buttons()
        return False

    def _management_row(self, group, action, title, subtitle, caption):
        row = Adw.ActionRow(title=GLib.markup_escape_text(title),
                            subtitle=GLib.markup_escape_text(subtitle))
        row.set_title(GLib.markup_escape_text(_(title)))
        row.set_subtitle(GLib.markup_escape_text(_(subtitle)))
        button = Gtk.Button(label=caption)
        button.set_label(_(caption))
        button.set_valign(Gtk.Align.CENTER)
        button.connect('clicked', self._management_clicked, action)
        row.add_suffix(button)
        group.add(row)
        self.widgets['manager_' + action] = button

    def _refresh_manager_buttons(self):
        busy = self.runtime_management_busy
        available = self.runtime_manager.archive_ready()
        backups = self.runtime_manager.list_backups()
        for action in ('download', 'backup', 'install', 'rollback', 'start',
                       'stop', 'restart', 'uninstall', 'purge_config'):
            widget = self.widgets['manager_' + action]
            widget.set_sensitive(not busy and (action != 'install' or available)
                                 and (action != 'rollback' or bool(backups)))

    def _management_clicked(self, _button, action):
        if self.runtime_management_busy:
            return
        if action == 'download':
            self._manager_execute(action)
            return
        if action == 'backup':
            self._manager_execute(action)
            return
        prompts = {
            'install': ('Install / upgrade Runtime application?',
                        'This changes the shared application program and service unit. '
                        'An automatic backup will be made. It will NOT restart Runtime '
                        'or update GPU backends/models.'),
            'rollback': ('Restore most recent Runtime backup?',
                         'This replaces program and configuration files with saved copies. '
                         'It does NOT automatically restart Runtime.'),
            'start': ('Start Runtime service?', 'Other clients may connect to this shared service.'),
            'stop': ('Stop shared Runtime?',
                     'This interrupts any other clients and stops currently loaded models.'),
            'restart': ('Restart shared Runtime?',
                        'This interrupts any ongoing inference and reloads the application.'),
            'uninstall': ('Uninstall Runtime application?',
                          'The shared service will be stopped and disabled. Program files '
                          'and service unit will be removed. Configuration, GPU backend '
                          'packages and ALL model files are preserved. A backup is made.'),
            'purge_config': ('Uninstall Runtime and DELETE its settings?',
                             'The shared service will be stopped and disabled. Three '
                             'managed settings/registry JSON files will be deleted. '
                             'GPU backends and ALL model files remain untouched. A backup is made.'),
        }
        title, body = prompts[action]
        dialog = Adw.MessageDialog(transient_for=self.window, heading=title, body=body)
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('confirm', 'Confirm action')
        dialog.set_response_appearance('confirm', Adw.ResponseAppearance.DESTRUCTIVE
                                       if action in ('stop', 'uninstall', 'purge_config')
                                       else Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', self._management_confirmed, action)
        dialog.present()

    def _management_confirmed(self, _dialog, response, action):
        if response == 'confirm':
            self._manager_execute(action)

    def _manager_execute(self, action):
        if self.runtime_management_busy:
            return
        self.runtime_management_busy = True
        self._refresh_manager_buttons()
        self.widgets['manager_status'].set_subtitle('Running ' + action + '…')
        def worker():
            try:
                manager = self.runtime_manager
                if action == 'download':
                    result = manager.download_and_verify()
                elif action == 'backup':
                    result = 'Backup created: ' + manager.backup().name
                elif action == 'install':
                    result = manager.install_verified(confirmed=True)
                elif action == 'rollback':
                    backups = manager.list_backups()
                    if not backups:
                        raise ManagementError('No backups available')
                    result = manager.rollback(backups[0], confirmed=True)
                elif action in ('start', 'stop', 'restart'):
                    result = manager.service_action(action, confirmed=True)
                elif action in ('uninstall', 'purge_config'):
                    result = manager.uninstall(confirmed=True,
                                               remove_config=(action == 'purge_config'))
                else:
                    raise ManagementError('Unknown operation')
                error = None
            except (ManagementError, OSError, ValueError, RuntimeError) as exc:
                error, result = str(exc), None
            GLib.idle_add(self._management_done, action, result, error)
        threading.Thread(target=worker, daemon=True).start()

    def _management_done(self, action, result, error):
        self.runtime_management_busy = False
        self._refresh_manager_buttons()
        self.widgets['manager_status'].set_subtitle((error or result or 'No result')[:280])
        self._message(_('Runtime management failed') if error else _('Runtime management'),
                      error or result)
        self.local_installation = inspect_local_installation()
        self.widgets['local_install'].set_subtitle(
            _('User installation files detected') if self.local_installation.complete else
            _('Partial user installation files detected') if self.local_installation.installed else
            _('No local user Runtime detected'))
        # Status check remains read-only. Never auto-restart after install.
        return False

    def _message(self, title, detail):
        dialog = Adw.MessageDialog(transient_for=self.window, heading=title, body=str(detail))
        dialog.add_response('ok', 'OK')
        dialog.present()

    def _set_available(self, available):
        for key in ('endpoint', 'check', 'backend_preference'):
            self.widgets[key].set_sensitive(available)
        if not available:
            self.widgets['refresh_models'].set_sensitive(False)

    def _reset_idle_editor(self, message='Read-only until Runtime 1.0.0+ is verified'):
        self.idle_verified_seconds = None
        self.idle_verified_endpoint = None
        self.widgets['idle_spin'].set_sensitive(False)
        self.widgets['idle_save'].set_sensitive(False)
        self.widgets['idle_scope'].set_subtitle('Shared Runtime setting · ' + message)

    def _idle_save_clicked(self, _button):
        if (self.idle_saving or not self.config['enabled'] or
                self.idle_verified_seconds is None or
                self.idle_verified_endpoint != self.config['endpoint']):
            return
        seconds = self.widgets['idle_spin'].get_value_as_int()
        before = self.idle_verified_seconds
        if seconds == before:
            self._message(_('No changes'), _('The idle timeout already has this value.'))
            return
        endpoint = self.idle_verified_endpoint
        dialog = Adw.MessageDialog(transient_for=self.window,
                                   heading=_('Change shared Runtime idle timeout?'),
                                   body=(f'Current: {before} seconds. New: {seconds} seconds.\n'
                                         + ('0 disables automatic model unloading.\n' if seconds == 0 else '')
                                         + 'This affects other applications using this Runtime. '
                                           'It does not restart Runtime or unload a model immediately.'))
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('save', 'Change timeout')
        dialog.set_response_appearance('save', Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', self._idle_save_confirmed,
                       self.generation, endpoint, before, seconds)
        dialog.present()

    def _idle_save_confirmed(self, _dialog, response, generation, endpoint, before, seconds):
        if (response != 'save' or self.idle_saving or generation != self.generation or
                not self.config['enabled'] or endpoint != self.config['endpoint'] or
                self.idle_verified_seconds != before):
            return
        self.idle_saving = True
        self.widgets['idle_save'].set_sensitive(False)
        self.widgets['idle_spin'].set_sensitive(False)
        self.widgets['idle_scope'].set_subtitle(_('Saving confirmed timeout…'))

        def worker():
            try:
                value, error = change_idle_seconds(endpoint, seconds,
                                                   expected_seconds=before,
                                                   confirmed=True), None
            except (RuntimeIntegrationError, OSError, ValueError) as exc:
                value, error = None, str(exc)
            GLib.idle_add(self._idle_save_done, generation, endpoint, value, error)
        threading.Thread(target=worker, daemon=True).start()

    def _idle_save_done(self, generation, endpoint, value, error):
        self.idle_saving = False
        if generation != self.generation or endpoint != self.config['endpoint']:
            return False
        self._message(_('Cannot save shared timeout') if error else _('Runtime timeout updated'),
                      error or f'Saved {value} seconds to Local AI Runtime. No service restart.')
        self._start_probe(endpoint)  # always reread actual service state
        return False

    def _start_idle_read(self, generation, endpoint, version):
        def worker():
            outcome = read_idle_capability(endpoint, version)
            GLib.idle_add(self._idle_read_done, generation, endpoint, outcome)
        threading.Thread(target=worker, daemon=True).start()

    def _idle_read_done(self, generation, endpoint, outcome):
        if (generation != self.generation or not self.config['enabled'] or
                endpoint != self.config['endpoint'] or self.idle_saving):
            return False
        if not outcome.writable:
            self._reset_idle_editor(outcome.reason)
            return False
        self.idle_verified_seconds = outcome.seconds
        self.idle_verified_endpoint = endpoint
        self.widgets['idle_spin'].set_value(outcome.seconds)
        self.widgets['idle_spin'].set_sensitive(True)
        self.widgets['idle_save'].set_sensitive(True)
        self.widgets['idle_scope'].set_subtitle(
            _('Shared Runtime setting · editing requires confirmation · 0 disables unloading'))
        self.widgets['idle_unload'].set_subtitle(
            _('Disabled (0 seconds)') if outcome.seconds == 0 else
            f'{outcome.seconds} seconds · verified via Runtime preferences API')
        return False

    def _enabled_changed(self, switch, _property):
        enabled = switch.get_active()
        try:
            self.config = self.settings.update(enabled=enabled)
        except (OSError, RuntimeIntegrationError) as exc:
            self._message(_('Cannot save AI Runtime setting'), exc)
            switch.handler_block(self._enabled_handler)
            switch.set_active(self.config['enabled'])
            switch.handler_unblock(self._enabled_handler)
            return
        self.generation += 1
        self._reset_idle_editor()
        self._set_available(enabled)
        self.widgets['status'].set_subtitle(_('Not checked') if enabled else _('Integration disabled'))
        self.widgets['version_summary'].set_subtitle(_('Not checked'))
        self.widgets['effective'].set_subtitle(_('Not checked'))
        self.widgets['service_preference'].set_subtitle(_('Not checked'))
        self.widgets['actual'].set_subtitle(_('Not checked'))
        self.widgets['loaded'].set_subtitle(_('Not checked'))
        for key in ('preload', 'preload_state', 'idle_unload'):
            self.widgets[key].set_subtitle(_('Not checked'))
        self.widgets['installation_status'].set_subtitle(
            _('Not checked') if enabled else _('Integration disabled'))
        self._set_models(())
        self.registration_generation += 1
        if enabled:
            self._start_probe(self.config['endpoint'])

    def _backend_changed(self, dropdown, _property):
        preference = BACKEND_PREFERENCES[dropdown.get_selected()]
        if preference == self.config['backend_preference']:
            return
        try:
            self.config = self.settings.update(backend_preference=preference)
        except (OSError, RuntimeIntegrationError) as exc:
            self._message(_('Cannot save backend preference'), exc)
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
            self._message(_('Invalid Runtime endpoint'), exc)
            return
        self._start_probe(self.config['endpoint'])

    def _refresh_models_clicked(self, _button):
        if self.config['enabled'] and self.widgets['refresh_models'].get_sensitive():
            self._start_probe(self.config['endpoint'], refresh_models=True)

    def _start_probe(self, endpoint, *, refresh_models=False):
        self.backend_overview = None
        self.backend_overview_endpoint = None
        self._b4_buttons()
        self.backend_overview = None
        self.backend_overview_endpoint = None
        self._b4_buttons()
        self._reset_idle_editor()
        self.generation += 1
        self.registration_generation += 1
        generation = self.generation
        self.widgets['status'].set_subtitle(_('Connecting…'))
        self.widgets['check'].set_sensitive(False)
        self.widgets['refresh_models'].set_sensitive(False)
        self._set_models(())

        def work():
            try:
                outcome, error = probe_runtime(endpoint, refresh_models=refresh_models), None
            except (RuntimeIntegrationError, OSError) as exc:
                outcome, error = None, str(exc)
            GLib.idle_add(self._probe_done, generation, outcome, error)

        threading.Thread(target=work, daemon=True).start()

    def _probe_done(self, generation, result, error):
        if generation != self.generation or not self.config['enabled']:
            return False
        self.widgets['check'].set_sensitive(True)
        self.widgets['refresh_models'].set_sensitive(error is None)
        if error:
            self.widgets['status'].set_subtitle('Unavailable: ' + error[:180])
            self.widgets['version_summary'].set_subtitle(_('Unavailable'))
            self.widgets['effective'].set_subtitle(_('Not reported'))
            self.widgets['service_preference'].set_subtitle(_('Not reported'))
            self.widgets['actual'].set_subtitle(_('Not running'))
            self.widgets['loaded'].set_subtitle(_('Not loaded'))
            for key in ('preload', 'preload_state', 'idle_unload'):
                self.widgets[key].set_subtitle(_('Unavailable'))
            self.widgets['installation_status'].set_subtitle(
                _('Service not reachable · installation not determined'))
            return False
        self.widgets['status'].set_subtitle(_('Connected') + ' · ' + result.health)
        self.widgets['version_summary'].set_subtitle(result.version or _('Not reported'))
        self.widgets['effective'].set_subtitle(result.backend + (
            ' (query unavailable)' if result.backend_error else ''))
        self.widgets['service_preference'].set_subtitle(result.configured_backend or _('Not reported'))
        self.widgets['actual'].set_subtitle(
            result.active_backend if result.active_backend else
            (_('Running · backend unknown') if result.backend_running else _('Not running')))
        self.widgets['loaded'].set_subtitle(
            result.current_model if result.current_model else _('Not loaded'))
        self.widgets['preload'].set_subtitle(describe_preload(result))
        self.widgets['preload_state'].set_subtitle(result.preload_state or _('Not reported'))
        self.widgets['idle_unload'].set_subtitle(describe_idle_unload(result))
        self._start_idle_read(generation, result.endpoint, result.version)
        self.installed_runtime_version = result.version
        self.widgets['installation_status'].set_subtitle(
            'Connected service detected' +
            (f' · Runtime {result.version}' if result.version else '') +
            ' · version check available (manual)')
        self._set_models(result.models, snapshot=result)
        if result.models_error:
            self.widgets['models_placeholder'].set_title(_('Model query unavailable'))
            self.widgets['models_placeholder'].set_subtitle(result.models_error[:180])
        return False

    def _set_models(self, names, snapshot=None):
        group = self.widgets['models_group']
        for row in self.model_rows:
            group.remove(row)
        self.model_rows = []
        placeholder = self.widgets['models_placeholder']
        placeholder.set_title(_('No models reported'))
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

    def _check_release_clicked(self, _button):
        # B3-1 is intentionally read-only. A release-metadata lookup is NOT
        # an archive verification, and never starts an installer or service.
        if self.release_checking:
            return
        self.release_checking = True
        self.release_probe_generation += 1
        generation = self.release_probe_generation
        self.widgets['release_check'].set_sensitive(False)
        self.widgets['release_status'].set_subtitle(_('Checking official pinned release metadata…'))

        def worker():
            try:
                result, error = fetch_official_release(), None
            except (ReleaseCheckError, OSError, ValueError) as exc:
                result, error = None, str(exc)
            GLib.idle_add(self._release_check_done, generation, result, error)

        threading.Thread(target=worker, daemon=True).start()

    def _release_check_done(self, generation, result, error):
        if generation != self.release_probe_generation:
            return False
        self.release_checking = False
        self.widgets['release_check'].set_sensitive(True)
        if error:
            self.widgets['release_status'].set_subtitle('Release check unavailable · ' + error[:140])
            self.widgets['upgrade_preflight'].set_subtitle(_('Not verified · existing Runtime unchanged'))
            return False
        self.widgets['release_status'].set_subtitle(
            f'Official release {result.version} · {len(result.assets)} assets listed · no download')
        relation = compare_versions(self.installed_runtime_version, result.version)
        if not self.local_installation.installed:
            advice = 'No local installation detected · install needs separate B3-2 verification'
        elif relation == 'older':
            advice = (f'Runtime {self.installed_runtime_version} → {result.version} candidate · '
                      'installation and rollback NOT enabled')
        elif relation == 'equal':
            advice = f'Runtime {result.version} already reported · no update planned'
        elif relation == 'newer':
            advice = 'Installed service newer than pinned release · no downgrade available'
        else:
            advice = 'Cannot compare local service version · installation not enabled'
        self.widgets['upgrade_preflight'].set_subtitle(advice)
        return False

    def _open_instructions(self, _button):
        try:
            Gio.AppInfo.launch_default_for_uri(RUNTIME_PROJECT, None)
        except GLib.Error as exc:
            self._message(_('Could not open Runtime instructions'), exc)

    def _open_releases(self, _button):
        try:
            Gio.AppInfo.launch_default_for_uri(RUNTIME_RELEASES, None)
        except GLib.Error as exc:
            self._message(_('Could not open Runtime releases'), exc)

    def _choose_files(self, _button):
        dialog = Gtk.FileDialog.new()
        dialog.set_title(_('Select GGUF model files (main, mmproj, or splits)'))
        filt = Gtk.FileFilter()
        filt.set_name(_('GGUF models'))
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
            self._message(_('Local files only'), _('Please choose files on a local filesystem.'))
            return
        self._preview_async(paths=paths)

    def _choose_folder(self, _button):
        dialog = Gtk.FileDialog.new()
        dialog.set_title(_('Select local GGUF model folder'))
        dialog.select_folder(self.window, None, self._folder_chosen)

    def _folder_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result).get_path()
        except GLib.Error:
            return
        if not folder:
            self._message(_('Local folder only'), _('Please choose a local directory.'))
            return
        self._preview_async(folder=folder)

    def _preview_async(self, *, paths=None, folder=None):
        self.preview_generation += 1
        generation = self.preview_generation
        self.widgets['preview_placeholder'].set_visible(True)
        self.widgets['preview_placeholder'].set_title(_('Inspecting model files…'))
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
        placeholder.set_title(_('Cannot inspect model files') if error else _('No GGUF bundles found'))
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
            if bundle.ready_for_review and bundle.main and not bundle.shards and len(bundle.projectors) <= 1:
                inspect_button = Gtk.Button(label=_('Inspect with Runtime…'))
                inspect_button.set_valign(Gtk.Align.CENTER)
                inspect_button.set_sensitive(self.config['enabled'])
                inspect_button.connect('clicked', self._inspect_bundle, bundle)
                row.add_suffix(inspect_button)
        return False

    def _inspect_bundle(self, button, bundle):
        if not self.config['enabled'] or self.registration_in_progress:
            return
        self.registration_generation += 1
        generation = self.registration_generation
        endpoint = self.config['endpoint']
        button.set_sensitive(False)
        self.registration_in_progress = True

        def worker():
            try:
                review, error = inspect_registration(endpoint, bundle), None
            except (RuntimeIntegrationError, OSError, ValueError) as exc:
                review, error = None, str(exc)
            GLib.idle_add(self._inspect_done, generation, button, review, error)
        threading.Thread(target=worker, daemon=True).start()

    def _inspect_done(self, generation, button, review, error):
        self.registration_in_progress = False
        if generation != self.registration_generation or not self.config['enabled']:
            return False
        button.set_sensitive(True)
        if error:
            self._message(_('Runtime inspection failed'), error)
            return False
        payload = review.payload
        message = '\n'.join((
            'Model ID: ' + payload['id'],
            'Purpose: ' + payload['type'],
            'Main GGUF: ' + payload['model_path'],
            'Projector: ' + (payload['mmproj_path'] or 'None'),
            'Context: ' + str(payload['context_size']),
            'GPU layers: ' + str(payload['gpu_layers']),
            'Warnings: ' + ('; '.join(review.notes) if review.notes else 'None'),
            '',
            'The model files remain in place. Register only if you trust their origin. '
            'This changes the external Runtime custom-model registry, not the model files.'
        ))
        dialog = Adw.MessageDialog(transient_for=self.window,
                                   heading=_('Register this local model?'), body=message)
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('register', 'Register model')
        dialog.set_response_appearance('register', Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', self._registration_response, review)
        dialog.present()
        return False

    def _registration_response(self, _dialog, response, review):
        if response != 'register' or not self.config['enabled'] or self.registration_in_progress:
            return
        if self.config['endpoint'] != review.endpoint:
            self._message(_('Connection changed'), _('Reconnect and inspect the model again.'))
            return
        self.registration_in_progress = True
        self.registration_generation += 1
        generation = self.registration_generation

        def worker():
            try:
                result, error = register_reviewed_model(review, confirmed=True), None
            except (RuntimeIntegrationError, OSError, ValueError) as exc:
                result, error = None, str(exc)
            GLib.idle_add(self._registration_done, generation, result, error)
        threading.Thread(target=worker, daemon=True).start()

    def _registration_done(self, generation, result, error):
        self.registration_in_progress = False
        if generation != self.registration_generation:
            return False
        if error:
            self._message(_('Registration failed'), error)
        else:
            self._message(_('Model registered'),
                          result['id'] + ' was added to Local AI Runtime. No model files were moved.')
            if self.config['enabled']:
                self._start_probe(self.config['endpoint'], refresh_models=True)
        return False
