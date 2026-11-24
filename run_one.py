"""Research ONE app end to end and verify it: the runnable proof trigger.

    python run_one.py --app "Stripe"

What it does, for a single app of the 100:
  1. loads the researched record (all six claim fields with value, reason and
     evidence quotes + URLs);
  2. looks the app up in Composio's own catalog (GET /api/v3/toolkits/{slug});
  3. re-fetches every evidence URL and checks (a) the page is live, (b) it is on
     a first-party domain, and (c) each quote still appears in the page text;
  4. cross-checks Composio's auth schemes against the researched auth;
  5. prints one JSON object with the quotes, URLs and every verification result.

Add --offline to skip the network and only print the stored evidence plus the
catalog cross-check. The API key is read from .env and never printed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import requests

import catalog_lookup as lookup
import catalog_crosscheck as crosscheck
import composio_catalog_fetch as catalog
import verify_checked_sources as verifier
import context_pass_v4 as ctx

ROOT = Path(__file__).resolve().parent
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; ProductOpsResearch/4.0)'}


def load_app(name: str) -> dict:
    for app in lookup.load_dataset():
        if app['app'].casefold() == name.casefold():
            return app
    raise SystemExit(f'No app named {name!r} in checked_dataset_v4.json')


def check_url(url: str, quotes: list[str]) -> dict:
    """Liveness + quote reproduction for one URL, mirroring verify_checked_sources."""
    result = {'url': url, 'status': None, 'final_url': None, 'quotes': []}
    try:
        response = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
        result['status'] = response.status_code
        result['final_url'] = response.url
        if response.status_code == 200:
            page = verifier.visible_text(verifier.decoded_text(response))
            page_tokens = verifier.tokens(page)
            for quote in quotes:
                normalized = verifier.normalize(quote)
                quote_tokens = verifier.tokens(normalized)
                exact = bool(normalized and normalized in page)
                token_exact = bool(quote_tokens and verifier.contains_tokens(page_tokens, quote_tokens))
                result['quotes'].append({'quote': quote, 'exact': exact,
                                         'token_exact': token_exact, 'found': exact or token_exact})
        response.close()
    except Exception as exc:  # noqa: BLE001 - a failed fetch is a verification result
        result['error'] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Research and verify one app end to end.')
    parser.add_argument('--app', required=True, help='App name, e.g. "Stripe"')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--live', action='store_true',
                      help='Fetch evidence URLs and perform the Composio catalog check (default)')
    mode.add_argument('--offline', action='store_true', help='Skip network fetch of evidence URLs')
    args = parser.parse_args()

    app = load_app(args.app)

    # 1. Researched record: the six claim fields with evidence quotes + URLs.
    researched = {}
    for field, claim in app['fields'].items():
        researched[field] = {
            'value': claim.get('value'), 'status': claim.get('status'), 'reason': claim.get('reason'),
            'evidence': [{'url': e.get('url'), 'title': e.get('title'), 'quote': e.get('quote'),
                          'retrieved_at': e.get('retrieved_at')} for e in claim.get('evidence', [])],
        }

    # 2. Composio catalog entry for this app. Offline mode must not perform a
    # hidden catalog request: use the checked-in snapshot instead.
    if args.offline:
        snapshot = json.loads((ROOT / 'composio_catalog.json').read_text(encoding='utf-8'))
        catalog_record = next((item for item in snapshot['records']
                               if item['app'].casefold() == app['app'].casefold()), None)
        if catalog_record is None:
            raise SystemExit(f"No saved Composio catalog record for {app['app']}")
        catalog_record = dict(catalog_record)
        catalog_record['fetched_at'] = snapshot.get('fetched_at')
    else:
        catalog_record = catalog.probe(app)

    # 3. Verification loops: URL liveness, first-party domain, quote reproduction.
    evidence_checks = []
    quotes_total = quotes_found = first_party_ok = live = 0
    for field, claim in app['fields'].items():
        for evidence in claim.get('evidence', []):
            url = evidence.get('url')
            if not url:
                continue
            quote = evidence.get('quote')
            if args.offline:
                checked = {'url': url, 'status': None, 'final_url': None, 'quotes': [],
                           'skipped': 'offline'}
            else:
                checked = check_url(url, [quote] if quote else [])
            checked['field'] = field
            checked['first_party'] = ctx.official_source(url, app['app'], field)
            evidence_checks.append(checked)
            live += int(checked.get('status') == 200)
            first_party_ok += int(checked['first_party'])
            for quote_checked in checked['quotes']:
                quotes_total += 1
                quotes_found += int(quote_checked['found'])

    # 4. Auth cross-check (Composio catalog vs researched auth).
    research_methods, research_transport = crosscheck.researched_methods(app['fields']['auth']['value'])
    if catalog_record['in_composio']:
        comp_methods, comp_transport = crosscheck.composio_methods(catalog_record['auth_schemes'])
        comparison = crosscheck.classify(research_methods, comp_methods)
        if comparison == 'disagree_no_overlap' and not research_methods and research_transport:
            comparison = 'research_transport_only'
        auth_crosscheck = {
            'composio_methods': sorted(comp_methods), 'composio_transport': sorted(set(comp_transport)),
            'researched_methods': sorted(research_methods), 'researched_transport': sorted(set(research_transport)),
            'comparison': comparison, 'likely_cause': crosscheck.CAUSE.get(comparison, ''),
        }
    else:
        auth_crosscheck = {'comparison': 'not_in_catalog',
                           'researched_methods': sorted(research_methods),
                           'researched_transport': sorted(set(research_transport))}

    # 5. Which Composio research tools this key can actually use.
    session_file = ROOT / 'composio_session_check.json'
    composio_tools = {'path': 'unknown', 'note': 'run composio_session_research.py first'}
    if session_file.exists():
        session = json.loads(session_file.read_text(encoding='utf-8'))
        composio_tools = {'path': session.get('composio_path'), 'user_id': session.get('user_id'),
                          'toolkits': session.get('toolkits'),
                          'resolved_tool_slugs': [t['slug'] for t in session.get('raw_tool_checks', []) if t.get('ok')],
                          'findings': session.get('findings', [])}

    payload = {
        'app': app['app'], 'category': app.get('category'), 'number': app.get('number'),
        'researched': researched,
        'composio_catalog': {k: catalog_record[k] for k in
                             ('in_composio', 'composio_slug', 'auth_schemes', 'composio_managed_auth_schemes',
                              'no_auth', 'auth_guide_url', 'tools_count', 'triggers_count', 'http_status', 'fetched_at')},
        'verification': {
            'offline': args.offline,
            'urls_checked': len(evidence_checks), 'urls_live': live,
            'first_party_urls': first_party_ok,
            'quotes_checked': quotes_total, 'quotes_reproduced': quotes_found,
            'checks': evidence_checks,
        },
        'auth_crosscheck': auth_crosscheck,
        'composio_research_tools': composio_tools,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
