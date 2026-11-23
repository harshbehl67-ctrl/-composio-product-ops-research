"""Merge independent source-review group logs into the preserved master review log."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / 'source_review_v4.json'
master = json.loads(MASTER.read_text(encoding='utf-8'))
existing = master['actions']
merged = master.setdefault('merged_group_files', [])
added = 0
for path in sorted((ROOT / 'data').glob('source_review_group_*_v4.json')):
    group = json.loads(path.read_text(encoding='utf-8'))
    for action in group.get('actions', []):
        key = (action.get('app'), action.get('field'), action.get('decision'),
               action.get('old_url'), action.get('old_quote'))
        conflicts = [item for item in existing if (item.get('app'), item.get('field'), item.get('decision'),
                      item.get('old_url'), item.get('old_quote')) == key]
        if conflicts:
            if any(item != action for item in conflicts):
                raise ValueError(f'Conflicting source-review action in {path.name}: {key}')
            continue
        existing.append(action)
        added += 1
    if path.name not in merged:
        merged.append(path.name)
if added:
    MASTER.write_text(json.dumps(master, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Added {added} source-review actions; master now contains {len(existing)}')
