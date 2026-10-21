"""C2-F advanced OCR settings, isolated from Runtime and existing OCR settings.

Never downloads weights, changes Runtime, or writes a profile implicitly.
"""
from __future__ import annotations
import json
import math
import os
import tempfile
from pathlib import Path

PRESETS = {
    'Model default': '',
    'Faithful text': 'Transcribe every visible word faithfully in reading order. Keep names, numbers and punctuation exactly as shown. Output only recognized text.',
    'Preserve paragraphs': 'Transcribe the image exactly. Preserve visible paragraph boundaries and line breaks when clear. Never summarize, translate or add information.',
    'Custom': '',
}
OUTPUTS = ('Plain text', 'Preserve paragraphs')
TOKENS = (2048, 4096, 8192)
DEFAULT = {'preset': 'Model default', 'prompt': '', 'temperature': 0.0,
           'max_tokens': 4096, 'streaming': False, 'output': 'Plain text'}


def profile_path():
    return (Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
            / 'snapmark' / 'ocr-advanced.json')


def native_paddle(model):
    return isinstance(model, str) and model.lower().startswith('paddleocr-vl-')


def validate(profile, model):
    if not isinstance(model, str) or not model or len(model) > 128:
        raise ValueError('Invalid OCR model identifier')
    if not isinstance(profile, dict):
        raise ValueError('Invalid OCR settings')
    obj = {**DEFAULT, **profile}
    if obj['preset'] not in PRESETS:
        raise ValueError('Unknown OCR preset')
    if not isinstance(obj['prompt'], str) or len(obj['prompt']) > 6000:
        raise ValueError('Invalid OCR prompt')
    if obj['preset'] == 'Custom' and not obj['prompt'].strip():
        raise ValueError('Custom OCR prompt cannot be empty')
    if type(obj['temperature']) not in (float, int) or not math.isfinite(obj['temperature']) or not 0 <= obj['temperature'] <= 1:
        raise ValueError('Temperature must be 0.0 to 1.0')
    if type(obj['max_tokens']) is not int or obj['max_tokens'] not in TOKENS:
        raise ValueError('Unsupported maximum output tokens')
    if type(obj['streaming']) is not bool:
        raise ValueError('Streaming must be true or false')
    if obj['output'] not in OUTPUTS:
        raise ValueError('Invalid OCR output mode')
    if native_paddle(model) and obj['preset'] != 'Model default':
        raise ValueError('PaddleOCR-VL requires the native task prompt')
    return {k: obj[k] for k in DEFAULT}


def _read_all():
    try:
        result = json.loads(profile_path().read_text('utf-8'))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def read_profile(model):
    if not isinstance(model, str) or not model:
        return dict(DEFAULT)
    entry = _read_all().get('models', {})
    profile = entry.get(model, {}) if isinstance(entry, dict) else {}
    # Read-only compatibility: a prior experimental table profile must not
    # reset its unrelated temperature, token or streaming preferences.
    if isinstance(profile, dict) and profile.get('output') == 'Table recognition (experimental)':
        profile = dict(profile, output='Plain text')
    try:
        return validate(profile, model)
    except (ValueError, TypeError):
        return dict(DEFAULT)


def save_profile(model, profile):
    value = validate(profile, model)
    data = _read_all()
    models = data.get('models')
    if not isinstance(models, dict):
        models = {}
    data['models'] = {**models, model: value}
    path = profile_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         prefix='.ocr-profile-', delete=False) as f:
            temp = Path(f.name)
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')
        temp.chmod(0o600)
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return value


def prompt_for(model, profile):
    obj = validate(profile, model)
    if native_paddle(model):
        return 'OCR:'
    if obj['preset'] == 'Custom':
        return obj['prompt'].strip()
    if obj['output'] == 'Preserve paragraphs':
        return PRESETS['Preserve paragraphs']
    if obj['preset'] in ('Faithful text', 'Preserve paragraphs'):
        return PRESETS[obj['preset']]
    return ('Transcribe all visible text from this image exactly. '
            'Preserve reading order and line breaks. Output only the recognized text.')
