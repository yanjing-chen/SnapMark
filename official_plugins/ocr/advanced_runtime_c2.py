"""SnapMark high-performance OCR through local Runtime 1.0.0.

Executed ONLY in a cancellable subprocess. No GTK and no model installation.
The only destination is http://127.0.0.1:8111; a model must be explicitly
installed and registered for OCR when the request is sent.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ENDPOINT = 'http://127.0.0.1:8111'
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'

class AdvancedOCRError(ValueError):
    pass


def _request(path, *, payload=None, endpoint=ENDPOINT, timeout=10):
    # endpoint injection is private test-only; production CLI always uses ENDPOINT.
    parts = urlsplit(endpoint)
    try:
        port = parts.port
    except ValueError as exc:
        raise AdvancedOCRError('Invalid local Runtime port') from exc
    if (parts.scheme != 'http' or parts.hostname != '127.0.0.1'
            or port is None or parts.username or parts.password
            or parts.path or parts.query or parts.fragment):
        raise AdvancedOCRError('High-performance OCR can only use local Runtime')
    data = (json.dumps(payload, ensure_ascii=False).encode('utf-8')
            if payload is not None else None)
    request = urllib.request.Request(
        endpoint + path, data=data,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST' if data is not None else 'GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise AdvancedOCRError(f'Local Runtime HTTP {exc.code} at {path}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AdvancedOCRError(f'Cannot reach local Runtime: {type(exc).__name__}') from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise AdvancedOCRError('Runtime response exceeds maximum size')
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise AdvancedOCRError('Runtime returned invalid JSON') from exc
    if not isinstance(result, dict):
        raise AdvancedOCRError('Runtime returned invalid response structure')
    return result


def eligible_models(inventory):
    models = inventory.get('data', inventory.get('models', [])) if isinstance(inventory, dict) else None
    if not isinstance(models, list):
        raise AdvancedOCRError('Runtime model registry is malformed')
    allowed = []
    for entry in models:
        if not isinstance(entry, dict):
            continue
        if entry.get('installed') is not True or entry.get('type') != 'ocr':
            continue
        caps = entry.get('capabilities')
        if not isinstance(caps, dict) or caps.get('ocr') is not True:
            continue
        ident = entry.get('id')
        if isinstance(ident, str) and ident and ident not in allowed:
            allowed.append(ident)
    return allowed


def parse_result(response):
    try:
        choice = response['choices'][0]
        message = choice['message']
        content = message['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise AdvancedOCRError('Runtime returned no OCR result') from exc
    if isinstance(content, list):
        content = '\n'.join(item['text'] for item in content
                            if isinstance(item, dict) and item.get('type') == 'text'
                            and isinstance(item.get('text'), str))
    if not isinstance(content, str) or not content.strip():
        raise AdvancedOCRError('Runtime returned empty OCR text')
    return content.strip()


def recognize(image, model_id, *, endpoint=ENDPOINT, timeout=240):
    if not isinstance(image, bytes) or not image.startswith(PNG_SIGNATURE):
        raise AdvancedOCRError('Input is not a PNG screenshot')
    if len(image) > MAX_IMAGE_BYTES:
        raise AdvancedOCRError('Screenshot exceeds 16 MiB OCR input limit')
    if not isinstance(model_id, str) or not model_id or len(model_id) > 128:
        raise AdvancedOCRError('Invalid OCR model identifier')
    available = eligible_models(_request('/v1/models', endpoint=endpoint, timeout=10))
    if model_id not in available:
        raise AdvancedOCRError('Model is not installed and registered for OCR in Runtime')
    data_uri = 'data:image/png;base64,' + base64.b64encode(image).decode('ascii')
    prompt = 'OCR:' if model_id.startswith('paddleocr-vl-') else (
        'Transcribe all visible text from this image exactly. '
        'Preserve reading order and line breaks. Output only the recognized text.')
    response = _request('/v1/chat/completions', endpoint=endpoint, timeout=timeout, payload={
        'model': model_id,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': data_uri}},
        ]}],
        'temperature': 0.0, 'stream': False, 'max_tokens': 4096,
    })
    return parse_result(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding='utf-8'))
        image_path = Path(request['image_path'])
        if not image_path.is_absolute() or not image_path.is_file():
            raise AdvancedOCRError('Missing screenshot file')
        with image_path.open('rb') as fp:
            image = fp.read(MAX_IMAGE_BYTES + 1)
        text = recognize(image, request['model'])
        args.result.write_text(json.dumps({'text': text}, ensure_ascii=False), encoding='utf-8')
    except (AdvancedOCRError, OSError, KeyError, ValueError) as exc:
        print('Advanced OCR failed: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
