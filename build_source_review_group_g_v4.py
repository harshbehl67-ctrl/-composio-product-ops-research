import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
rows = {row['app']: row for row in json.loads((ROOT / 'checked_dataset_v4.json').read_text(encoding='utf-8'))}
actions = []


def replace(app, field, old_url, old_quote, new_url, new_quote, title=None, published_at=None,
            published_label='undated', note=''):
    action = {'app': app, 'field': field, 'decision': 'replace', 'old_url': old_url,
              'old_quote': old_quote, 'new_url': new_url, 'new_quote': new_quote,
              'published_at': published_at, 'published_label': published_label, 'review_note': note}
    if title:
        action['new_title'] = title
    actions.append(action)


def reclassify(app, field, claim, note):
    actions.append({'app': app, 'field': field, 'decision': 'reclassify',
                    'claim': claim, 'review_note': note})


def keep(app, field, url, quote, method, note):
    actions.append({'app': app, 'field': field, 'decision': 'keep', 'old_url': url,
                    'old_quote': quote, 'verification_method': method, 'review_note': note})


replace('Help Scout', 'api_surface', 'https://developer.helpscout.com/llms.txt',
        '## Inbox API 2.0 (Primary API)\n\nThe primary REST API for managing Help Scout conversations, customers, and support operations.',
        'https://developer.helpscout.com/llms.txt',
        'The primary REST API for managing Help Scout conversations, customers, and support operations.',
        'Help Scout Developer APIs',
        note='The current plain-text index inserts base URL, authentication, rate-limit, and format lines between the heading and sentence. The replacement is the exact contiguous REST description.')

old_intercom = 'If you are building a private app for your paid Intercom workspace, log in through the Intercom app sign in and then go to the Developer Hub to create an app for that workspace, which we will show you in the next step.'
new_intercom = 'If you are building a private app for your paid Intercom workspace, log in through the Intercom app sign in and then go to the Developer Hub to create an app for that workspace, which we will show in the next step.'
for field in ('credential_gate', 'verdict'):
    replace('Intercom', field, 'https://developers.intercom.com/docs/build-an-integration/getting-started',
            old_intercom, 'https://developers.intercom.com/docs/build-an-integration/getting-started',
            new_intercom, 'Set up a Workspace',
            note='Rendered official text now says "show in the next step" rather than "show you in the next step"; the paid-workspace requirement is unchanged.')

replace('Front', 'official_mcp', 'https://help.front.com/en/articles/4883136',
        "If you want to use Front in an MCP client that doesn't (yet) have an official directory listing — or you're building your own internal agent — your workspace admin can create a private developer app in Front and use its credentials to connect.",
        'https://help.front.com/en/articles/4883136',
        "If you want to use Front in an MCP client that doesn't (yet) have an official directory listing - or if you're building your own internal agent - your workspace admin can create a private developer app in Front and use its credentials to connect.",
        'Front MCP',
        note='The rendered article uses hyphens and includes "if" before the internal-agent clause; the replacement is the exact current sentence.')

replace('Gladly', 'api_surface', 'https://help.gladly.com/developer-tutorials/docs/default-api-rate-limits.md',
        'Note that individual APIs may have their own API Rate Limit and will be documented as such. Otherwise, the following default rate limits apply.',
        'https://help.gladly.com/developer-tutorials/docs/default-api-rate-limits.md',
        'Note that individual APIs may have their API Rate Limit and will be documented as such. Otherwise, the following default rate limits apply.',
        'Default API Rate Limits',
        note='The current official Markdown omits "own"; the replacement matches the visible source exactly.')

replace('Gladly', 'credential_gate', 'https://help.gladly.com/developer-tutorials/docs/setup-and-testing/',
        "To allow a user to create API tokens and access the API:\n\n1. Log in to your **Gladly instance**.\n2. Open the **menu** on the top left-hand portion of the page.\n3. Navigate to **Settings > Users**.\n4. Search and click on the user profile that should have access.\n5. You'll see a permission called **API User**. Select it, while keeping the user's Agent role intact.\n6. Click **Save** to give access.",
        'https://help.gladly.com/developer-tutorials/docs/setup-and-testing/',
        "To allow a user to create API tokens and access the API: Log in to your Gladly instance. Open the menu on the top left-hand corner of the page. Navigate to Settings > Users. Search and click the user profile that should have access. You'll see a permission called API User. Select it, while keeping the user's Agent role intact. Click Save to give access.",
        'Set up and test your API integration',
        note='The rendered guide says "top left-hand corner" rather than "portion"; list markers and bold markup are normalized to visible text.')

replace('LiveAgent', 'api_surface', 'https://support.liveagent.com/802463-rest-api',
        'REST API\n\n### API key\n\n### API v1\n\n### API v3',
        'https://support.liveagent.com/802463-rest-api',
        'API key is an identity of your LiveAgent (like your username and password) which you can use to build your own custom integration solutions.',
        'REST API',
        note='The current page keeps the REST API title and API-key explanation but no longer exposes the old heading-only sequence as contiguous visible text.')
replace('LiveAgent', 'api_surface', 'https://support.liveagent.com/840770-complete-api-reference',
        'API version 1\nAgents\nApplication\nCompanies\nConversations\nCustomers\nCustomers groups',
        'https://support.liveagent.com/840770-complete-api-reference',
        'Api v.1 Agents Retrieves agent info and auth token Application Return application installation date and latest version Companies Retrieve list of companies Retrieve company info Conversations Delete conversation Retrieves all conversations Retrieves conversation info Retrieves all conversation messages Create new message in conversation Change status of the conversation Unassign a tag from a conversation Retrieve a list of tags assigned to a conversation Assign tag to a conversation Customers Delete custom field value in user contact Add custom field value to customer Retrieve customer groups Customers groups Delete customers group Retrieve customers group info Retrieve all groups of all customers Add customers group Change customers group',
        'Complete API reference',
        note='The current reference interleaves operation descriptions with resource names. The replacement is a contiguous visible excerpt preserving broad v1 resource coverage.')
replace('LiveAgent', 'credential_gate', 'https://www.liveagent.com/pricing/',
        'API keys\n\n1\n\n5\n\n10\n\nUnlimited\n\nLet third-party apps retrieve and push data and manage tickets from outside LiveAgent.',
        'https://www.liveagent.com/pricing/', 'API keys 1 5 10 Unlimited', 'LiveAgent pricing',
        note='The current visible comparison row contains the plan counts but no longer contains the old explanatory sentence; the replacement is the exact row text.')
replace('LiveAgent', 'official_mcp', 'https://www.liveagent.com/pricing/',
        'Business and Enterprise: connect LiveAgent’s MCP server to external AI tools such as Claude.',
        'https://www.liveagent.com/pricing/', 'AI MCP server for your own AI tools', 'LiveAgent Business plan',
        note="The current Business plan lists an AI MCP server for the customer's own AI tools; the older combined Business/Enterprise sentence is absent.")

old_paygent = 'We offer a sandbox environment with full API access at no cost. You can test transactions, webhooks, and integrations before going live. No credit card required to start.'
for field in ('credential_gate', 'verdict'):
    replace('Paygent Connect', field, 'https://www.gopaygent.com/pricing', old_paygent,
            'https://www.gopaygent.com/', 'Start for free No credit card required. Free plan available.',
            'Paygent developer platform',
            note='The current pricing page no longer contains the sandbox paragraph. The first-party homepage visibly states free no-card access; the separate homepage sandbox card remains documented on the page but is not needed for the gate classification.')

claim = copy.deepcopy(rows['Gorgias']['fields']['credential_gate'])
claim['reason'] = 'The official signup page states a seven-day all-features trial with no credit card. Private apps need no special creation process and can use access tokens. Public-app review and paid-plan MCP are separate distribution/feature gates. The signup page is undated; private-app guidance was updated 2025-09-16.'
claim['evidence'] = [
    {'url': 'https://www.gorgias.com/signup', 'title': 'Gorgias signup',
     'quote': 'Get started for free 7-day trial | All features unlocked | No credit card required.',
     'retrieved_at': '2026-11-24', 'published_at': None, 'published_label': 'undated'},
    {'url': 'https://developers.gorgias.com/docs/private-vs-public-app', 'title': 'Private vs. Public App',
     'quote': "You don't need to follow any special process to create a private app.",
     'retrieved_at': '2026-11-24', 'published_at': '2025-09-16',
     'published_label': 'Updated September 16, 2025'}
]
reclassify('Gorgias', 'credential_gate', claim,
           'The old pricing FAQ quotations are no longer visible. The current official signup page consolidates the seven-day, all-features, no-card trial evidence without duplicating three citations.')
replace('Gorgias', 'verdict', 'https://www.gorgias.com/pricing',
        'Yes, the Gorgias trial gives you access to all features so you can fully test the platform before committing.',
        'https://www.gorgias.com/signup',
        'Get started for free 7-day trial | All features unlocked | No credit card required.',
        'Gorgias signup',
        note='The current signup page visibly states the trial duration, feature access, and no-card requirement in one exact sentence.')

claim = copy.deepcopy(rows['QuickBooks']['fields']['official_mcp'])
claim['evidence'] = [source for source in claim['evidence']
                     if '/release-notes/general-release-notes' not in source['url']]
reclassify('QuickBooks', 'official_mcp', claim,
           'The dynamic release-notes route rendered an empty body in both direct and browser checks. The official repository and static Intuit connector guide already establish the local server and plugin distinction, so the inaccessible release-note citation is removed.')

claim = copy.deepcopy(rows['Aircall']['fields']['official_mcp'])
claim['evidence'] = [source for source in claim['evidence']
                     if '/articles/40626452723101' not in source['url']]
claim['reason'] = 'Aircall operates a remote MCP server at https://mcp.aircall.io/mcp using OAuth. It is in beta, requires Account Manager enrollment and an Admin connection, and is read-only for calls and conversation intelligence; the AI add-on is required for conversation-intelligence tools. The current support article is undated.'
reclassify('Aircall', 'official_mcp', claim,
           'The second support URL now contains unrelated partner-MCP release notes and no longer reproduces the old Aircall beta quotations. The current dedicated Aircall MCP article remains sufficient and is retained without the stale release-note citations.')

claim = copy.deepcopy(rows['SendGrid']['fields']['official_mcp'])
claim['evidence'] = [source for source in claim['evidence']
                     if source['url'] != 'https://docs.sendgrid.com/mcp']
reclassify('SendGrid', 'official_mcp', claim,
           "The SendGrid MCP route is a broken 404 link, so it is removed from checked evidence. The scoped no-vendor-execution-server finding remains supported by the merged product page and Twilio's official read-only documentation MCP page; the 404 attempt stays described in the review note and reason.")

keep('iPayX', 'credential_gate', 'https://www.ipayx.ai/pricing', '$299USD / mo',
     'headless Chromium rendered body innerText after extended wait (installed Chrome; no raw HTML)',
     'The current rendered pricing page shows "$299 USD / mo"; whitespace normalization reproduces the stored quotation. The shorter batch wait missed dynamically inserted pricing text.')

group = {
    'checked_at': '2026-11-24',
    'method': 'Current rendered-page inspection with installed Chrome and Qoder in-app browser, direct official text/Markdown/JSON/XML retrieval, and exact quote comparison; no search snippets or credentials.',
    'audit_summary': {'flagged_uses': 21, 'actions': len(actions),
                      'replace': sum(action['decision'] == 'replace' for action in actions),
                      'reclassify': sum(action['decision'] == 'reclassify' for action in actions),
                      'keep': sum(action['decision'] == 'keep' for action in actions),
                      'unresolved': 0,
                      'note': 'Stale wording is replaced, inaccessible or contradicted citations are removed, and the two dynamically rendered quotations are preserved as explicit browser keeps.'},
    'actions': actions,
    'unresolved': []
}
(ROOT / 'data' / 'source_review_group_g_v4.json').write_text(
    json.dumps(group, ensure_ascii=False, indent=2), encoding='utf-8')
print('actions', len(actions))
