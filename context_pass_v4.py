"""Conservative context-aware extraction and checked-evidence validation."""
import re
from datetime import date
from urllib.parse import urlparse

import improved_pass as prior

FIELDS = ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')
OFFICIAL_REPOS = {
    'GitHub': ('github/github-mcp-server',),
    'QuickBooks': ('intuit/quickbooks-online-mcp-server',),
    'Notion': ('make-notion/notion-sdk-js',),
    'Linear': ('linear/linear',),
    'Mermaid CLI': ('mermaid-js/mermaid-cli',),
    'Sherlock': ('sherlock-project/sherlock',),
    'Firecrawl': ('firecrawl/firecrawl-docs',),
    'Consensus': ('consensus-nlp/consensus-api', 'consensus-nlp/consensus-mcp'),
}
VERIFIED_ADDITIONAL = {
    'Sherlock': ['sherlockproject.xyz'],
    'Coda': ['superhuman.com'],
    'Harvest': ['getharvest.com'],
    'Fathom': ['fathom.ai'],
    'Mermaid CLI': ['mermaid.js.org'],
    'GitHub': ['docs.github.com', 'api.github.com'],
    'Binance': ['binance.com', 'binance-docs.github.io'],
    'Sentry': ['sentry.dev'],
    'Paygent Connect': ['gopaygent.com', 'transactiongateway.com', 'nmi.com'],
    'GoHighLevel': ['gohighlevel.com', 'leadconnectorhq.com', 'highlevel.stoplight.io'],
    'Podio': ['progress.com'],
    'Front': ['frontapp.com'],
    'Amazon Selling Partner': ['aboutamazon.com', 'amazonservices.com'],
    'SendGrid': ['twilio.com'],
    'fanbasis': ['commas.com'],
}
OFFICIAL_PAGES = {'Binance': ('binance-docs.github.io',)}
SHARED_CODE_HOSTS = {'github.com', 'github.io', 'raw.githubusercontent.com', 'api.github.com'}
RESOURCE_TERMS = (
    'user', 'contact', 'company', 'account', 'deal', 'lead', 'ticket', 'conversation',
    'message', 'channel', 'project', 'issue', 'task', 'event', 'payment', 'invoice',
    'order', 'product', 'customer', 'subscription', 'file', 'repository', 'commit',
    'campaign', 'ad', 'email', 'list', 'record', 'table', 'database', 'query',
)


def official_source(url, app_name, field):
    host = (urlparse(url).hostname or '').lower()
    if field == 'composio_toolkit':
        return host == 'composio.dev' or host.endswith('.composio.dev')
    if host == 'composio.dev' or host.endswith('.composio.dev'):
        return False
    app = next(a for a in prior.APPS if a['name'] == app_name)
    if host == 'github.io':
        return host in OFFICIAL_PAGES.get(app_name, ())
    if host in ('raw.githubusercontent.com', 'github.com', 'api.github.com'):
        parts = urlparse(url).path.strip('/').lower().split('/')
        if host == 'api.github.com':
            parts = parts[1:] if parts[:1] == ['repos'] else []
        repo = '/'.join(parts[:2]) if len(parts) >= 2 else ''
        return repo in OFFICIAL_REPOS.get(app_name, ())
    roots = [prior.root_for(app)] + prior.ADDITIONAL.get(app_name, []) + VERIFIED_ADDITIONAL.get(app_name, [])
    roots = [root for root in roots if '.' in root and root not in SHARED_CODE_HOSTS]
    return any(host == root or host.endswith('.' + root) for root in roots)


def _negated(text, start, end):
    prefix = re.split(r'[.!?;,\n]', text[max(0, start - 100):start])[-1]
    suffix = re.split(r'[.!?;,\n]', text[end:end + 100])[0]
    if re.search(r"\b(?:not|no|never|without|doesn't|don't|isn't|aren't|cannot|can't)\b", prefix, re.I):
        return True
    return bool(re.match(r'\s+(?:is|are|was|were)?\s*(?:currently\s+)?(?:not|never|no longer)\b', suffix, re.I))


def _excerpt(text, start, end, before=90, after=170):
    return text[max(0, start - before):min(len(text), end + after)].strip()


def classify_mcp(title, text, brand, source_url=''):
    title, text, brand = title or '', text or '', re.sub(r'\s*\(.*?\)', '', brand).strip()
    if source_url and (urlparse(source_url).hostname or '').endswith('composio.dev'):
        return 'unknown', '', 'Composio catalog evidence cannot establish a vendor MCP server.'
    if re.search(r'\b(?:mcp client|connect (?:to |external )?mcp servers|connect mcp servers to|use external mcp)\b', title, re.I):
        return 'client_only', _excerpt(text, 0, min(len(text), 180)), 'Source describes connecting to external MCP servers, not operating a vendor server.'
    negative_patterns = (
        rf"(?:\bwe\b|\b{re.escape(brand)}\b)\s+(?:currently\s+)?(?:do(?:es)?\s+not|don't|doesn't|never|no longer)\s+(?:currently\s+)?(?:offer|provide|have|support|maintain)[^.\n]{{0,100}}\bMCP\s+serv(?:er|ier)\b",
        rf"\b{re.escape(brand)}(?:'s)?\s+MCP\s+server\b.{{0,60}}\b(?:is|are)\s+(?:currently\s+)?not\s+(?:available|offered|supported|maintained)\b",
        r'\bno\s+(?:official\s+)?MCP\s+server\b',
        r'\bMCP\s+server\b.{0,50}\b(?:is|are)\s+(?:currently\s+)?not\s+(?:available|offered|supported)\b',
    )
    for pattern in negative_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return 'no_vendor_server_documented', _excerpt(text, match.start(), match.end()), 'Explicit dated/scoped negation; not a universal absence claim.'
    if re.search(r'\b(?:connect|connecting|client)\b.{0,80}\b(?:external|third.party|other vendors?)\b.{0,80}\bMCP\s+servers?\b', text, re.I):
        return 'client_only', _excerpt(text, 0, min(len(text), 220)), 'Passage describes a client connection to external servers.'
    positive_patterns = (
        rf"\b{re.escape(brand)}(?:'s)?\b.{{0,55}}\bMCP\s+server\b.{{0,100}}\b(?:is|are)\s+(?:now\s+)?(?:available|offered|supported|launched|introduced)\b",
        rf"\b{re.escape(brand)}(?:'s)?\s+MCP\s+server\b.{{0,100}}\b(?:enables|provides|lets|allows|exposes)\b",
        rf"\b(?:introducing|announcing|launching|offering|providing)\b.{{0,80}}\b{re.escape(brand)}(?:'s)?\b.{{0,40}}\bMCP\s+server\b",
        rf"\bour\s+MCP\s+server\b.{{0,100}}\b(?:is|are)\s+(?:now\s+)?(?:available|offered|supported|launched|introduced)\b",
    )
    for pattern in positive_patterns:
        match = re.search(pattern, text, re.I)
        if match and not _negated(text, match.start(), match.end()):
            return 'vendor_server', _excerpt(text, match.start(), match.end()), 'Vendor-owned server statement; review date and access scope.'
    return 'unknown', '', 'No explicit vendor-operated server statement in the retrieved text.'


def api_types(text):
    patterns = (
        ('REST', r'\bREST(?:ful)?(?:\s+(?:Admin|Web|Management|Public|Storefront))?\s+APIs?\b'),
        ('GraphQL', r'\bGraphQL(?:\s+(?:Admin|Web|Management|Public|Storefront|Core))?\s+APIs?\b'),
        ('HTTP API', r'\bHTTP\s+APIs?\b'),
        ('gRPC', r'\bgRPC\s+APIs?\b'),
        ('SOAP', r'\bSOAP\s+APIs?\b'),
    )
    found = []
    for label, pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            if not _negated(text, match.start(), match.end()):
                found.append(label)
                break
    return found


def api_breadth(text, types):
    if not types:
        return 'unknown'
    lowered = text.lower()
    resources = {term for term in RESOURCE_TERMS if re.search(rf'\b{re.escape(term)}(?:s|es)?\b', lowered)}
    if re.search(r'\b(?:no|not a)\s+public\s+API\b', text, re.I):
        return 'no_public_api'
    if len(resources) >= 8:
        return 'broad'
    if len(resources) >= 4:
        return 'moderate'
    return 'narrow'


def auth_methods(text):
    patterns = (
        ('OAuth 2.0', r'\bOAuth\s*(?:2(?:\.0)?|v2)\b'),
        ('API key', r'\bAPI[ -]keys?\b'),
        ('API token', r'\bAPI\s+(?:access\s+)?tokens?\b'),
        ('Bearer token', r'\bBearer\s+(?:access\s+)?tokens?\b'),
        ('Basic authentication', r'\bBasic\s+auth(?:entication)?\b'),
        ('Session authentication', r'\bsession\s+(?:cookie|token|authentication)\b'),
    )
    found = []
    for label, pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            before = re.split(r'[.!?;\n]', text[max(0, match.start()-140):match.start()])[-1]
            after = re.split(r'[.!?;\n]', text[match.end():match.end()+180])[0]
            local = before + text[match.start():match.end()] + after
            if _negated(text, match.start(), match.end()) or re.search(r'\bRequestBin\b', local, re.I):
                continue
            scoped = label
            if label == 'Basic authentication' and re.search(r'\b(?:client_id|client_secret|token endpoint)\b', local, re.I):
                scoped = 'Basic authentication (OAuth client or endpoint-specific)'
            found.append(scoped)
            break
    return found


def credential_gate(text):
    patterns = (
        ('partner_or_sales', r'\b(?:contact sales|partnership|partner program|approved partner|invite.only)\b'),
        ('admin_approval', r'\b(?:must be an?\s+administrator|requires?\s+admin(?:istrator)?\s+access|admin approval|app review)\b'),
        ('paid_plan', r'\b(?:paid plan|paid subscription|API addon|purchas(?:e|ing)\s+API|API access (?:is )?available (?:only )?on)\b'),
        ('self_serve_trial', r'\b(?:free trial|trial account|developer trial)\b'),
        ('self_serve_free', r'\b(?:free developer account|free developer workspace|create (?:a )?free account|sign up for free)\b'),
    )
    found = []
    for label, pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            if _negated(text, match.start(), match.end()):
                continue
            if re.search(r"\b(?:does not|doesn't|do not|don't|not)\s+require[^.]{0,60}\b(?:approval|review|sales)\b", _excerpt(text, match.start(), match.end()), re.I):
                continue
            found.append((label, _excerpt(text, match.start(), match.end())))
            break
    return found


def _blank_fields():
    return {field: {'value': 'unknown', 'status': 'provisional', 'sources': [], 'evidence': [],
                    'reason': 'No sufficiently specific official evidence extracted.'}
            for field in FIELDS}


def extract(app, pages):
    fields = _blank_fields()
    mcp_votes = []
    for page in pages:
        if page.get('status') != 200 or not page.get('text'):
            continue
        url = page.get('url', '')
        if not official_source(url, app['name'], 'auth'):
            continue
        text, title = page['text'], page.get('title', '')
        date = page.get('published_label')
        for method in auth_methods(text):
            match = re.search(re.escape(method.split(' (')[0]), text, re.I)
            fields['auth']['evidence'].append({'value': method, 'url': url,
                'excerpt': _excerpt(text, match.start(), match.end()) if match else text[:280], 'published_label': date})
        types = api_types(text)
        if types:
            fields['api_surface']['evidence'].append({'value': types, 'breadth': api_breadth(text, types),
                'url': url, 'excerpt': text[:280], 'published_label': date})
        comparison_blog = '/blog/' in url.lower() and sum(
            re.search(r'\b' + re.escape(other['name']) + r'\b', text, re.I) is not None
            for other in prior.APPS if other['name'] != app['name'] and len(other['name']) > 4) >= 2
        for gate, excerpt in credential_gate(text):
            if not comparison_blog:
                fields['credential_gate']['evidence'].append({'value': gate, 'url': url, 'excerpt': excerpt, 'published_label': date})
        if re.search(r'\bmcp\b', title + ' ' + text[:4000], re.I):
            value, excerpt, reason = classify_mcp(title, text, app['name'], url)
            if value != 'unknown':
                mcp_votes.append(value)
                fields['official_mcp']['evidence'].append({'value': value, 'url': url, 'excerpt': excerpt,
                    'published_label': date, 'context_note': reason})
    for field in ('auth', 'api_surface', 'credential_gate'):
        evidence = fields[field]['evidence']
        if evidence:
            if field == 'auth':
                value = list(dict.fromkeys(item['value'] for item in evidence))
            elif field == 'api_surface':
                types = list(dict.fromkeys(t for item in evidence for t in item['value']))
                breadth = 'broad' if any(item['breadth'] == 'broad' for item in evidence) else ('moderate' if any(item['breadth'] == 'moderate' for item in evidence) else 'narrow')
                value = f"{', '.join(types)}; {breadth} documented surface"
            else:
                value = list(dict.fromkeys(item['value'] for item in evidence))
            fields[field].update(value=value, sources=list(dict.fromkeys(item['url'] for item in evidence)),
                                 reason='Provisional extraction; validate scope and completeness against cited pages.')
    if mcp_votes:
        unique = set(mcp_votes)
        value = next(iter(unique)) if len(unique) == 1 else 'unknown'
        fields['official_mcp'].update(value=value, sources=list(dict.fromkeys(item['url'] for item in fields['official_mcp']['evidence'])),
            reason='Conflicting or undated MCP evidence requires review.' if len(unique) > 1 else 'Provisional; check date, ownership and access scope.')
    entry = prior.CATALOG[app['name']]
    match = entry['matches'][0] if entry['matches'] else prior.ALIASES.get(app['name'])
    if match:
        fields['composio_toolkit'].update(value='listed', sources=[match['url']], reason='Catalog match only; not vendor MCP evidence.')
    if fields['auth']['value'] != 'unknown' and fields['api_surface']['value'] != 'unknown' and fields['credential_gate']['value'] != 'unknown':
        gate = fields['credential_gate']['value']
        if 'partner_or_sales' in gate:
            verdict = 'partner_outreach'
        elif any(x in gate for x in ('paid_plan', 'admin_approval')):
            verdict = 'gated_build_candidate'
        else:
            verdict = 'documented_build_candidate'
        fields['verdict'].update(value=verdict, sources=list(dict.fromkeys(fields['auth']['sources'] + fields['api_surface']['sources'] + fields['credential_gate']['sources'])),
            reason='Inferred only from extracted auth, API and access evidence; independent review required.')
    return fields


def validate_record(record):
    errors = []
    for key in ('number', 'app', 'category', 'summary', 'fields', 'blocker', 'next_action'):
        if not record.get(key):
            errors.append(f'missing {key}')
    fields = record.get('fields', {})
    if set(fields) != set(FIELDS):
        errors.append('fields must contain exactly the six research fields')
    for field in FIELDS:
        item = fields.get(field, {})
        value, status, reason, evidence = item.get('value'), item.get('status'), item.get('reason'), item.get('evidence', [])
        if status not in ('checked', 'unknown'):
            errors.append(f'{field}: invalid status')
        if not reason:
            errors.append(f'{field}: missing reason')
        if status == 'unknown':
            if value != 'unknown':
                errors.append(f'{field}: unknown status requires unknown value')
            if len(reason) < 30:
                errors.append(f'{field}: unknown reason is not specific')
            if not evidence:
                errors.append(f'{field}: unknown lacks attempted-source record')
            for source in evidence:
                url = source.get('url', '')
                if not url.startswith('https://'):
                    errors.append(f'{field}: non-HTTPS attempted-source URL')
                if not official_source(url, record.get('app', ''), field):
                    errors.append(f'{field}: attempted source is not recognized as official: {url}')
            if field == 'credential_gate' and item.get('gate_class') not in (None, 'unknown'):
                errors.append('credential_gate: unknown status cannot retain a positive gate_class')
            if field == 'api_surface':
                if item.get('api_types'):
                    errors.append('api_surface: unknown status cannot retain API types')
                if item.get('breadth') not in (None, 'unknown'):
                    errors.append('api_surface: unknown status cannot retain a positive breadth')
            if field == 'official_mcp':
                if item.get('mcp_mode') not in (None, 'unknown'):
                    errors.append('official_mcp: unknown status cannot retain a positive mcp_mode')
                if item.get('server_urls') or item.get('authentication'):
                    errors.append('official_mcp: unknown status cannot retain server or authentication details')
            if field == 'composio_toolkit' and any(item.get(key) for key in ('slug', 'auth_display', 'tools', 'triggers', 'version')):
                errors.append('composio_toolkit: unknown status cannot retain listing details')
            continue
        if value == 'unknown' or value in (None, [], '') or not evidence:
            errors.append(f'{field}: checked claim lacks value or evidence')
        if field == 'auth' and not isinstance(value, list):
            errors.append('auth: checked value must be a scoped method array')
        for source in evidence:
            url, quote = source.get('url', ''), source.get('quote', '')
            if not url.startswith('https://'):
                errors.append(f'{field}: non-HTTPS evidence URL')
            if not official_source(url, record.get('app', ''), field):
                errors.append(f'{field}: source is not recognized as official: {url}')
            if not quote:
                errors.append(f'{field}: checked claim lacks a supporting quote')
            if len(quote) > 800:
                errors.append(f'{field}: evidence quote is too long')
            if source.get('retrieved_at') != '2026-11-24':
                errors.append(f'{field}: evidence lacks retrieved_at date')
            if source.get('published_at'):
                try:
                    date.fromisoformat(source['published_at'])
                except (TypeError, ValueError):
                    errors.append(f'{field}: published_at must be a valid ISO date or null')
            if re.search(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{24,}', quote):
                errors.append(f'{field}: credential-shaped bearer value in quote')
        if field in ('official_mcp', 'credential_gate', 'verdict') and evidence:
            for source in evidence:
                if not source.get('published_at') and not source.get('published_label') and 'undated' not in reason.lower():
                    errors.append(f'{field}: time-sensitive evidence lacks date or undated note')
    if fields.get('api_surface', {}).get('status') == 'checked':
        breadth = fields['api_surface'].get('breadth')
        if breadth not in ('broad', 'moderate', 'narrow', 'no_public_api'):
            errors.append('api_surface: checked claim requires a valid breadth')
        if breadth != 'no_public_api' and not fields['api_surface'].get('api_types'):
            errors.append('api_surface: checked API claim requires API types')
    if fields.get('credential_gate', {}).get('status') == 'checked':
        if fields['credential_gate'].get('gate_class') not in ('self_serve_free', 'self_serve_trial', 'paid_plan', 'admin_approval', 'partner_or_sales', 'mixed', 'no_public_api'):
            errors.append('credential_gate: invalid gate_class')
    if fields.get('official_mcp', {}).get('status') == 'checked':
        if fields['official_mcp'].get('value') not in ('vendor_server', 'client_only', 'no_vendor_server_documented'):
            errors.append('official_mcp: invalid checked value')
        if fields['official_mcp'].get('mcp_mode') not in ('remote', 'local', 'both', 'early_access', 'unknown'):
            errors.append('official_mcp: invalid mcp_mode')
        for source in fields['official_mcp'].get('evidence', []):
            direction, _, _ = classify_mcp(source.get('title', ''), source.get('quote', ''), record['app'], source.get('url', ''))
            if fields['official_mcp']['value'] == 'vendor_server' and direction in ('client_only', 'no_vendor_server_documented'):
                errors.append('official_mcp: vendor_server contradicts client-only or negated evidence')
            if fields['official_mcp']['value'] == 'client_only' and direction == 'vendor_server':
                errors.append('official_mcp: client_only contradicts vendor-server evidence')
            if fields['official_mcp']['value'] == 'no_vendor_server_documented' and direction in ('vendor_server', 'client_only'):
                errors.append('official_mcp: documented absence contradicts vendor-server or client-only evidence')
        if fields['official_mcp']['value'] == 'no_vendor_server_documented':
            review_basis = fields['official_mcp'].get('review_basis')
            directions = [classify_mcp(source.get('title', ''), source.get('quote', ''), record['app'], source.get('url', ''))[0]
                          for source in fields['official_mcp'].get('evidence', [])]
            reason = fields['official_mcp'].get('reason', '').lower()
            if review_basis == 'explicit_negation':
                if 'no_vendor_server_documented' not in directions:
                    errors.append('official_mcp: explicit-negation basis lacks scoped negation evidence')
            elif review_basis == 'scoped_documentation_review':
                if (len(fields['official_mcp'].get('evidence', [])) < 2 or 'document' not in reason
                        or not re.search(r'\bno\b.{0,80}\bserver\b', reason)):
                    errors.append('official_mcp: scoped review requires multiple official sources and a scoped reason')
            else:
                errors.append('official_mcp: documented absence requires an explicit review_basis')
    if fields.get('composio_toolkit', {}).get('status') == 'checked' and fields['composio_toolkit'].get('value') not in ('listed_exact', 'listed_alias', 'not_listed'):
        errors.append('composio_toolkit: invalid checked value')
    if fields.get('composio_toolkit', {}).get('value') == 'not_listed':
        catalog_sources = [source for source in fields['composio_toolkit'].get('evidence', [])
                           if urlparse(source.get('url', '')).path.rstrip('/') in ('/toolkits', '/toolkits.md')]
        if not catalog_sources or 'catalog' not in fields['composio_toolkit'].get('reason', '').lower():
            errors.append('composio_toolkit: not_listed requires complete-catalog evidence and scope note')
    if fields.get('verdict', {}).get('status') == 'checked':
        if fields['verdict'].get('value') not in ('documented_build_candidate', 'gated_build_candidate', 'partner_outreach', 'wrapper_or_cli', 'no_public_api'):
            errors.append('verdict: invalid checked value')
        if any(fields.get(field, {}).get('status') != 'checked' for field in ('auth', 'credential_gate', 'api_surface')):
            errors.append('verdict: checked verdict requires checked auth, gate and API surface')
        verdict = fields['verdict']['value']
        gate = fields.get('credential_gate', {}).get('gate_class')
        breadth = fields.get('api_surface', {}).get('breadth')
        if gate == 'partner_or_sales' and verdict != 'partner_outreach':
            errors.append('verdict: partner/sales gate requires partner_outreach')
        if breadth == 'no_public_api' and verdict not in ('no_public_api', 'wrapper_or_cli'):
            errors.append('verdict: no public API requires no_public_api or wrapper_or_cli')
        if gate == 'no_public_api' and verdict not in ('no_public_api', 'wrapper_or_cli'):
            errors.append('verdict: no-public-API gate requires no_public_api or wrapper_or_cli')
        if gate in ('self_serve_free', 'self_serve_trial') and verdict not in ('documented_build_candidate', 'wrapper_or_cli'):
            errors.append('verdict: self-serve gate is inconsistent with build verdict')
    return errors
