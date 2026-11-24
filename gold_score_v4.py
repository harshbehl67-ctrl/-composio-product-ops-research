"""Score three agent passes against the saved AI-labeled gold records.

Workflow this script closes:

  1. ``gold_set_v4.py`` wrote an EMPTY ``gold_template.csv`` (questions + first-party
     links only, no ratings).
  2. ``build_blind_packets.py`` cut frozen excerpts into ``private/full/R###.txt``
     + ``private/raw/R###.json`` packets, one per app x judgment field (R001..R080),
     with every agent-authored phrase redacted.
  3. A separate session reportedly labelled those packets from excerpts only and
     returned ``private/labels_returned.csv``. Its identity and prior-label exposure
     cannot be verified from the saved artifacts.
  4. ``merge_gold_labels.py`` merged them into ``gold_template.csv`` by ``row_id``.
  5. THIS script compares the saved labels and agent answers.

Only four fields are hand-labelled: ``auth``, ``credential_gate``, ``api_surface``,
``official_mcp``. The other two are scored by rule, never by opinion:
``composio_toolkit`` against the Composio catalog snapshot, and ``verdict`` derived
from the four gold fields by ``VERDICT_RULE``.

Per pass and per field it reports coverage over sampled and scoreable rows,
precision (correct / answered) in strict and half-credit form, and a Wilson 95%
interval only for integer-success scores. Every non-correct row is written to ``misses``
with a cause category. Reads ``gold_template.csv``, writes ``gold_ratings_v4.json``.
"""
import collections
import csv
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED_AT = '2026-11-24'

JUDGMENT_FIELDS = ('auth', 'credential_gate', 'api_surface', 'official_mcp')
RULE_FIELDS = ('composio_toolkit', 'verdict')
ALL_FIELDS = JUDGMENT_FIELDS + RULE_FIELDS
PASS_SOURCE = {'pass1': 'data/pass2 (first extraction)',
               'pass2': 'data/pass7 (after re-search)',
               'pass3': 'checked_dataset_v4.json (final)'}
VERDICTS = ('documented_build_candidate', 'gated_build_candidate', 'wrapper_or_cli',
            'partner_outreach', 'unknown')
# flatten() folds '_' to ' ', so match the agent answer on the folded spelling.
VERDICT_SLUGS = {verdict.replace('_', ' '): verdict for verdict in VERDICTS}
Z = 1.959963984540054  # 95%

VERDICT_RULE = (
    'Buildability is derived from the gold fields, not hand-labelled. '
    '1) If gold auth, gold credential_gate, or gold api_surface is not "found", verdict = unknown; '
    'an excerpt that does not discuss credential access cannot prove a paid or gated path. '
    '2) Else if the gold credential text names a partner/sales/contact gate, verdict = partner_outreach. '
    '3) Else if the gold api_surface names only a wrapper or CLI, verdict = wrapper_or_cli. '
    '4) Else if the gold credential text names a self-serve free or trial path AND the gold api breadth '
    'is broad or moderate, verdict = documented_build_candidate. '
    '5) If self-serve is found but breadth is not stated, verdict = unknown; missing breadth is not evidence '
    'of an access gate. '
    '6) Else a paid, approval or partner gate with no self-serve path yields gated_build_candidate; '
    'if the excerpt does not establish one of these outcomes, verdict = unknown.'
)

RUBRIC = {
    'coverage': 'answered / total sampled rows.',
    'scoreable_coverage': (
        'For the four judgment fields, answered / rows with gold_status="found"; '
        'not_stated_in_docs and unresolved rows are gold-unscoreable and excluded. '
        'For the two rule fields, all sampled rows are scoreable by convention: '
        'Composio toolkit status comes from the saved catalog snapshot and verdict is rule-derived.'
    ),
    'precision_strict': 'correct / answered.',
    'precision_half': '(correct + 0.5 * partial) / answered.',
    'interval': 'Wilson 95% interval for integer-success proportions only; no interval is reported for fractional half-credit.',
    'missing': 'abstained = the pass made no claim; unresolved = the gold excerpt did not state the answer.',
    'cause_categories': ['over_inclusive', 'under_inclusive', 'wrong_value', 'missing_api_type',
                         'wrong_api_type', 'breadth_mismatch', 'mcp_server_missed', 'mcp_false_positive',
                         'mcp_tier_mismatch', 'catalog_mismatch', 'verdict_mismatch',
                         'unmappable_answer', 'abstained_on_scoreable', 'gold_unscoreable'],
}


def load_json(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def flatten(value):
    """Any claim value -> one lower-cased string ('_' folded to space)."""
    if value is None:
        return ''
    items = value if isinstance(value, list) else [value]
    return ' '.join(str(item) for item in items).lower().replace('_', ' ')


def is_unknown(value):
    if value is None:
        return True
    items = value if isinstance(value, list) else [value]
    return not any(str(item).strip().lower() not in ('', 'unknown', 'none') for item in items)


# --- canonical label maps ----------------------------------------------------

AUTH_NEEDLES = (
    ('oauth', 'oauth2'),
    ('api key', 'api key / PAT'),
    ('personal access token', 'api key / PAT'),
    ('programmatic access token', 'api key / PAT'),
    ('service key', 'api key / PAT'),
    ('private-app access', 'api key / PAT'),
    ('private-app token', 'api key / PAT'),
    ('api token', 'api key / PAT'),
    ('bot token', 'api key / PAT'),
    ('basic', 'basic'),
    ('jwt', 'JWT-signed'),
    ('key-pair', 'JWT-signed'),
    ('key pair', 'JWT-signed'),
    ('no authentication', 'none'),
)
GATE_NEEDLES = (
    ('self_serve_free', 'self_serve'), ('self serve free', 'self_serve'),
    ('self_serve_trial', 'self_serve'), ('self serve trial', 'self_serve'),
    ('free or trial', 'self_serve'), ('free', 'self_serve'), ('trial', 'self_serve'),
    ('paid plan', 'paid'), ('paid_plan', 'paid'), ('paid', 'paid'), ('subscription', 'paid'),
    ('admin_approval', 'approval'), ('app_review', 'approval'), ('administrator', 'approval'),
    ('admin', 'approval'), ('approval', 'approval'), ('review', 'approval'),
    ('partner', 'partner'), ('sales', 'partner'), ('contact', 'partner'),
)
API_TYPES = ('rest', 'graphql', 'soap', 'grpc', 'websocket')
TYPE_RE = {kind: re.compile(rf'\b{kind}\b', re.I) for kind in API_TYPES}
SDK_RE = re.compile(r'\bsdk\b', re.I)
MCP_SERVER_LABELS = ('hosted with actions', 'read-only/docs', 'local only', 'beta/eap/closed', 'prelaunch')


def auth_buckets(value):
    text = flatten(value)
    return {label for needle, label in AUTH_NEEDLES if needle in text}


def gate_buckets(value):
    text = flatten(value)
    return {label for needle, label in GATE_NEEDLES if needle in text}


def api_parts(value):
    text = flatten(value)
    types = {kind for kind, regex in TYPE_RE.items() if regex.search(text)}
    breadth = next((level for level in ('broad', 'moderate', 'narrow') if level in text), None)
    return types, breadth, bool(SDK_RE.search(text))


def api_negative_types(note):
    """Protocol types explicitly rejected by the saved labeler's excerpt note."""
    text = flatten(note)
    rejected = set()
    for kind, regex in TYPE_RE.items():
        if re.search(rf"\bnot\s+(?:a\s+)?{kind}\b|\bisn't\s+(?:a\s+)?{kind}\b|\bis\s+not\s+(?:a\s+)?{kind}\b", text, re.I):
            rejected.add(kind)
    return rejected


def gold_mcp_server(value):
    text = flatten(value)
    return any(label in text for label in MCP_SERVER_LABELS)


def agent_mcp_server(value):
    text = flatten(value)
    if any(word in text for word in ('no vendor server', 'no_vendor_server', 'client_only', 'client only',
                                     'no server', 'no mcp', ' not documented')):
        return False
    if any(word in text for word in ('vendor_server', 'hosted', 'server', 'yes', 'prelaunch')):
        return True
    return None


# --- graders -----------------------------------------------------------------

def grade_judgment(agent, gold_value, gold_status, field, gold_note=''):
    """Rate one agent answer against the gold truth for a judgment field."""
    if is_unknown(agent):
        return 'abstained'
    if gold_status != 'found' or not gold_value.strip():
        return 'unresolved'
    if field == 'official_mcp':
        have, truth = agent_mcp_server(agent), gold_mcp_server(gold_value)
        if have is None:
            return 'partial'
        return 'correct' if have == truth else 'incorrect'
    if field == 'api_surface':
        agent_types, agent_breadth, agent_sdk = api_parts(agent)
        gold_types, gold_breadth, gold_sdk = api_parts(gold_value)
        if agent_types & api_negative_types(gold_note):
            return 'incorrect'
        dimensions = []
        if gold_types:
            if not agent_types:
                dimensions.append('partial')
            elif not (agent_types & gold_types):
                dimensions.append('incorrect')
            else:
                dimensions.append('correct' if agent_types == gold_types else 'partial')
        if gold_sdk:
            dimensions.append('correct' if agent_sdk else 'partial')
        if gold_breadth:
            dimensions.append('correct' if agent_breadth == gold_breadth else 'partial')
        # The saved gold labels are excerpt-only. Omitted dimensions are unscored, not
        # negative evidence: an excerpt that names an SDK alone does not reject
        # a protocol claim found in another cited first-party source.
        if 'incorrect' in dimensions:
            return 'incorrect'
        if 'partial' in dimensions:
            return 'partial'
        return 'correct' if dimensions else 'partial'
    if field == 'credential_gate':
        agent_gate, gold_gate = gate_buckets(agent), gate_buckets(gold_value)
        if not agent_gate:
            return 'partial'                      # e.g. 'mixed': access conditions we cannot map to the labels
        if agent_gate == gold_gate:
            return 'correct'
        return 'partial' if agent_gate & gold_gate else 'incorrect'
    agent_tokens, gold_tokens = auth_buckets(agent), auth_buckets(gold_value)
    if not agent_tokens:
        return 'partial'                          # answer present, but names no allowed mechanism
    if agent_tokens == gold_tokens:
        return 'correct'
    return 'partial' if agent_tokens & gold_tokens else 'incorrect'


def grade_composio(agent, catalog):
    """Rate the Composio-toolkit claim against the catalog snapshot."""
    if is_unknown(agent):
        return 'abstained'
    if catalog is None:
        return 'unresolved'
    truth_listed = bool(catalog.get('in_composio'))
    text = flatten(agent)
    negative = any(word in text for word in ('not_listed', 'not listed', 'no exact', 'no listing'))
    positive = (not negative) and ('listed' in text or text.strip() == 'yes')
    if positive != truth_listed:
        return 'incorrect'
    if truth_listed:
        agent_exact, agent_alias = 'exact' in text, 'alias' in text
        truth_exact = catalog.get('claim') == 'listed_exact'
        truth_alias = catalog.get('claim') == 'listed_alias'
        if (agent_exact or agent_alias) and (agent_exact != truth_exact or agent_alias != truth_alias):
            return 'partial'
    return 'correct'


def derive_verdict(gold_fields):
    auth = gold_fields.get('auth') or {}
    api = gold_fields.get('api_surface') or {}
    access = gold_fields.get('credential_gate') or {}
    missing = [field for field, row in (('auth', auth), ('credential_gate', access),
                                        ('api_surface', api))
               if (row.get('gold_status') or '') != 'found']
    if missing:
        return 'unknown', f'{", ".join(missing)} not found in the frozen excerpt'
    access_text = flatten(access.get('gold_value'))
    api_text = flatten(api.get('gold_value'))
    if any(word in access_text for word in ('partner', 'sales', 'contact', 'agreement', 'enterprise')):
        return 'partner_outreach', 'access names a partner/sales/agreement gate'
    if 'wrapper' in api_text or 'cli' in api_text:
        return 'wrapper_or_cli', 'documented surface is a wrapper or CLI'
    _, breadth, _ = api_parts(api.get('gold_value'))
    self_serve = any(word in access_text for word in ('self-serve', 'self serve', 'self serve', 'free', 'trial'))
    if self_serve and breadth in ('broad', 'moderate'):
        return 'documented_build_candidate', f'self-serve access with a {breadth} API'
    access_buckets = gate_buckets(access_text)
    if self_serve and breadth is None:
        return 'unknown', 'self-serve access found, but API breadth is not stated'
    if access_buckets & {'paid', 'approval', 'partner'} and not self_serve:
        return 'gated_build_candidate', 'documented API and explicit paid/approval gate with no self-serve path'
    return 'unknown', 'the excerpt does not establish a buildability verdict'


def grade_verdict(agent, derived):
    if is_unknown(agent):
        return 'abstained'
    slug = flatten(agent).strip()
    if slug not in VERDICT_SLUGS:
        return 'abstained'
    if derived == 'unknown':
        return 'unresolved'
    return 'correct' if VERDICT_SLUGS[slug] == derived else 'incorrect'


def cause_category(field, rating, agent, gold_value, gold_status, gold_note=''):
    if rating == 'correct':
        return None
    if rating == 'unresolved':
        return 'gold_unscoreable'
    if rating == 'abstained':
        # An abstention is only a scoring miss when there was a scoreable truth.
        # The three rule/default paths pass a non-'found' sentinel, so treat the
        # truth value itself as the signal there.
        if field == 'verdict':
            return 'gold_unscoreable' if str(gold_value).strip().lower() == 'unknown' else 'abstained_on_scoreable'
        if field == 'composio_toolkit':
            return 'abstained_on_scoreable' if str(gold_value).strip() else 'gold_unscoreable'
        return 'abstained_on_scoreable' if gold_status == 'found' else 'gold_unscoreable'
    if field == 'official_mcp':
        have, truth = agent_mcp_server(agent), gold_mcp_server(gold_value)
        if truth and have is False:
            return 'mcp_server_missed'
        if not truth and have:
            return 'mcp_false_positive'
        return 'mcp_tier_mismatch'
    if field == 'api_surface':
        agent_types, agent_breadth, agent_sdk = api_parts(agent)
        gold_types, gold_breadth, gold_sdk = api_parts(gold_value)
        if agent_types & api_negative_types(gold_note):
            return 'wrong_api_type'
        if not agent_types and not agent_sdk:
            return 'missing_api_type'
        if gold_types and agent_types and not (agent_types & gold_types):
            return 'wrong_api_type'
        if (gold_types - agent_types) or (gold_sdk and not agent_sdk):
            return 'under_inclusive'
        if (agent_types - gold_types) or (agent_sdk and not gold_sdk):
            return 'over_inclusive'
        return 'breadth_mismatch' if (gold_breadth and agent_breadth != gold_breadth) else 'wrong_value'
    if field == 'composio_toolkit':
        return 'catalog_mismatch'
    if field == 'verdict':
        return 'verdict_mismatch'
    if field == 'credential_gate':
        agent_tokens, gold_tokens = gate_buckets(agent), gate_buckets(gold_value)
    else:
        agent_tokens, gold_tokens = auth_buckets(agent), auth_buckets(gold_value)
    if not agent_tokens:
        return 'unmappable_answer'
    if agent_tokens - gold_tokens:
        return 'over_inclusive'
    if gold_tokens - agent_tokens:
        return 'under_inclusive'
    return 'wrong_value'


# --- metrics -----------------------------------------------------------------

def wilson(k, n, z=Z):
    if not n:
        return (None, None)
    p = k / n
    scale = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / scale
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / scale
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def summarise(rows, scoreable_total=None):
    """Summarize with sampled, scoreable, and answered denominators kept distinct."""
    counter = collections.Counter(rows)
    total = len(rows)
    correct = counter.get('correct', 0)
    partial = counter.get('partial', 0)
    incorrect = counter.get('incorrect', 0)
    answered = correct + partial + incorrect
    unresolved = counter.get('unresolved', 0)
    scoreable = total if scoreable_total is None else scoreable_total
    weighted = correct + 0.5 * partial
    strict = correct / answered if answered else None
    half = weighted / answered if answered else None
    return {
        'total': total,
        'scoreable': scoreable,
        'answered': answered,
        'coverage': round(answered / total, 4) if total else None,
        'scoreable_coverage': round(answered / scoreable, 4) if scoreable else None,
        'scoreable_coverage_ci': list(wilson(answered, scoreable)),
        'n': answered,
        'correct': correct, 'partial': partial, 'incorrect': incorrect,
        'abstained': counter.get('abstained', 0), 'unresolved': unresolved,
        'precision_strict': round(strict, 4) if strict is not None else None,
        'strict_ci': list(wilson(correct, answered)),
        'precision_half': round(half, 4) if half is not None else None,
        'fixed_half': round(weighted / total, 4) if total else None,
        'half_ci': None,
    }


# --- data assembly -----------------------------------------------------------

def agent_answers():
    selection = load_json('holdout_selection_v4.json')
    apps = {app['name']: app for app in load_json('apps.json')}
    names = list(selection['selected_sample']) + [item['app'] for item in selection['random_holdout']]
    checked = {row['app']: row for row in load_json('checked_dataset_v4.json')}
    passes = {source: {} for source in PASS_SOURCE}
    for name in names:
        number = apps[name]['number']
        p2 = load_json(f'data/pass2/{number:03}.json')['claims']
        p7 = load_json(f'data/pass7/{number:03}.json')['claims']
        for field in ALL_FIELDS:
            passes['pass1'][(name, field)] = p2[field]['value']
            passes['pass2'][(name, field)] = p7[field]['value']
            passes['pass3'][(name, field)] = checked[name]['fields'][field]['value']
    return passes, names


def load_gold():
    rows = {}
    with (ROOT / 'gold_template.csv').open(encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            rows[(row['app'], row['field'])] = row
    return rows


def validate_gold(gold, names):
    problems = []
    for name in names:
        for field in JUDGMENT_FIELDS:
            row = gold.get((name, field))
            if row is None:
                problems.append(f'{name}/{field}: row missing')
                continue
            status = (row.get('gold_status') or '').strip()
            if status not in ('found', 'not_stated_in_docs', 'unresolved'):
                problems.append(f'{name}/{field}: bad/empty gold_status "{status}"')
            elif status == 'found' and not (row.get('gold_value') or '').strip():
                problems.append(f'{name}/{field}: found but gold_value empty')
    return problems


def row_quality(gold):
    """Count rows whose frozen excerpts could not support a judgment."""
    fetch_failed, off_topic = [], []
    for (app, field), row in gold.items():
        note = (row.get('labeler_note') or '').upper()
        row_id = f'{app}·{field}'
        if 'FETCH_FAILED' in note:
            fetch_failed.append(row_id)
        if 'PAGE_OFF_TOPIC' in note:
            off_topic.append(row_id)
    statuses = collections.Counter((row.get('gold_status') or '').strip() for row in gold.values())
    return {
        'total_rows': len(gold),
        'labeled_found': statuses.get('found', 0),
        'labeled_not_stated_in_docs': statuses.get('not_stated_in_docs', 0),
        'labeled_unresolved': statuses.get('unresolved', 0),
        'fetch_failed': len(fetch_failed), 'fetch_failed_rows': fetch_failed,
        'off_topic': len(off_topic), 'off_topic_rows': off_topic,
    }


def main():
    gold = load_gold()
    passes, names = agent_answers()
    problems = validate_gold(gold, names)
    if problems:
        print(f'gold_template.csv not ready: {len(problems)} problem(s)')
        for item in problems[:12]:
            print('  -', item)
        raise SystemExit('finish labelling gold_template.csv, then rerun.')

    catalog = {rec['app']: rec for rec in load_json('composio_catalog.json')['records']}
    catalog_fetched_at = load_json('composio_catalog.json')['fetched_at']

    per_field = {source: {field: [] for field in ALL_FIELDS} for source in PASS_SOURCE}
    ratings = {source: {} for source in PASS_SOURCE}
    misses = []
    adjudication = []
    derived_verdicts = {}

    for name in names:
        gold_fields = {field: gold[(name, field)] for field in JUDGMENT_FIELDS}
        derived, reason = derive_verdict(gold_fields)
        derived_verdicts[name] = {'verdict': derived, 'reason': reason}
        for source in PASS_SOURCE:
            for field in JUDGMENT_FIELDS:
                row = gold[(name, field)]
                agent = passes[source][(name, field)]
                rating = grade_judgment(agent, row.get('gold_value', ''), (row.get('gold_status') or '').strip(), field,
                                        row.get('labeler_note', ''))
                per_field[source][field].append(rating)
                ratings[source][f'{name}|{field}'] = rating
                if rating != 'correct':
                    misses.append({'pass': source, 'app': name, 'field': field, 'rating': rating,
                                   'agent': agent, 'gold': row.get('gold_value'),
                                   'gold_status': row.get('gold_status'),
                                   'cause': cause_category(field, rating, agent, row.get('gold_value', ''),
                                                           (row.get('gold_status') or '').strip(),
                                                           row.get('labeler_note', '')),
                                   'labeler_note': row.get('labeler_note', '')})
                if rating == 'partial':
                    adjudication.append({'pass': source, 'app': name, 'field': field, 'agent': agent,
                                         'gold': row.get('gold_value'), 'rating': rating,
                                         'note': row.get('labeler_note', '')})
            agent = passes[source][(name, 'composio_toolkit')]
            rating = grade_composio(agent, catalog.get(name))
            per_field[source]['composio_toolkit'].append(rating)
            ratings[source][f'{name}|composio_toolkit'] = rating
            if rating != 'correct':
                misses.append({'pass': source, 'app': name, 'field': 'composio_toolkit', 'rating': rating,
                               'agent': agent, 'gold': (catalog.get(name) or {}).get('claim'),
                               'gold_status': 'catalog', 'cause': cause_category('composio_toolkit', rating, agent, '', 'catalog'),
                               'labeler_note': 'Composio catalog snapshot'})
            if rating == 'partial':
                adjudication.append({'pass': source, 'app': name, 'field': 'composio_toolkit', 'agent': agent,
                                     'gold': (catalog.get(name) or {}).get('claim'), 'rating': rating,
                                     'note': 'catalog snapshot'})
            agent = passes[source][(name, 'verdict')]
            rating = grade_verdict(agent, derived)
            per_field[source]['verdict'].append(rating)
            ratings[source][f'{name}|verdict'] = rating
            if rating != 'correct':
                misses.append({'pass': source, 'app': name, 'field': 'verdict', 'rating': rating,
                               'agent': agent, 'gold': derived, 'gold_status': 'derived',
                               'cause': cause_category('verdict', rating, agent, derived, 'derived'),
                               'labeler_note': reason})
            if rating == 'partial':
                adjudication.append({'pass': source, 'app': name, 'field': 'verdict', 'agent': agent,
                                     'gold': derived, 'rating': rating, 'note': reason})

    scoreable_by_field = {
        field: (sum(gold[(name, field)].get('gold_status') == 'found' for name in names)
                if field in JUDGMENT_FIELDS else len(names))
        for field in ALL_FIELDS
    }
    scores = {source: {
        field: summarise(rows, scoreable_by_field[field])
        for field, rows in table.items()
    } for source, table in per_field.items()}
    overall = {}
    for source, table in per_field.items():
        judgment = [rating for field in JUDGMENT_FIELDS for rating in table[field]]
        everything = [rating for field in ALL_FIELDS for rating in table[field]]
        judgment_scoreable = sum(scoreable_by_field[field] for field in JUDGMENT_FIELDS)
        all_scoreable = judgment_scoreable + sum(scoreable_by_field[field] for field in RULE_FIELDS)
        overall[source] = {
            'judgment_fields': summarise(judgment, judgment_scoreable),
            'all_six_fields': summarise(everything, all_scoreable),
        }

    miss_causes = collections.Counter((m['field'], m['cause']) for m in misses)

    out = {
        'generated_at': GENERATED_AT,
        'label_source': 'gold_template.csv; AI labeler/session identity not recorded',
        'label_provenance': load_json('gold_provenance_v1.json'),
        'disclosure': (
            'The saved project record attributes these labels to a separate AI session using frozen page excerpts. '
            'The model and session identities were not recorded. The record says agent answers were not shown, '
            'but this was not independently verified; exclusion of earlier chat labels is also unverified. '
            'Coverage is reported separately over all sampled and scoreable rows. Gold-unscoreable rows remain '
            'distinct from agent abstentions on scoreable rows.'
        ),
        'row_quality': row_quality(gold),
        'apps': len(names),
        'pass_sources': PASS_SOURCE,
        'judgment_fields': list(JUDGMENT_FIELDS),
        'rule_scored_fields': {
            'composio_toolkit': f'compared to composio_catalog.json (fetched_at {catalog_fetched_at})',
            'verdict': VERDICT_RULE,
        },
        'composio_catalog_fetched_at': catalog_fetched_at,
        'rubric': RUBRIC,
        'per_field': {source: {field: scores[source][field] for field in ALL_FIELDS} for source in PASS_SOURCE},
        'ratings': ratings,
        'overall': overall,
        'derived_verdicts': derived_verdicts,
        'misses': misses,
        'miss_causes': {f'{field}:{cause}': count for (field, cause), count in sorted(miss_causes.items())},
        'adjudication_queue': adjudication,
    }
    (ROOT / 'gold_ratings_v4.json').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

    quality = out['row_quality']
    print('gold_ratings_v4.json written')
    print(f"  rows {quality['total_rows']}: found {quality['labeled_found']}, "
          f"not_stated {quality['labeled_not_stated_in_docs']}, unresolved {quality['labeled_unresolved']}")
    print(f"  FETCH_FAILED {quality['fetch_failed']} ({', '.join(quality['fetch_failed_rows']) or '-'}); "
          f"off-topic {quality['off_topic']} ({', '.join(quality['off_topic_rows']) or '-'})")
    for source in PASS_SOURCE:
        view = overall[source]['all_six_fields']
        strict_ci = view['strict_ci']
        print(f"  {source}: coverage {view['answered']}/{view['total']} sampled "
              f"({100*view['coverage']:.1f}%), {view['answered']}/{view['scoreable']} scoreable "
              f"({100*view['scoreable_coverage']:.1f}%); strict {100*view['precision_strict']:.1f}% "
              f"[{100*strict_ci[0]:.1f}-{100*strict_ci[1]:.1f}%]; half {100*view['precision_half']:.1f}%; "
              f"fixed-half {100*view['fixed_half']:.1f}%; n={view['n']}")
    print(f"  misses {len(misses)}; adjudication queue {len(adjudication)}")


if __name__ == '__main__':
    main()
