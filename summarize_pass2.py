"""Explain unresolved fields and summarize a frozen research experiment."""
import collections
import json
from pathlib import Path

apps = json.loads(Path('apps.json').read_text(encoding='utf-8'))
reviewed = {x['name']: x for x in json.loads(Path('reviewed_dataset.json').read_text(encoding='utf-8'))}
unresolved, coverage = [], collections.Counter()
http = collections.Counter()
for app in apps:
    path = Path(f"data/pass2/{app['number']:03}.json")
    raw = json.loads(path.read_text(encoding='utf-8'))
    pages = raw['pages']
    for p in pages:
        http[str(p.get('status', 'network error'))] += 1
    for field, claim in raw['claims'].items():
        if claim['value'] != 'unknown':
            coverage[field] += 1
    unknown_fields = []
    for field, claim in reviewed[app['name']]['fields'].items():
        if claim['value'] != 'unknown':
            continue
        provisional = raw['claims'][field]['value']
        if provisional != 'unknown':
            reason = 'Automated pass proposed an answer, but it has not been independently reviewed.'
        elif field == 'credential_gate':
            reason = 'Access-tier extraction is not implemented in the automated pass; targeted search results require review.'
        elif field == 'verdict':
            reason = 'Automated buildability classification is not implemented; documented auth, surface and access remain to be assessed.'
        elif field == 'composio_toolkit':
            reason = 'No exact or reviewed alias match in the saved catalog; this does not establish absence.'
        elif not raw['candidates']:
            reason = 'Targeted search produced no candidate on the allowed vendor domains.'
        elif not any(p.get('status') == 200 for p in pages):
            reason = 'Candidate pages could not be retrieved successfully (HTTP error, network failure, or no selected page).'
        else:
            reason = 'Retrieved pages did not produce a matching extract for this field; documentation may still exist elsewhere.'
        unknown_fields.append({'field': field, 'reason': reason})
    if unknown_fields:
        unresolved.append({'app': app['name'], 'category': app['category'], 'unknown_fields': unknown_fields})
result = {'apps': len(apps), 'provisional_answered_fields': dict(coverage), 'http_statuses': dict(http),
          'note': 'These extraction counts are not verified findings or population accuracy.', 'unresolved': unresolved}
Path('remaining_unknowns.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
print('Pass 2:', dict(coverage), 'HTTP:', dict(http), 'apps with unknowns:', len(unresolved))
