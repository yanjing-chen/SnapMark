#!/usr/bin/env python3
"""Non-mutating source audit for static GTK/Adwaita UI text and gettext coverage."""
from pathlib import Path
from collections import defaultdict
import ast
import gettext
import json
ROOT=Path(__file__).resolve().parent.parent
SRC=[ROOT/'snapmark',ROOT/'official_plugins']
KEYS={'title','subtitle','label','tooltip_text','description','placeholder_text'}
texts=defaultdict(set)
for base in SRC:
 if not base.exists():continue
 for file in base.rglob('*.py'):
  if '__pycache__' in file.parts:continue
  try:tree=ast.parse(file.read_text('utf-8'))
  except (SyntaxError,UnicodeError):continue
  for node in ast.walk(tree):
   if not isinstance(node,ast.Call):continue
   for kw in node.keywords:
    if kw.arg in KEYS and isinstance(kw.value,ast.Constant) and isinstance(kw.value.value,str):
     val=kw.value.value
     # Do not report technical IDs, internal filenames or numeric settings.
     if val and any(c.isalpha() for c in val) and not val.startswith(('/', 'http')):
      texts[str(file.relative_to(ROOT))].add(val)
result={}
for code in sorted(p.name for p in (ROOT/'snapmark/locale').iterdir() if p.is_dir()):
 core=gettext.translation('snapmark',localedir=str(ROOT/'snapmark/locale'),languages=[code],fallback=True)
 ocr=gettext.translation('snapmark-ocr',localedir=str(ROOT/'snapmark/locale'),languages=[code],fallback=True)
 trans=gettext.translation('snapmark-translation',localedir=str(ROOT/'snapmark/locale'),languages=[code],fallback=True)
 all_found=missing=[]
 missing=[];total=0
 for filename,strings in texts.items():
  domain=ocr if '/ocr/' in filename else trans if '/translation/' in filename else core
  for key in strings:
   total+=1
   if domain.gettext(key)==key and core.gettext(key)==key:
    missing.append((filename,key))
 result[code]={'discovered_ui_strings':total, 'needs_translation':len(missing),'examples':missing[:20]}
out=ROOT/'docs/C3_SOURCE_UI_TRANSLATION_AUDIT.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print('C3_I18N_SOURCE_AUDIT=PASS')
for code in ('zh_CN','en'):
 if code in result:print(code, result[code]['discovered_ui_strings'],result[code]['needs_translation'])
