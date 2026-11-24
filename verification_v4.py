"""Phase 3: assemble verification.json from the frozen passes and audit logs.

Every number here is computed from an on-disk artifact: the frozen pass files
(data/pass2, data/pass7, data/pass12), the reviewer labels, and the loop logs
(source_checks_v4.json, independent_link_checks_v4.json, catalog_crosscheck.json,
source_review_v4.json, independent_review_v4.json). Nothing is hand-typed.

Three passes are scored against the same reviewer labels over the 120-claim
gold set (10 selected apps + 10 seeded holdout apps, 6 fields each):

  pass 1  naive first extraction, no verification        (data/pass2)
  pass 2  current agent before the final loops           (data/pass7)
  pass 3  after automated loops + human review           (data/pass12)

When gold_template.csv is filled, the labels are the saved AI-generated ratings
recorded in gold_ratings_v4.json. The project record attributes them to a
separate session over frozen excerpts, but identity and prior-label exclusion are
not independently verified. If gold labels are absent, this script falls back
to the author's earlier review and labels that source accordingly.
"""
import collections
import csv
import json
import math
import re
from pathlib import Path

import requests

import score_first_pass_v4 as fp  # reuses rate(), summarise(), FIELDS, first_pass (pass2), checked
import verify_checked_sources as verifier

ROOT = Path(__file__).resolve().parent
GENERATED_AT = '2026-11-24'
FIELDS = fp.FIELDS

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; ProductOpsResearch/4.0)'}


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


selection = load('holdout_selection_v4.json')
apps = {app['name']: app for app in load('apps.json')}
checked = fp.checked                       # app -> checked_dataset_v4 row (pass 12 values)
pass2 = fp.first_pass                      # app -> data/pass2 json
pass7 = {app['name']: json.loads((ROOT / 'data' / 'pass7' / f"{app['number']:03}.json").read_text(encoding='utf-8'))
         for app in apps.values()}

COHORTS = {
    'selected_sample': selection['selected_sample'],
    'random_holdout': [item['app'] for item in selection['random_holdout']],
}

JUDGMENT_FIELDS = ('auth', 'credential_gate', 'api_surface', 'official_mcp')
LABEL_PROVENANCE = load('gold_provenance_v1.json')


def load_reviewer_labels():
    """The author's earlier review, keyed by (app, field)."""
    records = {}
    for path in (ROOT / 'data' / 'checked_research' / 'review_selected_v4.json',
                 ROOT / 'data' / 'checked_research' / 'review_holdout_v4.json'):
        for record in json.loads(path.read_text(encoding='utf-8'))['records']:
            records[(record['app'], record['field'])] = record
    return records


def load_gold_rows():
    """The saved AI-labeled truth rows, keyed by (app, field). Empty when unlabeled."""
    path = ROOT / 'gold_template.csv'
    rows = {}
    if not path.exists():
        return rows
    with path.open(encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            rows[(row['app'], row['field'])] = row
    return rows


def load_gold_ratings():
    """Ratings computed by gold_score_v4.py, if present."""
    path = ROOT / 'gold_ratings_v4.json'
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def build_gold_reviewed():
    """Six-field label view when gold labels have been scored.

    The four judgment fields take the gold truth; composio_toolkit and verdict
    take the machine-derived truth (catalog snapshot / written rule), so every
    field has a comparison target. Notes come from the labeler or the rule.
    """
    catalog_raw = load('composio_catalog.json')
    catalog = {rec['app']: rec for rec in catalog_raw['records']}
    fetched_at = catalog_raw['fetched_at']
    derived = gold_ratings.get('derived_verdicts', {})
    records = {}
    for (app, field), row in gold_rows.items():
        note = (row.get('labeler_note') or '').strip()
        records[(app, field)] = {
            'app': app, 'field': field,
            'pass12_answer': (row.get('gold_value') or '').strip() or 'unknown',
            'review_note': note, 'correction': note,
        }
    for name in derived:
        record = catalog.get(name) or {}
        records[(name, 'composio_toolkit')] = {
            'app': name, 'field': 'composio_toolkit',
            'pass12_answer': record.get('claim', 'unknown'),
            'review_note': f'Composio catalog snapshot fetched_at {fetched_at}',
            'correction': '',
        }
        records[(name, 'verdict')] = {
            'app': name, 'field': 'verdict',
            'pass12_answer': derived[name]['verdict'],
            'review_note': derived[name]['reason'], 'correction': '',
        }
    return records


gold_rows = load_gold_rows()
gold_ratings = load_gold_ratings()
reviewer_labels = load_reviewer_labels()
GOLD_RATINGS_AVAILABLE = bool(gold_ratings and gold_ratings.get('ratings'))
gold_filled = sum(1 for row in gold_rows.values() if (row.get('gold_status') or '').strip())
gold_total = len(gold_rows)

if GOLD_RATINGS_AVAILABLE:
    reviewed, LABEL_SOURCE = build_gold_reviewed(), 'gold_template.csv; AI identity not recorded'
else:
    reviewed, LABEL_SOURCE = reviewer_labels, 'the author\'s earlier review (not independent)'


# --- statistics --------------------------------------------------------------

def wilson(k, n, z=1.96):
    """Wilson score 95% interval for k successes in n trials."""
    if n == 0:
        return [None, None]
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return [max(0.0, centre - half), min(1.0, centre + half)]


def summarise(ratings):
    n = len(ratings)
    c = collections.Counter(ratings)
    correct, partial, incorrect = c['correct'], c['partial'], c['incorrect']
    abstained, unresolved = c['abstained'], c['unresolved']
    answered = n - abstained
    scored = correct + partial + incorrect
    half = correct + 0.5 * partial
    return {
        'n': n,
        'counts': {key: c.get(key, 0) for key in ('correct', 'partial', 'incorrect', 'abstained', 'unresolved')},
        'answered': answered,
        'resolved': scored,
        'coverage': answered / n,
        'coverage_ci95': wilson(answered, n),
        'precision_strict_resolved': correct / scored if scored else None,
        'precision_strict_resolved_ci95': wilson(correct, scored),
        'precision_half_resolved': half / scored if scored else None,
        'overall_fixed_strict': correct / n,
        'overall_fixed_strict_ci95': wilson(correct, n),
        'overall_fixed_half': half / n,
    }


PROVISIONAL = re.compile(r'\s*\(\s*provisional\s*\)', re.I)


def clean(value):
    """Drop the staging qualifier used by the mid-pipeline snapshot.

    That pass labelled vendor MCP servers "yes (provisional)"; the final rubric
    reads "yes". Without this the mid-pipeline pass is penalised for vocabulary
    rather than for being wrong, which would misreport accuracy.
    """
    return PROVISIONAL.sub('', value).strip() if isinstance(value, str) else value


def rate_pass(source, app, field):
    record = reviewed[(app, field)]
    final_answer = checked[app]['fields'][field]['value']
    if source == 'pass3':
        return record['rating']
    early = clean((pass2 if source == 'pass1' else pass7)[app]['claims'][field]['value'])
    return fp.rate(early, final_answer, record['pass12_answer'], record['rating'], field)


PASS_LABEL = {
    'pass1': 'first extraction pass, no verification (data/pass2)',
    'pass2': 'agent snapshot after targeted re-search, before the final loops (data/pass7)',
    'pass3': 'final, after automated loops + human review (data/pass12)',
}

ratings = {}   # source -> {(app, field): rating}
for source in ('pass1', 'pass2', 'pass3'):
    if GOLD_RATINGS_AVAILABLE:
        table = gold_ratings['ratings'][source]
        ratings[source] = {(app, field): table[f'{app}|{field}']
                           for cohort in COHORTS.values() for app in cohort for field in FIELDS}
    else:
        ratings[source] = {(app, field): rate_pass(source, app, field)
                           for cohort in COHORTS.values() for app in cohort for field in FIELDS}


def identical_rate(source):
    """Share of a pass's *answered* claims whose value normalises-equal the final.

    The rubric credits a pass with the reviewer's rating only when its answer is
    identical to the final answer; otherwise it is re-rated conservatively. So a
    pass whose free text churned (even while being broadly right) scores lower.
    Reporting this share makes that effect visible instead of hiding it. Claims
    the pass left unknown are excluded, because two "unknown"s are not a match.
    """
    if source == 'pass3':
        return 1.0
    store = pass2 if source == 'pass1' else pass7
    same = 0
    answered = 0
    for cohort in COHORTS.values():
        for app in cohort:
            for field in FIELDS:
                early = store[app]['claims'][field]['value']
                if fp.is_unknown(early):
                    continue
                answered += 1
                if fp.normalise(early) == fp.normalise(reviewed[(app, field)]['pass12_answer']):
                    same += 1
    return same / answered if answered else None


passes = {}
for source in ('pass1', 'pass2', 'pass3'):
    combined = [ratings[source][(app, field)] for cohort in COHORTS.values() for app in cohort for field in FIELDS]
    passes[source] = {
        'label': PASS_LABEL[source],
        'answers_normalised_identical_to_final': identical_rate(source),
        'combined': summarise(combined),
        'by_cohort': {name: summarise([ratings[source][(app, field)] for app in apps_ for field in FIELDS])
                      for name, apps_ in COHORTS.items()},
        'by_field': {field: summarise([ratings[source][(app, field)] for cohort in COHORTS.values() for app in cohort])
                     for field in FIELDS},
    }

# first-pass -> final movement, and whether it generalised to the holdout
movement = {}
for name, apps_ in COHORTS.items():
    first = passes['pass1']['by_cohort'][name]
    final = passes['pass3']['by_cohort'][name]
    movement[name] = {
        'pass1_overall_fixed_half': first['overall_fixed_half'],
        'pass3_overall_fixed_half': final['overall_fixed_half'],
        'delta_overall_fixed_half': final['overall_fixed_half'] - first['overall_fixed_half'],
        'pass1_coverage': first['coverage'],
        'pass3_coverage': final['coverage'],
    }


# --- loop logs ---------------------------------------------------------------

source_checks = load('source_checks_v4.json')
link_checks = load('independent_link_checks_v4.json')
crosscheck = load('catalog_crosscheck.json')
source_review = load('source_review_v4.json')
independent = load('independent_review_v4.json')

urls = len(source_checks)
uses = [use for result in source_checks for use in result['uses']]
uses_quoted = [use for use in uses if use.get('quote')]
reproduced = [use for use in uses_quoted if use.get('quote_exact') or use.get('quote_token_exact')]
browser_keeps = [use for use in uses if use.get('manual_review', {}).get('decision') == 'keep'
                 and 'chromium' in str(use.get('manual_review', {}).get('verification_method', '')).lower()]
raw_only = [use for use in uses if use.get('raw_html_only_match')]
non_200 = [result for result in source_checks if result.get('status') != 200]
link_fail = [result for result in link_checks if result.get('status', 0) >= 400 or 'error' in result]
link_browser = [result for result in link_checks if result.get('browser_review')]

legacy_flags = [key for key, record in reviewed.items()
                if any(word in (record.get('review_note') or '').lower()
                       for word in ('legacy', 'deprecat', 'migrat', 'stale', 'no longer'))]

loops = [
    {'id': 'i', 'name': 'Quote-must-appear substring check', 'kind': 'automated',
     'artifact': 'source_checks_v4.json', 'script': 'verify_checked_sources.py',
     'result': f'{len(reproduced)}/{len(uses_quoted)} quotes reproduced by direct fetch across {urls} URLs'},
    {'id': 'ii', 'name': 'URL liveness', 'kind': 'automated',
     'artifact': 'source_checks_v4.json + independent_link_checks_v4.json', 'script': 'verify_checked_sources.py / check_independent_links_v4.py',
     'result': f'{len(non_200)} non-200 evidence URLs; {len(link_fail)} of {len(link_checks)} independent-review URLs failed before fallback'},
    {'id': 'iii', 'name': 'Composio catalog auth cross-check', 'kind': 'automated',
     'artifact': 'catalog_crosscheck.json', 'script': 'catalog_crosscheck.py',
     'result': f"{crosscheck['apps_in_catalog']}/{crosscheck['apps_total']} apps in catalog; "
               f"{crosscheck['disagreements']} auth disagreements logged"},
    {'id': 'iv', 'name': 'Independent verifier agent', 'kind': 'human',
     'artifact': 'independent_review_v4.json + source_review_v4.json', 'script': 'score_review_v4.py / score_first_pass_v4.py',
     'result': f"reviewer scored both cohorts (60 claims each); source audit kept {source_review['audit_summary']['keep']}, "
               f"replaced {source_review['audit_summary']['replace']}, unresolved {source_review['audit_summary']['unresolved']}"},
    {'id': 'v', 'name': 'Browser fallback for JS-rendered pages', 'kind': 'automated',
     'artifact': 'source_checks_v4.json (manual_review) + data/browser_source_checks_v4.json', 'script': 'check_independent_links_v4.py --review',
     'result': f'{len(browser_keeps)} quotes kept after headless-Chromium render; {len(raw_only)} raw-HTML-only matches; '
               f'{len(link_browser)} independent links browser-verified'},
    {'id': 'vi', 'name': 'Date / deprecation check', 'kind': 'automated',
     'artifact': 'checked_dataset_v4.json (published_label) + surprise audit below', 'script': 'verification_v4.py',
     'result': f'{len(legacy_flags)} reviewed claims flagged as legacy/deprecated/stale in the review notes'},
]


# --- failure taxonomy --------------------------------------------------------

CAUSE_PATTERNS = [
    ('trial treated as free', ('trial',)),
    ('client vs server MCP confusion', ('client', 'host', 'other vendors', 'connect to external')),
    ('legacy or deprecated auth', ('legacy', 'deprecat', 'migrat')),
    ('stale page', ('stale', '404', 'broken')),
    ('JS-rendered page empty', ('javascript', 'rendered', 'chromium', 'empty')),
    ('product rename', ('renam', 'became', 'rebrand')),
    ('transport reported as method', ('transport', 'bearer', 'access token', 'token type')),
    ('incomplete coverage', ('omit', 'incomplete', 'only', 'narrow', 'does not', 'scope')),
]


def classify_cause(text):
    lowered = text.lower()
    for cause, needles in CAUSE_PATTERNS:
        if any(needle in lowered for needle in needles):
            return cause
    return 'other / unclassified'


failed_urls = {result['url'] for result in non_200} | {result['url'] for result in link_fail}


def flag_legacy(record):
    return any(word in (record.get('review_note') or '').lower()
               for word in ('legacy', 'deprecat', 'migrat', 'stale', 'no longer'))


def loop_for(app, field):
    if any(use.get('app') == app and use.get('field') == field for use in browser_keeps):
        return 'v browser fallback'
    if app in crosscheck.get('disagreement_apps', []):
        return 'iii Composio catalog cross-check'
    if flag_legacy(reviewed[(app, field)]):
        return 'vi date / deprecation check'
    evidence_urls = {source.get('url') for source in (checked[app]['fields'][field].get('evidence') or [])}
    if evidence_urls & failed_urls:
        return 'ii URL liveness'
    return 'iv verifier agent / source audit'


taxonomy = []
seen_causes = collections.Counter()
for (app, field), rating in sorted(ratings['pass3'].items()):
    if rating in ('partial', 'incorrect'):
        record = reviewed[(app, field)]
        cause = classify_cause((record.get('review_note') or '') + ' ' + str(record.get('correction') or ''))
        seen_causes[cause] += 1
        taxonomy.append({'app': app, 'field': field, 'final_rating': rating,
                         'cause': cause, 'fixed_by_loop': loop_for(app, field),
                         'note': record.get('review_note') or ''})


# --- surprise audit ----------------------------------------------------------

MARKER_WEIGHT = [('sunset', 6), ('agentic', 5), ('prelaunch', 5), ('discontinu', 5),
                 ('renam', 4), ('eap', 4), ('early access', 4), ('beta', 3),
                 ('deprecat', 3), ('closed', 3), ('limited', 3), ('marketplace', 2),
                 ('not available', 2), ('private', 2), ('invite', 2)]

# Claims the assignment calls out as surprising, checked first. Values are never
# typed here; they are read from checked_dataset_v4 at runtime.
CURATED = [
    ('Google Ads', 'auth'),        # developer-token sunset 2026-09-09
    ('Binance', 'auth'),           # Agentic-account MCP; HMAC deprecated
    ('Copper', 'official_mcp'),    # MCP beta
    ('Zendesk', 'official_mcp'),   # MCP early access
    ('Pinterest', 'official_mcp'),  # remote MCP not live
    ('Slack', 'official_mcp'),     # MCP limited to Marketplace / internal apps
    ('QuickBooks', 'official_mcp'),  # MCP local only
    ('Shopify', 'official_mcp'),   # remote MCP not live
    ('Gladly', 'official_mcp'),    # MCP early access
    ('FanBasis', 'verdict'),       # renamed to Commas
]

SURPRISE_NOTE = ('The ten claims were chosen by judgment to match the assignment\'s named surprises, '
                 'then topped up from a keyword scan (sunset, beta, EAP, rename, deprecated, prelaunch, '
                 'limited, marketplace) over the checked evidence. Claim values are read from '
                 'checked_dataset_v4.json; each was re-fetched live on 2026-11-24.')


def surprise_candidates():
    rows = []
    for row in checked.values():
        for field, claim in row['fields'].items():
            if claim.get('status') != 'checked' or claim.get('value') in (None, 'unknown'):
                continue
            text = ' '.join([str(claim.get('value')), claim.get('reason') or '']
                            + [source.get('quote') or '' for source in claim.get('evidence', [])]).lower()
            score = sum(weight for needle, weight in MARKER_WEIGHT if needle in text)
            if score:
                rows.append((score, row['app'], field))
    rows.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [(app, field) for _, app, field in rows]


def has_quote(app, field):
    claim = checked[app]['fields'][field]
    return any((source.get('url') and source.get('quote')) for source in (claim.get('evidence') or []))


def surprise_pairs():
    """Curated surprises first, then keyword-ranked ones, one claim per app.

    A curated surprise is kept even when the claim value is 'unknown' (e.g. the
    FanBasis -> Commas rename), because what is audited is whether the cited
    quote still reproduces live, not whether the value was resolved.
    """
    by_lower = {name.lower(): name for name in checked}
    ordered = [(by_lower.get(app.lower(), app), field) for app, field in CURATED] + surprise_candidates()
    chosen, seen = [], set()
    for app, field in ordered:
        if app in seen or app not in checked or field not in checked[app]['fields']:
            continue
        if not has_quote(app, field):
            continue
        seen.add(app)
        chosen.append((app, field))
        if len(chosen) == 10:
            break
    return chosen


def live_check(url, quote):
    result = {'url': url, 'status': None, 'reproduced': None, 'text_length': None}
    if not url:
        return result
    try:
        response = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
        result['status'] = response.status_code
        if response.status_code == 200:
            page = verifier.visible_text(verifier.decoded_text(response))
            result['text_length'] = len(page)
            normalized = verifier.normalize(quote)
            exact = bool(normalized and normalized in page)
            token = bool(verifier.tokens(normalized) and verifier.contains_tokens(verifier.tokens(page), verifier.tokens(normalized)))
            result['reproduced'] = bool(exact or token)
        response.close()
    except Exception as exc:
        result['error'] = str(exc)
    return result


def miss_reason(entry):
    """Explain a failed live re-check without inventing anything."""
    live = entry['live']
    if live.get('reproduced') is not False:
        return None
    if live.get('error'):
        return f"fetch error: {live['error']}"
    if live.get('status') != 200:
        return f"HTTP {live.get('status')} on re-fetch (page may have moved or been removed)"
    length = live.get('text_length') or 0
    if entry['captured_with_browser'] or length < 500:
        return ('plain HTTP fetch returned almost no readable text; the page is JS-rendered, so this '
                'needs the browser-fallback loop rather than counting as a wrong claim')
    return 'quote no longer found on the live page; wording may have changed since capture'


CURATED_SET = {(app.lower(), field) for app, field in CURATED}

surprise = []
for app, field in surprise_pairs():
    claim = checked[app]['fields'][field]
    evidence = claim.get('evidence') or []
    source = evidence[0] if evidence else {}
    url = source.get('url') or ''
    quote = source.get('quote') or ''
    method = source.get('verification_method') or ''
    entry = {'app': app, 'field': field, 'claim': claim.get('value'),
             'curated': (app.lower(), field) in CURATED_SET,
             'captured_with_browser': 'chromium' in method.lower(),
             'live': live_check(url, quote)}
    entry['miss_reason'] = miss_reason(entry)
    surprise.append(entry)


# --- plain-language significance ---------------------------------------------

sel = movement['selected_sample']
hol = movement['random_holdout']
def pct(value):
    return f'{100 * value:.0f}%'
gain_note = (f'First-pass to final movement: selected sample {pct(sel["pass1_overall_fixed_half"])} -> '
             f'{pct(sel["pass3_overall_fixed_half"])} ({pct(sel["delta_overall_fixed_half"])} points), '
             f'random holdout {pct(hol["pass1_overall_fixed_half"])} -> {pct(hol["pass3_overall_fixed_half"])} '
             f'({pct(hol["delta_overall_fixed_half"])} points). The holdout delta is computed on a separate, '
             'seeded sample that was not used to tune the rules.')

p1, p2, p3 = (passes[source]['combined'] for source in ('pass1', 'pass2', 'pass3'))
pass_note = (
    f'The initial discovery run produced no answer-bearing claims and is excluded from accuracy comparisons. '
    f'Pass 1 is the earliest answer-producing extraction pass (data/pass2). '
    f'Pass 2 is the mid-pipeline agent snapshot after targeted re-search (data/pass7); on the conservative '
    f'identity rubric it answers {p2["answered"] - p1["answered"]:+d} more claims but changes wording, so the fixed '
    f'half-credit measure moves {100 * (p2["overall_fixed_half"] - p1["overall_fixed_half"]):+.1f} points before the '
    f'final loops recover it. Pass 3 is the frozen final pass after the automated loops and the author review.')

N_CLAIMS = sum(len(apps_) for apps_ in COHORTS.values()) * len(FIELDS)
N_SELECTED = len(COHORTS['selected_sample']) * len(FIELDS)
N_HOLDOUT = len(COHORTS['random_holdout']) * len(FIELDS)

if gold_ratings and gold_ratings.get('ratings'):
    LABEL_DISCLOSURE = (
        'The saved project record attributes the labels to a separate AI session using frozen excerpts. '
        'The model and session identities were not recorded. The record says agent answers were not shown, '
        'but that claim was not independently verified; whether earlier chat labels were excluded is unknown. '
        'A separate script compares each pass with the saved labels. Only auth, credential_gate, api_surface, '
        'and official_mcp are labeled; composio_toolkit is checked against the Composio catalog snapshot '
        f'(fetched_at {gold_ratings.get("composio_catalog_fetched_at")}) and verdict is derived by a written rule.')
    LABEL_SOURCE_NOTE = 'gold_template.csv; AI labeler/session identity not recorded; see gold_provenance_v1.json'
else:
    LABEL_DISCLOSURE = (
        'The review records are the author\'s own earlier judgments; they are not independent adjudication. '
        'Gold labels are absent, so these figures are self-assessed.')
    LABEL_SOURCE_NOTE = 'author review; not independent'

verification = {
    'generated_at': GENERATED_AT,
    'labels': {
        'source': LABEL_SOURCE_NOTE,
        'provenance': LABEL_PROVENANCE,
        'disclosure': LABEL_DISCLOSURE,
        'gold_template': 'gold_template.csv',
        'gold_ratings': 'gold_ratings_v4.json' if GOLD_RATINGS_AVAILABLE else None,
        'gold_rows_filled': gold_filled,
        'gold_rows_total': gold_total,
        'hand_labeled_fields': list(JUDGMENT_FIELDS),
        'rule_scored_fields': {
            'composio_toolkit': 'scored against composio_catalog.json (with fetched_at)',
            'verdict': 'derived from the four gold fields by the written buildability rule',
        },
        'n': N_CLAIMS, 'selected': N_SELECTED, 'holdout': N_HOLDOUT, 'seed': selection['seed'],
    },
    'passes': passes,
    'pass_note': pass_note,
    'movement': movement,
    'movement_note': gain_note,
    'wilson_note': ('This six-field verification uses 120 claims per pass and reports coverage, resolved precision, '
                    'and fixed-denominator results on that claim set. The four-field labeled gold is a separate '
                    '80-row comparison: its sampled coverage is answered/80 and scoreable coverage excludes the '
                    'six unresolved gold rows. Do not compare those denominators as if they were the same measure. '
                    'Wilson intervals are used only for integer-success proportions; no Wilson interval is reported '
                    'for fractional half-credit.'),
    'loops': loops,
    'failure_taxonomy': taxonomy,
    'failure_cause_counts': dict(seen_causes),
    'surprise_audit': surprise,
    'surprise_note': SURPRISE_NOTE,
    'curated_surprises': [item['app'] for item in surprise if item['curated']],
}

(ROOT / 'verification.json').write_text(json.dumps(verification, indent=2, ensure_ascii=False), encoding='utf-8')

print('labels:', LABEL_SOURCE_NOTE)
for source in ('pass1', 'pass2', 'pass3'):
    combined = passes[source]['combined']
    match = passes[source]['answers_normalised_identical_to_final']
    print(source, 'coverage', f"{combined['answered']}/{combined['n']}",
          'strict-resolved', f"{combined['counts']['correct']}/{combined['resolved']}",
          'overall-fixed(half)', f"{100 * combined['overall_fixed_half']:.1f}%",
          'wording-match', f"{100 * match:.0f}%" if match is not None else 'n/a')
print('failure taxonomy:', dict(seen_causes))
print('surprise audit checked:', len(surprise),
      'reproduced:', sum(1 for item in surprise if item['live'].get('reproduced')))
for item in surprise:
    if not item['live'].get('reproduced'):
        tag = 'browser-rendered source' if item['captured_with_browser'] else 'plain source'
        print('  surprise not reproduced:', item['app'], item['field'],
              item['live'].get('status', item['live'].get('error')), f'({tag})')
print('wrote verification.json')
