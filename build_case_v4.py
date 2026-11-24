"""Build the submission case study exclusively from validated v4 evidence."""
import collections
import html
import json
import math
import re
from pathlib import Path

import context_pass_v4 as pipeline
import datamodel_v2

ROOT = Path(__file__).resolve().parent
apps = json.loads((ROOT / 'checked_dataset_v4.json').read_text(encoding='utf-8'))
summary = json.loads((ROOT / 'research_summary_v4.json').read_text(encoding='utf-8'))
independent = json.loads((ROOT / 'independent_review_v4.json').read_text(encoding='utf-8'))
first_pass = json.loads((ROOT / 'first_pass_review_v4.json').read_text(encoding='utf-8'))
sdk_check = json.loads((ROOT / 'composio_sdk_check_v4.json').read_text(encoding='utf-8'))
gold = json.loads((ROOT / 'gold_ratings_v4.json').read_text(encoding='utf-8'))
final_gold_incorrect = gold['overall']['pass3']['judgment_fields']['incorrect']
gold_provenance = json.loads((ROOT / 'gold_provenance_v1.json').read_text(encoding='utf-8'))
spotcheck = json.loads((ROOT / 'gold_source_recheck_v1.json').read_text(encoding='utf-8'))
spotcheck_counts = collections.Counter(row['result'] for row in spotcheck['rows'])
source_adjudication = json.loads((ROOT / 'current_source_adjudication_v1.json').read_text(encoding='utf-8'))
source_adjudication_count = len(source_adjudication['records'])
human_spotcheck = json.loads((ROOT / 'human_gold_spotcheck_results_v1.json').read_text(encoding='utf-8'))
human_spotcheck_summary = human_spotcheck['summary']
auth_crosscheck = json.loads((ROOT / 'catalog_crosscheck.json').read_text(encoding='utf-8'))
firecrawl_comparison_path = ROOT / 'firecrawl_before_after_v4.json'
firecrawl_comparison = (json.loads(firecrawl_comparison_path.read_text(encoding='utf-8'))
                        if firecrawl_comparison_path.exists() else {'completed': False})
model_records, _model_log = datamodel_v2.build()
model_by_app = {record['app']: record for record in model_records}
assert len(apps) == len({row['app'] for row in apps}) == 100
assert all(not pipeline.validate_record(row) for row in apps)
assert summary['apps'] == 100
app_count = len(apps)
category_count = len({row['category'] for row in apps})
vendor_field_count = len(pipeline.FIELDS) - 1
vendor_claim_total = app_count * vendor_field_count
checked_date = summary['checked_at']
holdout_seed = json.loads((ROOT / 'holdout_selection_v4.json').read_text(encoding='utf-8'))['seed']

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
    'admin_approval': 'Admin approval', 'app_review': 'App review', 'partner_or_sales': 'Partner / sales',
    'mixed': 'Mixed access conditions', 'no_public_api': 'No public API', 'unknown': 'Unknown',
}
MCP_LABELS = {
    'hosted_action': 'Hosted actions', 'docs_readonly': 'Docs / read-only', 'local': 'Local',
    'beta': 'Beta / EAP', 'prelaunch': 'Prelaunch', 'none': 'None documented', 'unresolved': 'Unresolved',
}
MCP_TIER_LABELS = {
    'hosted_action': 'hosted actions', 'docs_readonly': 'docs / read-only',
    'local': 'local server', 'beta': 'beta / EAP', 'prelaunch': 'prelaunch',
    'none': 'none documented', 'unresolved': 'unresolved',
}
AUTH_CHIP_LABELS = {
    'oauth2_user': 'OAuth 2.0', 'oauth2_client_creds': 'OAuth 2.0 client credentials',
    'oauth2_service_account': 'OAuth 2.0 service account', 'signed_request': 'API key + signed request',
    'api_key_or_pat': 'API key / personal access token', 'basic': 'Basic auth',
    'jwt_signed': 'Signed JWT', 'none': 'No auth documented', 'unknown': 'Unresolved',
}
COMPOSIO_LABELS = {
    'listed_exact': 'Exact listing', 'listed_alias': 'Alias listing',
    'not_listed': 'No exact/alias listing found', 'unknown': 'Unresolved',
}
BLOCKER_LABELS = {
    'none_documented_for_prototype': 'No blocker documented for a prototype', 'credential_access_gate': 'Paid plan / admin approval / app review / partner',
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
auth = summary['auth_methods']


auth_chip_counts = collections.Counter()
for record in model_records:
    auth_chip_counts.update(set(record['auth_chips']) - {'unknown', 'none'})
auth_known_app_count = sum(bool(set(record['auth_chips']) - {'unknown', 'none'}) for record in model_records)
auth_unrecognized_app_count = app_count - auth_known_app_count
top_auth_chip = max(auth_chip_counts.items(), key=lambda item: item[1]) if auth_chip_counts else ('unknown', 0)
prototype_access_counts = collections.Counter(record['prototype_access'] for record in model_records)
production_access_counts = collections.Counter(record['production_access'] for record in model_records)
ACCESS_LABELS = {
    'self_serve_free': 'Self-serve free', 'self_serve_trial': 'Self-serve trial',
    'paid_plan': 'Paid plan', 'admin_approval': 'Admin approval',
    'app_review': 'App review', 'partner_or_sales': 'Partner / sales', 'unknown': 'Unknown',
}
ACCESS_ORDER = ('self_serve_free', 'self_serve_trial', 'paid_plan', 'admin_approval',
                'app_review', 'partner_or_sales', 'unknown')
access_table_rows = ''.join(
    f'<tr><th scope="row">{esc(ACCESS_LABELS[key])}</th>'
    f'<td>{prototype_access_counts.get(key, 0)}</td><td>{production_access_counts.get(key, 0)}</td></tr>'
    for key in ACCESS_ORDER)
production_gate_keys = ('paid_plan', 'admin_approval', 'app_review', 'partner_or_sales')
production_gate_total = sum(production_access_counts.get(key, 0) for key in production_gate_keys)
production_gate_text = ', '.join(
    f'{ACCESS_LABELS[key].lower()} {production_access_counts.get(key, 0)}' for key in production_gate_keys)
prototype_self_serve = prototype_access_counts.get('self_serve_free', 0) + prototype_access_counts.get('self_serve_trial', 0)
production_self_serve = production_access_counts.get('self_serve_free', 0) + production_access_counts.get('self_serve_trial', 0)
focus_categories = ('Marketing, Ads, Email and Social', 'Ecommerce', 'Support and Helpdesk', 'Finance and Fintech')
focus_rows = [record for record in model_records if record['category'] in focus_categories]
focus_gated = [record for record in focus_rows if record['production_access'] in ('paid_plan', 'admin_approval', 'app_review', 'partner_or_sales')]
focus_gate_counts = collections.Counter(record['production_access'] for record in focus_rows if record['production_access'] in ('paid_plan', 'admin_approval', 'app_review', 'partner_or_sales'))
prototype_open = {'self_serve_free', 'self_serve_trial'}
production_gated_names = [record['app'] for record in model_records
                          if record['prototype_access'] in prototype_open and record['production_access'] not in prototype_open]
assert len(production_gated_names) == 16
production_drop_html = '<ul>' + ''.join(f'<li>{esc(name)}</li>' for name in production_gated_names) + '</ul>'
category_gate_rows = []
for category in dict.fromkeys(record['category'] for record in model_records):
    cat_rows = [record for record in model_records if record['category'] == category]
    cat_gated = [record for record in cat_rows if record['production_access'] in ('paid_plan', 'admin_approval', 'app_review', 'partner_or_sales')]
    top_gate = collections.Counter(record['production_access'] for record in cat_gated).most_common(1)
    category_gate_rows.append((category, len(cat_gated), len(cat_rows), ACCESS_LABELS[top_gate[0][0]] if top_gate else 'No gate'))
category_gate_html = '<ul>' + ''.join(f'<li><b>{esc(name)}</b> — {n}/{d} production-gated; main gate: {esc(gate)}</li>'
                                      for name, n, d, gate in category_gate_rows) + '</ul>'
auth_chip_count_total = sum(auth_chip_counts.values())
auth_labels_sorted = sorted(auth_chip_counts.items(), key=lambda item: (-item[1], item[0]))
auth_chip_rows = ''.join(
    f'<li><b>{esc(AUTH_CHIP_LABELS.get(key, key))}</b> — {count} apps</li>'
    for key, count in auth_labels_sorted)
blocker_counts = collections.Counter(record['blocker'] for record in model_records if record['blocker'] != 'none')
blocker_total = sum(blocker_counts.values())
blocker_display = {'paid_gate': 'Paid plan', 'admin_gate': 'Admin approval',
                   'app_review': 'App review', 'partner_gate': 'Partner / sales',
                   'sparse_api': 'Sparse API docs', 'no_docs': 'No public API docs'}
blocker_rows = ''.join(
    f'<li><b>{esc(blocker_display.get(key, key))}</b> — {count} apps</li>'
    for key, count in sorted(blocker_counts.items(), key=lambda item: (-item[1], item[0])))
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
documented_candidates = verdicts.get('documented_build_candidate', 0)
build_next = sorted(datamodel_v2.build_next(model_records), key=lambda item: item['app'].casefold())
build_next_html = '<ul>' + ''.join('<li>' + esc(item['app']) + ' · ' + esc(item['category']) + '</li>'
                                  for item in build_next) + '</ul>'
human_log_counts = collections.Counter(item.get('field', 'unknown') for item in _model_log)
rename_rows = []
for row in apps:
    match = re.search(r'\b([A-Za-z0-9 .-]+) became ([A-Za-z0-9 .-]+) on \d{4}-\d{2}-\d{2}', row.get('summary', ''))
    if match:
        rename_rows.append(f'{match.group(1).strip()} → {match.group(2).strip()}')
manual_log_total = len(_model_log)
rename_html = ', '.join(esc(item) for item in rename_rows) or 'none recorded'
assert len(easy_wins) == len(datamodel_v2.easy_wins(model_records))
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
assert auth_crosscheck['apps_total'] == 100 and auth_crosscheck['apps_in_catalog'] == catalog_listed
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
                        '</span><h3>' + esc(record['app']) + ' · ' + esc(FIELD_LABELS[record['field']]) + '</h3><p><b>Frozen agent answer:</b> ' +
                        esc(display(record['pass12_answer'])) + '</p><p><b>Review:</b> ' + esc(record['review_note']) + '</p><p><b>Checked correction:</b> ' +
                        esc(display(record['correction'])) + (f'</p><p class="muted">Earlier extraction example; final AI-labeled-gold pass had {final_gold_incorrect} incorrect answers.</p>' if record['app'] == 'Zendesk' and record['rating'] == 'incorrect' else '') + '</article>' for record in examples)


def half_fixed(view):
    total = view['total_claims']
    return f"{pct(view['weighted_numerator'], total)} ({view['weighted_numerator']:g}/{total})"


def answered_view(view):
    return f"{view['answered']}/{view['total_claims']} ({pct(view['answered'], view['total_claims'])})"


def strict_answered(view):
    scored = view['scored_answered']
    return pct(view['strict_numerator'], scored) if scored else 'undefined'


fp_selected, fp_holdout = first_pass['selected_sample'], first_pass['random_holdout']
assert fp_selected['first_pass']['total_claims'] == fp_holdout['first_pass']['total_claims'] == 60
fp_sel_first, fp_sel_final = fp_selected['first_pass'], fp_selected['final_pass']
fp_hol_first, fp_hol_final = fp_holdout['first_pass'], fp_holdout['final_pass']


def move_row(label, selected_view, holdout_view):
    return ('<tr><th scope="row">' + label + '</th><td>' + half_fixed(selected_view) + '</td><td>' +
            half_fixed(holdout_view) + '</td><td>' + answered_view(selected_view) + ' / ' +
            answered_view(holdout_view) + '</td></tr>')


movement_html = (
    '<details><summary>Earlier author self-review (secondary)</summary>'
    '<p class="muted">The AI-labeled gold panel above is the scored comparison. The cards and table below are my own '
    'earlier six-field review of the same sample; they are disclosed as self-assessed, not as independent adjudication.</p>'
    '<div class="notice"><b>How I checked the accuracy.</b> '
    'First my script pulled all six fields for the 60 sampled claims — that is the first pass. '
    'Then I went back over the same 60 claims myself: I searched wider, re-read the dates and the surrounding '
    'context, and fixed the ones the script got wrong — that is the final pass. I scored both passes over the same '
    '60 claims; unanswered claims score zero.'
    '<div class="tablewrap"><table><thead><tr><th>Pass</th><th>Selected sample</th><th>Random holdout</th>'
    '<th>Claims answered<br>(selected / holdout)</th></tr></thead><tbody>'
    + move_row('First pass — script only', fp_sel_first, fp_hol_first) +
    move_row('After my manual review', fp_sel_final, fp_hol_final) +
    '</tbody></table></div>'
    '<p>Half-credit means a partly-correct claim counts as 0.5 and an unresolved one counts as 0, out of all 60. '
    'My script scored lower on the first pass because its rule insisted on a vendor-root API path, so it gave up on '
    'most of the tricky claims. On the claims it did answer it actually looks better — ' +
    strict_answered(fp_sel_first) + ' against ' + strict_answered(fp_sel_final) +
    ' on the selected sample — but that is only because my script answered the easy ones and skipped the rest. '
    'Once every claim has to count, my review moves the score up: the selected sample goes from ' +
    half_fixed(fp_sel_first) + ' to ' + half_fixed(fp_sel_final) + ', and the random holdout from ' +
    half_fixed(fp_hol_first) + ' to ' + half_fixed(fp_hol_final) + '.</p></div></details>')


GOLD_PASS_NAMES = {'pass1': 'Pass 1 — first extraction', 'pass2': 'Pass 2 — after re-search',
                   'pass3': 'Pass 3 — final (checked dataset)'}
GOLD_SCOPES = (('judgment_fields', '4 AI-labeled fields'), ('all_six_fields', 'all six fields'))
GOLD_FIELD_ORDER = ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')


def gold_cov(view):
    if not view['total'] or view['coverage'] is None:
        return '—'
    return f"{view['answered']}/{view['total']} ({100 * view['coverage']:.1f}%)"


def gold_prec(view, which):
    value = view['precision_strict' if which == 'strict' else 'precision_half']
    if value is None:
        return '—'
    if which == 'half':
        return f'{100 * value:.1f}%'
    low, high = view['strict_ci']
    return f"{100 * value:.1f}% [{100 * low:.1f}–{100 * high:.1f}%]"


def gold_fixed_half(view):
    """Half-credit across every row, with abstained/unresolved scoring zero."""
    if not view['total']:
        return '—'
    return f"{100 * (view['correct'] + 0.5 * view['partial']) / view['total']:.1f}%"


def gold_pct(value):
    return '—' if value is None else f'{100 * value:.1f}%'


def gold_ci(view):
    low, high = view['strict_ci']
    return f'{100 * low:.1f}–{100 * high:.1f}%'


gold_pass_rows = ''
for scope, scope_label in GOLD_SCOPES:
    for source in ('pass1', 'pass2', 'pass3'):
        view = gold['overall'][source][scope]
        gold_pass_rows += (
            f'<tr><th scope="row">{esc(GOLD_PASS_NAMES[source])}<br>'
            f'<span class="muted">{esc(scope_label)} · {esc(gold["pass_sources"][source])}</span></th>'
            f'<td>{gold_cov(view)}</td><td>{gold_prec(view, "strict")}</td><td>{gold_prec(view, "half")}</td>'
            f'<td>{gold_fixed_half(view)}</td>'
            f'<td>{view["n"]}</td><td>{view["correct"]} / {view["partial"]} / {view["incorrect"]}</td>'
            f'<td>{view["abstained"]}</td><td>{view["unresolved"]}</td></tr>')

gold_field_rows = ''
for field in GOLD_FIELD_ORDER:
    for source in ('pass1', 'pass2', 'pass3'):
        view = gold['per_field'][source][field]
        gold_field_rows += (
            f'<tr><th scope="row">{esc(FIELD_LABELS[field])}</th><td>{esc(GOLD_PASS_NAMES[source])}</td>'
            f'<td>{gold_cov(view)}</td><td>{gold_prec(view, "strict")}</td><td>{gold_prec(view, "half")}</td>'
            f'<td>{view["n"]}</td><td>{view["correct"]} / {view["partial"]} / {view["incorrect"]}</td>'
            f'<td>{view["abstained"]}</td><td>{view["unresolved"]}</td></tr>')

gold_cause_rows = ''.join(
    f'<li><b>{esc(FIELD_LABELS.get(key.split(":", 1)[0], key.split(":", 1)[0]))}</b> · '
    f'{esc(key.split(":", 1)[1])} — {count}</li>'
    for key, count in sorted(gold['miss_causes'].items(), key=lambda item: (-item[1], item[0])))

gold_quality = gold['row_quality']
fetch_rows_text = ', '.join(gold_quality['fetch_failed_rows']) or 'none'
off_topic_rows_text = ', '.join(gold_quality['off_topic_rows']) or 'none'
gold_miss_count = len(gold['misses'])
gold_unscoreable_ratings = sum(count for key, count in gold['miss_causes'].items()
                               if key.endswith(':gold_unscoreable'))
agent_miss_causes = gold_miss_count - gold_unscoreable_ratings
gold_judgment_final = gold['overall']['pass3']['judgment_fields']
gold_judgment_first = gold['overall']['pass1']['judgment_fields']
gold_all_final = gold['overall']['pass3']['all_six_fields']
human_agreement = {}
gold_labels = __import__('gold_score_v4').load_gold()
app_lookup = {row['app']: row for row in apps}
for cohort_name, result in (('Selected sample', selected), ('Random holdout', holdout)):
    pairs = []
    for record in result['records']:
        if record['field'] not in ('auth', 'credential_gate', 'api_surface', 'official_mcp'):
            continue
        app_number = app_lookup[record['app']]['number']
        pass12_claims = json.loads((ROOT / f"data/pass12/{app_number:03}.json").read_text(encoding='utf-8'))['claims']
        gold_row = gold_labels[(record['app'], record['field'])]
        gold_rating = __import__('gold_score_v4').grade_judgment(
            pass12_claims[record['field']]['value'], gold_row['gold_value'], gold_row['gold_status'],
            record['field'], gold_row.get('labeler_note', ''))
        pairs.append((record['rating'], gold_rating))
    human_agreement[cohort_name] = {'n': len(pairs), 'agree': sum(a == b for a, b in pairs)}
assert sum(x['n'] for x in human_agreement.values()) == 80
agreement_total = sum(x['agree'] for x in human_agreement.values())
agreement_n = sum(x['n'] for x in human_agreement.values())

firecrawl_before = firecrawl_comparison.get('before') or {}
firecrawl_after = firecrawl_comparison.get('after') or {}
firecrawl_targets = firecrawl_comparison.get('apps') or []
firecrawl_before_matches = sum(bool((firecrawl_before.get(name) or {}).get('quote_found'))
                               for name in firecrawl_targets)
firecrawl_after_matches = sum(bool((firecrawl_after.get(name) or {}).get('quote_found'))
                              for name in firecrawl_targets)
firecrawl_recovered = [name for name in firecrawl_targets
                       if not (firecrawl_before.get(name) or {}).get('quote_found')
                       and (firecrawl_after.get(name) or {}).get('quote_found')]
firecrawl_lost = [name for name in firecrawl_targets
                  if (firecrawl_before.get(name) or {}).get('quote_found')
                  and not (firecrawl_after.get(name) or {}).get('quote_found')]
firecrawl_all_200 = bool(firecrawl_targets) and all(
    (firecrawl_before.get(name) or {}).get('status') == 200
    and (firecrawl_after.get(name) or {}).get('status') == 200
    for name in firecrawl_targets)
firecrawl_rows = ''.join(
    '<tr><th scope="row">' + esc(name) + '</th><td>' +
    ('HTTP ' + str((firecrawl_before.get(name) or {}).get('status'))
     if (firecrawl_before.get(name) or {}).get('status') is not None else 'No response') +
    '</td><td>' + ('Yes' if (firecrawl_before.get(name) or {}).get('quote_found') else 'No') +
    '</td><td>' + ('HTTP ' + str((firecrawl_after.get(name) or {}).get('status'))
                   if (firecrawl_after.get(name) or {}).get('status') is not None else 'No response') +
    '</td><td>' + ('Yes' if (firecrawl_after.get(name) or {}).get('quote_found') else 'No') + '</td></tr>'
    for name in firecrawl_targets)

# Re-score the __HAND_FIELD_COUNT__ labeled fields separately within the selected and holdout cohorts.
gold_score_module = __import__('gold_score_v4')
gold_labels = gold_score_module.load_gold()
gold_cohort_scores = {}
for cohort_name, result in (('Selected sample', selected), ('Random holdout', holdout)):
    cohort_apps = sorted({record['app'] for record in result['records']})
    ratings = collections.Counter()
    total_rows = 0
    scoreable_rows = 0
    for app_name in cohort_apps:
        checked_row = app_lookup[app_name]
        for field in gold['judgment_fields']:
            label = gold_labels[(app_name, field)]
            claim_value = checked_row['fields'][field]['value']
            rating = gold_score_module.grade_judgment(
                claim_value, label['gold_value'], label['gold_status'], field,
                label.get('labeler_note', ''))
            ratings[rating] += 1
            total_rows += 1
            if label['gold_status'] == 'found':
                scoreable_rows += 1
    answered_rows = sum(ratings[key] for key in ('correct', 'partial', 'incorrect'))
    gold_cohort_scores[cohort_name] = {
        'apps': len(cohort_apps), 'total': total_rows, 'scoreable': scoreable_rows,
        'answered': answered_rows, 'correct': ratings['correct'], 'partial': ratings['partial'],
        'incorrect': ratings['incorrect'],
        'unscoreable': total_rows - scoreable_rows,
        'coverage': pct(answered_rows, scoreable_rows),
        'strict': pct(ratings['correct'], answered_rows),
        'half': pct(ratings['correct'] + 0.5 * ratings['partial'], answered_rows),
    }
assert sum(item['total'] for item in gold_cohort_scores.values()) == gold['overall']['pass3']['judgment_fields']['total']
assert sum(item['scoreable'] for item in gold_cohort_scores.values()) == gold['row_quality']['labeled_found']
selected_score = gold_cohort_scores['Selected sample']
holdout_score = gold_cohort_scores['Random holdout']
success_a, total_a = selected_score['correct'], selected_score['answered']
success_b, total_b = holdout_score['correct'], holdout_score['answered']
combined_success = success_a + success_b
combined_total = total_a + total_b
observed_prob = math.comb(total_a, success_a) * math.comb(total_b, success_b) / math.comb(combined_total, combined_success)
fisher_p = 0.0
for x in range(max(0, combined_success - total_b), min(total_a, combined_success) + 1):
    probability = math.comb(total_a, x) * math.comb(total_b, combined_success - x) / math.comb(combined_total, combined_success)
    if probability <= observed_prob + 1e-12:
        fisher_p += probability
strict_gap_points = abs(float(selected_score['strict'].rstrip('%')) - float(holdout_score['strict'].rstrip('%')))

sdk_schemes = collections.Counter(scheme for rec in sdk_check['records']
                                  for scheme in (rec.get('sdk_auth_schemes') or []))
sdk_scheme_rows = ''.join(f'<li><b>{esc(scheme)}</b> — {count} app assignments</li>'
                          for scheme, count in sorted(sdk_schemes.items(), key=lambda item: (-item[1], item[0])))
mcp_tiers = collections.Counter(record['mcp_tier'] for record in model_records)
assert sum(mcp_tiers.values()) == app_count
assert set(mcp_tiers).issubset(MCP_TIER_LABELS)
assert all(1 <= len(record['what_it_does'].split()) <= 10 and len(record['what_it_does']) <= 80
           for record in model_records)
assert auth_known_app_count + auth_unrecognized_app_count == app_count
mcp_tier_rows = ''.join(f'<li><b>{esc(MCP_TIER_LABELS[tier])}</b> — {count}</li>'
                        for tier, count in sorted(mcp_tiers.items()))
auth_crosscheck_rows = auth_crosscheck['by_comparison']
pattern_items = [
    f'{len(focus_categories)}/{category_count} categories (__FOCUS_CATEGORY_SHARE__ of apps) account for {len(focus_gated)}/{production_gate_total} production gates ({pct(len(focus_gated), production_gate_total)}).',
    f'Free/trial self-serve access totals {prototype_self_serve} apps for prototypes and {production_self_serve} for production; {len(production_gated_names)} apps move behind a production gate. Managed OAuth cannot grant a paid plan, app review, admin approval, or partner access.',
    f'{production_gate_total}/{app_count} apps document paid-plan, admin, app-review, or partner access for production.',
    f'For {auth_crosscheck_rows["research_broader"]}/{auth_crosscheck["apps_in_catalog"]} catalog apps, documented auth is broader than Composio auth_schemes.',
    f'{mcp_tiers.get("hosted_action", 0)} apps have hosted-action MCP; local, docs-only, beta, prelaunch, none, and unresolved are distinct.'
]
patterns_html = '<ol>' + ''.join(f'<li>{esc(item)}</li>' for item in pattern_items) + '</ol>'

broader_apps = sorted((row for row in auth_crosscheck.get('records', [])
                       if row.get('comparison') == 'research_broader'),
                      key=lambda row: (-len(row.get('research_not_in_composio', [])), row['app']))[:10]
broader_html = '<ol>' + ''.join(f'<li><b>{esc(row["app"])}</b> — {len(row.get("research_not_in_composio", []))}: '
                               f'{esc(", ".join(row.get("research_not_in_composio", [])))}</li>'
                               for row in broader_apps) + '</ol>'

gold_labeling = gold_provenance['gold_labels']
label_provenance_note = (
    f"AI-labeled from {gold_labeling['evidence_source']}; model/session identity {gold_labeling['labeler_identity']}. "
    f"A separate session is {gold_labeling['separate_session']}. "
    f"{gold_labeling['agent_answer_exposure']['reported_status']} "
    f"Earlier chat label exclusion is {gold_labeling['earlier_chat_label_exclusion']['status']}."
)

gold_panel_html = (
    f'<h3>AI-labeled gold · {len(gold["judgment_fields"])} fields</h3>'
    f'<div class="notice"><b>Label provenance:</b> {esc(label_provenance_note)} '
    f'Gold status across the {gold_judgment_final["total"]} rows: '
    f'<b>{gold_quality["labeled_found"]} found</b>, <b>{gold_quality["labeled_not_stated_in_docs"]} not stated</b>, '
    f'<b>{gold_quality["labeled_unresolved"]} unresolved</b>. The {gold_quality["fetch_failed"]} fetch-failed row '
    f'({esc(fetch_rows_text)}) and {gold_quality["off_topic"]} off-topic row ({esc(off_topic_rows_text)}) remain reported. '
    f'Unresolved ratings rose from {gold_judgment_first["unresolved"]} to {gold_judgment_final["unresolved"]}: Pass 1 abstained on '
    f'{gold_judgment_first["abstained"]} rows, so some gold-unscoreable rows were recorded as abstentions. Pass 3 abstained on '
    f'{gold_judgment_final["abstained"]} rows, surfacing all {gold_judgment_final["unresolved"]} gold-unscoreable rows '
    f'({gold_quality["labeled_not_stated_in_docs"]} not stated, {gold_quality["labeled_unresolved"]} unresolved). '
    'Strict precision is correct / answered; half-credit is (correct + 0.5 × partial) / answered; fixed-half counts unanswered rows as zero.</div>'
    f'<p>Separate AI source re-check of {len(spotcheck["rows"])} seeded rows: {spotcheck_counts.get("supported", 0)} supported, '
    f'{spotcheck_counts.get("conflict", 0)} current-source conflicts, {spotcheck_counts.get("partial_or_inconclusive", 0)} partial / inconclusive. '
    f'This was an AI source re-check, not a human agreement check; it was not independent of saved labels and did not rescore the frozen results. '
    f'<a href="gold_source_recheck_v1.json">Open the row-level re-check</a>.</p>'
    f'<p>Current-source follow-up reviewed {source_adjudication_count} known conflicts against current first-party docs. '
    'This is separate from the frozen-excerpt score and does not silently change its labels. '
    '<a href="current_source_adjudication_v1.json">Open the current-source adjudication ledger</a>.</p>'
    f'<p>Author-reported human check of {human_spotcheck["sample"]["n"]} rows sampled from '
    f'{human_spotcheck["sample"]["eligible_rows"]} eligible rows: '
    f'{human_spotcheck_summary["status_matches"]}/{human_spotcheck_summary["clear_rows"]} clear status matches '
    f'({human_spotcheck_summary["clear_status_agreement"]:.1%}); '
    f'{human_spotcheck_summary["status_disagreements"]} status disagreements and '
    f'{human_spotcheck_summary["weak_or_ambiguous"]} weak row. If the weak row is counted as found, '
    f'{human_spotcheck_summary["if_weak_counts_as_found_matches"]}/{human_spotcheck_summary["if_weak_counts_as_found_total"]} match '
    f'({human_spotcheck_summary["if_weak_counts_as_found_agreement"]:.1%}). Status only, not full field-value agreement; '
    f'{human_spotcheck_summary["field_scope_mismatches"]} credential-gate quotes address authentication. '
    f'The author had seen prior assistant answers, so this check is not independent and was not blind. '
    f'<a href="human_gold_spotcheck_results_v1.json">Open the row-level human-check results</a>; '
    f'<a href="human_gold_spotcheck_queue_v1.json">open the sample queue</a>.</p>'
    f'<div class="notice"><b>{len(FIELD_LABELS)}-field score · secondary:</b> final coverage {gold_cov(gold_all_final)}; strict '
    f'{gold_prec(gold_all_final, "strict")}; half-credit {gold_prec(gold_all_final, "half")}; '
    f'n={gold_all_final["n"]}; fixed half over all {gold_all_final["total"]} rows {gold_fixed_half(gold_all_final)}. '
    f'The {len(FIELD_LABELS) - len(gold["judgment_fields"])} added fields are checked against the Composio catalog and the written verdict rule.</div>'
    '<div class="tablewrap"><table><thead><tr><th>Pass</th><th>Coverage<br>(answered / total)</th>'
    '<th>Strict accuracy<br>(correct / answered)</th><th>Half-credit<br>(+0.5 × partial)</th>'
    '<th>Half over all rows<br>(abstentions = 0)</th><th>n</th>'
    '<th>correct / partial / incorrect</th><th>Abstained</th><th>Unresolved</th></tr></thead><tbody>'
    + gold_pass_rows + '</tbody></table></div>'
    '<p class="muted">Strict precision carries a Wilson 95% interval with n = answered. No interval is reported for fractional half-credit. '
    'Coverage is answered / all sampled rows; scoreable coverage is answered / rows labeled found. The per-field table below '
    'repeats every count for every pass.</p>'
    '<details><summary>Per-field breakdown — each pass × each field (coverage, strict, half-credit, n)</summary>'
    '<div class="tablewrap"><table><thead><tr><th>Field</th><th>Pass</th><th>Coverage</th>'
    '<th>Strict (95% CI)</th><th>Half-credit</th><th>n</th>'
    '<th>correct / partial / incorrect</th><th>Abstained</th><th>Unresolved</th></tr></thead><tbody>'
    + gold_field_rows + '</tbody></table></div></details>'
    f'<h3>All-pass miss accounting</h3><p>{gold_miss_count} non-correct ratings across three passes split into '
    f'{agent_miss_causes} agent-caused misses on scoreable gold and {gold_unscoreable_ratings} gold-unscoreable ratings across passes '
    f'({gold_quality["labeled_not_stated_in_docs"] + gold_quality["labeled_unresolved"]} distinct gold rows per pass). This is not the final-pass error count. Causes:</p><ul>' + gold_cause_rows + '</ul>'
    f'<details><summary>Inspect all {gold_miss_count} misses</summary><div class="tablewrap"><table class="reviewtable">'
    '<thead><tr><th>Pass</th><th>App / field</th><th>Agent answer</th><th>Gold</th><th>Rating</th><th>Cause</th></tr>'
    '</thead><tbody id="missrows"></tbody></table></div></details>'
)

gold_misses_payload = json.dumps(
    [{'pass': miss['pass'], 'app': miss['app'], 'field': miss['field'], 'agent': miss['agent'],
      'gold': miss['gold'], 'rating': miss['rating'], 'cause': miss['cause']} for miss in gold['misses']],
    ensure_ascii=False).replace('</', '<\\/')


public_apps = []
for row in apps:
    public_row = {key: row[key] for key in PUBLIC_ROW_KEYS if key in row}
    public_row['fields'] = {field: public_claim(claim) for field, claim in row['fields'].items()}
    model = model_by_app[row['app']]
    public_row['what_it_does'] = model['what_it_does']
    public_row['auth_chips'] = [AUTH_CHIP_LABELS.get(chip, chip) for chip in model['auth_chips']]
    public_row['mcp_tier'] = model['mcp_tier']
    public_row['prototype_access'] = model['prototype_access']
    public_row['production_access'] = model['production_access']
    mcp_sources = row['fields']['official_mcp'].get('evidence', [])
    dates = [source.get('published_at') for source in mcp_sources if source.get('published_at')]
    public_row['mcp_updated'] = (f"Updated {max(dates)}" if dates else
                                 f"Undated · checked {max((s.get('retrieved_at', '') for s in mcp_sources), default='')}")
    public_apps.append(public_row)
assert_public_payload(public_apps)
payload = json.dumps(public_apps, ensure_ascii=False).replace('</', '<\\/')
review_payload = json.dumps(review_records, ensure_ascii=False).replace('</', '<\\/')
repo = 'https://github.com/harshbehl67-ctrl/-composio-product-ops-research'
page = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Official-documentation research across 100 apps: authentication, access, API surface, MCP, buildability, and independent accuracy review."><title>100-app integration evidence | Composio take-home</title><style>
:root{--ink:#173b31;--paper:#f4f3eb;--line:#d4ddcf;--lime:#d9f99d;--muted:#5b6e62;--white:#fff;--amber:#fff0c2;--red:#ffe0dc;--blue:#dcecff}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}a{color:#1f6b49;text-underline-offset:3px}header{background:#153c30;color:#f5f7ee;padding:24px max(5vw,24px) 88px}header a{color:#dcf7c7}.nav{display:flex;justify-content:space-between;gap:20px;font-size:12px;letter-spacing:.12em;text-transform:uppercase}.hero{max-width:1200px;margin:auto;display:grid;grid-template-columns:1.25fr .75fr;gap:44px;align-items:center}h1,h2,h3{font-family:Georgia,serif;font-weight:400;line-height:1.08}h1{font-size:clamp(42px,6.4vw,78px);margin:64px 0 22px}h2{font-size:clamp(32px,4vw,48px);margin:0 0 18px}h3{font-size:24px;margin:0 0 12px}.lead{font-size:19px;max-width:760px;color:#d9e8da}.badge{display:inline-block;background:var(--lime);color:#173b31;border-radius:40px;padding:7px 14px;font-size:12px;font-weight:750}.scene{border:1px solid #79a48a;border-radius:22px;padding:24px;display:grid;gap:12px}.step{border:1px solid #6c967d;border-radius:10px;padding:13px}.step b{color:var(--lime);margin-right:10px}main{max-width:1200px;padding:0 24px;margin:auto}.metrics{display:grid;grid-template-columns:repeat(4,1fr);background:#fff;border:1px solid var(--line);margin-top:-38px}.metric{padding:24px;border-right:1px solid var(--line)}.metric:last-child{border-right:0}.metric strong{display:block;font:36px Georgia,serif}.metric small{color:var(--muted)}section{padding:68px 0;border-bottom:1px solid var(--line)}.kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:750;color:#52735b}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#fff;border:1px solid var(--line);padding:24px}.card p:last-child{margin-bottom:0}.notice{padding:22px;background:#e7efdc;border-left:4px solid #6b9644}.warning{background:var(--amber);border-left-color:#b37a12}.tablewrap{overflow:auto;border:1px solid var(--line);background:#fff}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:12px;border-bottom:1px solid #e2e8dd;text-align:left;vertical-align:top}thead th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;background:#f8faf5}tbody tr:last-child th,tbody tr:last-child td{border-bottom:0}.controls{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}label{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}input,select,button{font:inherit;padding:10px;border:1px solid #a9b9aa;background:#fff;color:var(--ink);border-radius:4px}input{min-width:220px}button{cursor:pointer}.flow{display:flex;flex-wrap:wrap;gap:9px}.flow span{padding:12px 14px;background:#fff;border:1px solid var(--line)}pre{overflow:auto;background:#102d25;color:#e6f4df;padding:18px;border-radius:8px;font-size:13px}.rating{display:inline-block;border-radius:20px;padding:3px 9px;font-size:11px;font-weight:800;text-transform:uppercase;background:#e7ece3}.rating.correct{background:#d9f5d0}.rating.partial{background:var(--amber)}.rating.incorrect{background:var(--red)}.rating.abstained{background:#e8e8e8}.rating.unresolved{background:var(--blue)}details{min-width:150px}summary{cursor:pointer;font-weight:700}.source{display:inline-block;margin:3px 10px 3px 0}.quote{display:block;margin:4px 0 10px;color:var(--muted);font-size:13px}.muted{color:var(--muted)}.pill{display:inline-block;border:1px solid var(--line);border-radius:20px;padding:3px 8px;font-size:12px;background:#fff}.chip{display:inline-block;border:1px solid var(--line);border-radius:20px;padding:2px 7px;margin:2px;font-size:11px;background:#f8faf5}.purpose{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;max-width:260px}.unknown{color:#785d18}.checked{color:#216442}.rowdetails p{margin:10px 0}.rowdetails b{font-weight:750}.reviewtable{font-size:13px}footer{padding:42px 0 56px;color:var(--muted)}code{font-family:ui-monospace,monospace}@media(max-width:860px){.hero{grid-template-columns:1fr}.scene{display:none}.metrics{grid-template-columns:repeat(2,1fr)}.metric{border-bottom:1px solid var(--line)}.cards{grid-template-columns:1fr}section{padding:50px 0}h1{margin-top:46px}.nav span{display:none}}@media(max-width:520px){main{padding:0 16px}header{padding-left:16px;padding-right:16px}.metrics{grid-template-columns:1fr}.metric{border-right:0}input{min-width:100%;width:100%}.controls label{width:100%}.controls select,.controls button{width:100%}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
</style></head><body><header><nav class="nav"><span>Composio · AI Product Ops take-home</span><a href="#evidence">Explore 100 apps ↓</a></nav><div class="hero"><div><h1>100 apps. What can an agent actually build?</h1><p class="lead">I read the official docs for 100 apps across ten categories to work out where an agent could really build something — and where it can't, and why. Every claim below links to the first-party source I used.</p><span class="badge">CHECKED 24 NOV 2026 · NO VENDOR CREDENTIALS TESTED</span></div><div class="scene" aria-label="How I worked"><div class="step"><b>01</b>Find each app's official API, auth, access and MCP docs</div><div class="step"><b>02</b>Save the raw passes and the exact quotes</div><div class="step"><b>03</b>Check the dates, the context and who owns the page</div><div class="step"><b>04</b>Score a category sample and a random holdout</div></div></div></header><main><div class="metrics"><div class="metric"><strong>100</strong><small>apps across 10 categories</small></div><div class="metric"><strong>__CHECKED__/500</strong><small>vendor-field answers with a cited source</small></div><div class="metric"><strong>__BUILD__</strong><small>documented build candidates</small></div><div class="metric"><strong>__GOLD_STRICT_PCT__</strong><small>AI-labeled 4-field gold · coverage __GOLD_COVERAGE_COUNT__/__GOLD_TOTAL__ sampled (__GOLD_COVERAGE_PCT__), __GOLD_COVERAGE_COUNT__/__GOLD_SCOREABLE__ scoreable (__GOLD_SCOREABLE_COVERAGE_PCT__) · half-credit __GOLD_HALF__ · n=__GOLD_N__ · __GOLD_INCORRECT__ incorrect · strict 95% CI __GOLD_STRICT_CI__</small></div></div>
<section><div class="kicker">01 / Headline findings</div><h2>Prototype access and production access are different questions.</h2><div class="notice"><b>Production gates</b> are counted separately: __PRODUCTION_GATE_TOTAL__/__APP_COUNT__ apps document a paid plan, admin approval, app review, or partner / sales requirement (__PRODUCTION_GATE_TEXT__). The blocker ranking below includes only apps with a documented blocker (__BLOCKER_TOTAL__).</div><h3>Prototype vs production access</h3><div class="tablewrap"><table><thead><tr><th>Access path</th><th>Prototype</th><th>Production</th></tr></thead><tbody>__ACCESS_ROWS__</tbody></table></div><h3>Blockers among apps that have one</h3><ul>__BLOCKER_ROWS__</ul><div class="cards"><article class="card"><h3>Authentication chips</h3><p>__AUTH_KNOWN_APPS__/__APP_COUNT__ apps have a recognized auth chip; __AUTH_UNRECOGNIZED__ are labeled none or unresolved. Most common: <b>__TOP_AUTH__</b> (__TOP_AUTH_COUNT__ apps). Chip assignments overlap, so category counts do not sum to app count.</p><ul>__AUTH_CHIP_ROWS__</ul></article><article class="card"><h3>API surface</h3><p>REST is documented for __REST__ apps and GraphQL for __GRAPHQL__. __BROAD__ have a broad surface, __MODERATE__ a moderate one and __NARROW__ a narrow one.</p></article><article class="card"><h3>Vendor MCP tiers</h3><ul>__MCP_TIER_ROWS__</ul><p>Google Ads MCP is local or customer self-hosted on Cloud Run; read-only mode is configurable, with limited propose-and-confirm mutations. Brex is beta, Lark is local, Pinterest is prelaunch, NotebookLM is beta / Early Access Public Preview, and Shopify Dev MCP is local and read-only for docs/schema lookup.</p><p>Composio catalog: __CATALOG_LISTED__ listed, __CATALOG_NOT_LISTED__ not listed. Vendor MCP source review checked __MCP_CHECKED__/__APP_COUNT__ apps; __MCP_UNRESOLVED_TIERS__ MCP tier labels remain unresolved. Source verification and tier classification are separate counts.</p></article></div><h3>Build candidates and easy wins</h3><p>__DOCUMENTED_CANDIDATES__/__APP_COUNT__ apps meet the documented-candidate label; __EASY_WIN_COUNT__ meet the stricter easy-win rule: a documented build candidate with free or trial access for both prototype and production, plus a broad or moderate API.</p>__EASY_WINS__<h3>Build next · catalog gaps among eligible apps (__BUILD_NEXT_COUNT__)</h3>__BUILD_NEXT__</section>
<section><div class="kicker">02 / Category matrix</div><h2>Ten categories, six honest outcomes.</h2><p>“Documented build candidate” means the docs show a real path to build a working prototype. It does not mean I got a production credential.</p><div class="notice"><h3>Patterns</h3>__PATTERNS__<h4>Production-gate concentration by category</h4><p>Category shares are calculated from the normalized prototype/production rows; an earlier estimate did not reconcile with those app-level fields.</p>__CATEGORY_GATE_LIST__<p>Apps that move from prototype free/trial access to a production gate (__DROP_COUNT__):</p>__DROP_LIST__<h4>Top 10 research-broader auth cross-checks</h4>__BROADER_APPS__</div><div class="tablewrap"><table><thead><tr><th>Category</th><th>Apps</th><th>Documented</th><th>Gated</th><th>Partner</th><th>Wrapper</th><th>No public API</th><th>Unresolved</th></tr></thead><tbody>__MATRIX__</tbody></table></div></section>
<section><div class="kicker">03 / The research agent</div><h2>Search is just triage. The evidence is the point.</h2><p class="muted">Official-source discovery → frozen evidence → context-aware extraction → independent review → strict assembly gate.</p><div class="cards"><article class="card"><h3>What my script does</h3><p>For each app it searches for the API reference, authentication, credential-creation, access/pricing and MCP docs. It saves every raw pass, pulls out the scoped claims, keeps the publication dates, and throws away client-only or negated MCP “proofs” before anything gets assembled.</p></article><article class="card"><h3>Where review changed classifications</h3><p>__MANUAL_LOG_TOTAL__ decisions are recorded in the model log: __ACCESS_DECISIONS__ prototype/production splits, __MCP_DECISIONS__ MCP tier decisions, and __AUTH_DECISIONS__ auth-chip decisions, plus __OTHER_DECISIONS__ other logged reviews. The gold set records __FETCH_FAILED__ fetch-failed excerpt(s). Documented rebrand(s): __RENAMES__.</p></article><article class="card"><h3>Firecrawl retrieval check</h3><p>__FIRECRAWL_CONNECTION_STATUS__ On a small __FIRECRAWL_TARGET_COUNT__-page illustration (not a benchmark), direct retrieval reproduced __FIRECRAWL_BEFORE_MATCHES__ stored quotes and Firecrawl reproduced __FIRECRAWL_AFTER_MATCHES__. It recovered __FIRECRAWL_RECOVERED__ and lost __FIRECRAWL_LOST__; all pages returned HTTP 200 in both paths: __FIRECRAWL_ALL_200__. Lark remains unmatched in both paths despite successful HTTP responses; this may indicate a stored-quote/page-content discrepancy rather than a fetch failure.</p></article><article class="card"><h3>Composio SDK cross-check</h3><p>Composio SDK/catalog listing agreement is __SDK_AGREEMENT__ of 100 apps (__SDK_LISTED__ listed and __SDK_NOT_LISTED__ not listed); this is separate from vendor MCP source verification. For __SDK_TOOLS_COMPARED__ apps with a documented tool count, __SDK_TOOLS_MATCH__ match the current SDK count; the rest show count drift.</p><p>SDK <code>auth_schemes</code> assignments across listed toolkits (one app may have multiple):</p><ul>__SDK_SCHEME_ROWS__</ul><p>In the __AUTH_CROSSCHECK_CATALOG__ apps in the catalog comparison, auth detail agrees on __AUTH_AGREE__; research is broader on __AUTH_RESEARCH_BROADER__, Composio on __AUTH_COMPOSIO_BROADER__, with __AUTH_NO_OVERLAP__ no-overlap and __AUTH_TRANSPORT_ONLY__ transport-only cases. This compares documented scope; it is not a wrong-claim count.</p></article></div><h3>__FIRECRAWL_TARGET_COUNT__-page Firecrawl-through-Composio illustration</h3><p>This __FIRECRAWL_BEFORE_MATCHES__-versus-__FIRECRAWL_AFTER_MATCHES__ quote-reproduction result is an illustration, not a benchmark or accuracy measurement; page status is checked independently.</p><div class="tablewrap"><table><thead><tr><th>Hard app</th><th>Direct status</th><th>Direct quote</th><th>Firecrawl status</th><th>Firecrawl quote</th></tr></thead><tbody>__FIRECRAWL_ROWS__</tbody></table></div><h3>Runnable proof</h3><pre>python run_submission_demo_v4.py
python run_one.py --app "Google Ads" --live</pre><p>Run the live check after configuring the Composio session and authorizing Firecrawl. Captured offline output: <a href="run_submission_demo_sample_v4.json">Google Ads demo sample</a>. The full source, saved passes, review logs and validation reports are in the <a href="__REPO__">source repository</a>. You can also export the checked JSON or CSV from the evidence table below.</p></section>
<section><div class="kicker">04 / Accuracy lab</div><h2>Coverage first. Then accuracy, with real denominators.</h2><div class="notice"><b>__HAND_FIELD_COUNT__ labeled fields: coverage rose from __FIRST_GOLD_COVERAGE__ to __FINAL_GOLD_COVERAGE__; strict precision fell from __FIRST_GOLD_STRICT__ to __FINAL_GOLD_STRICT__ as more rows were answered; there were __FINAL_GOLD_INCORRECT__ incorrect answers.</b> __LABEL_PROVENANCE__ The six-field score is secondary: it adds catalog matching and rule-derived buildability.</div>__GOLD_PANEL____MOVEMENT__<h3>__HAND_FIELD_COUNT__-field gold by cohort</h3><div class="cards"><article class="card"><h3>Selected sample · __GOLD_SELECTED_APPS__ apps</h3><p>__GOLD_SELECTED_ANSWERED__/__GOLD_SELECTED_SCOREABLE__ scoreable gold rows answered (__GOLD_SELECTED_COVERAGE__); strict <b>__GOLD_SELECTED_STRICT__</b>; half-credit <b>__GOLD_SELECTED_HALF__</b>; __GOLD_SELECTED_UNSCOREABLE__ gold-unscoreable excluded.</p></article><article class="card"><h3>Random holdout · __GOLD_HOLDOUT_APPS__ apps</h3><p>__GOLD_HOLDOUT_ANSWERED__/__GOLD_HOLDOUT_SCOREABLE__ scoreable gold rows answered (__GOLD_HOLDOUT_COVERAGE__); strict <b>__GOLD_HOLDOUT_STRICT__</b>; half-credit <b>__GOLD_HOLDOUT_HALF__</b>; __GOLD_HOLDOUT_UNSCOREABLE__ gold-unscoreable excluded.</p></article></div><p>Count units: __DOCUMENTED_CANDIDATES__ is the number of apps labeled documented build candidates; __SELECTED_TOTAL__ is the claim count within each author-review cohort; the AI-labeled gold has __GOLD_TOTAL__ rows across both cohorts. Selected/holdout strict gap: __STRICT_GAP__ percentage points (two-sided Fisher exact p=__FISHER_P__; not statistically significant at this sample size). __GOLD_UNSCOREABLE_TOTAL__ gold-unscoreable rows are excluded from __GOLD_SCOREABLE_TOTAL__ scoreable rows.</p><div class="cards"><article class="card"><h3>Selected author review · __SELECTED_APPS__ apps</h3><p>Six claims per app (__SELECTED_TOTAL__ total): __SELECTED_ANSWERED__/__SELECTED_TOTAL__ answered; strict <b>__SELECTED_STRICT__</b>; half-credit <b>__SELECTED_WEIGHTED__</b>.</p><p>Gold-rating agreement on __SEL_AGREE_N__ shared fields: <b>__SEL_AGREE__/__SEL_AGREE_N__</b> (__SEL_AGREE_PCT__).</p></article><article class="card"><h3>Random holdout author review · __HOLDOUT_APPS__ apps</h3><p>Seed __HOLDOUT_SEED__; __HOLDOUT_ANSWERED__/__HOLDOUT_TOTAL__ claims answered; strict <b>__HOLDOUT_STRICT__</b>; half-credit <b>__HOLDOUT_WEIGHTED__</b>.</p><p>Gold-rating agreement on __HOLD_AGREE_N__ shared fields: <b>__HOLD_AGREE__/__HOLD_AGREE_N__</b> (__HOLD_AGREE_PCT__).</p></article></div><h3>Hits and misses, shown honestly</h3><div class="cards">__EXAMPLES__</div><details><summary>Inspect all __REVIEW_TOTAL__ author-reviewed claims</summary><div class="controls"><label>Cohort <select id="cohort"><option value="">All reviews</option><option>Selected sample</option><option>Random holdout</option></select></label></div><div class="tablewrap"><table class="reviewtable"><thead><tr><th>Cohort</th><th>App / field</th><th>Frozen answer</th><th>Author rating</th><th>Correction</th><th>Sources</th></tr></thead><tbody id="reviewrows"></tbody></table></div></details></section>
<section id="evidence"><div class="kicker">05 / The __APP_COUNT__ apps</div><h2>Every claim has a source—or a reason.</h2><p>Of __VENDOR_TOTAL__ vendor-field claims, __CHECKED__ are checked and __VENDOR_UNKNOWN__ remain unresolved. Composio listing status is cross-checked separately for __CATALOG__ apps. The __CHECKED__/__VENDOR_TOTAL__ vendor-field answers are answers with a cited source, not a claim that every source passed a quote-reproduction check.</p><div class="tablewrap"><table><thead><tr><th>Field</th><th>Checked</th><th>Unknown</th><th>Coverage</th></tr></thead><tbody>__COVERAGE_ROWS__</tbody></table></div><div class="controls"><label>Search <input id="search" type="search" placeholder="App, purpose or category"></label><label>Category <select id="category"><option value="">All categories</option></select></label><label>Prototype <select id="prototype"><option value="">All prototype access</option></select></label><label>Production <select id="production"><option value="">All production access</option></select></label><label>Verdict <select id="verdict"><option value="">All verdicts</option></select></label><label>MCP <select id="mcp"><option value="">All MCP states</option></select></label><button id="sort">Sort A–Z</button><button id="json">Export JSON</button><button id="csv">Export CSV</button></div><p id="count" aria-live="polite"></p><div class="tablewrap"><table><thead><tr><th>App</th><th>What it does</th><th>Category</th><th>Auth</th><th>Prototype</th><th>Production</th><th>API</th><th>Vendor MCP tier</th><th>Composio</th><th>Verdict</th><th>Evidence</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section><div class="kicker">06 / Limits and handoff</div><h2>What this evidence does—and does not—prove.</h2><div class="cards"><article class="card"><h3>Documentation, not credentials</h3><p>I never used a live token, a paid plan, admin approval, a partner agreement or a production connection. If something is gated, that is a real finding, not a failed build.</p></article><article class="card"><h3>Dates and absence</h3><p>Where I could, I kept the page’s published or updated date; when there was none, the field reason says so. “No vendor server documented” only covers the source I cite, and unresolved is not the same as absent.</p></article><article class="card"><h3>Security review</h3><p>The bearer-shaped value in my first Git commit is an exact match for a public Zendesk documentation example. It was not a real user’s credential, so I did not rewrite history or revoke anything.</p></article></div><p>Next step: start with the documented easy wins, send the gated apps to the exact access step each one needs, and put the partner-only apps into outreach. Recheck the time-sensitive pages before building.</p></section><footer><a href="__REPO__">Source repository</a> · Checked 24 November 2026 · All page counts are generated from the checked dataset.</footer></main><script>
const data=__DATA__,reviews=__REVIEW__,misses=__MISSES__;const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const safe=u=>/^https?:\/\//i.test(u),vals=v=>Array.isArray(v)?v.join(', '):(typeof v==='object'&&v!==null?JSON.stringify(v):String(v??''));let asc=true;
const gateNames=__GATES__,verdictNames=__VERDICTS__,mcpNames=__MCP__,composioNames=__COMPOSIO__,fieldNames=__FIELDS__;
[...new Set(data.map(a=>a.category))].forEach(c=>{let o=document.createElement('option');o.value=o.textContent=c;$('#category').append(o)});Object.entries(gateNames).forEach(([v,l])=>{for(const id of ['prototype','production']){let o=document.createElement('option');o.value=v;o.textContent=l;$('#'+id).append(o)}});Object.entries(verdictNames).forEach(([v,l])=>{let o=document.createElement('option');o.value=v;o.textContent=l;$('#verdict').append(o)});Object.entries(mcpNames).forEach(([v,l])=>{let o=document.createElement('option');o.value=v;o.textContent=l;$('#mcp').append(o)});
function sources(items){return (items||[]).filter(s=>s&&safe(s.url)).map(s=>`<a class="source" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title||'Source')} ↗${s.published_label?` · ${esc(s.published_label)}`:''}${s.published_at?` · ${esc(s.published_at)}`:''}</a>${s.quote?`<span class="quote">“${esc(s.quote)}”</span>`:''}`).join('')}
function details(row){return `<div class="rowdetails">${Object.entries(row.fields).map(([k,v])=>`<div class="fielddetail"><b>${esc(fieldNames[k])}:</b> <span class="${esc(v.status)}">${esc(vals(v.value))}</span> <em>(${esc(v.status)})</em><br><span class="muted">${esc(v.reason)}</span><br>${sources(v.evidence)}</div>`).join('')}<div class="fielddetail"><b>Blocker:</b> ${esc(row.blocker)}</div><div class="fielddetail"><b>Next action:</b> ${esc(row.next_action)}</div></div>`}
function render(){let q=$('#search').value.toLowerCase(),list=data.filter(a=>(a.app+' '+a.what_it_does+' '+a.category).toLowerCase().includes(q)&&(!$('#category').value||a.category===$('#category').value)&&(!$('#prototype').value||a.prototype_access===$('#prototype').value)&&(!$('#production').value||a.production_access===$('#production').value)&&(!$('#verdict').value||a.fields.verdict.value===$('#verdict').value)&&(!$('#mcp').value||a.mcp_tier===$('#mcp').value )).sort((a,b)=>asc?a.app.localeCompare(b.app):b.app.localeCompare(a.app));window.currentList=list;$('#count').textContent=`${list.length} of ${data.length} apps shown`;$('#rows').innerHTML=list.map(a=>`<tr><td><b>${esc(a.app)}</b></td><td><span class="purpose" title="${esc(a.what_it_does)}">${esc(a.what_it_does)}</span></td><td>${esc(a.category)}</td><td>${a.auth_chips.map(x=>`<span class="chip">${esc(x)}</span>`).join('')}</td><td>${esc(gateNames[a.prototype_access]||a.prototype_access)}</td><td>${esc(gateNames[a.production_access]||a.production_access)}</td><td>${esc(a.fields.api_surface.value)}${a.fields.api_surface.breadth?`<br><span class="pill">${esc(a.fields.api_surface.breadth)}</span>`:''}</td><td><span class="chip">${esc(mcpNames[a.mcp_tier]||a.mcp_tier)}</span><br><span class="muted">${esc(a.mcp_updated)}</span></td><td>${esc(composioNames[a.fields.composio_toolkit.value]||a.fields.composio_toolkit.value)}</td><td>${esc(verdictNames[a.fields.verdict.value]||a.fields.verdict.value)}</td><td><details><summary>View evidence</summary>${details(a)}</details></td></tr>`).join('')}
function renderReviews(){let cohort=$('#cohort').value;$('#reviewrows').innerHTML=reviews.filter(r=>!cohort||r.cohort===cohort).map(r=>`<tr><td>${esc(r.cohort)}</td><td><b>${esc(r.app)}</b><br>${esc(fieldNames[r.field])}</td><td>${esc(vals(r.pass12_answer))}</td><td><span class="rating ${esc(r.rating)}">${esc(r.rating)}</span></td><td>${esc(r.review_note)}<br><b>${esc(vals(r.correction))}</b></td><td>${sources((r.independent_sources||[]).map(url=>({url,title:'Official source'})))}</td></tr>`).join('')}
function renderMisses(){let b=$('#missrows');if(b)b.innerHTML=misses.map(m=>`<tr><td>${esc(m.pass)}</td><td><b>${esc(m.app)}</b><br>${esc(fieldNames[m.field]||m.field)}</td><td>${esc(vals(m.agent))}</td><td>${esc(vals(m.gold))}</td><td><span class="rating ${esc(m.rating)}">${esc(m.rating)}</span></td><td>${esc(m.cause)}</td></tr>`).join('')}
['search','category','prototype','production','verdict','mcp'].forEach(id=>$('#'+id).addEventListener('input',render));$('#cohort').addEventListener('input',renderReviews);$('#sort').onclick=()=>{asc=!asc;$('#sort').textContent=asc?'Sort A–Z':'Sort Z–A';render()};function save(name,content,type){let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([content],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}$('#json').onclick=()=>save('checked-dataset-v4.json',JSON.stringify(window.currentList||data,null,2),'application/json');$('#csv').onclick=()=>{let cols=['app','what_it_does','category','auth','prototype_access','production_access','api_surface','official_mcp','composio_toolkit','verdict','blocker','next_action'],quote=x=>'"'+(/^[=+\-@\t\r]/.test(String(x??''))?"'":'')+String(x??'').replaceAll('"','""')+'"';save('checked-dataset-v4.csv',[cols.join(','),...(window.currentList||data).map(a=>cols.map(k=>quote(k==='app'?a.app:k==='category'?a.category:k==='what_it_does'?a.what_it_does:k==='blocker'?a.blocker:k==='next_action'?a.next_action:k==='prototype_access'?a.prototype_access:k==='production_access'?a.production_access:a.fields[k]?.value)).join(','))].join('\r\n'),'text/csv')};render();renderReviews();renderMisses();
</script></body></html>'''

# Study-scope figures in reader-facing copy come from the checked artifacts.
page = page.replace('100-app integration evidence', '__APP_COUNT__-app integration evidence')
page = page.replace('Explore 100 apps', 'Explore __APP_COUNT__ apps')
page = page.replace('100 apps. What can an agent actually build?', '__APP_COUNT__ apps. What can an agent actually build?')
page = page.replace('official docs for 100 apps across ten categories', 'official docs for __APP_COUNT__ apps across __CATEGORY_COUNT__ categories')
page = page.replace('CHECKED 24 NOV 2026', 'CHECKED __CHECKED_DATE__')
page = page.replace('Checked 24 November 2026', 'Checked __CHECKED_DATE__')
page = page.replace('100 apps across 10 categories', '__APP_COUNT__ apps across __CATEGORY_COUNT__ categories')
page = page.replace('100 apps', '__APP_COUNT__ apps')
page = page.replace('<strong>100</strong><small>apps across 10 categories</small>',
                    '<strong>__APP_COUNT__</strong><small>apps across __CATEGORY_COUNT__ categories</small>')
page = page.replace('<strong>100</strong>', '<strong>__APP_COUNT__</strong>')
page = page.replace('apps across 10 categories</small>', 'apps across __CATEGORY_COUNT__ categories</small>')
page = page.replace('/500', '/__VENDOR_TOTAL__')
page = page.replace('__CHECKED__/500', '__CHECKED__/__VENDOR_TOTAL__')
page = page.replace('500 vendor-field claims', '__VENDOR_TOTAL__ vendor-field claims')
page = page.replace('100 Composio listing claims', '__APP_COUNT__ Composio listing claims')
page = page.replace('Across 100 apps,', 'Across __APP_COUNT__ apps,')
page = page.replace('100 apps meet', '__APP_COUNT__ apps meet')
page = page.replace('over the same 100 apps', 'over the same __APP_COUNT__ apps')
page = page.replace('the 100 apps', 'the __APP_COUNT__ apps')
page = page.replace('Ten categories, six honest outcomes.', '__CATEGORY_COUNT__ categories, six honest outcomes.')
page = page.replace('all six fields', 'all __FIELD_COUNT__ fields')
page = page.replace('six-field score', '__FIELD_COUNT__-field score')
page = page.replace('six-field review', '__FIELD_COUNT__-field review')
page = page.replace('Six claims per app', '__FIELD_COUNT__ claims per app')
page = page.replace('(60 total)', '(__SELECTED_TOTAL__ total)')
page = page.replace('Four hand-labeled fields', '__HAND_FIELD_COUNT__ hand-labeled fields')
page = page.replace('four-field headline', '__HAND_FIELD_COUNT__-field headline')
page = page.replace('for all 60 claims', 'for all __SELECTED_TOTAL__ claims')
page = page.replace('same 60 claims', 'same __SELECTED_TOTAL__ claims')
page = page.replace('out of all 60', 'out of all __SELECTED_TOTAL__')
page = page.replace('the 60 sampled claims', 'the __SELECTED_TOTAL__ sampled claims')
page = page.replace('60 claims and counted', '__SELECTED_TOTAL__ claims and counted')
page = page.replace('Inspect all 120 reviewed claims', 'Inspect all __REVIEW_TOTAL__ reviewed claims')
page = page.replace('all 120 claims', 'all __REVIEW_TOTAL__ claims')
page = page.replace('ten apps / 60 fields', '__HOLDOUT_APPS__ apps / __HOLDOUT_TOTAL__ fields')
page = page.replace('ten apps / 60 claims', '__HOLDOUT_APPS__ apps / __HOLDOUT_TOTAL__ claims')
page = page.replace('These 80 app × field rows', 'These __GOLD_TOTAL__ app × field rows')
page = page.replace('across the 80 rows', 'across the __GOLD_TOTAL__ rows')
page = page.replace('four hand-labelled fields', '__HAND_FIELD_COUNT__ hand-labelled fields')
page = page.replace('four fields', '__HAND_FIELD_COUNT__ fields')
page = page.replace('six fields', '__FIELD_COUNT__ fields')

replacements = {
    '__DATA__': payload, '__REVIEW__': review_payload, '__GOLD_PANEL__': gold_panel_html, '__MISSES__': gold_misses_payload,
    '__GATES__': json.dumps(GATE_LABELS), '__VERDICTS__': json.dumps(VERDICT_LABELS),
    '__MCP__': json.dumps(MCP_LABELS), '__COMPOSIO__': json.dumps(COMPOSIO_LABELS),
    '__FIELDS__': json.dumps(FIELD_LABELS), '__REPO__': repo,
    '__APP_COUNT__': app_count, '__CATEGORY_COUNT__': category_count, '__VENDOR_TOTAL__': vendor_claim_total,
    '__VENDOR_UNKNOWN__': vendor_claim_total - checked_vendor,
    '__CHECKED_DATE__': __import__('datetime').datetime.fromisoformat(checked_date).strftime('%d %b %Y').upper(),
    '__GOLD_TOTAL__': gold_judgment_final['total'], '__HAND_FIELD_COUNT__': len(gold['judgment_fields']),
    '__FIELD_COUNT__': len(FIELD_LABELS), '__SELECTED_TOTAL__': selected['total_claims'],
    '__SELECTED_APPS__': len({record['app'] for record in selected['records']}),
    '__HOLDOUT_TOTAL__': holdout['total_claims'], '__HOLDOUT_APPS__': len({record['app'] for record in holdout['records']}),
    '__HOLDOUT_SEED__': holdout_seed, '__REVIEW_TOTAL__': len(review_records),
    '__BLOCKER_TOTAL__': blocker_total, '__BLOCKER_ROWS__': blocker_rows,
    '__ACCESS_ROWS__': access_table_rows,
    '__PRODUCTION_GATE_TOTAL__': production_gate_total,
    '__PRODUCTION_GATE_TEXT__': production_gate_text,
    '__AUTH_KNOWN_APPS__': auth_known_app_count,
    '__AUTH_UNRECOGNIZED__': auth_unrecognized_app_count,
    '__AUTH_CHIP_ROWS__': auth_chip_rows,
    '__TOP_AUTH__': AUTH_CHIP_LABELS.get(top_auth_chip[0], top_auth_chip[0]),
    '__TOP_AUTH_COUNT__': top_auth_chip[1],
    '__PATTERNS__': patterns_html,
    '__MCP_TIER_ROWS__': mcp_tier_rows, '__DOCUMENTED_CANDIDATES__': documented_candidates,
    '__MCP_UNRESOLVED_TIERS__': mcp_tiers.get('unresolved', 0), '__MCP_CHECKED__': coverage['official_mcp']['checked'],
    '__FOCUS_CATEGORIES__': len(focus_categories), '__FOCUS_GATED__': len(focus_gated), '__FOCUS_GATE_PCT__': pct(len(focus_gated), production_gate_total), '__FOCUS_CATEGORY_SHARE__': pct(len(focus_categories), category_count),
    '__DROP_COUNT__': len(production_gated_names), '__DROP_LIST__': production_drop_html,
    '__CATEGORY_GATE_LIST__': category_gate_html, '__BROADER_APPS__': broader_html,
    '__MANUAL_LOG_TOTAL__': manual_log_total,
    '__ACCESS_DECISIONS__': human_log_counts.get('prototype_access/production_access', 0),
    '__MCP_DECISIONS__': human_log_counts.get('mcp_tier', 0),
    '__AUTH_DECISIONS__': human_log_counts.get('auth_chips', 0), '__OTHER_DECISIONS__': manual_log_total - human_log_counts.get('auth_chips', 0) - human_log_counts.get('mcp_tier', 0) - human_log_counts.get('prototype_access/production_access', 0),
    '__FETCH_FAILED__': gold_quality['fetch_failed'], '__RENAMES__': rename_html,
    '__FISHER_P__': f'{fisher_p:.3f}', '__STRICT_GAP__': f'{strict_gap_points:.1f}',
    '__GOLD_SELECTED_UNSCOREABLE__': selected_score['unscoreable'], '__GOLD_UNSCOREABLE_TOTAL__': selected_score['unscoreable'] + holdout_score['unscoreable'], '__GOLD_SCOREABLE_TOTAL__': selected_score['scoreable'] + holdout_score['scoreable'],
    '__GOLD_HOLDOUT_UNSCOREABLE__': holdout_score['unscoreable'],
    '__EASY_WIN_COUNT__': len(easy_wins), '__BUILD_NEXT_COUNT__': len(build_next), '__BUILD_NEXT__': build_next_html,
    '__SDK_SCHEME_ROWS__': sdk_scheme_rows,
    '__FIRECRAWL_CONNECTION_STATUS__': ('Composio reported an active Firecrawl connection.'
                                        if firecrawl_comparison.get('completed') else
                                        'Firecrawl connection is not active yet.'),
    '__FIRECRAWL_TARGET_COUNT__': len(firecrawl_targets),
    '__FIRECRAWL_BEFORE_MATCHES__': firecrawl_before_matches,
    '__FIRECRAWL_AFTER_MATCHES__': firecrawl_after_matches,
    '__FIRECRAWL_RECOVERED__': ', '.join(firecrawl_recovered) or 'none',
    '__FIRECRAWL_LOST__': ', '.join(firecrawl_lost) or 'none',
    '__FIRECRAWL_ALL_200__': 'yes' if firecrawl_all_200 else 'no',
    '__FIRECRAWL_ROWS__': firecrawl_rows,
    '__AUTH_CROSSCHECK_CATALOG__': auth_crosscheck['apps_in_catalog'],
    '__AUTH_AGREE__': auth_crosscheck_rows['agree'], '__AUTH_RESEARCH_BROADER__': auth_crosscheck_rows['research_broader'],
    '__AUTH_COMPOSIO_BROADER__': auth_crosscheck_rows['composio_broader'],
    '__AUTH_NO_OVERLAP__': auth_crosscheck_rows['disagree_no_overlap'],
    '__AUTH_TRANSPORT_ONLY__': auth_crosscheck_rows['research_transport_only'],
    '__GOLD_COVERAGE_PCT__': gold_pct(gold_judgment_final['coverage']),
    '__GOLD_COVERAGE_COUNT__': gold_judgment_final['answered'], '__GOLD_TOTAL__': gold_judgment_final['total'],
    '__GOLD_SCOREABLE__': gold_judgment_final['scoreable'],
    '__GOLD_SCOREABLE_COVERAGE_PCT__': gold_pct(gold_judgment_final['scoreable_coverage']),
    '__GOLD_STRICT_PCT__': gold_pct(gold_judgment_final['precision_strict']),
    '__GOLD_STRICT__': gold_prec(gold_judgment_final, 'strict'),
    '__GOLD_STRICT_CI__': gold_ci(gold_judgment_final), '__GOLD_HALF__': gold_pct(gold_judgment_final['precision_half']),
    '__GOLD_N__': gold_judgment_final['n'], '__GOLD_INCORRECT__': gold_judgment_final['incorrect'],
    '__FINAL_GOLD_INCORRECT__': final_gold_incorrect,
    '__LABEL_PROVENANCE__': esc(label_provenance_note),
    '__SOURCE_ADJUDICATION_COUNT__': source_adjudication_count,
    '__FIRST_GOLD_COVERAGE__': gold_cov(gold_judgment_first), '__FINAL_GOLD_COVERAGE__': gold_cov(gold_judgment_final),
    '__FIRST_GOLD_STRICT__': gold_pct(gold_judgment_first['precision_strict']),
    '__FINAL_GOLD_STRICT__': gold_pct(gold_judgment_final['precision_strict']),
    '__SEL_AGREE__': human_agreement['Selected sample']['agree'], '__SEL_AGREE_N__': human_agreement['Selected sample']['n'],
    '__SEL_AGREE_PCT__': pct(human_agreement['Selected sample']['agree'], human_agreement['Selected sample']['n']),
    '__HOLD_AGREE__': human_agreement['Random holdout']['agree'], '__HOLD_AGREE_N__': human_agreement['Random holdout']['n'],
    '__HOLD_AGREE_PCT__': pct(human_agreement['Random holdout']['agree'], human_agreement['Random holdout']['n']),
    '__HUMAN_AGREE__': agreement_total, '__HUMAN_AGREE_N__': agreement_n,
    '__HUMAN_AGREE_PCT__': pct(agreement_total, agreement_n),
    '__CHECKED__': checked_vendor, '__CATALOG__': catalog_checked, '__CATALOG_LISTED__': catalog_listed,
    '__CATALOG_NOT_LISTED__': catalog_not_listed, '__BUILD__': verdicts.get('documented_build_candidate', 0),
    '__GOLD_SELECTED_APPS__': gold_cohort_scores['Selected sample']['apps'],
    '__GOLD_SELECTED_ANSWERED__': gold_cohort_scores['Selected sample']['answered'],
    '__GOLD_SELECTED_SCOREABLE__': gold_cohort_scores['Selected sample']['scoreable'],
    '__GOLD_SELECTED_COVERAGE__': gold_cohort_scores['Selected sample']['coverage'],
    '__GOLD_SELECTED_STRICT__': gold_cohort_scores['Selected sample']['strict'],
    '__GOLD_SELECTED_HALF__': gold_cohort_scores['Selected sample']['half'],
    '__GOLD_HOLDOUT_APPS__': gold_cohort_scores['Random holdout']['apps'],
    '__GOLD_HOLDOUT_ANSWERED__': gold_cohort_scores['Random holdout']['answered'],
    '__GOLD_HOLDOUT_SCOREABLE__': gold_cohort_scores['Random holdout']['scoreable'],
    '__GOLD_HOLDOUT_COVERAGE__': gold_cohort_scores['Random holdout']['coverage'],
    '__GOLD_HOLDOUT_STRICT__': gold_cohort_scores['Random holdout']['strict'],
    '__GOLD_HOLDOUT_HALF__': gold_cohort_scores['Random holdout']['half'],
    '__REST__': api_types.get('REST', 0), '__GRAPHQL__': api_types.get('GraphQL', 0),
    '__BROAD__': breadth.get('broad', 0), '__MODERATE__': breadth.get('moderate', 0), '__NARROW__': breadth.get('narrow', 0),
    '__MCP_SERVER__': mcp.get('vendor_server', 0), '__MCP_CLIENT__': mcp.get('client_only', 0),
    '__MCP_NO_SERVER__': mcp.get('no_vendor_server_documented', 0), '__MCP_UNKNOWN__': mcp.get('unknown', 0),
    '__EASY_WINS__': easy_win_html, '__MATRIX__': matrix, '__COVERAGE_ROWS__': coverage_rows, '__EXAMPLES__': example_cards,
    '__MOVEMENT__': movement_html,
    '__SELECTED_ANSWERED__': selected['answered'], '__SELECTED_COVERAGE__': pct(selected['answered'], 60),
    '__SELECTED_RATINGS__': ', '.join(f'{key} {value}' for key, value in selected['ratings'].items()),
    '__SELECTED_STRICT__': review_score(selected), '__SELECTED_WEIGHTED__': weighted_score(selected),
    '__SEL_STRICT__': f"{100 * gold['overall']['pass3']['all_six_fields']['precision_strict']:.1f}%",
    '__SEL_HALF__': f"{100 * gold['overall']['pass3']['all_six_fields']['precision_half']:.1f}%",
    '__GOLD_FIXED__': gold_fixed_half(gold['overall']['pass3']['all_six_fields']),
    '__HOLDOUT_ANSWERED__': holdout['answered'], '__HOLDOUT_COVERAGE__': pct(holdout['answered'], 60),
    '__HOLDOUT_RATINGS__': ', '.join(f'{key} {value}' for key, value in holdout['ratings'].items()),
    '__HOLDOUT_STRICT__': review_score(holdout), '__HOLDOUT_WEIGHTED__': weighted_score(holdout),
    '__SDK_LISTED__': sdk_check['listed_claims'], '__SDK_NOT_LISTED__': sdk_check['not_listed_claims'],
    '__SDK_AGREEMENT__': f"{sdk_check['listing_agreement']}/{sdk_check['apps_checked']}",
    '__SDK_TOOLS_COMPARED__': sdk_check['tools_compared'], '__SDK_TOOLS_MATCH__': sdk_check['tools_match'],
}
for key, value in replacements.items():
    page = page.replace(key, str(value))
unreplaced = sorted(set(re.findall(r'__[A-Z_]+__', page)))
assert not unreplaced, f'Unreplaced page placeholders: {unreplaced}'
assert 'synthetic test row' not in page, 'Synthetic fixture must not be published'
Path('index.html').write_text(page, encoding='utf-8')
print('Built index.html from checked_dataset_v4.json')
print('Checked vendor claims', checked_vendor, '/500; catalog', catalog_checked, '/100; documented candidates', verdicts.get('documented_build_candidate', 0))

