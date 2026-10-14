#!/usr/bin/env bash
# Ryzen 7 6800H: read-only local Runtime API discovery (NO POST, installs or model changes).
set -Eeuo pipefail
printf '===== EXECUTION MACHINE: Ryzen 7 6800H =====\n'
/usr/bin/python3 - <<'PY'
import json
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

base = 'http://127.0.0.1:8111'
for route in ('/health', '/openapi.json'):
    try:
        request = Request(base + route, headers={'Accept': 'application/json'}, method='GET')
        with urlopen(request, timeout=3) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                print(route, 'response too large'); continue
            obj = json.loads(raw)
    except (OSError, URLError, HTTPError, ValueError) as exc:
        print(route, 'unavailable:', type(exc).__name__, str(exc)[:120])
        continue
    if route == '/health':
        print('Runtime:', obj.get('service'), obj.get('runtime_version'),
              'status:', obj.get('status'))
        continue
    print('OpenAPI version:', obj.get('openapi', 'unknown'))
    print('Relevant write routes and request schemas (discovery ONLY):')
    found = False
    for path, operations in obj.get('paths', {}).items():
        if not any(word in path.lower() for word in ('model', 'import', 'register', 'runtime')):
            continue
        for method, operation in operations.items():
            if method.upper() not in ('POST', 'PUT', 'PATCH') or not isinstance(operation, dict):
                continue
            found = True
            body = operation.get('requestBody', {})
            schema = (body.get('content', {}).get('application/json', {}).get('schema', {})
                      if isinstance(body, dict) else {})
            print(f'  {method.upper()} {path} | operationId={operation.get("operationId", "-")} | schema={json.dumps(schema, ensure_ascii=False)[:600]}')
    if not found:
        print('  None documented. No registration route is assumed.')
print('END: read-only; no files or service settings changed.')
PY
