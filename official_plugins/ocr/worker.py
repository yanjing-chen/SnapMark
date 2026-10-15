"""Standalone PP-OCRv5/v6 CPU worker; never imported by SnapMark's GTK process.

Input/output are bounded local JSON files. Every referenced inference-model
folder must exist before PaddleOCR is imported. No automatic downloads.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def inspect_request(payload, model_definitions):
    if not isinstance(payload, dict):
        raise ValueError('OCR request must be an object')
    choice = payload.get('model')
    if choice not in model_definitions:
        raise ValueError('Unsupported PP-OCR model family and size')
    directory = Path(payload.get('models_root', '')).expanduser()
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError('Configure an existing absolute local OCR models folder')
    det_name, rec_name = model_definitions[choice]
    det, rec = directory / det_name, directory / rec_name
    for path in (det, rec):
        # Verify real files exist; empty placeholders must not trigger a network download.
        if not path.is_dir() or not any(p.is_file() for p in path.iterdir()):
            raise ValueError(f'Offline model missing: {path}')
    source = Path(payload.get('image_path', ''))
    if not source.is_absolute() or not source.is_file():
        raise ValueError('OCR source PNG is missing')
    if source.stat().st_size > 100 * 1024 * 1024:
        raise ValueError('OCR image exceeds 100 MiB')
    if source.suffix.lower() != '.png':
        raise ValueError('OCR input must be a PNG screenshot')
    return str(source), (det_name, str(det)), (rec_name, str(rec))


def _extract_text(result):
    if isinstance(result, list):
        return '\n'.join(filter(None, (_extract_text(i) for i in result)))
    if not isinstance(result, dict):
        return ''
    if 'rec_texts' in result and isinstance(result['rec_texts'], list):
        return '\n'.join(str(line) for line in result['rec_texts'] if isinstance(line, str))
    if 'res' in result:
        return _extract_text(result['res'])
    return ''


def recognize(request, specs):
    source, det, rec = inspect_request(request, specs)
    # Local-only model paths and disabled auxiliary classifiers prevent PaddleOCR
    # from resolving default models over the network.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from paddleocr import PaddleOCR
    engine = PaddleOCR(
        text_detection_model_name=det[0], text_detection_model_dir=det[1],
        text_recognition_model_name=rec[0], text_recognition_model_dir=rec[1],
        use_doc_orientation_classify=False, use_doc_unwarping=False,
        use_textline_orientation=False, device='cpu',
    )
    pieces = []
    for result in engine.predict(source):
        value = getattr(result, 'json', None)
        if callable(value):
            value = value()
        if value is None and isinstance(result, dict):
            value = result
        if not isinstance(value, (dict, list)):
            raise RuntimeError('PaddleOCR response format is unsupported')
        pieces.append(_extract_text(value))
    return '\n'.join(p for p in pieces if p)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    parser.add_argument('--result', required=True)
    args = parser.parse_args(argv)
    try:
        src = Path(args.request)
        if src.stat().st_size > 64 * 1024:
            raise ValueError('OCR request exceeds 64 KiB')
        request = json.loads(src.read_text('utf-8'))
        specs = json.loads(Path(__file__).with_name('models.json').read_text('utf-8'))
        answer = {'text': recognize(request, specs)}
        Path(args.result).write_text(json.dumps(answer, ensure_ascii=False), encoding='utf-8')
        return 0
    except Exception as exc:
        print(f'OCR worker: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
