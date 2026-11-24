"""Score the first extraction pass (data/pass2) against the frozen verified pass.

The final pass (pass 12) is already scored by the independent review in
review_selected_v4.json and review_holdout_v4.json. To show how accuracy moved
from a lower first pass to a higher final one, the first pass is rated with the
same rubric, anchored on the frozen reviewed answer:

* ``unknown`` in the first pass -> ``abstained`` (no claim to score).
* first-pass answer identical to the reviewed pass-12 answer (after synonym
  normalisation) -> inherit the reviewed rating, because the answer is identical.
* first-pass answer changed -> re-rate it against the checked final answer:
  - ``official_mcp``: a first-pass "yes" is credited only where the checked answer
    is a vendor-operated server, otherwise it is a false positive.
  - ``composio_toolkit``: "listed" is credited only where a listed answer is checked.
  - list/text fields: a narrower or overlapping answer is ``partial``; a disjoint
    answer is ``incorrect``.

Two views are reported for each pass, over the same fixed 60-claim sample:

* ``strict_answered`` / ``weighted_answered``: accuracy among claims the pass
  answered (the denominator the reviewer uses).
* ``fixed_strict`` / ``fixed_weighted``: accuracy across all 60 sampled claims,
  where an unresolved/abstained claim scores zero. This view is immune to the
  survivorship effect that makes a pass look better when it answers only the easy
  claims, and it is the measure used to show first-pass -> final movement.
"""
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')
SELECTED_REVIEW = ROOT / 'data' / 'checked_research' / 'review_selected_v4.json'
HOLDOUT_REVIEW = ROOT / 'data' / 'checked_research' / 'review_holdout_v4.json'
selection = json.loads((ROOT / 'holdout_selection_v4.json').read_text(encoding='utf-8'))
apps = {app['name']: app for app in json.loads((ROOT / 'apps.json').read_text(encoding='utf-8'))}
first_pass = {app['name']: json.loads((ROOT / 'data' / 'pass2' / f"{app['number']:03}.json").read_text(encoding='utf-8'))
              for app in apps.values()}
checked = {row['app']: row for row in json.loads((ROOT / 'checked_dataset_v4.json').read_text(encoding='utf-8'))}

# --- value normalisation -----------------------------------------------------

METHODS = (
    ('oauth', 'OAuth 2.0'),
    ('api key', 'API key'),
    ('x-api-key', 'API key'),
    ('key id', 'API key'),
    ('api token', 'Access token'),
    ('access token', 'Access token'),
    ('bearer', 'Bearer token'),
    ('basic', 'Basic authentication'),
    ('session', 'Session authentication'),
    ('no authentication', 'No authentication'),
)


def normalise(value):
    """Return a comparable, order-independent token set for any claim value."""
    if value is None:
        return set()
    items = value if isinstance(value, list) else [value]
    tokens = set()
    for item in items:
        lowered = str(item).strip().lower()
        if not lowered or lowered == 'unknown':
            continue
        matched = False
        for needle, label in METHODS:
            if needle in lowered:
                tokens.add(label)
                matched = True
        if not matched:
            tokens.add(lowered)
    return tokens


def api_parts(value):
    text = ' '.join(str(item) for item in (value if isinstance(value, list) else [value])) if value else ''
    lowered = text.lower()
    types = {kind for kind in ('rest', 'graphql', 'soap', 'grpc', 'websocket', 'http') if kind in lowered}
    breadth = next((level for level in ('broad', 'moderate', 'narrow') if level in lowered), None)
    return types, breadth


def is_unknown(value):
    return value is None or value == 'unknown' or (isinstance(value, list) and not any(v != 'unknown' for v in value))


def rate(early, final_answer, reviewed_answer, reviewed_rating, field):
    """Rate a first-pass answer against the frozen reviewed pass-12 answer."""
    if is_unknown(early):
        return 'abstained'
    if normalise(early) == normalise(reviewed_answer):
        return reviewed_rating
    if field == 'official_mcp':
        claims_server = any('server' in token or token == 'yes' for token in normalise(early))
        truth_is_server = final_answer == 'vendor_server'
        return 'correct' if (claims_server and truth_is_server) else 'incorrect'
    if field == 'composio_toolkit':
        claims_listed = 'listed' in normalise(early) or normalise(early) == {'listed'}
        truth_listed = str(final_answer).startswith('listed')
        return 'correct' if (claims_listed == truth_listed) else 'incorrect'
    if field == 'api_surface':
        early_types, early_breadth = api_parts(early)
        ref_types, ref_breadth = api_parts(reviewed_answer)
        if not early_types:
            return 'incorrect'
        if early_types == ref_types and early_breadth == ref_breadth:
            return 'correct'
        if early_types <= ref_types:
            return 'partial'
        return 'partial' if early_types & ref_types else 'incorrect'
    early_tokens, ref_tokens = normalise(early), normalise(reviewed_answer)
    if not early_tokens:
        return 'incorrect'
    if early_tokens <= ref_tokens:
        return 'partial'
    return 'partial' if early_tokens & ref_tokens else 'incorrect'


def summarise(counter, total=60):
    correct = counter.get('correct', 0)
    partial = counter.get('partial', 0)
    incorrect = counter.get('incorrect', 0)
    abstained = counter.get('abstained', 0)
    unresolved = counter.get('unresolved', 0)
    scored = correct + partial + incorrect
    answered = total - abstained - unresolved
    weighted = correct + 0.5 * partial
    assert answered == scored, 'denominator mismatch'
    return {
        'total_claims': total,
        'answered': answered,
        'coverage': answered / total,
        'abstained': abstained,
        'unresolved': unresolved,
        'ratings': {key: counter.get(key, 0) for key in ('correct', 'partial', 'incorrect', 'abstained', 'unresolved')},
        'scored_answered': scored,
        'strict_numerator': correct,
        'strict_answered': correct / scored if scored else None,
        'weighted_numerator': weighted,
        'weighted_answered': weighted / scored if scored else None,
        'resolved': correct + partial,
        'fixed_strict': correct / total,
        'fixed_weighted': weighted / total,
    }


def score(path, expected_apps, label):
    review = json.loads(path.read_text(encoding='utf-8'))
    records = review['records']
    assert len(records) == 60, f'{label}: expected 60 claims'
    assert {record['app'] for record in records} == set(expected_apps), f'{label}: app mismatch'
    rated = []
    for record in records:
        early = first_pass[record['app']]['claims'][record['field']]['value']
        final_answer = checked[record['app']]['fields'][record['field']]['value']
        rating = rate(early, final_answer, record['pass12_answer'], record['rating'], record['field'])
        rated.append({
            'app': record['app'], 'field': record['field'],
            'first_answer': early, 'pass12_answer': record['pass12_answer'],
            'pass12_rating': record['rating'], 'first_rating': rating,
        })
    first_view = summarise(collections.Counter(item['first_rating'] for item in rated))
    final_view = summarise(collections.Counter(record['rating'] for record in records))
    return {'sample': label, 'first_pass': first_view, 'final_pass': final_view, 'records': rated}


outputs = {
    'checked_at': '2026-11-24',
    'first_pass': 'data/pass2 (first deterministic extraction pass)',
    'final_pass': 'data/pass12 (frozen, independently reviewed)',
    'rubric': ('First-pass answers identical to the reviewed pass-12 answer inherit its rating; '
               'changed answers are re-rated against the checked final answer; unknown abstains. '
               'Conservative: never more credit than the reviewed answer for the same value.'),
    'metric': ('fixed_* scores all 60 sampled claims and gives an unresolved claim zero credit, so a pass '
               'cannot score higher by abstaining on hard claims; *_answered scores only the claims a pass '
               'answered, which is the reviewer denominator.'),
    'selected_sample': score(SELECTED_REVIEW, selection['selected_sample'], 'selected_sample'),
    'random_holdout': score(HOLDOUT_REVIEW, [item['app'] for item in selection['random_holdout']], 'random_holdout'),
}
outputs['baseline'] = {'status': 'excluded_no_answer_output',
                       'note': 'The empty discovery run is retained in raw data but excluded from accuracy scoring.'}
(ROOT / 'first_pass_review_v4.json').write_text(json.dumps(outputs, indent=2, ensure_ascii=False), encoding='utf-8')
for label in ('selected_sample', 'random_holdout'):
    result = outputs[label]
    first, final = result['first_pass'], result['final_pass']
    print(label,
          'first: answered', f"{first['answered']}/60",
          'fixed half-credit', f"{100 * first['fixed_weighted']:.1f}%",
          '-> final: answered', f"{final['answered']}/60",
          'fixed half-credit', f"{100 * final['fixed_weighted']:.1f}%")
