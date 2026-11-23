"""Build the submission case study exclusively from validated v4 evidence."""
import collections
import html
import json
import re
from pathlib import Path

import context_pass_v4 as pipeline

ROOT = Path(__file__).resolve().parent
apps = json.loads((ROOT / 'checked_dataset_v4.json').read_text(encoding='utf-8'))
summary = json.loads((ROOT / 'research_summary_v4.json').read_text(encoding='utf-8'))
independent = json.loads((ROOT / 'independent_review_v4.json').read_text(encoding='utf-8'))
assert len(apps) == len({row['app'] for row in apps}) == 100
assert all(not pipeline.validate_record(row) for row in apps)
assert summary['apps'] == 100

FIELD_LABELS = {
    'auth': 'Authentication', 'credential_gate': 'Credential access', 'api_surface': 'API surface',
    'official_mcp': 'Vendor MCP', 'composio_toolkit': 'Composio toolkit', 'verdict': 'Buildability',
}
VERDICT_LABELS = {
    'documented_build_candidate': 'Documented build candidate', 'gated_build_candidate': 'Gated build candidate',
    'partner_outreach': 'Partner / sales outreach', 'wrapper_or_cli': 'Wrapper or CLI path',
    'no_public_api': 'No documented public API', 'unknown': 'Unresolved',
}
GATE_LABELS = {
    'self_serve_free': 'Self-serve free', 'self_serve_trial': 'Self-serve trial', 'paid_plan': 'Paid plan',
    'admin_approval': 'Admin / app approval', 'partner_or_sales': 'Partner / contact sales',
    'mixed': 'Mixed access conditions', 'no_public_api': 'No public API', 'unknown': 'Unresolved',
}
MCP_LABELS = {
    'vendor_server': 'Vendor server', 'client_only': 'Client only', 'no_vendor_server_documented': 'No server documented',
    'unknown': 'Unresolved',
}
COMPOSIO_LABELS = {
    'listed_exact': 'Exact listing', 'listed_alias': 'Alias listing',
    'not_listed': 'No exact/alias listing found', 'unknown': 'Unresolved',
}
BLOCKER_LABELS = {
    'none_documented_for_prototype': 'No blocker documented for a prototype', 'credential_access_gate': 'Credential access gate',
    'partnership_or_sales': 'Partnership or sales gate', 'no_documented_public_api': 'No documented public API',
    'wrapper_required': 'Wrapper or CLI required', 'unresolved_official_evidence': 'Official evidence unresolved',
}
PUBLIC_ROW_KEYS = ('number', 'app', 'category', 'summary', 'fields', 'blocker', 'next_action', 'blocker_class')
PUBLIC_FIELD_KEYS = (
    'value', 'status', 'reason', 'evidence', 'gate_class', 'details', 'api_types', 'breadth',
    'mcp_mode', 'review_basis', 'server_urls', 'transport', 'authentication', 'plan_access', 'permission_model',
    'slug', 'auth_display', 'managed_oauth', 'tools', 'triggers', 'version',
)
PUBLIC_EVIDENCE_KEYS = (
    'url', 'title', 'quote', 'retrieved_at', 'published_at', 'published_label', 'original_url',
    'source_review', 'verification_method', 'verification_note', 'verified_at',
)
FORBIDDEN_PUBLIC_KEYS = {
    'first_pass', 'provisional_pass12', 'composio_auth_config', 'raw_pass', 'pass12',
    'pages', 'page_text', 'raw_text', 'response', 'search_response',
}


def public_claim(claim):
    result = {key: claim[key] for key in PUBLIC_FIELD_KEYS if key in claim}
    if 'evidence' in result:
        result['evidence'] = [{key: source[key] for key in PUBLIC_EVIDENCE_KEYS if key in source}
                              for source in result['evidence']]
    return result


def assert_public_payload(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_PUBLIC_KEYS or key.startswith('raw_'):
                raise ValueError(f'Forbidden raw-research key in public payload: {key}')
            assert_public_payload(item)
    elif isinstance(value, list):
        for item in value:
            assert_public_payload(item)


def esc(value):
    return html.escape(str(value if value is not None else ''))


def display(value):
    if isinstance(value, list):
        return ', '.join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def pct(numerator, denominator):
    return f'{100 * numerator / denominator:.1f}%' if denominator else 'undefined'


def review_score(result):
    scored = result['scored_answered']
    if not scored:
        return '0/0, undefined'
    return f"{result['strict_numerator']}/{scored} ({pct(result['strict_numerator'], scored)})"


def weighted_score(result):
    scored = result['scored_answered']
    if not scored:
        return '0/0, undefined'
    return f"{result['weighted_numerator']:g}/{scored} ({pct(result['weighted_numerator'], scored)})"


checked_vendor = sum(claim['status'] == 'checked' for row in apps for field, claim in row['fields'].items() if field != 'composio_toolkit')
catalog_checked = sum(row['fields']['composio_toolkit']['status'] == 'checked' for row in apps)
catalog_values = collections.Counter(row['fields']['composio_toolkit']['value'] for row in apps)
catalog_listed = catalog_values.get('listed_exact', 0) + catalog_values.get('listed_alias', 0)
catalog_not_listed = catalog_values.get('not_listed', 0)
coverage = {field: {'checked': sum(row['fields'][field]['status'] == 'checked' for row in apps),
                    'unknown': sum(row['fields'][field]['status'] == 'unknown' for row in apps)}
            for field in pipeline.FIELDS}
verdicts = collections.Counter(row['fields']['verdict']['value'] for row in apps)
gates = collections.Counter(row['fields']['credential_gate'].get('gate_class', 'unknown') for row in apps)
mcp = collections.Counter(row['fields']['official_mcp']['value'] for row in apps)
blockers = collections.Counter(row['blocker_class'] for row in apps)
api_types = collections.Counter(item for row in apps for item in row['fields']['api_surface'].get('api_types', []))
breadth = collections.Counter(row['fields']['api_surface'].get('breadth', 'unknown') for row in apps)


def auth_categories(value):
    lowered = str(value).lower()
    found = set()
    if 'oauth' in lowered:
        found.add('OAuth 2.0')
    if 'api key' in lowered or 'x-api-key' in lowered or 'key id' in lowered:
        found.add('API key')
    if 'token' in lowered:
        found.add('Access token')
    if 'basic' in lowered:
        found.add('Basic authentication')
    if 'bearer' in lowered:
        found.add('Bearer token')
    if 'session' in lowered and ('cookie' in lowered or 'authentication' in lowered):
        found.add('Session authentication')
    if 'no account' in lowered or lowered.startswith('none') or 'no authentication' in lowered:
        found.add('No authentication')
    return found or {'Other documented method'}


auth = collections.Counter()
for row in apps:
    categories = set()
    if row['fields']['auth']['status'] == 'checked':
        value = row['fields']['auth']['value']
        for item in value if isinstance(value, list) else [value]:
            categories.update(auth_categories(item))
    auth.update(categories)
self_serve = gates.get('self_serve_free', 0) + gates.get('self_serve_trial', 0)
access_gated = gates.get('paid_plan', 0) + gates.get('admin_approval', 0) + gates.get('mixed', 0)
partner = gates.get('partner_or_sales', 0)
top_auth = max(auth.items(), key=lambda item: item[1]) if auth else ('unresolved', 0)
top_blocker = max(blockers.items(), key=lambda item: item[1]) if blockers else ('unresolved', 0)
selected = independent['selected_sample']
holdout = independent['random_holdout']
for result in (selected, holdout):
    assert result['total_claims'] == 60
    assert result['answered'] + result['abstained'] == 60
    assert result['scored_answered'] == sum(result['ratings'].get(rating, 0)
                                             for rating in ('correct', 'partial', 'incorrect'))
    assert result['weighted_numerator'] == result['ratings'].get('correct', 0) + 0.5 * result['ratings'].get('partial', 0)

categories = {}
for category in dict.fromkeys(row['category'] for row in apps):
    rows = [row for row in apps if row['category'] == category]
    categories[category] = {'apps': len(rows),
                            'verdicts': dict(collections.Counter(row['fields']['verdict']['value'] for row in rows)),
                            'gates': dict(collections.Counter(row['fields']['credential_gate'].get('gate_class', 'unknown') for row in rows))}
matrix_rows = []
for category, values in categories.items():
    counts = values['verdicts']
    matrix_rows.append('<tr><th scope="row">' + esc(category) + '</th><td>' + str(values['apps']) + '</td>' +
                       ''.join('<td>' + str(counts.get(key, 0)) + '</td>' for key in (
                           'documented_build_candidate', 'gated_build_candidate', 'partner_outreach',
                           'wrapper_or_cli', 'no_public_api', 'unknown')) + '</tr>')
matrix = ''.join(matrix_rows)
coverage_rows = ''.join('<tr><th scope="row">' + esc(FIELD_LABELS[field]) + '</th><td>' +
                        str(values['checked']) + '/100</td><td>' + str(values['unknown']) +
                        '</td><td>' + pct(values['checked'], 100) + '</td></tr>'
                        for field, values in coverage.items())

easy_wins = [row['app'] for row in apps if row['fields']['verdict']['value'] == 'documented_build_candidate'
             and row['fields']['credential_gate'].get('gate_class') in ('self_serve_free', 'self_serve_trial')
             and row['fields']['api_surface'].get('breadth') in ('broad', 'moderate')]
assert summary['coverage'] == coverage
assert summary['verdicts'] == dict(verdicts)
assert summary['credential_gates'] == dict(gates)
assert summary['official_mcp'] == dict(mcp)
assert summary['composio_toolkit'] == dict(catalog_values)
assert summary['blockers'] == dict(blockers)
assert summary['auth_methods'] == dict(auth)
assert summary['api_types'] == dict(api_types)
assert summary['api_breadth'] == dict(breadth)
assert summary['categories'] == categories
assert summary['documented_easy_wins'] == easy_wins
easy_win_html = '<ul>' + ''.join('<li>' + esc(name) + '</li>' for name in easy_wins) + '</ul>' if easy_wins else '<p>No app met the strict documented-easy-win rule in this checked set.</p>'

review_records = []
for cohort, result in (('Selected sample', selected), ('Random holdout', holdout)):
    for record in result['records']:
        item = dict(record)
        item['cohort'] = cohort
        review_records.append(item)
examples = []
for rating in ('correct', 'partial', 'incorrect', 'unresolved'):
    match = next((record for record in review_records if record['rating'] == rating), None)
    if match:
        examples.append(match)
    if len(examples) == 3:
        break
example_cards = ''.join('<article class="card"><span class="rating ' + esc(record['rating']) + '">' + esc(record['rating']) +
                        '</span><h3>' + esc(record['app']) + ' · ' + esc(FIELD_LABELS[record['field']]) + '</h3><p><b>Pass 12:</b> ' +
                        esc(display(record['pass12_answer'])) + '</p><p><b>Review:</b> ' + esc(record['review_note']) + '</p><p><b>Checked correction:</b> ' +
                        esc(display(record['correction'])) + '</p></article>' for record in examples)

public_apps = []
for row in apps:
    public_row = {key: row[key] for key in PUBLIC_ROW_KEYS if key in row}
    public_row['fields'] = {field: public_claim(claim) for field, claim in row['fields'].items()}
    public_apps.append(public_row)
assert_public_payload(public_apps)
payload = json.dumps(public_apps, ensure_ascii=False).replace('</', '<\\/')
review_payload = json.dumps(review_records, ensure_ascii=False).replace('</', '<\\/')
repo = 'https://github.com/harshbehl67-ctrl/-composio-product-ops-research'
page = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Official-documentation research across 100 apps: authentication, access, API surface, MCP, buildability, and independent accuracy review."><title>100-app integration evidence | Composio take-home</title><style>
:root{--ink:#173b31;--paper:#f4f3eb;--line:#d4ddcf;--lime:#d9f99d;--muted:#5b6e62;--white:#fff;--amber:#fff0c2;--red:#ffe0dc;--blue:#dcecff}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}a{color:#1f6b49;text-underline-offset:3px}header{background:#153c30;color:#f5f7ee;padding:24px max(5vw,24px) 88px}header a{color:#dcf7c7}.nav{display:flex;justify-content:space-between;gap:20px;font-size:12px;letter-spacing:.12em;text-transform:uppercase}.hero{max-width:1200px;margin:auto;display:grid;grid-template-columns:1.25fr .75fr;gap:44px;align-items:center}h1,h2,h3{font-family:Georgia,serif;font-weight:400;line-height:1.08}h1{font-size:clamp(42px,6.4vw,78px);margin:64px 0 22px}h2{font-size:clamp(32px,4vw,48px);margin:0 0 18px}h3{font-size:24px;margin:0 0 12px}.lead{font-size:19px;max-width:760px;color:#d9e8da}.badge{display:inline-block;background:var(--lime);color:#173b31;border-radius:40px;padding:7px 14px;font-size:12px;font-weight:750}.scene{border:1px solid #79a48a;border-radius:22px;padding:24px;display:grid;gap:12px}.step{border:1px solid #6c967d;border-radius:10px;padding:13px}.step b{color:var(--lime);margin-right:10px}main{max-width:1200px;padding:0 24px;margin:auto}.metrics{display:grid;grid-template-columns:repeat(4,1fr);background:#fff;border:1px solid var(--line);margin-top:-38px}.metric{padding:24px;border-right:1px solid var(--line)}.metric:last-child{border-right:0}.metric strong{display:block;font:36px Georgia,serif}.metric small{color:var(--muted)}section{padding:68px 0;border-bottom:1px solid var(--line)}.kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:750;color:#52735b}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#fff;border:1px solid var(--line);padding:24px}.card p:last-child{margin-bottom:0}.notice{padding:22px;background:#e7efdc;border-left:4px solid #6b9644}.warning{background:var(--amber);border-left-color:#b37a12}.tablewrap{overflow:auto;border:1px solid var(--line);background:#fff}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:12px;border-bottom:1px solid #e2e8dd;text-align:left;vertical-align:top}thead th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;background:#f8faf5}tbody tr:last-child th,tbody tr:last-child td{border-bottom:0}.controls{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}label{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}input,select,button{font:inherit;padding:10px;border:1px solid #a9b9aa;background:#fff;color:var(--ink);border-radius:4px}input{min-width:220px}button{cursor:pointer}.flow{display:flex;flex-wrap:wrap;gap:9px}.flow span{padding:12px 14px;background:#fff;border:1px solid var(--line)}pre{overflow:auto;background:#102d25;color:#e6f4df;padding:18px;border-radius:8px;font-size:13px}.rating{display:inline-block;border-radius:20px;padding:3px 9px;font-size:11px;font-weight:800;text-transform:uppercase;background:#e7ece3}.rating.correct{background:#d9f5d0}.rating.partial{background:var(--amber)}.rating.incorrect{background:var(--red)}.rating.abstained{background:#e8e8e8}.rating.unresolved{background:var(--blue)}details{min-width:150px}summary{cursor:pointer;font-weight:700}.source{display:inline-block;margin:3px 10px 3px 0}.quote{display:block;margin:4px 0 10px;color:var(--muted);font-size:13px}.muted{color:var(--muted)}.pill{display:inline-block;border:1px solid var(--line);border-radius:20px;padding:3px 8px;font-size:12px;background:#fff}.unknown{color:#785d18}.checked{color:#216442}.rowdetails p{margin:10px 0}.rowdetails b{font-weight:750}.reviewtable{font-size:13px}footer{padding:42px 0 56px;color:var(--muted)}code{font-family:ui-monospace,monospace}@media(max-width:860px){.hero{grid-template-columns:1fr}.scene{display:none}.metrics{grid-template-columns:repeat(2,1fr)}.metric{border-bottom:1px solid var(--line)}.cards{grid-template-columns:1fr}section{padding:50px 0}h1{margin-top:46px}.nav span{display:none}}@media(max-width:520px){main{padding:0 16px}header{padding-left:16px;padding-right:16px}.metrics{grid-template-columns:1fr}.metric{border-right:0}input{min-width:100%;width:100%}.controls label{width:100%}.controls select,.controls button{width:100%}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
</style></head><body><header><nav class="nav"><span>Composio · AI Product Ops take-home</span><a href="#evidence">Explore 100 apps ↓</a></nav><div class="hero"><div><h1>100 apps. What can an agent actually build?</h1><p class="lead">An official-documentation audit across ten categories, separating documented developer paths from access gates, partner outreach, wrappers, and unresolved evidence.</p><span class="badge">CHECKED 24 NOV 2026 · NO LIVE CREDENTIALS TESTED</span></div><div class="scene" aria-label="Research workflow"><div class="step"><b>01</b>Target official API, auth, access and MCP docs</div><div class="step"><b>02</b>Preserve raw passes and source excerpts</div><div class="step"><b>03</b>Validate context, dates and ownership</div><div class="step"><b>04</b>Score a selected sample and random holdout</div></div></div></header><main><div class="metrics"><div class="metric"><strong>100</strong><small>apps across 10 categories</small></div><div class="metric"><strong>__CHECKED__/500</strong><small>checked vendor-field claims</small></div><div class="metric"><strong>__BUILD__</strong><small>documented build candidates</small></div><div class="metric"><strong>0/60</strong><small>baseline answered; accuracy undefined</small></div></div>
<section><div class="kicker">01 / Headline findings</div><h2>Access, not API labels, decides the route.</h2><div class="notice"><b>__SELF_SERVE__ apps have a checked self-serve free or trial path; __ACCESS_GATED__ have paid, admin, or mixed gates; __PARTNER__ require partner or sales access.</b> The most common checked blocker is __TOP_BLOCKER__ (__TOP_BLOCKER_COUNT__ apps). These are documentation findings, not production-access tests.</div><div class="cards"><article class="card"><h3>Authentication</h3><p>The most common checked label is <b>__TOP_AUTH__</b> (__TOP_AUTH_COUNT__ apps). OAuth 2.0 appears in __OAUTH__; API keys in __API_KEYS__. Legacy and endpoint-specific methods remain scoped in the evidence table.</p></article><article class="card"><h3>API surface</h3><p>REST is documented for __REST__ apps and GraphQL for __GRAPHQL__. __BROAD__ have a broad checked surface, __MODERATE__ moderate, and __NARROW__ narrow. Breadth is a documented-resource assessment, not an endpoint census.</p></article><article class="card"><h3>MCP ownership</h3><p>__MCP_SERVER__ vendor-operated MCP servers are documented; __MCP_CLIENT__ products are client-only in the checked source; __MCP_NO_SERVER__ have explicit scoped no-server documentation. __MCP_UNKNOWN__ remain unresolved. __CATALOG_LISTED__ exact/alias Composio listings and __CATALOG_NOT_LISTED__ scoped no-listing findings are reported separately and never imply a vendor MCP server.</p></article></div><h3>Documented easy wins</h3><p>Strict rule: documented build candidate + self-serve free/trial + broad or moderate API.</p>__EASY_WINS__</section>
<section><div class="kicker">02 / Category matrix</div><h2>Ten categories, six honest outcomes.</h2><p>“Documented build candidate” means the docs support a developer prototype path. It does not mean a production credential was obtained.</p><div class="tablewrap"><table><thead><tr><th>Category</th><th>Apps</th><th>Documented</th><th>Gated</th><th>Partner</th><th>Wrapper</th><th>No public API</th><th>Unresolved</th></tr></thead><tbody>__MATRIX__</tbody></table></div></section>
<section><div class="kicker">03 / The research agent</div><h2>Search is triage. Evidence is the product.</h2><div class="flow"><span>Targeted official-source discovery</span><span>→ frozen page retrieval</span><span>→ context-aware extraction</span><span>→ independent category review</span><span>→ strict assembly gate</span></div><div class="cards"><article class="card"><h3>What the pipeline does</h3><p>Searches each app for API reference, authentication, credential creation, access/pricing, and MCP documentation. It saves raw passes, extracts scoped claims, retains publication labels, rejects client-only or negated MCP proofs, and validates every checked field before assembly.</p></article><article class="card"><h3>Where judgment was needed</h3><p>Independent AI-assisted reviewers resolved product aliases, current versus legacy auth, app-review scope, early-access MCP, and “server” versus “client” direction. Final production-access approval and authorized credential testing remain human checkpoints.</p></article><article class="card"><h3>What was not claimed</h3><p>No Composio SDK or MCP runtime was executed; the public Composio catalog was cross-checked separately. No paid account, customer permission, live token, or production integration was tested.</p></article></div><h3>Runnable proof</h3><pre>python -m unittest discover -v
python normalize_checked_research_v4.py
python apply_source_review_v4.py
python assemble_checked_v4.py
python verify_checked_sources.py --review source_review_v4.json
python check_links_v4.py --review source_review_v4.json
python check_independent_links_v4.py --review independent_link_review_v4.json
python score_review_v4.py
python scan_secrets.py
python build_case_v4.py
node test_page_v4.cjs</pre><p>The source, preserved passes, review logs, and validation reports are in the <a href="__REPO__">source repository</a>. Export the checked JSON or CSV from the evidence table below.</p></section>
<section><div class="kicker">04 / Accuracy lab</div><h2>Coverage first. Accuracy with denominators.</h2><div class="notice warning"><b>The original baseline answered 0/60 claims, so its answered-claim accuracy is undefined (0/0), not 0%.</b> No baseline accuracy-improvement claim is made. The deliberately selected ten-category sample and the seeded random holdout are scored separately.</div><div class="cards"><article class="card"><h3>Selected sample</h3><p>One app per category, six fields each. Pass 12 answered <b>__SELECTED_ANSWERED__/60</b> (__SELECTED_COVERAGE__). Independent review: __SELECTED_RATINGS__.</p><p>Strict: <b>__SELECTED_STRICT__</b><br>Half-credit: <b>__SELECTED_WEIGHTED__</b></p></article><article class="card"><h3>Random holdout</h3><p>Seed 20261124, selected after pass 12 froze, ten apps / 60 fields. Pass 12 answered <b>__HOLDOUT_ANSWERED__/60</b> (__HOLDOUT_COVERAGE__). Independent review: __HOLDOUT_RATINGS__.</p><p>Strict: <b>__HOLDOUT_STRICT__</b><br>Half-credit: <b>__HOLDOUT_WEIGHTED__</b></p></article><article class="card"><h3>Scoring rule</h3><p>Correct = all material parts supported and scoped. Partial = core direction right but incomplete or overbroad. Incorrect = contradicts official evidence. Abstained and unresolved claims are excluded from the accuracy denominator.</p></article></div><h3>Hits and misses, shown honestly</h3><div class="cards">__EXAMPLES__</div><details><summary>Inspect all 120 reviewed claims</summary><div class="controls"><label>Cohort <select id="cohort"><option value="">All reviews</option><option>Selected sample</option><option>Random holdout</option></select></label></div><div class="tablewrap"><table class="reviewtable"><thead><tr><th>Cohort</th><th>App / field</th><th>Pass 12</th><th>Rating</th><th>Independent correction</th><th>Sources</th></tr></thead><tbody id="reviewrows"></tbody></table></div></details></section>
<section id="evidence"><div class="kicker">05 / The 100 apps</div><h2>Every claim has a source—or a reason.</h2><p>__CHECKED__ of 500 vendor-field claims are checked; __CATALOG__ of 100 Composio toolkit fields are checked. Unknown means targeted official-source research did not resolve the claim, not that the capability is absent.</p><div class="tablewrap"><table><thead><tr><th>Field</th><th>Checked</th><th>Unknown</th><th>Coverage</th></tr></thead><tbody>__COVERAGE_ROWS__</tbody></table></div><div class="controls"><label>Search <input id="search" type="search" placeholder="App, purpose or category"></label><label>Category <select id="category"><option value="">All categories</option></select></label><label>Access <select id="gate"><option value="">All access paths</option></select></label><label>Verdict <select id="verdict"><option value="">All verdicts</option></select></label><label>MCP <select id="mcp"><option value="">All MCP states</option></select></label><button id="sort">Sort A–Z</button><button id="json">Export JSON</button><button id="csv">Export CSV</button></div><p id="count" aria-live="polite"></p><div class="tablewrap"><table><thead><tr><th>App / purpose</th><th>Category</th><th>Auth</th><th>Access</th><th>API</th><th>Vendor MCP</th><th>Composio</th><th>Verdict</th><th>Evidence</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section><div class="kicker">06 / Limits and handoff</div><h2>What this evidence does—and does not—prove.</h2><div class="cards"><article class="card"><h3>Documentation, not credentials</h3><p>No live token, paid plan, admin approval, partner agreement, or production connection was tested. A gated finding is a valid research result, not a failed build.</p></article><article class="card"><h3>Dates and absence</h3><p>Time-sensitive claims retain publication/update labels when available. Undated pages are identified in field reasons. “No vendor server documented” is scoped to the cited source; unresolved is not universal absence.</p></article><article class="card"><h3>Security review</h3><p>The bearer-shaped value in the first Git commit exactly matches a publicly labeled Zendesk documentation example. It was not established as a user-owned credential, so no history rewrite or revocation was performed.</p></article></div><p>Next action: prioritize the documented easy wins, route gated apps to the named access step, and send partner-only apps to outreach. Recheck time-sensitive pages before implementation.</p></section><footer><a href="__REPO__">Source repository</a> · Checked 24 November 2026 · All page counts are generated from the checked dataset.</footer></main><script>
const data=__DATA__,reviews=__REVIEW__;const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const safe=u=>/^https?:\/\//i.test(u),vals=v=>Array.isArray(v)?v.join(', '):(typeof v==='object'&&v!==null?JSON.stringify(v):String(v??''));let asc=true;
const gateNames=__GATES__,verdictNames=__VERDICTS__,mcpNames=__MCP__,composioNames=__COMPOSIO__,fieldNames=__FIELDS__;
[...new Set(data.map(a=>a.category))].forEach(c=>{let o=document.createElement('option');o.value=o.textContent=c;$('#category').append(o)});Object.entries(gateNames).forEach(([v,l])=>{let o=document.createElement('option');o.value=v;o.textContent=l;$('#gate').append(o)});Object.entries(verdictNames).forEach(([v,l])=>{let o=document.createElement('option');o.value=v;o.textContent=l;$('#verdict').append(o)});Object.entries(mcpNames).forEach(([v,l])=>{let o=document.createElement('option');o.value=v;o.textContent=l;$('#mcp').append(o)});
function sources(items){return (items||[]).filter(s=>s&&safe(s.url)).map(s=>`<a class="source" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title||'Source')} ↗${s.published_label?` · ${esc(s.published_label)}`:''}${s.published_at?` · ${esc(s.published_at)}`:''}</a>${s.quote?`<span class="quote">“${esc(s.quote)}”</span>`:''}`).join('')}
function details(row){return `<div class="rowdetails">${Object.entries(row.fields).map(([k,v])=>`<p><b>${esc(fieldNames[k])}:</b> <span class="${esc(v.status)}">${esc(vals(v.value))}</span> <em>(${esc(v.status)})</em><br><span class="muted">${esc(v.reason)}</span><br>${sources(v.evidence)}</p>`).join('')}<p><b>Blocker:</b> ${esc(row.blocker)}</p><p><b>Next action:</b> ${esc(row.next_action)}</p></div>`}
function render(){let q=$('#search').value.toLowerCase(),list=data.filter(a=>(a.app+' '+a.summary+' '+a.category).toLowerCase().includes(q)&&(!$('#category').value||a.category===$('#category').value)&&(!$('#gate').value||a.fields.credential_gate.gate_class===$('#gate').value)&&(!$('#verdict').value||a.fields.verdict.value===$('#verdict').value)&&(!$('#mcp').value||a.fields.official_mcp.value===$('#mcp').value)).sort((a,b)=>asc?a.app.localeCompare(b.app):b.app.localeCompare(a.app));$('#count').textContent=`${list.length} of ${data.length} apps shown`;$('#rows').innerHTML=list.map(a=>`<tr><td><b>${esc(a.app)}</b><br><span class="muted">${esc(a.summary)}</span></td><td>${esc(a.category)}</td><td>${esc(vals(a.fields.auth.value))}</td><td>${esc(gateNames[a.fields.credential_gate.gate_class]||a.fields.credential_gate.value)}</td><td>${esc(a.fields.api_surface.value)}${a.fields.api_surface.breadth?`<br><span class="pill">${esc(a.fields.api_surface.breadth)}</span>`:''}</td><td>${esc(mcpNames[a.fields.official_mcp.value]||a.fields.official_mcp.value)}</td><td>${esc(composioNames[a.fields.composio_toolkit.value]||a.fields.composio_toolkit.value)}</td><td>${esc(verdictNames[a.fields.verdict.value]||a.fields.verdict.value)}</td><td><details><summary>View evidence</summary>${details(a)}</details></td></tr>`).join('')}
function renderReviews(){let cohort=$('#cohort').value;$('#reviewrows').innerHTML=reviews.filter(r=>!cohort||r.cohort===cohort).map(r=>`<tr><td>${esc(r.cohort)}</td><td><b>${esc(r.app)}</b><br>${esc(fieldNames[r.field])}</td><td>${esc(vals(r.pass12_answer))}</td><td><span class="rating ${esc(r.rating)}">${esc(r.rating)}</span></td><td>${esc(r.review_note)}<br><b>${esc(vals(r.correction))}</b></td><td>${sources((r.independent_sources||[]).map(url=>({url,title:'Official source'})))}</td></tr>`).join('')}
['search','category','gate','verdict','mcp'].forEach(id=>$('#'+id).addEventListener('input',render));$('#cohort').addEventListener('input',renderReviews);$('#sort').onclick=()=>{asc=!asc;$('#sort').textContent=asc?'Sort A–Z':'Sort Z–A';render()};function save(name,content,type){let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([content],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}$('#json').onclick=()=>save('checked-dataset-v4.json',JSON.stringify(data,null,2),'application/json');$('#csv').onclick=()=>{let cols=['app','category','summary','auth','credential_gate','api_surface','official_mcp','composio_toolkit','verdict','blocker','next_action'],quote=x=>'"'+(/^[=+\-@\t\r]/.test(String(x??''))?"'":'')+String(x??'').replaceAll('"','""')+'"';save('checked-dataset-v4.csv',[cols.join(','),...data.map(a=>cols.map(k=>quote(k==='app'?a.app:k==='category'?a.category:k==='summary'?a.summary:k==='blocker'?a.blocker:k==='next_action'?a.next_action:a.fields[k]?.value)).join(','))].join('\r\n'),'text/csv')};render();renderReviews();
</script></body></html>'''

replacements = {
    '__DATA__': payload, '__REVIEW__': review_payload, '__GATES__': json.dumps(GATE_LABELS), '__VERDICTS__': json.dumps(VERDICT_LABELS),
    '__MCP__': json.dumps(MCP_LABELS), '__COMPOSIO__': json.dumps(COMPOSIO_LABELS),
    '__FIELDS__': json.dumps(FIELD_LABELS), '__REPO__': repo,
    '__CHECKED__': checked_vendor, '__CATALOG__': catalog_checked, '__CATALOG_LISTED__': catalog_listed,
    '__CATALOG_NOT_LISTED__': catalog_not_listed, '__BUILD__': verdicts.get('documented_build_candidate', 0),
    '__SELF_SERVE__': self_serve, '__ACCESS_GATED__': access_gated, '__PARTNER__': partner,
    '__TOP_BLOCKER__': BLOCKER_LABELS.get(top_blocker[0], top_blocker[0]), '__TOP_BLOCKER_COUNT__': top_blocker[1],
    '__TOP_AUTH__': top_auth[0], '__TOP_AUTH_COUNT__': top_auth[1], '__OAUTH__': auth.get('OAuth 2.0', 0), '__API_KEYS__': auth.get('API key', 0),
    '__REST__': api_types.get('REST', 0), '__GRAPHQL__': api_types.get('GraphQL', 0),
    '__BROAD__': breadth.get('broad', 0), '__MODERATE__': breadth.get('moderate', 0), '__NARROW__': breadth.get('narrow', 0),
    '__MCP_SERVER__': mcp.get('vendor_server', 0), '__MCP_CLIENT__': mcp.get('client_only', 0),
    '__MCP_NO_SERVER__': mcp.get('no_vendor_server_documented', 0), '__MCP_UNKNOWN__': mcp.get('unknown', 0),
    '__EASY_WINS__': easy_win_html, '__MATRIX__': matrix, '__COVERAGE_ROWS__': coverage_rows, '__EXAMPLES__': example_cards,
    '__SELECTED_ANSWERED__': selected['answered'], '__SELECTED_COVERAGE__': pct(selected['answered'], 60),
    '__SELECTED_RATINGS__': ', '.join(f'{key} {value}' for key, value in selected['ratings'].items()),
    '__SELECTED_STRICT__': review_score(selected), '__SELECTED_WEIGHTED__': weighted_score(selected),
    '__HOLDOUT_ANSWERED__': holdout['answered'], '__HOLDOUT_COVERAGE__': pct(holdout['answered'], 60),
    '__HOLDOUT_RATINGS__': ', '.join(f'{key} {value}' for key, value in holdout['ratings'].items()),
    '__HOLDOUT_STRICT__': review_score(holdout), '__HOLDOUT_WEIGHTED__': weighted_score(holdout),
}
for key, value in replacements.items():
    page = page.replace(key, str(value))
assert not re.search(r'__[A-Z_]+__', page), 'Unreplaced page placeholder'
assert 'synthetic test row' not in page, 'Synthetic fixture must not be published'
Path('index.html').write_text(page, encoding='utf-8')
print('Built index.html from checked_dataset_v4.json')
print('Checked vendor claims', checked_vendor, '/500; catalog', catalog_checked, '/100; documented candidates', verdicts.get('documented_build_candidate', 0))
