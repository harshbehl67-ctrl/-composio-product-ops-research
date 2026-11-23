"""Apply independently reviewed sample corrections without changing pass2."""
import collections
import json
from pathlib import Path

rows = json.loads(Path('assessed_dataset.json').read_text(encoding='utf-8'))
sample = json.loads(Path('pass2_review.json').read_text(encoding='utf-8'))['records']
facts = json.loads(Path('manual_facts.json').read_text(encoding='utf-8'))
by_name = {r['name']: r for r in rows}
for item in sample:
    correction = item['correction']
    source = item['independent_source']
    if correction == 'unknown' or not source:
        continue
    target = by_name[item['app']]['fields'][item['field']]
    target.update(value=correction, sources=list(dict.fromkeys([source] + item.get('additional_sources', []))),
                  status='independent sample review; scoped and possibly incomplete')
for fact in facts:
    row = by_name[fact['app']]
    status = ('AI-assisted review of cached vendor page; not independently re-fetched' if fact.get('evidence_excerpt')
              else 'independent documentation review; scoped inference' if fact['field'] == 'verdict'
              else 'independent documentation review')
    row['fields'][fact['field']] = {'value': fact['value'], 'sources': [fact['url']] + fact.get('additional_sources', []),
                                    'status': status}
    if fact['field'] == 'verdict':
        row['blocker'] = fact['note']
        row['next_action'] = 'Test the developer path and verify customer-specific permissions before rollout'
counts = collections.Counter('unknown' if row['fields']['verdict']['value'] == 'unknown' else 'documented or inferred' for row in rows)
assert len(rows) == 100 and sum(counts.values()) == 100
Path('reviewed_dataset.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print('Build verdicts:', dict(counts))
