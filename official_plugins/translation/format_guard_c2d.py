"""Protect executable/technical substrings during human-language translation.

Pure Python, offline and deterministic. Only text is changed; never runs code.
"""
from __future__ import annotations

import re

MARKER_PATTERN = re.compile(r'\[\[SMTECH_[0-9]{5}\]\]')
FENCE = re.compile(r'(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*(?=\n|\Z)')
# All these matches are atomic: preserve whole commands, not just their arguments.
COMMAND_LINE = re.compile(
    r'(?m)^(?:[ \t]*)(?:(?:\$|>)\s*)?'
    r'(?:sudo|cd|bash|sh|python(?:3(?:\.\d+)?)?|git|curl|wget|'
    r'apt(?:-get)?|pip(?:3)?|mkdir|cp|mv|rm|chmod|chown|'
    r'unzip|sha256sum|export|systemctl|journalctl|grep|find)'
    r'\b[^\n]*'
)
INLINE = re.compile(r'`+[^`\n]+`+')
URL = re.compile(r'(?i)\b(?:https?://|ftp://)[^\s<>"\']+')
PATH = re.compile(
    r'(?<![\w])(?:~/|\./|\.\./|/(?:home|mnt|tmp|etc|usr|opt|var|run|media)/)'
    r'[^\s\]\[(){}<>"\'，。；：！？、]+'
)
FLAGS = re.compile(r'(?<![\w-])--[a-zA-Z][a-zA-Z0-9_-]*(?:=[^\s,;]+)?')
FILES = re.compile(r'(?<![\w])(?:[\w-]+\.)+(?:sh|py|json|yaml|yml|txt|md|gguf|onnx|pdf|zip|csv|xlsx|docx|png|jpg|jpeg|deb|AppImage)\b', re.I)
# Do not protect ordinary Chinese or Dutch text, even if it contains version numbers.
MODEL_IDS = re.compile(r'(?<![\w])(?:[A-Za-z][A-Za-z0-9]*-){2,}[A-Za-z0-9._-]+')


def protect(source: str):
    """Return a model-safe source string and exact originals keyed by markers.

    Processes longer spans first to avoid accidental nested placeholders.
    """
    if not isinstance(source, str):
        raise TypeError('Source must be text')
    if MARKER_PATTERN.search(source):
        raise ValueError('Source contains a reserved technical placeholder')
    current = source
    replacements: dict[str, str] = {}
    for pattern in (FENCE, COMMAND_LINE, INLINE, URL, PATH, FLAGS, FILES, MODEL_IDS):
        def swap(match):
            raw = match.group(0)
            # Skip items previously replaced with our markers.
            if MARKER_PATTERN.search(raw):
                return raw
            # Trim punctuation added by a prose sentence, but not interior characters.
            trailing = ''
            if pattern in (URL, PATH):
                stripped = raw.rstrip('.,;:!?。，；：！？')
                trailing = raw[len(stripped):]
                raw = stripped
            if not raw:
                return match.group(0)
            if len(replacements) >= 99999:
                raise ValueError('Too many protected tokens')
            marker = f'[[SMTECH_{len(replacements):05d}]]'
            replacements[marker] = raw
            return marker + trailing
        current = pattern.sub(swap, current)
    return current, replacements


def restore(translated: str, replacements: dict[str, str]):
    """Fail closed if a model changes or drops any placeholder."""
    if not isinstance(translated, str) or not translated.strip():
        raise ValueError('Translation was empty')
    found = MARKER_PATTERN.findall(translated)
    expected = set(replacements)
    if set(found) != expected or len(found) != len(replacements):
        raise ValueError('Translation model altered or omitted protected technical text; original commands have not been changed')
    for marker, original in replacements.items():
        translated = translated.replace(marker, original)
    return translated
