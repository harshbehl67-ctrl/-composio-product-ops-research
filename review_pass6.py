"""Independent AI-assisted six-field review of the deliberately tuned sample."""
import collections
import json
from pathlib import Path

apps = json.loads(Path('apps.json').read_text(encoding='utf-8'))
checked = {x['name']: x for x in json.loads(Path('reviewed_dataset.json').read_text(encoding='utf-8'))}
sample = ['HubSpot', 'Zendesk', 'Slack', 'Google Ads', 'Shopify', 'Apify', 'GitHub', 'Notion', 'Stripe', 'Reducto']
fields = ['auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict']
partial = {
    ('HubSpot', 'auth'): 'OAuth and bearer service keys are documented, but the extracted labels do not distinguish service keys from historical API keys.',
    ('HubSpot', 'credential_gate'): 'Free developer test accounts are documented; installing a public or creating a private app may require a super admin.',
    ('Zendesk', 'auth'): 'The API token and Basic descriptions are legacy migration paths; OAuth is current, and the separate Conversations API key is product-scoped.',
    ('Zendesk', 'credential_gate'): 'The cited administrator requirement is specific to legacy API-token creation; OAuth requirements are separate.',
    ('Google Ads', 'credential_gate'): 'Production access needs the appropriate approved access level; test access is available without that production approval.',
    ('Shopify', 'auth'): 'OAuth is valid for relevant flows, but tokens and authorization differ among Admin, Storefront and Customer Account APIs.',
    ('GitHub', 'auth'): 'Basic applies only to some endpoints; the answer omits personal access tokens, app tokens, and OAuth.',
}
correct = {
    ('HubSpot', 'official_mcp'), ('HubSpot', 'composio_toolkit'),
    ('Zendesk', 'composio_toolkit'),
    ('Slack', 'auth'), ('Slack', 'official_mcp'), ('Slack', 'composio_toolkit'),
    ('Google Ads', 'auth'), ('Google Ads', 'official_mcp'), ('Google Ads', 'composio_toolkit'),
    ('Shopify', 'api_surface'), ('Shopify', 'composio_toolkit'),
    ('Apify', 'api_surface'), ('Apify', 'official_mcp'), ('Apify', 'composio_toolkit'),
    ('GitHub', 'api_surface'), ('GitHub', 'official_mcp'), ('GitHub', 'composio_toolkit'),
    ('Notion', 'composio_toolkit'),
    ('Stripe', 'auth'), ('Stripe', 'official_mcp'), ('Stripe', 'composio_toolkit'),
}
records = []
for name in sample:
    app = next(a for a in apps if a['name'] == name)
    candidate = json.loads(Path(f"data/pass6/{app['number']:03}.json").read_text(encoding='utf-8'))
    for field in fields:
        claim = candidate['claims'][field]
        answer = claim['value']
        key = (name, field)
        truth = checked[name]['fields'][field]
        if answer == 'unknown':
            rating, note = 'abstained', 'The pass did not answer this field.'
        elif key in partial:
            rating, note = 'partial', partial[key]
        elif key in correct:
            rating, note = 'correct', 'The cited positive claim is supported by the independently checked vendor or catalog source.'
        else:
            rating, note = 'unresolved', 'The answer was not scored because independent review did not establish the full claim.'
        independent_sources = list(truth.get('sources', []))
        if key == ('GitHub', 'api_surface'):
            independent_sources = ['https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api', 'https://docs.github.com/en/graphql']
        if key == ('Shopify', 'api_surface'):
            independent_sources = ['https://shopify.dev/docs/api/usage/authentication', 'https://shopify.dev/docs/api/admin-rest']
        records.append({'app': name, 'category': app['category'], 'field': field,
                        'pass6_answer': answer, 'pass6_sources': claim['sources'],
                        'pass6_publication_labels': [e.get('published_label') for e in claim.get('evidence', []) if e.get('published_label')],
                        'rating': rating, 'review_note': note, 'independent_sources': independent_sources,
                        'correction': truth['value']})
counts = collections.Counter(r['rating'] for r in records)
answered = sum(r['pass6_answer'] != 'unknown' for r in records)
scored = counts['correct'] + counts['partial'] + counts['incorrect']
assert len(records) == 60 and len({r['category'] for r in records}) == 10
assert answered == scored + counts['unresolved']
weighted = counts['correct'] + counts['partial'] * 0.5
result = {'sample': 'Deliberately selected ten-category sample used during rule tuning; not a random holdout',
          'scoring': 'strict: correct/scored; half-credit: (correct + 0.5 * partial)/scored; abstained and unresolved excluded',
          'total_claims': 60, 'answered': answered, 'ratings': dict(counts), 'scored_answered': scored,
          'strict_numerator': counts['correct'], 'weighted_numerator': weighted,
          'strict_accuracy': counts['correct']/scored if scored else None,
          'weighted_accuracy': weighted/scored if scored else None, 'records': records}
Path('pass6_review.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
print('Coverage', f'{answered}/60', 'ratings', dict(counts),
      'strict', f"{counts['correct']}/{scored}", 'half-credit', f'{weighted}/{scored}')
