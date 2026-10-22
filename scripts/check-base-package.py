#!/usr/bin/env python3
"""Verify basic distributions contain no optional plugin, runtime, model or GGUF."""
from pathlib import Path
import sys

FORBIDDEN={'official_plugins','local-ai-runtime','models','models.gguf'}
EXTENSIONS={'.gguf','.onnx','.safetensors','.pt','.pth'}
def verify(root):
    root=Path(root)
    if not root.is_dir(): raise SystemExit(f'Package tree absent: {root}')
    contents=list(root.rglob('*'))
    for item in contents:
        parts=set(item.relative_to(root).parts)
        if parts & FORBIDDEN or item.suffix.lower() in EXTENSIONS:
            raise SystemExit(f'C3_BASE_PACKAGE_FORBIDDEN_CONTENT={item}')
    print(f'C3_BASE_PACKAGE_CLEAN=PASS files={sum(p.is_file() for p in contents)}')
if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('usage: check-base-package.py DIRECTORY')
    verify(sys.argv[1])
