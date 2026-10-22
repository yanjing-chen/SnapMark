"""SnapMark C3 interface localization shared by core and optional plugins.

User OCR/translations, filenames, editable text, and model identifiers must not
be modified by interface localization. Translations are gettext catalog entries,
not runtime machine translation. Plugin-specific catalogs have priority when
available; missing strings fall back to the core domain, then English.
"""
from __future__ import annotations
import gettext
import os
from pathlib import Path

DOMAIN = 'snapmark'
LOCALE_DIR = Path(__file__).resolve().parent / 'locale'
# Only two selectable languages ship in C3: English and Simplified Chinese.
# Legacy 'system' is accepted internally but is not offered in the UI.
LANGUAGES = (
    ('zh_CN', 'Chinese (Simplified)', '简体中文'),
    ('en', 'English', 'English'),
)
assert len(LANGUAGES) == 2
assert [name.casefold() for _, name, _ in LANGUAGES] == sorted(name.casefold() for _, name, _ in LANGUAGES)
CODES = frozenset(code for code, _, _ in LANGUAGES)
_current_code = 'system'
_current = gettext.NullTranslations()
_cache = {}


def language_options():
    """Two selectable languages; no legacy System Default menu item."""
    return [(code, f'{english} ({native})' if english != native else english)
            for code, english, native in LANGUAGES]


def configure(code='system'):
    global _current_code, _current
    if code != 'system' and code not in CODES:
        raise ValueError('Unsupported interface language')
    _current_code = code
    _cache.clear()
    _current = gettext.translation(DOMAIN, localedir=str(LOCALE_DIR),
                                   languages=None if code == 'system' else [code],
                                   fallback=True)


def _(message):
    return _current.gettext(message)


def plugin_gettext(plugin_id, message, plugin_path=None):
    """Look up optional plugin's own gettext domain, then host SnapMark catalog.

    Plugin ZIPs may supply locale/<lang>/LC_MESSAGES/snapmark-<id>.mo.
    Host's bundled catalogs are used if older plugin ZIPs have no translations.
    """
    if not isinstance(message, str):
        return message
    if plugin_id not in ('ocr', 'translation'):
        return _(message)
    root = Path(plugin_path).resolve() if plugin_path else LOCALE_DIR
    locale_dir = root / 'locale' if plugin_path else LOCALE_DIR
    key = (_current_code, plugin_id, str(locale_dir))
    if key not in _cache:
        _cache[key] = gettext.translation('snapmark-' + plugin_id,
                                          localedir=str(locale_dir),
                                          languages=None if _current_code == 'system' else [_current_code],
                                          fallback=True)
    result = _cache[key].gettext(message)
    if result == message and locale_dir != LOCALE_DIR:
        # Older localized ZIP might carry only a partial catalog.
        result = plugin_gettext(plugin_id, message)
    return _(message) if result == message else result


def localize_widget_tree(root, plugin_id=None, plugin_path=None, max_widgets=5000):
    """Legacy compatibility for unit-test doubles and older non-GTK adapters.

    GTK/Adwaita widgets MUST be translated when they are created, not by walking
    a live GTK child/sibling tree. Traversing real GTK widget ownership has
    caused crashes in C3.  UI constructors now call gettext directly.
    Never inspect or modify text buffers or editable user content.
    """
    if root is None or getattr(type(root), '__gtype__', None) is not None:
        return 0
    translator = ((lambda s: plugin_gettext(plugin_id, s, plugin_path))
                  if plugin_id in ('ocr', 'translation') else _)
    visited = set()
    pending = [root]
    count = 0
    while pending and count < max_widgets:
        widget = pending.pop()
        if id(widget) in visited:
            continue
        visited.add(id(widget))
        count += 1
        for name in ('label', 'title', 'subtitle', 'description',
                     'tooltip_text', 'placeholder_text'):
            getter = getattr(widget, 'get_' + name, None)
            setter = getattr(widget, 'set_' + name, None)
            if not callable(getter) or not callable(setter):
                continue
            try:
                value = getter()
                if isinstance(value, str) and value:
                    translated = translator(value)
                    if translated != value:
                        setter(translated)
            except (TypeError, ValueError, RuntimeError, AttributeError):
                pass
        get_first = getattr(widget, 'get_first_child', None)
        if callable(get_first):
            try:
                child = get_first()
                while child is not None and len(pending) < max_widgets:
                    pending.append(child)
                    sibling = getattr(child, 'get_next_sibling', None)
                    child = sibling() if callable(sibling) else None
            except (TypeError, ValueError, RuntimeError, AttributeError):
                pass
    return count
