"""Local-only text translation via the shared Runtime OpenAI-compatible API.

Pure Python: no GTK and no model/package install. All network requests stay
on localhost; a translation POST may cause the user's registered model to load.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ENDPOINT = 'http://127.0.0.1:8111'

# Loaded by file path because official plugins are installed in versioned
# directories and have no conventional Python package import context.
_guard_spec = importlib.util.spec_from_file_location(
    'snapmark_translation_format_guard', Path(__file__).with_name('format_guard_c2d.py'))
if _guard_spec is None or _guard_spec.loader is None:
    raise RuntimeError('Missing technical-format protection module')
_guard = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(_guard)


class TranslationError(ValueError):
    pass


def _endpoint(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment or not parsed.port):
        raise TranslationError('Translation must use a local Runtime HTTP endpoint')
    return url.rstrip('/')


def _request(endpoint, path, *, payload=None, timeout=10):
    base = _endpoint(endpoint)
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(base + path, data=data,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST' if payload is not None else 'GET')
    # Bypass environment proxy settings even for loopback, including on Ubuntu.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        # Error body should not be surfaced wholesale; it can contain request text.
        raise TranslationError(f'Runtime API HTTP {exc.code} on {path}') from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise TranslationError(f'Cannot contact Runtime on {base}: {exc}') from exc
    if not isinstance(result, dict):
        raise TranslationError('Runtime returned malformed JSON')
    return result


def registered_models(listing):
    """Only installed models explicitly registered as translation (never OCR)."""
    entries = listing.get('data', listing.get('models', [])) if isinstance(listing, dict) else None
    if not isinstance(entries, list):
        raise TranslationError('Runtime model list is malformed')
    found = []
    for item in entries:
        if not isinstance(item, dict) or item.get('installed') is not True:
            continue
        kind = item.get('type')
        if kind is not None and kind != 'translation':
            continue
        caps = item.get('capabilities')
        if not isinstance(caps, dict) or caps.get('translation') is not True:
            continue
        identifier = item.get('id') or item.get('name')
        if isinstance(identifier, str) and identifier.strip() and identifier.strip() not in found:
            found.append(identifier.strip())
    return found


def list_translation_models(endpoint=ENDPOINT):
    return registered_models(_request(endpoint, '/v1/models', timeout=5))


def choose_model(listing):
    models = registered_models(listing)
    if not models:
        raise TranslationError('No installed translation-capable model. Register or install a translation model in AI Runtime first.')
    return next((mid for mid in models if 'hy-mt' in mid.casefold()), models[0])


def translate(source_text, target_language, *, endpoint=ENDPOINT, model_id=None):
    if not isinstance(source_text, str) or not source_text.strip():
        raise TranslationError('OCR text is empty; enter or recognize some text first')
    if not isinstance(target_language, str) or not target_language.strip():
        raise TranslationError('Choose a target language')
    if len(source_text) > 24000:
        raise TranslationError('Text is too long for one request (maximum 24,000 characters)')
    listing = _request(endpoint, '/v1/models', timeout=10)
    eligible = registered_models(listing)
    if model_id is not None:
        if model_id not in eligible:
            raise TranslationError('Selected model is not installed and registered for translation. Refresh the catalog.')
        model = model_id
    else:
        model = choose_model(listing)
    try:
        protected_source, protected_tokens = _guard.protect(source_text)
    except (TypeError, ValueError) as exc:
        raise TranslationError(f'Cannot protect technical text: {exc}') from exc
    # No source-language setting: the model is instructed to detect it itself.
    prompt = ('Translate the following text into ' + target_language.strip() +
              '. Automatically identify the source language. Preserve meaning, names, '
              'paragraph breaks and formatting as faithfully as possible. '
              'Return ONLY the translation, without introductions or explanations.')
    if protected_tokens:
        prompt += (' IMPORTANT: Technical placeholders of the form '
                   '[[SMTECH_00000]] represent protected command lines, file paths, '
                   'code blocks, URLs and model identifiers. Keep each placeholder '
                   'EXACTLY unchanged and present exactly once. Translate surrounding '
                   'natural-language text only. Never translate, split, remove, '
                   'duplicate or reinterpret a placeholder.')
    response = _request(endpoint, '/v1/chat/completions', payload={
        'model': model,
        'messages': [{'role': 'system', 'content': prompt},
                     {'role': 'user', 'content': protected_source}],
        'stream': False, 'temperature': 0.0,
    }, timeout=240)
    try:
        content = response['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise TranslationError('Runtime returned no translation text') from exc
    if not isinstance(content, str) or not content.strip():
        raise TranslationError('Runtime returned an empty translation')
    try:
        safe_translation = _guard.restore(content.strip(), protected_tokens)
    except ValueError as exc:
        raise TranslationError(str(exc)) from exc
    return safe_translation, model
