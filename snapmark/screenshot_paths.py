"""Pure-Python screenshot path rules, independent of GTK.

Some localized GNOME installations create ~/图片/截图 rather than an
English Screenshots folder.
"""
import os
from pathlib import Path

IMAGE_SUFFIXES = frozenset({'.png', '.jpg', '.jpeg', '.webp'})
SCREENSHOT_FOLDER_NAMES = frozenset({
    'screenshots', 'screenshot', '截图', '屏幕截图', '截屏',
    'capturas de pantalla', 'bildschirmfotos', 'captures d’écran',
})
SCREENSHOT_FILE_PREFIXES = (
    'screenshot', 'screen shot', 'screen capture',
    '截图', '屏幕截图', '截屏',
    'capture d’écran', "capture d'ecran", 'bildschirmfoto',
    'captura de pantalla', 'schermafbeelding',
)


def is_screenshot_name(name: str) -> bool:
    item = Path(name)
    return (item.suffix.casefold() in IMAGE_SUFFIXES and
            item.name.casefold().startswith(SCREENSHOT_FILE_PREFIXES))


def is_screenshot_folder(name: str) -> bool:
    return name.casefold() in SCREENSHOT_FOLDER_NAMES


def monitored_directories(pictures_dir: Path, home: Path | None = None,
                          custom_dir: str | None = None) -> list[Path]:
    """Existing screenshot folders plus Pictures root for new directory discovery."""
    pictures_dir = Path(pictures_dir).expanduser()
    home = Path(home) if home else Path.home()
    candidates = [pictures_dir]
    for name in ('截图', 'Screenshots', '屏幕截图', '截屏'):
        candidates.append(pictures_dir / name)
    try:
        candidates.extend(p for p in pictures_dir.iterdir()
                          if p.is_dir() and is_screenshot_folder(p.name))
    except OSError:
        pass
    candidates.extend([home / 'Pictures' / 'Screenshots', home / '图片' / '截图'])
    custom = custom_dir if custom_dir is not None else os.environ.get('SNAPMARK_SCREENSHOT_DIR')
    if custom:
        candidates.append(Path(custom).expanduser())
    found: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        normalized = candidate.resolve(strict=False)
        if normalized not in seen and normalized.is_dir():
            seen.add(normalized)
            found.append(normalized)
    return found
