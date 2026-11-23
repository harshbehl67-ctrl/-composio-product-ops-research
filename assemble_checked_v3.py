"""Overlay source-reviewed corrections without mutating earlier datasets or passes."""
import collections
import json
from pathlib import Path

rows = json.loads(Path('reviewed_dataset.json').read_text(encoding='utf-8'))
facts = json.loads(Path('manual_facts_v3.json').read_text(encoding='utf-8'))
lookup = {x['name']: x for x in rows}
for fact in facts:
    target = lookup[fact['app']]['fields'][fact['field']]
    target.update(value=fact['value'], sources=[fact['url']] + fact.get('additional_sources', []),
                  status='AI-assisted review of vendor documentation; scope noted',
                  checked_date=fact['checked_date'], review_note=fact['note'])
assert len(rows) == len(lookup) == 100
Path('checked_dataset_v3.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print('Unknown fields:', {field: sum(r['fields'][field]['value'] == 'unknown' for r in rows)
      for field in ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')})
