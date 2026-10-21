"""C2-E per-model Translation settings; pure Python; never touches Runtime."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

PRESETS = {
    'General': 'Preserve the source meaning, tone, names, paragraph breaks and formatting faithfully. Return only the translation.',
    'Technical': 'Translate technical documentation precisely. Preserve quoted technical literals, file names, identifiers, configuration names and paths. Do not explain or rewrite code.',
    'Academic': 'Translate into a precise academic register. Maintain historical distinctions, terminology, citations, personal names and dates without adding interpretations.',
    'Literary': 'Translate fluently while preserving narrative voice, tone, style, imagery and register. Do not add information or commentary.',
}
DEFAULT = {'preset': 'General', 'prompt': PRESETS['General'], 'temperature': 0.0,
           'streaming': False, 'max_tokens': None, 'thinking': 'auto'}
ALLOWED_TOKENS = (None, 1024, 2048, 4096, 8192)

def settings_file():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'snapmark' / 'translation.json'

def _load():
    try:
        value = json.loads(settings_file().read_text('utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}

def validate(profile):
    if not isinstance(profile, dict):
        raise ValueError('Invalid translation profile')
    preset = profile.get('preset', 'General')
    if preset not in (*PRESETS.keys(), 'Custom'):
        raise ValueError('Unknown translation preset')
    prompt = profile.get('prompt', PRESETS.get(preset, PRESETS['General']))
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 10000:
        raise ValueError('Translation prompt must be 1–10000 characters')
    temperature = profile.get('temperature', 0.0)
    if type(temperature) not in (int, float) or not 0.0 <= temperature <= 1.0:
        raise ValueError('Temperature out of bounds')
    streaming = profile.get('streaming', False)
    if not isinstance(streaming, bool):
        raise ValueError('Streaming must be a boolean')
    max_tokens = profile.get('max_tokens')
    if max_tokens not in ALLOWED_TOKENS or isinstance(max_tokens, bool):
        raise ValueError('Unsupported max_tokens')
    # Runtime 1.0.0 thinking API has not been capability-verified; fail closed.
    if profile.get('thinking', 'auto') != 'auto':
        raise ValueError('Explicit thinking requires verified Runtime support')
    return {'preset': preset, 'prompt': prompt, 'temperature': float(temperature),
            'streaming': streaming, 'max_tokens': max_tokens, 'thinking': 'auto'}

def read_profile(model_id):
    profiles = _load().get('model_profiles', {})
    if not isinstance(profiles, dict):
        return dict(DEFAULT)
    value = profiles.get(model_id, profiles.get('__default__', {}))
    try:
        return validate(value)
    except ValueError:
        return dict(DEFAULT)

def save_profile(model_id, profile):
    if not isinstance(model_id, str) or not model_id or len(model_id) > 128:
        raise ValueError('Invalid translation model name')
    entry = validate(profile)
    path = settings_file()
    data = _load()
    profiles = data.get('model_profiles')
    if not isinstance(profiles, dict):
        profiles = {}
    data['model_profiles'] = {**profiles, model_id: entry}
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         prefix='.translation-profile-', delete=False) as out:
            tmp = Path(out.name)
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write('\n')
        tmp.chmod(0o600)
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return entry
