"""Read-only role-filtered OCR catalog; user installs/registers models in Preferences.

The editor must not install models. Model type is authoritative when supplied;
otherwise an explicit capability flag is required. Never infer OCR capability
from an ID, a family name or an installed vision/chat model.
"""
from __future__ import annotations
import json
import os
import urllib.request
from pathlib import Path

ENDPOINT = 'http://127.0.0.1:8111'


def registered_for(item, purpose):
    if not isinstance(item, dict) or item.get('installed') is not True:
        return False
    ident = item.get('id') or item.get('name')
    if not isinstance(ident, str) or not ident.strip():
        return False
    model_type = item.get('type')
    if model_type is not None and model_type != purpose:
        return False
    cap = item.get('capabilities')
    return isinstance(cap, dict) and cap.get(purpose) is True


def runtime_models(payload, purpose):
    entries = payload.get('data', payload.get('models', [])) if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError('Runtime returned an invalid model catalog')
    result = []
    for item in entries:
        if registered_for(item, purpose):
            ident = (item.get('id') or item.get('name')).strip()
            if ident not in result:
                result.append(ident)
    return result


def fetch_runtime_models(purpose, endpoint=ENDPOINT, timeout=5):
    if purpose not in ('ocr', 'translation'):
        raise ValueError('Unsupported model purpose')
    if endpoint != ENDPOINT:
        raise ValueError('OCR and translation model discovery must stay on local Runtime')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(endpoint + '/v1/models', headers={'Accept': 'application/json'})
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Runtime model list is too large')
    return runtime_models(json.loads(raw), purpose)


def lightweight_available(settings, specifications):
    """Only explicitly OCR-registered local models with real model files."""
    python = Path(settings.get('python') or '')
    base = Path(settings.get('models_root') or '')
    if (not python.is_absolute() or not python.is_file() or
            not os.access(python, os.X_OK) or not base.is_absolute() or not base.is_dir()):
        return []
    registered = settings.get('registered_lightweight', [])
    if not isinstance(registered, list):
        return []
    result = []
    for ident in registered:
        if ident not in specifications or ident in result:
            continue
        paths = [base / folder for folder in specifications[ident]]
        if all(folder.is_dir() and any(f.is_file() for f in folder.iterdir()) for folder in paths):
            result.append(ident)
    return result
