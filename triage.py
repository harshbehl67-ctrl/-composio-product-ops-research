"""Index, but do not assert, claim-related text from retrieved candidate pages."""
import json
import re
from pathlib import Path

terms = {'auth': r'\boauth\b|api key|api token|bearer token|basic auth',
         'credential_gate': r'\btrial\b|\bpaid\b|\bapproval\b|\bpartner\b|administrator',
         'api_surface': r'\bgraphql\b|\brest api\b|\bapi reference\b',
         'official_mcp': r'\bmcp server\b|model context protocol'}
apps = json.loads(Path('apps.json').read_text(encoding='utf-8'))
result = []
for app in apps:
    data = json.loads(Path(f"data/discovery/{app['number']:03}.json").read_text(encoding='utf-8'))
    record = {'app': app['name'], 'candidates': [], 'assessment': 'unreviewed snippets; not claim evidence'}
    for page in data.get('fetches', []):
        snippets = {}
        for field, pattern in terms.items():
            match = re.search(pattern, page.get('text', ''), flags=re.I)
            if match:
                snippets[field] = page['text'][max(0, match.start()-140):match.end()+220]
        record['candidates'].append({'url': page['url'], 'status': page['status'], 'possible_claim_context': snippets})
    result.append(record)
Path('candidate_triage.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
print('Indexed candidate pages for', len(result), 'apps; no candidate is automatically marked verified')
