"""SnapMark plugin API v1: controlled UI extension points for official plugins.

Plugins are executable user-level Python code. A package must originate from
SnapMark's official release channel. API registration belongs on GTK main loop.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .plugins import PluginError, valid_plugin_id


class PluginHost:
    API_VERSION = 1

    def __init__(self, editor):
        self.editor = editor
        self._loading_plugin_id = None
        self._loading_manager = None
        self.settings_factories = {}  # plugin id -> (title, builder)
        self.text_providers = {}  # registered plugin id -> current text getter

    def _check(self, plugin_id):
        if not valid_plugin_id(plugin_id):
            raise PluginError('Invalid plugin ID')
        if self._loading_plugin_id is None or self._loading_manager is None:
            raise PluginError('Plugin registration outside the active loader')
        if plugin_id != self._loading_plugin_id:
            raise PluginError('Plugin attempted registration under another ID')
        if not self._loading_manager.is_available(plugin_id):
            raise PluginError('Only enabled, dependency-ready plugins can register')

    def register_toolbar_action(self, plugin_id, label, callback):
        if not isinstance(label, str) or not callable(callback):
            raise PluginError('Invalid toolbar action registration')
        self._check(plugin_id)
        self.editor.add_plugin_action(plugin_id, label, callback)

    def register_preferences_page(self, plugin_id, title, builder):
        if not isinstance(title, str) or not callable(builder):
            raise PluginError('Invalid plugin preferences registration')
        self._check(plugin_id)
        if plugin_id in self.settings_factories:
            raise PluginError('Duplicate preferences registration')
        self.settings_factories[plugin_id] = (title, builder)

    def register_result_panel(self, plugin_id, title, builder):
        if not isinstance(title, str) or not callable(builder):
            raise PluginError('Invalid plugin result registration')
        self._check(plugin_id)
        self.editor.add_plugin_result(plugin_id, title, builder)

    def register_text_provider(self, plugin_id, getter):
        """Expose current, user-edited OCR text to the optional translation plugin."""
        if not callable(getter):
            raise PluginError('Invalid text provider')
        self._check(plugin_id)
        self.text_providers[plugin_id] = getter

    def get_text_provider(self, plugin_id):
        if not valid_plugin_id(plugin_id):
            raise PluginError('Invalid text provider ID')
        return self.text_providers.get(plugin_id)


def load_plugin(manager, ident, host):
    """Load enabled official plugin entrypoint from its own version directory.

    Caller catches and reports failures; never load a disabled plugin.
    """
    if not valid_plugin_id(ident) or not manager.is_available(ident):
        return False
    selected = manager.selected(ident)
    manifest = manager.manifest(ident, selected)
    entry = manifest.get('entrypoint')
    if not entry:
        return False
    module, function = entry.split(':', 1)
    root = manager.root / ident / selected
    source = root.joinpath(*module.split('.')).with_suffix('.py')
    if not source.is_file() or not source.resolve().is_relative_to(root.resolve()):
        raise PluginError('Plugin entrypoint is missing or escapes plugin directory')
    name = f'_snapmark_plugin_{ident}_{selected.replace(".", "_")}_{module.replace(".", "_")}'
    spec = importlib.util.spec_from_file_location(name, source)
    if not spec or not spec.loader:
        raise PluginError('Unable to load plugin module')
    instance = importlib.util.module_from_spec(spec)
    sys.modules[name] = instance
    if host._loading_plugin_id is not None:
        raise PluginError('Recursive plugin registration is not allowed')
    host._loading_plugin_id = ident
    host._loading_manager = manager
    try:
        spec.loader.exec_module(instance)
        register = getattr(instance, function, None)
        if not callable(register):
            raise PluginError('Plugin entrypoint is not callable')
        register(host)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    finally:
        host._loading_plugin_id = None
        host._loading_manager = None
    return True
