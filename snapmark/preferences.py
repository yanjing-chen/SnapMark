"""Application preferences; no GSettings schema or system setting changes."""
import configparser
import json
import os
import shutil
from pathlib import Path

APP_ID = 'io.github.yanjingchen.SnapMark'


def configuration_dir() -> Path:
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'snapmark'


class Settings:
    def __init__(self, root=None):
        self.root = Path(root) if root else configuration_dir()
        self.file = self.root / 'preferences.json'

    def load(self) -> dict:
        try:
            data = json.loads(self.file.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                directory = data.get('screenshot_directory', '')
                return {'screenshot_directory': directory if isinstance(directory, str) else ''}
        except (FileNotFoundError, OSError, ValueError):
            pass
        return {'screenshot_directory': ''}

    def screenshot_directory(self) -> str:
        return self.load()['screenshot_directory']

    def set_screenshot_directory(self, value: str):
        self.root.mkdir(parents=True, exist_ok=True)
        if value:
            target = Path(value).expanduser().resolve(strict=False)
            if not target.is_dir():
                raise ValueError('Screenshot folder must exist')
            value = str(target)
        import tempfile
        fd, name = tempfile.mkstemp(prefix='.snapmark-', dir=self.root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump({'screenshot_directory': value}, output, ensure_ascii=False, indent=2)
                output.write('\n')
            os.replace(name, self.file)
        finally:
            if os.path.exists(name):
                os.unlink(name)


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
                    f'Exec={quoted} --watch\n'
                    'Terminal=false\nX-GNOME-Autostart-enabled=true\n')
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(contents, encoding='utf-8')
