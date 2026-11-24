"""Cross-check Composio's own auth schemes against the researched auth, per app.

This is an automated verification loop. Composio's catalog states which schemes a
toolkit supports (`composio_managed_auth_schemes` plus the modes in
`auth_config_details`). The research states which methods the vendor documents.
Where the two disagree we record the app, the two method sets and a likely cause.

The classifier is deliberately transparent and coarse: it looks for explicit
keywords in the researched auth text and maps Composio's scheme codes onto the
same vocabulary. "Bearer" and "access token" are treated as transports, not
methods, so a Composio BEARER_TOKEN scheme is noted separately rather than
counted as an auth method.

Inputs:  composio_catalog.json, checked_dataset_v4.json
Output:  catalog_crosscheck.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Composio scheme code -> our canonical method token. BEARER_TOKEN is a
# transport (a bearer credential can be an API key or an OAuth access token),
# so it is recorded separately and never counted as a method.
SCHEME_MAP = {
    'OAUTH2': 'oauth2',
    'DCR_OAUTH': 'oauth2',
    'S2S_OAUTH2': 'oauth2_client_creds',
    'API_KEY': 'api_key',
    'BASIC': 'basic',
    'BEARER_TOKEN': None,  # transport
}

# High-precision keyword groups for the researched auth text. Text is
# separators-normalised first (see normalise) so "api_key", "client-id" and
# "basic_auth" match their spaced forms.
RESEARCH_PATTERNS = [
    ('none', r'no account or api authentication|no api authentication|no authentication|none for local cli|without authentication'),
    ('oauth2_client_creds', r'client credentials|client creds|server to server|two legged|2 legged|machine to machine'),
    ('oauth2_service_account', r'service account'),
    ('oauth2', r'\boauth|authorization code|authorisation code|pkce|three legged|3 legged|member access token|user delegated|user authorization|user consent|user access token|login with amazon|\bslas\b'),
    ('basic', r'http basic|basic auth|basic authentication|basic style|http digest|digest authentication'),
    ('jwt_signed', r'\bjwt\b|json web token|signature version 4|key pair|signed api key|\bhmac\b|ed25519|\brsa\b'),
    ('api_key', r'api key|apikey|personal access token|personal api token|api token|bot\s+(?:authentication\s+)?tokens?|app key|secret key|consumer key|consumer secret|client secret|client id|app secret|app id|private key|integration key|addon key|mcp key|system user access token|publishable|secret project api key|private api key|public api key|agent api key|user token|service key|developer token|api account|access key'),
]
TRANSPORT_PATTERNS = [
    ('bearer', r'bearer'),
    ('access_token', r'access token'),
]


def normalise(text: str) -> str:
    """Lower-case and turn _ - / into spaces so keyword matching is separator-agnostic."""
    return re.sub(r'[_\-/]+', ' ', text.lower())


def researched_methods(texts: list[str]) -> tuple[set[str], list[str]]:
    joined = normalise(' '.join(t for t in texts if t))
    methods = {name for name, pat in RESEARCH_PATTERNS if re.search(pat, joined)}
    # "none" only counts when nothing else is documented.
    if methods - {'none'}:
        methods.discard('none')
    transports = [name for name, pat in TRANSPORT_PATTERNS if re.search(pat, joined)]
    return methods, transports


def composio_methods(schemes: list[str]) -> tuple[set[str], list[str]]:
    methods = {SCHEME_MAP[s] for s in schemes if SCHEME_MAP.get(s)}
    transports = ['bearer' for s in schemes if s == 'BEARER_TOKEN']
    return methods, transports


def classify(research: set[str], composio: set[str]) -> str:
    overlap = research & composio
    if not research and not composio:
        return 'both_none'
    if not overlap:
        return 'disagree_no_overlap'
    if composio - research:
        return 'composio_broader'
    if research - composio:
        return 'research_broader'
    return 'agree'


CAUSE = {
    'disagree_no_overlap': 'Research and Composio share no auth method; check the toolkit mapping, and whether the research missed the scheme Composio implements.',
    'composio_broader': 'Composio implements a scheme the research does not mention; the research likely under-reported the vendor\u2019s methods.',
    'research_broader': 'The research documents methods Composio does not implement; Composio covers a subset, which is expected.',
    'research_transport_only': 'The research documents only a bearer/access-token transport and no underlying method; the catalog names a concrete scheme. A human should confirm whether the credential is really a PAT or OAuth.',
}


def main() -> int:
    catalog = json.loads((ROOT / 'composio_catalog.json').read_text(encoding='utf-8'))
    dataset = {a['app']: a for a in json.loads((ROOT / 'checked_dataset_v4.json').read_text(encoding='utf-8'))}

    rows = []
    for rec in catalog['records']:
        app = rec['app']
        research, r_transport = researched_methods(dataset[app]['fields']['auth']['value'])
        comp, c_transport = composio_methods(rec['auth_schemes'])
        if not rec['in_composio']:
            rows.append({
                'app': app, 'in_catalog': False,
                'composio_slug': None, 'composio_schemes': [],
                'composio_methods': [], 'composio_transport': [],
                'researched_methods': sorted(research), 'researched_transport': sorted(set(r_transport)),
                'overlap': [], 'composio_not_in_research': [], 'research_not_in_composio': sorted(research),
                'comparison': 'not_in_catalog', 'likely_cause': 'No Composio toolkit matched this app, so there is no catalog auth to compare against.',
            })
            continue
        comparison = classify(research, comp)
        # A research entry that documents only a bearer/access token and no
        # method is its own case: the transport is known but the method is not.
        if comparison == 'disagree_no_overlap' and not research and r_transport:
            comparison = 'research_transport_only'
        rows.append({
            'app': app, 'in_catalog': True,
            'composio_slug': rec['composio_slug'], 'composio_schemes': rec['auth_schemes'],
            'composio_methods': sorted(comp), 'composio_transport': sorted(set(c_transport)),
            'researched_methods': sorted(research), 'researched_transport': sorted(set(r_transport)),
            'overlap': sorted(research & comp),
            'composio_not_in_research': sorted(comp - research),
            'research_not_in_composio': sorted(research - comp),
            'comparison': comparison,
            'likely_cause': CAUSE.get(comparison, ''),
        })

    in_cat = [r for r in rows if r['in_catalog']]
    by_comparison: dict[str, int] = {}
    for r in in_cat:
        by_comparison[r['comparison']] = by_comparison.get(r['comparison'], 0) + 1

    disagreements = [r for r in in_cat if r['comparison'] not in ('agree', 'both_none')]
    payload = {
        'source': 'composio_catalog.json vs checked_dataset_v4.json (researched auth)',
        'fetched_at': catalog['fetched_at'],
        'apps_total': len(rows),
        'apps_in_catalog': len(in_cat),
        'apps_not_in_catalog': len(rows) - len(in_cat),
        'by_comparison': by_comparison,
        'disagreements': len(disagreements),
        'disagreement_apps': [r['app'] for r in disagreements],
        'records': rows,
    }
    (ROOT / 'catalog_crosscheck.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'Catalog cross-check over {len(in_cat)} apps that are in Composio:')
    for key in ('agree', 'composio_broader', 'research_broader', 'disagree_no_overlap', 'both_none'):
        if by_comparison.get(key):
            print(f'  {key}: {by_comparison[key]}')
    print(f'  not in catalog: {len(rows) - len(in_cat)}')
    if by_comparison.get('disagree_no_overlap'):
        print('  no-overlap apps:',
              [r['app'] for r in in_cat if r['comparison'] == 'disagree_no_overlap'])
    print('Wrote catalog_crosscheck.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
