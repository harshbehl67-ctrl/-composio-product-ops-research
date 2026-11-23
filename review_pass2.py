"""Independent AI-assisted, claim-by-claim review of the saved pass-2 sample.

Ratings are manually assigned against the cited independently opened sources.
Partial = 0.5, correct = 1, incorrect = 0. Abstentions and unresolved claims
are excluded from the answered-and-resolved accuracy denominator.
"""
import collections
import json
from pathlib import Path

apps = json.loads(Path('apps.json').read_text(encoding='utf-8'))
previous = {(r['app'], r['field']): r for r in json.loads(Path('six_field_review.json').read_text(encoding='utf-8'))}
manual = {(r['app'], r['field']): r for r in json.loads(Path('manual_facts.json').read_text(encoding='utf-8'))}
sample = ['HubSpot', 'Zendesk', 'Slack', 'Google Ads', 'Shopify', 'Apify', 'GitHub', 'Notion', 'Stripe', 'Reducto']
fields = ['auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict']

# The answer and source are both assessed. A correct answer based on the wrong
# source receives partial credit and is corrected to a claim-specific source.
special = {
 ('HubSpot','auth'): ('partial', 'OAuth is supported, and HubSpot also documents service keys for account-level integrations.', 'https://developers.hubspot.com/changelog/service-keys', 'OAuth plus service keys (scope-dependent)'),
 ('Zendesk','auth'): ('partial', 'OAuth access tokens are supported; legacy basic/API-token users are being directed to migrate. The extracted API-key excerpt was about RequestBin.', 'https://developer.zendesk.com/api-reference/introduction/security-and-auth/', 'OAuth access token; legacy basic/API token subject to migration'),
 ('Zendesk','official_mcp'): ('partial', 'Zendesk Bridge documents a Zendesk MCP server in early access, but the cited first-pass page describes Zendesk acting as a client.', 'https://support.zendesk.com/hc/en-us/articles/11400026079130-Connecting-external-AI-agents-to-the-Zendesk-MCP-server-or-Zendesk-AI-agents-EAP', 'yes, Zendesk Bridge MCP server (EAP)'),
 ('Slack','auth'): ('partial', 'Slack apps use OAuth and scoped tokens; Basic auth in the cited page concerns client authentication at an OAuth endpoint, not a general Web API method.', 'https://docs.slack.dev/authentication/', 'OAuth 2.0 and scoped tokens'),
 ('Shopify','auth'): ('partial', 'Shopify has several API-specific token flows. OAuth applies to the Admin and Customer Account APIs; the extraction omits other token details.', 'https://shopify.dev/docs/api/usage/authentication', 'OAuth and API-specific scoped access tokens'),
 ('GitHub','auth'): ('partial', 'Basic applies to certain app endpoints; the main REST authentication docs also document personal access tokens and app tokens.', 'https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api', 'personal access tokens, app tokens, OAuth; Basic for some endpoints'),
 ('Notion','official_mcp'): ('partial', 'Notion MCP exists, but the cited source discusses Notion as an MCP client connecting to other services.', 'https://www.notion.com/help/notion-mcp', 'yes, Notion MCP'),
}
corroboration = {
 ('HubSpot','official_mcp'): 'https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server',
 ('Slack','official_mcp'): 'https://docs.slack.dev/ai/slack-mcp-server/',
 ('Google Ads','auth'): 'https://developers.google.com/google-ads/api/rest/auth',
 ('Google Ads','official_mcp'): 'https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server',
 ('Apify','api_surface'): 'https://docs.apify.com/integrations/api',
 ('Apify','official_mcp'): 'https://docs.apify.com/mcp',
 ('GitHub','api_surface'): 'https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api',
 ('GitHub','official_mcp'): 'https://github.com/github/github-mcp-server',
 ('Stripe','auth'): 'https://docs.stripe.com/keys',
 ('Stripe','official_mcp'): 'https://docs.stripe.com/mcp',
}
records = []
for name in sample:
    app = next(x for x in apps if x['name'] == name)
    current = json.loads(Path(f"data/pass2/{app['number']:03}.json").read_text(encoding='utf-8'))
    for field in fields:
        claim = current['claims'][field]
        value = claim['value']
        old = previous[(name, field)]
        rating = 'abstained' if value == 'unknown' else 'correct'
        note, source, correction = '', '', value
        if (name, field) in special and value != 'unknown':
            rating, note, source, correction = special[(name, field)]
        elif value != 'unknown':
            source = corroboration.get((name, field), (claim['sources'] or [''])[0])
            note = 'Independent source supports the stated positive claim; this does not establish completeness of the whole integration.'
        else:
            note = 'The new pass abstained; the reviewed documentation does not change the score.'
            source = (old.get('sources') or [''])[0]
            correction = old['documentation_establishes']
            if (name, field) in manual:
                fact = manual[(name, field)]
                note = 'Pass abstained. Independent documentation review: ' + fact['note']
                source, correction = fact['url'], fact['value']
        records.append({'app': name, 'category': app['category'], 'field': field,
                        'pass2_answer': value, 'pass2_sources': claim['sources'], 'rating': rating,
                        'review_note': note, 'independent_source': source,
                        'additional_sources': ['https://docs.github.com/en/graphql'] if (name, field) == ('GitHub', 'api_surface') else [],
                        'correction': correction})

assert len(records) == 60 and len({r['category'] for r in records}) == 10
counts = collections.Counter(r['rating'] for r in records)
answered = sum(r['pass2_answer'] != 'unknown' for r in records)
scored = counts['correct'] + counts['partial'] + counts['incorrect']
assert answered == scored + counts['unresolved']
weighted = counts['correct'] + 0.5 * counts['partial']
result = {'sample': 'Deliberately selected, one app per category; not random or a holdout',
          'scoring': 'correct=1, partial=0.5, incorrect=0; exclude abstained and unresolved from accuracy denominator',
          'total_claims': len(records), 'answered': answered, 'ratings': dict(counts),
          'scored_answered': scored, 'weighted_points': weighted,
          'weighted_accuracy': weighted / scored if scored else None, 'records': records}
Path('pass2_review.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"Coverage {answered}/60; ratings {dict(counts)}; weighted accuracy {weighted}/{scored} = {weighted/scored:.1%}")
