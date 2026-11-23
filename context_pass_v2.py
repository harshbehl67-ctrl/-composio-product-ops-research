"""A separate, conservative context-aware experiment on 100 apps.

The frozen baseline and pass 2 are inputs only. Results are provisional until
independently reviewed. No Composio toolkit is evidence of a vendor MCP server.
"""
import argparse
import concurrent.futures
import datetime
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import improved_pass as prior

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'pass4'
OUT.mkdir(exist_ok=True)


def classify_mcp(title, text, brand):
    """Return a scoped result and quote; reject client, negation and conflicts."""
    title = title or ''
    text = text or ''
    if re.search(r'\b(?:mcp client|connect (?:to |external )?mcp servers|connect mcp servers to)\b', title, re.I):
        return 'unknown', '', 'Source describes an MCP client or connection to external servers.'
    negative = re.search(r"(?:do(?:es)?\s+not|don't|doesn't|not|never|no longer)\s+(?:currently\s+)?(?:offer|provide|have|support)[^.\n]{0,90}\bMCP\s+serv(?:er|ier)\b|\bMCP\s+server\b.{0,45}\b(?:is|are)\s+(?:currently\s+)?not\s+(?:available|offered|supported)\b|\bno\s+(?:official\s+)?MCP\s+server\b", text, re.I)
    brand = re.sub(r'\s*\(.*?\)', '', brand).strip()
    phrase = rf'(?:\b{re.escape(brand)}(?:\'s)?\b.{{0,50}}\bMCP\s+server\b|\bour\s+MCP\s+server\b)'
    positive = re.search(phrase, text, re.I)
    if negative:
        excerpt = text[max(0, negative.start()-80):negative.end()+140]
        # A positive phrase in a title can simply name the topic of a denial.
        return 'no per source; date and scope need review', excerpt, 'Explicit negation; do not infer a current universal absence.'
    if positive:
        excerpt = text[max(0, positive.start()-80):positive.end()+160]
        if re.search(r'\b(?:external|third.party|another vendor)\b', excerpt, re.I) and re.search(r'\b(?:connect|client)\b', excerpt, re.I):
            return 'unknown', excerpt, 'Passage may describe a client connecting to another vendor.'
        return 'yes (provisional)', excerpt, 'Review vendor ownership, dates, and scope.'
    return 'unknown', '', 'No explicit vendor-server statement in the retrieved text.'


def snippets(text, patterns):
    found = []
    for label, pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            excerpt = text[max(0, m.start()-100):min(len(text), m.end()+180)]
            found.append((label, excerpt))
    return found


def api_snippets(text, patterns):
    """Suppress negated API-type mentions, retaining a direct excerpt."""
    found = []
    for label, pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            prefix = text[max(0, match.start()-55):match.start()]
            suffix = text[match.end():min(len(text), match.end()+55)]
            if re.search(r"(?:\bnot\s+(?:an?\s+|the\s+)?|\bno\s+(?:an?\s+)?|\bwithout\s+)$", prefix, re.I):
                continue
            if re.match(r'\s+(?:is|are)\s+(?:currently\s+)?not\s+(?:available|supported|offered)', suffix, re.I):
                continue
            found.append((label, text[max(0, match.start()-100):min(len(text), match.end()+180)]))
            break
    return found


def candidates(app, previous):
    path = ROOT / 'data' / 'pass4_search' / f"{app['number']:03}.json"
    data = json.loads(path.read_text(encoding='utf-8'))
    text = '\n'.join(c.get('text', '') for c in data.get('response', {}).get('content', []) if c.get('type') == 'text')
    existing = {p.get('requested_url', p.get('url')) for p in previous}
    chosen = []
    for block in re.split(r'\n-{20,}\n', text):
        lines = block.splitlines()
        if not lines:
            continue
        m = re.search(r'\((https?://[^\s)]+)\)', lines[0])
        if not m or not prior.allowed(m.group(1), app) or m.group(1) in existing:
            continue
        published = re.search(r'Published:\s*([^;\n]+)', block)
        chosen.append({'url': m.group(1), 'title': lines[0][:300],
                       'published_label': published.group(1).strip() if published else None})
        existing.add(m.group(1))
    selected = []
    for pattern in (r'auth|token|credential', r'api|reference', r'access|plan|pricing'):
        match = next((x for x in chosen if x not in selected and re.search(pattern, x['title'] + x['url'], re.I)), None)
        if match:
            selected.append(match)
    return chosen, selected[:3]


def extract(app, pages):
    fields = {k: {'value': 'unknown', 'sources': [], 'evidence': [], 'reason': 'No sufficiently specific positive evidence extracted; review targeted search results.'}
              for k in ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')}
    methods = [('OAuth 2.0', r'\boauth\s*(?:2(?:\.0)?|v2)\b'),
               ('API key', r'\bapi[ -]key\b'), ('API token', r'\bapi\s+(?:access\s+)?token\b'),
               ('Bearer token', r'\bbearer\s+(?:access\s+)?token\b'), ('Basic authentication', r'\bbasic\s+auth(?:entication)?\b')]
    api_types = [('REST', r'\bREST(?:ful)?(?:\s+(?:Admin|Web|Management|Public))?\s+APIs?\b'),
                 ('GraphQL', r'\bGraphQL(?:\s+(?:Admin|Storefront|Management|Public|Core))?\s+APIs?\b')]
    gate_types = [
        ('free or trial developer credential path', r'\b(?:free developer account|free developer workspace|free trial)\b.{0,120}\b(?:API|token|credential|developer|app)\b'),
        ('paid plan API condition', r'\b(?:free plan)\b.{0,100}\b(?:does not|doesn.t|excludes?)\b.{0,80}\bAPI\b'),
        ('administrator controls credential', r'\b(?:must be an?\s+administrator|requires?\s+admin(?:istrator)?\s+access)\b.{0,120}\b(?:API|token|credential)\b'),
        ('approval required', r'\b(?:API|app|integration)\b.{0,80}\b(?:requires?|must obtain)\b.{0,50}\b(?:approval|review)\b'),
    ]
    mcp_votes = []
    for p in pages:
        if p.get('status') != 200 or not p.get('text') or not prior.allowed(p['url'], app):
            continue
        text, title, url = p['text'], p.get('title', ''), p['url']
        if re.search(r'auth|credential|token|api.key', title + ' ' + url, re.I):
            for value, excerpt in snippets(text, methods):
                if re.search(r'\bRequestBin\b', excerpt, re.I):
                    continue
                if value == 'Basic authentication' and re.search(r'\b(?:client_id|client_secret|token endpoint)\b', excerpt, re.I):
                    value = 'Basic authentication (OAuth client or endpoint-specific)'
                fields['auth']['evidence'].append({'value': value, 'url': url, 'excerpt': excerpt, 'published_label': p.get('published_label')})
        for value, excerpt in api_snippets(text, api_types):
            fields['api_surface']['evidence'].append({'value': value, 'url': url, 'excerpt': excerpt, 'published_label': p.get('published_label')})
        for value, excerpt in snippets(text, gate_types):
            fields['credential_gate']['evidence'].append({'value': value, 'url': url, 'excerpt': excerpt, 'published_label': p.get('published_label')})
        if re.search(r'\bmcp\b', title + ' ' + url, re.I) and 'composio.dev' not in (urlparse(url).hostname or ''):
            value, excerpt, reason = classify_mcp(title, text, app['name'])
            if value != 'unknown':
                mcp_votes.append(value)
                fields['official_mcp']['evidence'].append({'value': value, 'url': url, 'excerpt': excerpt,
                    'published_label': p.get('published_label'), 'context_warning': reason})
    for field in ('auth', 'api_surface', 'credential_gate'):
        evidence = fields[field]['evidence']
        if evidence:
            fields[field].update(value=list(dict.fromkeys(e['value'] for e in evidence)),
                                 sources=list(dict.fromkeys(e['url'] for e in evidence)),
                                 reason='Provisional extraction: validate scope and completeness against the cited page.')
    if mcp_votes:
        positive = any(x.startswith('yes') for x in mcp_votes)
        negative = any(x.startswith('no') for x in mcp_votes)
        fields['official_mcp'].update(value='unknown' if positive and negative else ('yes (provisional)' if positive else 'no per dated source (provisional)'),
            sources=list(dict.fromkeys(e['url'] for e in fields['official_mcp']['evidence'])),
            reason='Conflicting positive and negative sources require dated review.' if positive and negative else 'Provisional; check source date, scope, and vendor ownership.')
    item = prior.CATALOG[app['name']]
    match = item['matches'][0] if item['matches'] else prior.ALIASES.get(app['name'])
    if match:
        fields['composio_toolkit'].update(value='listed', sources=[match['url']], reason='Catalog match; scope needs review.')
    else:
        fields['composio_toolkit']['reason'] = 'No exact or reviewed alias match; absence is not established.'
    gate = fields['credential_gate']['value']
    if gate != 'unknown' and fields['auth']['value'] != 'unknown' and fields['api_surface']['value'] != 'unknown':
        fields['verdict'].update(value='provisional: investigate documented access condition',
            sources=list(dict.fromkeys(fields['credential_gate']['sources'] + fields['api_surface']['sources'] + fields['auth']['sources'])),
            reason='Do not promote this inference without claim-specific review.')
    else:
        fields['verdict']['reason'] = 'A supported access path, authentication method and API surface were not all extracted.'
    return fields


def run(app):
    output = OUT / f"{app['number']:03}.json"
    if output.exists():
        return app['name'], 'resumed'
    prior_data = json.loads((ROOT / 'data' / 'pass2' / f"{app['number']:03}.json").read_text(encoding='utf-8'))
    cached = prior_data['pages']
    found, selected = candidates(app, cached)
    new_pages = []
    for candidate in selected:
        page = prior.fetch(candidate)
        page['published_label'] = candidate['published_label']
        new_pages.append(page)
    pages = cached + new_pages
    result = {'app': app, 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'prior_source': f"data/pass2/{app['number']:03}.json", 'search_source': f"data/pass4_search/{app['number']:03}.json",
              'new_candidates': found, 'selected': selected, 'new_pages': new_pages, 'claims': extract(app, pages),
              'validation': ['All claims are provisional', 'No vendor MCP inference from Composio catalog',
                             'Negated MCP or client-only source is not counted as vendor-server proof']}
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return app['name'], sum(c['value'] != 'unknown' for c in result['claims'].values())


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--app')
    p.add_argument('--workers', type=int, default=10)
    args = p.parse_args()
    apps = [a for a in prior.APPS if not args.app or a['name'].casefold() == args.app.casefold()]
    if not apps:
        raise SystemExit('No matching app')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name, count in pool.map(run, apps):
            print(name, f'{count}/6 provisional fields', flush=True)
