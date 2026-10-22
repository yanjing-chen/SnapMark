"""Application preferences; no GSettings schema or system setting changes."""
import configparser
import json
import os
import shutil
from pathlib import Path

APP_ID = 'io.github.yanjingchen.SnapMark'


def valid_color(value):
    return isinstance(value, str) and len(value) == 7 and value.startswith('#') and all(c in '0123456789abcdefABCDEF' for c in value[1:])



def configuration_dir() -> Path:
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'snapmark'


class Settings:
    DEFAULTS = {'screenshot_directory': '', 'start_minimized': False,
                'recent_colors': [], 'image_format': 'png', 'image_quality': 90, 'language': 'system'}

    def __init__(self, root=None):
        self.root = Path(root) if root else configuration_dir()
        self.file = self.root / 'preferences.json'

    def load(self) -> dict:
        data = {}
        try:
            source = json.loads(self.file.read_text(encoding='utf-8'))
            if isinstance(source, dict):
                data = source
        except (FileNotFoundError, OSError, ValueError):
            pass
        result = self.DEFAULTS.copy()
        from .i18n import CODES
        lang = data.get('language', 'system')
        # Older C3 releases allowed 30 languages and 'system'. Read them safely
        # without changing the user's preferences.json or any other setting.
        # An unsupported former explicit language (including nl) falls back
        # to English; legacy 'system' follows the OS only for Simplified Chinese.
        if lang == 'system':
            env = next((os.environ.get(k, '') for k in ('LC_ALL', 'LC_MESSAGES', 'LANGUAGE', 'LANG')
                        if os.environ.get(k)), '')
            result['language'] = 'zh_CN' if env.lower().replace('-', '_').startswith('zh_cn') else 'en'
        else:
            result['language'] = lang if lang in CODES else 'en'
        result['screenshot_directory'] = data.get('screenshot_directory', '') if isinstance(data.get('screenshot_directory', ''), str) else ''
        result['start_minimized'] = data.get('start_minimized', False) is True
        recent = data.get('recent_colors', [])
        result['recent_colors'] = [c.lower() for c in recent if valid_color(c)][:6] if isinstance(recent, list) else []
        raw_format = data.get('image_format', 'png')
        result['image_format'] = raw_format if raw_format in ('png', 'jpeg', 'webp') else 'png'
        raw_quality = data.get('image_quality', 90)
        result['image_quality'] = raw_quality if type(raw_quality) is int and 1 <= raw_quality <= 100 else 90
        return result

    def language(self):
        return self.load()['language']

    def set_language(self, code):
        from .i18n import CODES
        if code != 'system' and code not in CODES:
            raise ValueError('Unsupported interface language')
        data = self.load()
        data['language'] = code
        self._save(data)

    def image_format(self):
        return self.load()['image_format']
    def set_image_format(self, value):
        if value not in ('png', 'jpeg', 'webp'):
            raise ValueError('Unsupported export format')
        data = self.load()
        data['image_format'] = value
        self._save(data)
    def image_quality(self):
        return self.load()['image_quality']
    def set_image_quality(self, value):
        if type(value) is not int or not 1 <= value <= 100:
            raise ValueError('Image quality must be 1–100')
        data = self.load()
        data['image_quality'] = value
        self._save(data)
    def _save(self, data):
        self.root.mkdir(parents=True, exist_ok=True)
        import tempfile
        fd, name = tempfile.mkstemp(prefix='.snapmark-', dir=self.root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.write('\n')
            os.replace(name, self.file)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def screenshot_directory(self) -> str:
        return self.load()['screenshot_directory']

    def set_screenshot_directory(self, value: str):
        if value:
            target = Path(value).expanduser().resolve(strict=False)
            if not target.is_dir():
                raise ValueError('Screenshot folder must exist')
            value = str(target)
        data = self.load()
        data['screenshot_directory'] = value
        self._save(data)

    def start_minimized(self) -> bool:
        return self.load()['start_minimized']

    def set_start_minimized(self, enabled: bool):
        data = self.load()
        data['start_minimized'] = bool(enabled)
        self._save(data)

    def recent_colors(self) -> list[str]:
        return self.load()['recent_colors']

    def remember_color(self, color: str):
        if not valid_color(color):
            raise ValueError('Expected a 6-digit hex color')
        color = color.lower()
        data = self.load()
        data['recent_colors'] = [color] + [c for c in data['recent_colors'] if c != color]
        data['recent_colors'] = data['recent_colors'][:6]
        self._save(data)


class Autostart:
    def __init__(self, config_home=None):
        home = Path(config_home) if config_home else Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
        self.file = home / 'autostart' / (APP_ID + '-watcher.desktop')

    def enabled(self) -> bool:
        if not self.file.is_file():
            return False
        cfg = configparser.ConfigParser(interpolation=None)
        try:
            cfg.read(self.file, encoding='utf-8')
            section = cfg['Desktop Entry']
            return (section.get('Name') == 'SnapMark Screenshot Watcher'
                    and section.get('Hidden', 'false').lower() != 'true')
        except (OSError, KeyError, configparser.Error):
            return False

    @staticmethod
    def launcher() -> str | None:
        appimage = os.environ.get('APPIMAGE')
        if appimage:
            path = Path(appimage).expanduser().resolve(strict=False)
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
        local = Path.home() / '.local/bin/snapmark'
        if local.is_file() and os.access(local, os.X_OK):
            return str(local)
        which = shutil.which('snapmark')
        return which

    def set_enabled(self, enable: bool):
        if not enable:
            # Never remove an unrelated user's autostart file.
            if self.enabled():
                self.file.unlink()
            return
        executable = self.launcher()
        if not executable:
            raise ValueError('Run from AppImage or install the SnapMark launcher first')
        if self.file.exists() and not self.enabled():
            raise ValueError('Autostart file exists with unexpected content; it was not overwritten')
        quoted = '"' + executable.replace('\\', '\\\\').replace('"', '\\"') + '"'
        contents = ('[Desktop Entry]\nType=Application\n'
                    'Name=SnapMark Screenshot Watcher\n'
                    'Comment=Open GNOME screenshots automatically in SnapMark\n'
                    f'Exec={quoted} --login-start\n'
                    'Terminal=false\nX-GNOME-Autostart-enabled=true\n')
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(contents, encoding='utf-8')
