"""Validate category research and assemble the checked 100-app dataset."""
import collections
import json
from pathlib import Path

import context_pass_v4 as pipeline

ROOT = Path(__file__).resolve().parent
apps = json.loads((ROOT / 'apps.json').read_text(encoding='utf-8'))
expected = {app['name']: app for app in apps}
files = sorted(path for path in (ROOT / 'data' / 'checked_research').glob('*.json')
               if path.stem[:2].isdigit() and path.stem[2:3] == '_')
records = []
errors = []
seen_apps = set()
for path in files:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        errors.append(f'{path.name}: invalid JSON: {exc}')
        continue
    if not isinstance(data, dict) or not isinstance(data.get('records'), list):
        errors.append(f'{path.name}: expected an object with a records array')
        continue
    for record in data['records']:
        if not isinstance(record, dict):
            errors.append(f'{path.name}: record is not an object')
            continue
        app = expected.get(record.get('app'))
        if not app:
            errors.append(f'{path.name}: unexpected app {record.get("app")}')
            continue
        if record.get('number') != app['number'] or record.get('category') != app['category']:
            errors.append(f'{record.get("app")}: number/category mismatch')
        if record.get('app') in seen_apps:
            errors.append(f'{record.get("app")}: duplicate app record')
        seen_apps.add(record.get('app'))
        for error in pipeline.validate_record(record):
            errors.append(f'{record.get("app")}: {error}')
        records.append(record)
if len(records) != 100 or {record['app'] for record in records} != set(expected):
    errors.append(f'Expected 100 unique assigned apps, found {len(records)} records and {len({record["app"] for record in records})} unique names')
report = {'checked_at': '2026-11-24', 'files': [path.name for path in files],
          'record_count': len(records), 'error_count': len(errors), 'errors': errors}
(ROOT / 'validation_report_v4.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
if errors:
    print(f'Validation failed with {len(errors)} errors; see validation_report_v4.json')
    for error in errors[:80]:
        print(error)
    raise SystemExit(1)

records.sort(key=lambda record: record['number'])
old = {row['name']: row for row in json.loads((ROOT / 'checked_dataset_v3.json').read_text(encoding='utf-8'))}
for record in records:
    previous = old[record['app']]
    record['composio_auth_config'] = previous.get('composio_auth_config')
    record['first_pass'] = previous.get('first_pass', {})
    record['provisional_pass12'] = json.loads((ROOT / 'data' / 'pass12' / f"{record['number']:03}.json").read_text(encoding='utf-8'))['claims']
    gate = record['fields']['credential_gate']
    verdict = record['fields']['verdict']
    if verdict['status'] == 'unknown':
        blocker_class = 'unresolved_official_evidence'
    elif verdict['value'] == 'no_public_api':
        blocker_class = 'no_documented_public_api'
    elif verdict['value'] == 'wrapper_or_cli':
        blocker_class = 'wrapper_required'
    elif verdict['value'] == 'partner_outreach':
        blocker_class = 'partnership_or_sales'
    elif gate.get('gate_class') in ('paid_plan', 'admin_approval', 'mixed'):
        blocker_class = 'credential_access_gate'
    else:
        blocker_class = 'none_documented_for_prototype'
    record['blocker_class'] = blocker_class

(ROOT / 'checked_dataset_v4.json').write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding='utf-8')
unknowns = [{'number': record['number'], 'app': record['app'], 'fields': {
    field: {'reason': claim['reason'], 'attempted_sources': claim.get('evidence', [])}
    for field, claim in record['fields'].items() if claim['status'] == 'unknown'}} for record in records]
unknowns = [record for record in unknowns if record['fields']]
(ROOT / 'remaining_unknowns_v4.json').write_text(json.dumps(unknowns, indent=2, ensure_ascii=False), encoding='utf-8')

coverage = {field: {'checked': sum(record['fields'][field]['status'] == 'checked' for record in records),
                   'unknown': sum(record['fields'][field]['status'] == 'unknown' for record in records)}
            for field in pipeline.FIELDS}
def auth_categories(value):
    lowered = str(value).lower()
    found = set()
    if 'oauth' in lowered:
        found.add('OAuth 2.0')
    if 'api key' in lowered or 'x-api-key' in lowered or 'key id' in lowered:
        found.add('API key')
    if 'token' in lowered:
        found.add('Access token')
    if 'basic' in lowered:
        found.add('Basic authentication')
    if 'bearer' in lowered:
        found.add('Bearer token')
    if 'session' in lowered and ('cookie' in lowered or 'authentication' in lowered):
        found.add('Session authentication')
    if 'no account' in lowered or lowered.startswith('none') or 'no authentication' in lowered:
        found.add('No authentication')
    return found or {'Other documented method'}


auth = collections.Counter()
for record in records:
    value = record['fields']['auth']['value']
    values = value if isinstance(value, list) else [value]
    categories = set()
    if record['fields']['auth']['status'] == 'checked':
        for item in values:
            categories.update(auth_categories(item))
    auth.update(categories)
gates = collections.Counter(record['fields']['credential_gate'].get('gate_class', 'unknown') for record in records)
api_types = collections.Counter(t for record in records for t in record['fields']['api_surface'].get('api_types', []))
breadth = collections.Counter(record['fields']['api_surface'].get('breadth', 'unknown') for record in records)
mcp = collections.Counter(record['fields']['official_mcp']['value'] for record in records)
verdicts = collections.Counter(record['fields']['verdict']['value'] for record in records)
blockers = collections.Counter(record['blocker_class'] for record in records)
catalog = collections.Counter(record['fields']['composio_toolkit']['value'] for record in records)
categories = {}
for category in dict.fromkeys(record['category'] for record in records):
    rows = [record for record in records if record['category'] == category]
    categories[category] = {'apps': len(rows), 'verdicts': dict(collections.Counter(row['fields']['verdict']['value'] for row in rows)),
                            'gates': dict(collections.Counter(row['fields']['credential_gate'].get('gate_class', 'unknown') for row in rows))}
easy_wins = [record['app'] for record in records if record['fields']['verdict']['value'] == 'documented_build_candidate'
             and record['fields']['credential_gate'].get('gate_class') in ('self_serve_free', 'self_serve_trial')
             and record['fields']['api_surface'].get('breadth') in ('broad', 'moderate')]
summary = {'checked_at': '2026-11-24', 'apps': len(records), 'coverage': coverage, 'auth_methods': dict(auth),
           'credential_gates': dict(gates), 'api_types': dict(api_types), 'api_breadth': dict(breadth),
           'official_mcp': dict(mcp), 'composio_toolkit': dict(catalog), 'verdicts': dict(verdicts),
           'blockers': dict(blockers), 'categories': categories, 'documented_easy_wins': easy_wins,
           'notes': ['Counts describe checked documentation, not live credential tests.',
                     'Unknown is not evidence of absence.',
                     'Composio toolkit listings are separate from vendor-operated MCP servers.']}
(ROOT / 'research_summary_v4.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
print('Validated', len(records), 'apps')
print('Coverage', json.dumps(coverage))
print('Verdicts', json.dumps(summary['verdicts']))
print('Blockers', json.dumps(summary['blockers']))
