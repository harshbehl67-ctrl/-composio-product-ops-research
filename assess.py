"""Assemble a conservative dataset and an auditable six-field baseline review."""
import collections
import json
from pathlib import Path

load = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
apps = load('apps.json')
catalog = load('catalog_snapshot.json')
alias = {r['app']: r for r in load('catalog_aliases.json')}
lookup = {r['app']: r for r in catalog['results']}
reviews = load('review.json')
new_mcp = {
    'GitHub': 'https://github.com/github/github-mcp-server',
    'Google Ads': 'https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server',
    'HubSpot': 'https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server',
    'Stripe': 'https://docs.stripe.com/mcp',
}
for app, url in new_mcp.items():
    reviews.append({'app': app, 'field': 'official_mcp', 'original': 'unknown',
                    'checked': 'Vendor documents an official MCP server', 'correction': 'yes',
                    'rating': 'abstained', 'why': 'Baseline did not extract a claim', 'url': url})

fields = ['auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict']
out = []
for app in apps:
    name = app['name']
    baseline = load(f"data/{app['number']:03}.json")
    discovery = load(f"data/discovery/{app['number']:03}.json")
    entry = lookup[name]
    item = entry['matches'][0] if entry['matches'] else alias.get(name)
    row = dict(app)
    row['fields'] = {f: {'value': 'unknown', 'sources': [], 'status': 'unresolved'} for f in fields}
    if item:
        row['fields']['composio_toolkit'] = {'value': 'listed', 'sources': [item['url']],
            'status': 'catalog match' if entry['matches'] else 'catalog alias; scope review'}
        slug = item['slug']
        detail_path = Path('data/catalog') / (slug + '.json')
        if detail_path.exists():
            detail = load(detail_path)
            text = detail.get('text', '')
            if 'Authentication Details ' in text:
                config = text.split('Authentication Details ', 1)[1].split(' Frequently Asked Questions', 1)[0].split(' Tools (', 1)[0]
                row['composio_auth_config'] = {'value': config[:250], 'source': item['url'],
                    'note': 'Composio configuration only; not an exhaustive list of vendor authentication methods'}
    for r in [r for r in reviews if r['app'] == name]:
        field = row['fields'][r['field']]
        field['value'] = r['correction']
        field['sources'].append(r['url'])
        field['status'] = 'reviewed claim; may be incomplete'
    row['blocker'] = 'Claim-specific documentation and integration scope need review'
    row['next_action'] = 'Review authentication, access, API scope and vendor MCP; then make a build decision'
    if name == 'Google Ads':
        row['fields']['verdict'] = {'value': 'needs approval for production access',
            'sources': ['https://developers.google.com/google-ads/api/docs/api-policy/access-levels'],
            'status': 'reviewed inference; test access available'}
        row['blocker'] = 'Production account API access requires the appropriate project access level'
        row['next_action'] = 'Enable the API for test access and apply for Explorer access before production integration'
    cli_sources = {'Sherlock': 'https://github.com/sherlock-project/sherlock',
                   'Mermaid CLI': 'https://github.com/mermaid-js/mermaid-cli'}
    if name in cli_sources:
        url = cli_sources[name]
        row['fields']['api_surface'] = {'value': 'local command-line tool', 'sources': [url],
            'status': 'reviewed; no claim about separate hosted services'}
        row['fields']['verdict'] = {'value': 'requires hosted wrapper for CLI', 'sources': [url],
            'status': 'reviewed inference for the named CLI'}
        row['blocker'] = 'The named product runs as a command-line tool; a hosted integration needs an execution environment'
        row['next_action'] = 'Assess isolation, execution limits, and whether a hosted wrapper is appropriate'
    row['confidence'] = 'partial' if any(v['status'].startswith('reviewed') for v in row['fields'].values()) else 'unresolved'
    row['first_pass'] = baseline['first_pass']
    row['candidate_pages'] = [{'url': x['url'], 'status': x['status']} for x in discovery['fetches']]
    out.append(row)

# Deliberate coverage sample: one app per assignment category, not random.
sample = ['HubSpot', 'Zendesk', 'Slack', 'Google Ads', 'Shopify', 'Apify', 'GitHub', 'Notion', 'Stripe', 'Reducto']
assert len({next(a['category'] for a in out if a['name'] == n) for n in sample}) == 10
log = []
for name in sample:
    row = next(a for a in out if a['name'] == name)
    for field in fields:
        checked = row['fields'][field]
        # The original pipeline used "unknown" for every one of these fields.
        original = row['first_pass'].get(field, 'unknown')
        assert original in ('unknown', 'unclear')
        log.append({'app': name, 'category': row['category'], 'field': field,
                    'original': original, 'rating': 'abstained',
                    'documentation_establishes': checked['value'], 'sources': checked['sources'],
                    'correction': checked['value'],
                    'reason': 'First pass intentionally abstained; documentation may still be unresolved'})
assert len(out) == 100 and len({a['name'] for a in out}) == 100 and len(log) == 60
Path('assessed_dataset.json').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
Path('six_field_review.json').write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding='utf-8')
print('100 unique apps; review: 60/60 abstained, answered 0/60, accuracy on answers undefined (0/0)')
print('Composio exact or alias:', sum(r['fields']['composio_toolkit']['value'] == 'listed' for r in out))
