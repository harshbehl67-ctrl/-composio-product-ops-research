"""Conservative evidence extractor over separately saved targeted-search results.

This pass is independent of the frozen baseline. Extracted claims are tentative
until independently reviewed; absence of a search hit never proves absence.
"""
import argparse
import concurrent.futures
import datetime
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
APPS = json.loads((ROOT / 'apps.json').read_text(encoding='utf-8'))
CATALOG = {x['app']: x for x in json.loads((ROOT / 'catalog_snapshot.json').read_text(encoding='utf-8'))['results']}
ALIASES = {x['app']: x for x in json.loads((ROOT / 'catalog_aliases.json').read_text(encoding='utf-8'))}
OUT = ROOT / 'data' / 'pass2'
OUT.mkdir(exist_ok=True)
ADDITIONAL = {'Slack': ['slack.dev'], 'Notion': ['notion.com'], 'Google Ads': ['google.com'],
              'LinkedIn Ads': ['microsoft.com', 'linkedin.com'], 'Threads (Meta)': ['meta.com', 'facebook.com', 'threads.net'],
              'WhatsApp Business': ['meta.com', 'facebook.com', 'whatsapp.com'],
              'Lark (Larksuite)': ['larksuite.com'], 'MongoDB Atlas': ['mongodb.com'],
              'Magento (Adobe Commerce)': ['adobe.com'], 'Amazon Selling Partner': ['amazon.com'],
              'Zoho CRM': ['zoho.com'], 'Zoho Cliq': ['zoho.com'], 'Reducto': ['reducto.ai']}
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; ProductOpsResearch/2.0)'}


def root_for(app):
    host = urlparse('https://' + app['hint'].split(' ')[0]).hostname or ''
    return '.'.join(host.split('.')[-2:])


def allowed(url, app):
    p = urlparse(url)
    host = (p.hostname or '').lower()
    roots = [root_for(app)] + ADDITIONAL.get(app['name'], [])
    if not any(host == r or host.endswith('.' + r) for r in roots):
        return False
    if host == 'github.com' and app['name'] in ('Sherlock', 'Mermaid CLI'):
        return p.path.lower().startswith('/' + app['hint'].split('github.com/', 1)[1].lower())
    if p.path in ('', '/'):
        return False
    return bool(re.search(r'api|auth|developer|docs|reference|mcp|integration|credential|token|platform', p.path, re.I))


def search_candidates(app):
    path = ROOT / 'data' / 'new_search' / f"{app['number']:03}.json"
    search = json.loads(path.read_text(encoding='utf-8'))
    text = '\n'.join(x.get('text', '') for x in search.get('search_response', {}).get('content', []) if x.get('type') == 'text')
    blocks = re.split(r'\n-{20,}\n', text)
    result = []
    for block in blocks:
        first = block.splitlines()[0] if block.splitlines() else ''
        m = re.search(r'\((https?://[^\s)]+)\)', first)
        if m and allowed(m.group(1), app):
            result.append({'url': m.group(1), 'title': first[:300], 'snippet': block[:2000]})
    # Include independently reviewed sources, not search snippets, as candidates.
    review = json.loads((ROOT / 'review.json').read_text(encoding='utf-8')) + json.loads((ROOT / 'extra_review.json').read_text(encoding='utf-8'))
    for item in review:
        if item['app'] == app['name'] and allowed(item['url'], app):
            result.append({'url': item['url'], 'title': 'Previously independently reviewed source', 'snippet': ''})
    unique = list({x['url']: x for x in result}.values())
    # Choose candidates that cover separate topics, then fill remaining slots.
    selected = []
    for pattern in (r'auth|credential|token', r'api|reference', r'mcp', r'access|pricing|plan|approval'):
        match = next((x for x in unique if x not in selected and re.search(pattern, x['url'] + ' ' + x['title'], re.I)), None)
        if match:
            selected.append(match)
    selected.extend(x for x in unique if x not in selected)
    return unique, selected[:6]


def fetch(candidate):
    try:
        response = requests.get(candidate['url'], headers=HEADERS, timeout=18)
        soup = BeautifulSoup(response.text, 'html.parser')
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        return {'url': response.url, 'requested_url': candidate['url'], 'status': response.status_code,
                'title': candidate['title'], 'text': soup.get_text(' ', strip=True)[:120000]}
    except Exception as exc:
        return {'url': candidate['url'], 'error': str(exc)}


def evidence(text, pattern):
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    return text[max(0, match.start()-140):min(len(text), match.end()+220)]


def extract(app, pages):
    fields = {k: {'value': 'unknown', 'sources': [], 'evidence': [], 'reason': 'Targeted search found no usable, claim-specific official documentation'}
              for k in ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')}
    auth_patterns = [('OAuth 2.0', r'\boauth\s*(?:2\.0|2)\b'), ('API key', r'\bapi[ -]key\b'),
                     ('Bearer token', r'\bbearer\s+(?:access\s+)?token\b'), ('Basic auth', r'\bbasic\s+auth(?:entication)?\b')]
    found_auth = []
    found_api = []
    for page in pages:
        if page.get('status') != 200 or not page.get('text') or not allowed(page['url'], app):
            continue
        text, url = page['text'], page['url']
        title = page.get('title', '')
        if re.search(r'auth|credential|token|api.key', url + ' ' + title, re.I):
            for label, pattern in auth_patterns:
                excerpt = evidence(text, pattern)
                if excerpt:
                    if label not in found_auth:
                        found_auth.append(label)
                    fields['auth']['sources'].append(url)
                    fields['auth']['evidence'].append({'url': url, 'excerpt': excerpt, 'method': label})
        for label, pattern in [('REST', r'\bREST(?:ful)?\s+API\b'), ('GraphQL', r'\bGraphQL\s+API\b')]:
            excerpt = evidence(text, pattern)
            if excerpt:
                if label not in found_api:
                    found_api.append(label)
                fields['api_surface']['sources'].append(url)
                fields['api_surface']['evidence'].append({'url': url, 'excerpt': excerpt, 'surface': label})
        if re.search('mcp', url + ' ' + title, re.I):
            brand = re.escape(re.sub(r'\s*\(.*?\)', '', app['name']).strip())
            excerpt = evidence(text, rf'(?:\b{brand}\b.{{0,70}}\bMCP\s+server\b|\bMCP\s+server\b.{{0,70}}\b{brand}\b|\bour\s+MCP\s+server\b)')
            if excerpt:
                fields['official_mcp'].update(value='yes', sources=[url], evidence=[{'url': url, 'excerpt': excerpt}], reason='')
    for field, values in [('auth', found_auth), ('api_surface', found_api)]:
        if values:
            fields[field]['value'] = values
            fields[field]['sources'] = list(dict.fromkeys(fields[field]['sources']))
            fields[field]['reason'] = ''
    entry = CATALOG[app['name']]
    match = entry['matches'][0] if entry['matches'] else ALIASES.get(app['name'])
    if match:
        fields['composio_toolkit'].update(value='listed', sources=[match['url']],
            evidence=[{'url': match['url'], 'excerpt': 'Composio catalog match; verify product scope'}], reason='')
    else:
        fields['composio_toolkit']['reason'] = 'No exact or reviewed alias match in saved catalog; absence not established'
    fields['credential_gate']['reason'] = 'No reliable automated access-tier extraction; targeted search results require claim-specific review'
    fields['verdict']['reason'] = 'Insufficient independently verified authentication, API and access evidence for a build decision'
    return fields


def run(app, force=False):
    output = OUT / f"{app['number']:03}.json"
    if output.exists() and not force:
        return app['name'], 'resumed'
    if output.exists() and force:
        reruns = ROOT / 'data' / 'pass2_reruns'
        reruns.mkdir(exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output = reruns / f"{app['number']:03}-{stamp}.json"
    candidates, selected = search_candidates(app)
    pages = [fetch(candidate) for candidate in selected]
    row = {'app': app, 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'source_search': f"data/new_search/{app['number']:03}.json", 'candidates': candidates,
           'selected': selected, 'pages': pages, 'claims': extract(app, pages),
           'validation': ['Automatic extraction is provisional and must be checked independently',
                          'Unknown does not mean the capability is absent']}
    output.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
    count = sum(x['value'] != 'unknown' for x in row['claims'].values())
    return app['name'], f"{len(pages)} fetched; {count}/6 fields answered provisionally"


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--app')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    selected = [x for x in APPS if not args.app or x['name'].casefold() == args.app.casefold()]
    if args.limit:
        selected = selected[:args.limit]
    if not selected:
        raise SystemExit('No matching app')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name, result in pool.map(lambda x: run(x, args.force), selected):
            print(name, result, flush=True)
