"""Merge independently researched finance follow-up records into the checked category."""
import json
from pathlib import Path

import context_pass_v4 as pipeline

ROOT = Path(__file__).resolve().parent
FOLLOWUPS = {
    83: ROOT / 'data' / 'followup_83_binance.json',
    84: ROOT / 'data' / 'followup_84_paygent.json',
    86: ROOT / 'data' / 'followup_86_quickbooks_mcp.json',
    90: ROOT / 'data' / 'followup_90_pitchbook.json',
}
CATEGORY = ROOT / 'data' / 'checked_research' / '07_finance_fintech.json'

data = json.loads(CATEGORY.read_text(encoding='utf-8'))
records = data['records']
changed = False
applied = 0
for number, path in FOLLOWUPS.items():
    if not path.exists():
        continue
    replacement = json.loads(path.read_text(encoding='utf-8'))
    if replacement.get('number') != number or replacement.get('category') != 'Finance and Fintech':
        raise ValueError(f'{path.name}: unexpected app identity')
    errors = pipeline.validate_record(replacement)
    if errors:
        raise ValueError(f'{path.name}: {errors}')
    index = next((i for i, record in enumerate(records) if record.get('number') == number), None)
    if index is None:
        raise ValueError(f'{path.name}: target record is missing')
    if records[index] != replacement:
        records[index] = replacement
        changed = True
    applied += 1
if changed:
    CATEGORY.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Applied {applied} finance follow-up records; changed={changed}')
