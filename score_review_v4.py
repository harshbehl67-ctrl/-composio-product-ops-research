"""Validate and score independent selected-sample and random-holdout reviews."""
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
selection = json.loads((ROOT / 'holdout_selection_v4.json').read_text(encoding='utf-8'))
fields = ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')
apps = {app['name']: app for app in json.loads((ROOT / 'apps.json').read_text(encoding='utf-8'))}
pass12 = {app['name']: json.loads((ROOT / 'data' / 'pass12' / f"{app['number']:03}.json").read_text(encoding='utf-8'))
          for app in apps.values()}
outputs = {}


def score(path, expected_apps, label):
    review = json.loads(path.read_text(encoding='utf-8'))
    records = review['records']
    assert len(records) == 60, f'{label}: expected 60 claims'
    assert {record['app'] for record in records} == set(expected_apps), f'{label}: app mismatch'
    assert all(record['field'] in fields for record in records), f'{label}: invalid field'
    expected_claims = {(app, field) for app in expected_apps for field in fields}
    assert {(record['app'], record['field']) for record in records} == expected_claims, f'{label}: claim coverage mismatch'
    assert len({(record['app'], record['field']) for record in records}) == 60, f'{label}: duplicate claim'
    for record in records:
        expected_answer = pass12[record['app']]['claims'][record['field']]['value']
        assert record['pass12_answer'] == expected_answer, f"{label}: pass12 answer mismatch for {record['app']} / {record['field']}"
    counts = collections.Counter(record['rating'] for record in records)
    allowed = {'correct', 'partial', 'incorrect', 'abstained', 'unresolved'}
    assert set(counts) <= allowed, f'{label}: invalid rating'
    assert all(record.get('review_note') and 'correction' in record for record in records), f'{label}: incomplete review'
    answered = sum(record['pass12_answer'] != 'unknown' for record in records)
    assert all((record['pass12_answer'] == 'unknown') == (record['rating'] == 'abstained') for record in records), f'{label}: abstention mismatch'
    scored = counts['correct'] + counts['partial'] + counts['incorrect']
    assert answered == scored + counts['unresolved'], f'{label}: rating denominator mismatch'
    weighted = counts['correct'] + counts['partial'] * 0.5
    result = {
        'sample': label,
        'selection': 'deliberately selected ten-category sample used during rule tuning' if label == 'selected_sample' else 'seeded random holdout selected after pass12 froze',
        'total_claims': 60,
        'answered': answered,
        'coverage': answered / 60,
        'abstained': counts['abstained'],
        'ratings': dict(counts),
        'scored_answered': scored,
        'strict_numerator': counts['correct'],
        'strict_accuracy': counts['correct'] / scored if scored else None,
        'weighted_numerator': weighted,
        'weighted_accuracy': weighted / scored if scored else None,
        'records': records,
    }
    return result


outputs['selected_sample'] = score(ROOT / 'data' / 'checked_research' / 'review_selected_v4.json', selection['selected_sample'], 'selected_sample')
outputs['random_holdout'] = score(ROOT / 'data' / 'checked_research' / 'review_holdout_v4.json', [item['app'] for item in selection['random_holdout']], 'random_holdout')
outputs['baseline'] = {'total_claims': 60, 'answered': 0, 'coverage': 0, 'strict_accuracy': None,
                       'note': 'Original baseline answered 0/60; answered-claim accuracy is undefined (0/0), not 0%.'}
outputs['comparison_note'] = 'No baseline accuracy-improvement claim is made. Selected and holdout results are separate and are not population estimates.'
Path('independent_review_v4.json').write_text(json.dumps(outputs, indent=2, ensure_ascii=False), encoding='utf-8')
for label in ('selected_sample', 'random_holdout'):
    result = outputs[label]
    print(label, 'coverage', f"{result['answered']}/60", 'ratings', result['ratings'],
          'strict', f"{result['strict_numerator']}/{result['scored_answered']}",
          'half-credit', f"{result['weighted_numerator']}/{result['scored_answered']}")
