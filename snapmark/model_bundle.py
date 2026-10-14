"""Offline, read-only inspection of user-selected local GGUF model bundles.

This module NEVER changes a model or the external AI Runtime registry. The
preview is not a registration API and does not prove that Runtime can load it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MAX_FILES = 64
MAX_DIRECTORY_ENTRIES = 1000
_SPLIT = re.compile(r'^(.*)-(\d{5})-of-(\d{5})$', re.IGNORECASE)
_PROJECTOR = re.compile(r'(?i)(?:^mmproj[-_.]?|[-_.]mmproj(?:[-_.]|$))')


class ModelBundleError(ValueError):
    """Bad, incomplete, or ambiguous local model selection."""


@dataclass(frozen=True)
class ModelBundle:
    name: str
    main: Path | None
    shards: tuple[Path, ...]
    projectors: tuple[Path, ...]
    total_bytes: int
    warnings: tuple[str, ...]

    @property
    def ready_for_review(self) -> bool:
        """Files are coherent enough to review, NOT guaranteed loadable."""
        return self.main is not None and not any('Missing split' in x or 'Multiple ' in x or 'Invalid' in x
                                                     for x in self.warnings)


def _key(path: Path) -> tuple[str, bool, int | None, int | None]:
    stem = path.stem
    match = _SPLIT.match(stem)
    part, total = (int(match.group(2)), int(match.group(3))) if match else (None, None)
    if match:
        stem = match.group(1)
    is_projector = bool(_PROJECTOR.search(stem))
    if is_projector:
        stem = re.sub(r'(?i)(?:^mmproj[-_.]?|[-_.]mmproj(?=[-_.]|$))', '', stem)
        stem = stem.strip('-_. ')
    return stem.casefold(), is_projector, part, total


def _local_files(paths: Iterable[str | Path], *, find_companions: bool) -> list[Path]:
    selected = [Path(p).expanduser() for p in paths]
    if not selected:
        raise ModelBundleError('Select at least one GGUF file.')
    if len(selected) > MAX_FILES:
        raise ModelBundleError('Too many model files selected (maximum 64).')
    resolved: dict[Path, Path] = {}
    for path in selected:
        if path.suffix.lower() != '.gguf' or not path.is_file():
            raise ModelBundleError(f'Not a regular GGUF file: {path.name}')
        resolved[path.resolve()] = path.resolve()
    if find_companions:
        # Only inspect the immediate parent of EXPLICITLY selected files. Never
        # traverse a home directory or recursively search arbitrary drives.
        for parent in {p.parent for p in resolved}:
            entries = list(parent.iterdir())
            if len(entries) > MAX_DIRECTORY_ENTRIES:
                raise ModelBundleError('Selected folder has too many entries; choose files explicitly.')
            for child in entries:
                if child.suffix.lower() != '.gguf' or not child.is_file():
                    continue
                path = child.resolve()
                if path in resolved:
                    continue
                # Restrict companions to matching model names, never silently
                # combine unrelated models located in the same folder.
                if any(_key(path)[0] == _key(sel)[0] for sel in selected):
                    resolved[path] = path
                if len(resolved) > MAX_FILES:
                    raise ModelBundleError('Too many companion files (maximum 64).')
    return sorted(resolved.values(), key=lambda p: str(p).casefold())


def inspect_gguf_files(paths: Iterable[str | Path], *, find_companions: bool = True) -> tuple[ModelBundle, ...]:
    """Identify main GGUF, mmproj, and numbered shards as *one* logical model.

    No content is copied, downloaded, executed or registered. Every file needs
    to carry the GGUF header; model-specific backend compatibility is unknown.
    """
    candidates = _local_files(paths, find_companions=find_companions)
    grouped: dict[tuple[str, Path], list[tuple[Path, bool, int | None, int | None]]] = {}
    for path in candidates:
        try:
            with path.open('rb') as handle:
                if handle.read(4) != b'GGUF':
                    raise ModelBundleError(f'Invalid GGUF header: {path.name}')
        except OSError as exc:
            raise ModelBundleError(f'Cannot read {path.name}: {exc}') from exc
        key, projector, part, total = _key(path)
        grouped.setdefault((key, path.parent), []).append((path, projector, part, total))
    bundles = []
    for (key, _folder), parts in sorted(grouped.items(), key=lambda item: str(item[0])):
        mains = sorted((p, idx, total) for p, proj, idx, total in parts if not proj)
        projector_paths = tuple(sorted(p for p, proj, _, _ in parts if proj))
        warnings: list[str] = []
        main = None
        shards = ()
        if not mains:
            warnings.append('No main model GGUF was found; select it as well.')
        elif len(mains) == 1 and mains[0][1] is None:
            main = mains[0][0]
        elif all(idx is not None for _, idx, _ in mains):
            declared = {total for _, _, total in mains}
            numbers = {idx for _, idx, _ in mains}
            if len(declared) != 1 or 0 in numbers or not all(idx <= total for _, idx, total in mains):
                warnings.append('Invalid or inconsistent split GGUF sequence.')
            else:
                expected = next(iter(declared))
                absent = sorted(set(range(1, expected + 1)) - numbers)
                if absent:
                    warnings.append('Missing split parts: ' + ', '.join(str(x) for x in absent))
            shards = tuple(p for p, idx, _ in sorted(mains, key=lambda x: x[1]))
            main = shards[0] if shards and _key(shards[0])[2] == 1 else None
        else:
            warnings.append('Multiple main GGUF candidates; choose one model per bundle.')
        if len(projector_paths) > 1:
            warnings.append('Multiple mmproj candidates; select the correct one in Runtime.')
        if not projector_paths and any(hint in key for hint in ('ocr', '-vl', 'vision', 'multimodal')):
            warnings.append('Vision model may require an mmproj; confirm its model requirements.')
        bundles.append(ModelBundle(
            name=key, main=main, shards=shards, projectors=projector_paths,
            total_bytes=sum(p.stat().st_size for p, _, _, _ in parts),
            warnings=tuple(warnings)))
    return tuple(bundles)


def inspect_gguf_folder(folder: str | Path) -> tuple[ModelBundle, ...]:
    """Scan only one explicitly selected directory, without recursion."""
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise ModelBundleError('Select an existing model directory.')
    entries = list(root.iterdir())
    if len(entries) > MAX_DIRECTORY_ENTRIES:
        raise ModelBundleError('Folder has too many entries; choose GGUF files explicitly.')
    candidates = [p for p in entries if p.suffix.lower() == '.gguf' and p.is_file()]
    if not candidates:
        raise ModelBundleError('No GGUF files found in the selected folder.')
    return inspect_gguf_files(candidates, find_companions=False)
