"""Apply the preserved official-source review log to normalized category records."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'data' / 'checked_research'
review = json.loads((ROOT / 'source_review_v4.json').read_text(encoding='utf-8'))
actions = review['actions']
actions = [action for action in actions if action['decision'] != 'keep'] + [action for action in actions if action['decision'] == 'keep']
changed_files = 0
changed_names = []
applied = 0


def claim_updates_satisfied(claim, updates):
    for key, value in updates.items():
        if key != 'evidence':
            if claim.get(key) != value:
                return False
            continue
        current_evidence = claim.get('evidence', [])
        if len(current_evidence) != len(value):
            return False
        for expected in value:
            match = next((source for source in current_evidence
                          if source.get('url') == expected.get('url')
                          and source.get('quote') == expected.get('quote')), None)
            if match is None or any(match.get(item) != expected_value for item, expected_value in expected.items()):
                return False
    return True

for path in sorted(SOURCE.glob('*.json')):
    if not path.stem[:2].isdigit() or path.stem[2:3] != '_':
        continue
    data = json.loads(path.read_text(encoding='utf-8'))
    records = {record['app']: record for record in data.get('records', [])}
    changed = False
    for action_index, action in enumerate(actions):
        record = records.get(action['app'])
        if record is None:
            continue
        claim = record['fields'][action['field']] if 'field' in action else None
        decision = action['decision']
        if decision in ('replace', 'keep'):
            evidence = claim.get('evidence', [])
            match = next((source for source in evidence
                          if source.get('url') == action['old_url']
                          and source.get('quote') == action['old_quote']), None)
            if match is None:
                replacement = action.get('new_url') and any(
                    source.get('url') == action.get('new_url') and source.get('quote') == action.get('new_quote')
                    for source in evidence)
                already_kept = decision == 'keep' and any(
                    source.get('url') == action['old_url'] and source.get('quote') == action['old_quote']
                    and source.get('verification_method') for source in evidence)
                superseded = decision == 'replace' and any(
                    later.get('app') == action['app'] and later.get('field') == action['field']
                    and later.get('decision') == 'replace'
                    and later.get('old_url') == action.get('new_url')
                    and later.get('old_quote') == action.get('new_quote')
                    and any(source.get('url') == later.get('new_url')
                            and source.get('quote') == later.get('new_quote') for source in evidence)
                    for later in actions[action_index + 1:])
                if replacement or already_kept or superseded:
                    applied += 1
                    continue
                raise ValueError(f"{path.name}: source action did not match {action['app']} / {action['field']}")
            if decision == 'replace':
                updates = {'original_url': match.get('original_url', action['old_url']),
                           'url': action['new_url'], 'title': action.get('new_title') or match.get('title'),
                           'quote': action['new_quote'], 'source_review': action['review_note']}
                for date_key in ('published_at', 'published_label'):
                    if date_key in action:
                        updates[date_key] = action[date_key]
            else:
                updates = {'verification_method': action['verification_method'],
                           'verification_note': action['review_note'], 'verified_at': review['checked_at'],
                           'source_review': action['review_note']}
            if all(match.get(key) == value for key, value in updates.items()):
                applied += 1
                continue
            match.update(updates)
            changed = True
            applied += 1
        elif decision == 'reclassify':
            updates = action['claim']
            if claim_updates_satisfied(claim, updates):
                applied += 1
                continue
            claim.update(updates)
            changed = True
            applied += 1
        elif decision == 'record_update':
            updates = action['updates']
            if all(record.get(key) == value for key, value in updates.items()):
                applied += 1
                continue
            record.update(updates)
            changed = True
            applied += 1
        else:
            raise ValueError(f"Unknown source-review decision: {decision}")
    if changed:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        changed_files += 1
        changed_names.append(path.name)

if applied != len(actions):
    raise ValueError(f'Applied {applied} of {len(actions)} source-review actions')
print(f'Applied {applied} source-review actions across {changed_files} category files')
if changed_names:
    print('Updated:', ', '.join(changed_names))
