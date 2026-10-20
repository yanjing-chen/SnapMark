"""SnapMark controlled manifest, PaddlePaddle-official model downloads only.

Catalog: SnapMark GitHub development branch (later change channel for stable release).
Offline fallback: bundled catalog. No background updates; explicit refresh & downloads.
Online declarations cannot bypass engine compatibility or official-source checks.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

CATALOG_URL = ('https://raw.githubusercontent.com/yanjing-chen/SnapMark/'
               'snapmark-c2-onnx/ocr-models/catalog-v1.json')
BUILTIN_PATH = Path(__file__).with_name('catalog_builtin.json')
CACHE_PATH = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'snapmark' / 'ocr-catalog-v1.json'
PROFILE = 'ppocr-esearch-v6-tiny-v1'
ENGINE_API = 1
DEFAULT_ID = 'ppocr-v6-tiny'
MAX_CATALOG = 128 * 1024
MAX_MODELS = 24
MAX_MODEL_BYTES = 300 * 1024 * 1024

# Retained for explicit official-source provenance and prior regression tests.
DET_SHA256 = '193bab7a04fca699a6c82e6abb5b81bdb28177f0abd4062552b04908dafb19f8'
REC_SHA256 = '9ef676d6ed3c88256a2d92c640c44f25b0c40947e111b14b8be8f594091563e6'
OFFICIAL_DET_URL = ('https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_det_onnx/resolve/'
                    '2ba1506c0380b8f0b03dd142459aac66d4421f6c/inference.onnx')
OFFICIAL_REC_URL = ('https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_rec_onnx/resolve/'
                    '2612ab37152ae0a677521bae4e1e3d4fb4cf7c30/inference.onnx')
OFFICIAL_DICT_URL = ('https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/'
                     'ppocr/utils/dict/ppocrv6_tiny_dict.txt')


def _sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def _validate_dict(path, count):
    chars=Path(path).read_text(encoding='utf-8-sig').splitlines()
    if len(chars) != count or not any(c.strip() for c in chars):
        raise ValueError(f'OCR dictionary mismatch: {len(chars)} vs {count}')
    return _sha256(path)


def _official_url(url, kind):
    if not isinstance(url,str) or len(url)>350:
        return False
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    if kind in ('det','rec'):
        # Hugging Face public models from the verified official PaddlePaddle account;
        # commit-pinned URLs only, never a floating main revision.
        return (parsed.netloc=='huggingface.co'
                and bool(re.fullmatch(r'/PaddlePaddle/[A-Za-z0-9_.-]+/resolve/[a-f0-9]{40}/inference\.onnx', parsed.path)))
    return (parsed.netloc=='raw.githubusercontent.com'
            and bool(re.fullmatch(r'/PaddlePaddle/PaddleOCR/(?:[a-f0-9]{40}|main)/ppocr/utils/dict/[A-Za-z0-9_.-]+\.txt',parsed.path)))


def validate_catalog(data):
    if not isinstance(data,dict) or data.get('schema')!=1 or data.get('publisher')!='SnapMark':
        raise ValueError('Only SnapMark model catalog schema 1 is accepted')
    models=data.get('models')
    if not isinstance(models,list) or not 1<=len(models)<=MAX_MODELS:
        raise ValueError('Invalid model catalog length')
    seen_ids=set();seen_labels=set()
    for item in models:
        if not isinstance(item,dict): raise ValueError('Invalid model entry')
        identifier=item.get('id');label=item.get('label')
        if not isinstance(identifier,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,49}',identifier):
            raise ValueError('Invalid model identifier')
        if not isinstance(label,str) or not 4<=len(label)<=85 or any(ord(c)<32 for c in label):
            raise ValueError('Invalid model label')
        if identifier in seen_ids or label in seen_labels:raise ValueError('Duplicate OCR models')
        seen_ids.add(identifier);seen_labels.add(label)
        if item.get('publisher')!='PaddlePaddle':raise ValueError('Non-official publisher')
        if item.get('license')!='Apache-2.0':raise ValueError('Unapproved license')
        if item.get('verification') not in ('smoke-tested','unverified'):
            raise ValueError('Unrecognized verification status')
        if not isinstance(item.get('min_engine_api'),int) or isinstance(item.get('min_engine_api'),bool):
            raise ValueError('Bad engine compatibility marker')
        count=item.get('dictionary_entries')
        if not isinstance(count,int) or isinstance(count,bool) or not 100<=count<=200000:
            raise ValueError('Bad dictionary entry count')
        files=item.get('files')
        if not isinstance(files,dict) or set(files)!={'det','rec','dict'}:
            raise ValueError('Invalid official OCR asset set')
        for kind, spec in files.items():
            if not isinstance(spec,dict) or not _official_url(spec.get('url'),kind):
                raise ValueError('Non-official or unpinned OCR asset URL')
            digest=spec.get('sha256')
            # Temporary v6 legacy official dictionary exception (byte digest recorded on install).
            if not (isinstance(digest,str) and bool(re.fullmatch('[a-f0-9]{64}',digest)) or
                    kind=='dict' and identifier==DEFAULT_ID and digest is None):
                raise ValueError('Missing pinned SHA256 for OCR asset')
            size=spec.get('max_bytes')
            if not isinstance(size,int) or isinstance(size,bool) or not 1024<=size<=MAX_MODEL_BYTES:
                raise ValueError('Invalid asset byte limit')
    return data


def compatible(model):
    return (model['profile']==PROFILE and model['min_engine_api']<=ENGINE_API
            and model['verification']=='smoke-tested')


def _load_file(path):
    raw=Path(path).read_bytes()
    if len(raw)>MAX_CATALOG: raise ValueError('Catalog exceeds maximum allowed size')
    return validate_catalog(json.loads(raw.decode('utf-8')))


def current_catalog():
    for location in (CACHE_PATH, BUILTIN_PATH):
        try: return _load_file(location)
        except (OSError,UnicodeError,ValueError,TypeError,KeyError):pass
    raise RuntimeError('SnapMark bundled catalog missing or invalid')


def refresh_catalog():
    """Called only by explicit Refresh; cache remains intact on any failure."""
    req=Request(CATALOG_URL,headers={'User-Agent':'SnapMark-Official-OCR-Catalog/1'})
    with urlopen(req, timeout=25) as resp:
        if resp.geturl()!=CATALOG_URL:raise ValueError('Catalog URL redirected; refusing')
        raw=resp.read(MAX_CATALOG+1)
    if len(raw)>MAX_CATALOG:raise ValueError('Online catalog too large')
    validate_catalog(json.loads(raw.decode('utf-8')))
    CACHE_PATH.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,temp=tempfile.mkstemp(dir=CACHE_PATH.parent,prefix='.ocr-catalog-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.chmod(temp,0o600)
        os.replace(temp,CACHE_PATH)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return current_catalog()


def models():
    return current_catalog()['models']


def by_label(label):
    return next((m for m in models() if m['label']==label),None)


def _candidate_paths(root,identifier):
    root=Path(root)
    if identifier==DEFAULT_ID: return root/'official-model'
    return root/'official-models'/identifier


def _stored_model(folder):
    folder=Path(folder)
    path=folder/'install.json'
    if not path.is_file() or path.is_symlink():return None
    try:
        state=json.loads(path.read_text(encoding='utf-8'))
        model=state.get('model')
        validate_catalog({'schema':1,'publisher':'SnapMark','models':[model]})
        if not compatible(model):return None
        for kind,name in (('det','det.onnx'),('rec','rec.onnx'),('dict','dict.txt')):
            p=folder/name
            expected=model['files'][kind]['sha256']
            if not p.is_file() or p.is_symlink():return None
            digest=_sha256(p)
            if expected is not None and digest!=expected:return None
            if kind=='dict':
                if _validate_dict(p,model['dictionary_entries'])!=state.get('dict_sha256'):
                    return None
        return model
    except (OSError,ValueError,UnicodeError,TypeError,KeyError):return None


def installed(root):
    base=Path(root)
    paths=[base/'official-model']
    other=base/'official-models'
    if other.is_dir() and not other.is_symlink():
        paths.extend(p for p in other.iterdir() if p.is_dir() and not p.is_symlink())
    found={}
    for p in paths:
        m=_stored_model(p)
        if m is not None and p==_candidate_paths(base,m['id']):found[m['label']]=p
    return found


def ready(folder):
    return _stored_model(folder) is not None


def _download(url,output,max_bytes,kind):
    if not _official_url(url,kind):raise ValueError('Refusing non-official source')
    req=Request(url,headers={'User-Agent':'SnapMark-Official-OCR/1'})
    size=0
    with urlopen(req,timeout=45) as response, Path(output).open('wb') as out:
        if urlparse(response.geturl()).scheme!='https':raise ValueError('Insecure file download redirect')
        while True:
            block=response.read(256*1024)
            if not block:break
            size+=len(block)
            if size>max_bytes:raise ValueError('Official file exceeds manifest size limit')
            out.write(block)
    if not size:raise ValueError('Official download was empty')


def install(folder,*,confirmed=False,model=None):
    if not confirmed:raise PermissionError('Explicit user consent required')
    if model is None:model=next(x for x in models() if x['id']==DEFAULT_ID)
    validate_catalog({'schema':1,'publisher':'SnapMark','models':[model]})
    if not compatible(model):raise ValueError('Model not verified for this OCR engine')
    folder=Path(folder)
    if ready(folder):return 'Official OCR model already installed: '+model['label']
    if folder.exists():raise FileExistsError('Existing model files are never overwritten: '+str(folder))
    folder.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    stage=Path(tempfile.mkdtemp(prefix='.ocr-official-',dir=folder.parent))
    try:
        for kind,name in (('det','det.onnx'),('rec','rec.onnx'),('dict','dict.txt')):
            spec=model['files'][kind];path=stage/name
            _download(spec['url'],path,spec['max_bytes'],kind)
            expected=spec['sha256']
            if expected is not None and _sha256(path)!=expected:
                raise ValueError('Official SHA256 mismatch: '+name)
        dict_sha=_validate_dict(stage/'dict.txt',model['dictionary_entries'])
        state={'model':model,'source':'PaddlePaddle official models','dict_sha256':dict_sha}
        (stage/'install.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.chmod(stage/'install.json',0o600)
        if not ready(stage):raise ValueError('Model staging integrity failed')
        if folder.exists():raise FileExistsError('Target created by another operation')
        stage.rename(folder)
    finally:
        if stage.exists():shutil.rmtree(stage)
    return 'PaddlePaddle official model installed: '+model['label']
