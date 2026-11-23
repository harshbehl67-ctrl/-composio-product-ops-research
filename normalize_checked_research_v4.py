"""Preserve raw category output and normalize it to the strict six-field schema."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'data' / 'checked_research'
RAW = ROOT / 'data' / 'checked_research_raw'
FIELDS = ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')
RAW.mkdir(exist_ok=True)


def auth_value(value):
    if not isinstance(value, list):
        return value
    normalized = []
    for item in value:
        if isinstance(item, dict):
            method = item.get('method') or item.get('name') or item.get('type') or 'documented method'
            scope = item.get('scope') or item.get('description') or item.get('notes')
            normalized.append(f'{method}: {scope}' if scope else str(method))
        else:
            normalized.append(str(item))
    return normalized


def normalize_claim(field, claim):
    claim = dict(claim)
    value = claim.get('value')
    if field == 'auth':
        claim['value'] = auth_value(value)
    elif field == 'credential_gate':
        gate = claim.get('gate_class') or (value.get('gate_class') if isinstance(value, dict) else None)
        if gate:
            claim['gate_class'] = gate
            claim['value'] = gate
        if isinstance(value, dict):
            claim['details'] = value
    elif field == 'api_surface':
        if isinstance(value, dict):
            claim['api_types'] = claim.get('api_types') or value.get('api_types') or []
            claim['breadth'] = claim.get('breadth') or value.get('breadth') or 'unknown'
            claim['details'] = value
            claim['value'] = ('No public API documented' if claim['breadth'] == 'no_public_api'
                              else f"{', '.join(claim['api_types'])}; {claim['breadth']} documented surface")
        else:
            claim.setdefault('api_types', [])
            claim.setdefault('breadth', 'unknown')
    elif field == 'official_mcp':
        if isinstance(value, dict):
            claim['value'] = value.get('classification') or value.get('value') or 'unknown'
            claim['mcp_mode'] = claim.get('mcp_mode') or value.get('mcp_mode') or 'unknown'
            claim['details'] = value
        else:
            claim.setdefault('mcp_mode', 'unknown')
    return claim


for path in sorted(SOURCE.glob('*.json')):
    if not path.stem[:2].isdigit() or path.stem[2:3] != '_':
        continue
    data = json.loads(path.read_text(encoding='utf-8'))
    changed = False
    for record in data.get('records', []):
        if 'fields' in record:
            continue
        claims = {field: normalize_claim(field, record[field]) for field in FIELDS if field in record}
        missing = [field for field in FIELDS if field not in claims]
        if missing:
            raise ValueError(f'{path.name} / {record.get("app")}: missing fields {missing}')
        for field in FIELDS:
            record.pop(field, None)
        record['fields'] = claims
        changed = True
    if changed:
        backup = RAW / path.name
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        print('Normalized', path.name)
