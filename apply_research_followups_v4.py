"""Merge validated follow-up records into their checked category files."""
import json
from pathlib import Path

import context_pass_v4 as pipeline

ROOT = Path(__file__).resolve().parent
categories = {}
for path in sorted((ROOT / 'data' / 'checked_research').glob('[0-9][0-9]_*.json')):
    data = json.loads(path.read_text(encoding='utf-8'))
    for index, record in enumerate(data['records']):
        categories[record['number']] = (path, data, index)

updates = []
for path in sorted((ROOT / 'data').glob('followup_*.json')):
    payload = json.loads(path.read_text(encoding='utf-8'))
    records = payload.get('records') if isinstance(payload, dict) else None
    if records is None:
        records = [payload]
    for record in records:
        errors = pipeline.validate_record(record)
        if errors:
            raise ValueError(f'{path.name}: {errors}')
        number = record.get('number')
        if number not in categories:
            raise ValueError(f'{path.name}: no checked category record for app {number}')
        category_path, _, index = categories[number]
        current = json.loads(category_path.read_text(encoding='utf-8'))['records'][index]
        if current.get('app') != record.get('app') or current.get('category') != record.get('category'):
            raise ValueError(f'{path.name}: app identity mismatch for {record.get("app")}')
        updates.append((path, record))

changed_paths = set()
for path, record in updates:
    category_path, data, index = categories[record['number']]
    if data['records'][index] != record:
        data['records'][index] = record
        changed_paths.add(category_path)
for path in sorted(changed_paths):
    data = json.loads(path.read_text(encoding='utf-8'))
    original = json.loads(path.read_text(encoding='utf-8'))
    for followup_path, record in updates:
        category_path, _, index = categories[record['number']]
        if category_path == path:
            data['records'][index] = record
    if data != original:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Validated {len(updates)} follow-up records across {len(changed_paths)} category files')
