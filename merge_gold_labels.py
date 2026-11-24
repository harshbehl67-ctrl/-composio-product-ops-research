"""Merge a returned-label CSV into gold_template.csv.

The saved workflow record says labels were returned for ``private/full/R###.txt``
and ``private/raw/R###.json`` packets, one row per ``row_id`` (R001..R080).
``private/mapping.csv``
maps each ``row_id`` to the 1-based data row (``csv_row``) of
``gold_template.csv``. This script copies the four gold columns across and
writes the template back, refusing to run if any row is left unlabeled or if the
row ids or the row counts do not line up.

Inputs :  private/labels_returned.csv   (the returned labels)
          private/mapping.csv           (row_id -> csv_row)
          gold_template.csv             (the empty template)
Output :  gold_template.csv             (same file, gold columns filled)
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / 'gold_template.csv'
MAPPING = ROOT / 'private' / 'mapping.csv'
LABELS = ROOT / 'private' / 'labels_returned.csv'
GOLD_COLUMNS = ('gold_value', 'gold_status', 'gold_evidence_quote', 'labeler_note')
VALID_STATUS = {'found', 'not_stated_in_docs', 'unresolved'}


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def main():
    mapping = read_csv(MAPPING)
    labels = read_csv(LABELS)
    template = read_csv(TEMPLATE)

    row_by_id = {row['row_id']: row for row in labels}
    csv_row_by_id = {row['row_id']: int(row['csv_row']) for row in mapping}

    problems = []
    if len(row_by_id) != len(labels):
        problems.append('duplicate row_id in labels_returned.csv')
    if set(row_by_id) != set(csv_row_by_id):
        missing = sorted(set(csv_row_by_id) - set(row_by_id))
        extra = sorted(set(row_by_id) - set(csv_row_by_id))
        if missing:
            problems.append(f'labels missing for {len(missing)} row(s): {", ".join(missing[:6])}')
        if extra:
            problems.append(f'unknown row_id(s) in labels: {", ".join(extra[:6])}')
    if problems:
        raise SystemExit('label merge refused:\n  - ' + '\n  - '.join(problems))

    filled = 0
    for row_id, csv_row in sorted(csv_row_by_id.items()):
        if not 1 <= csv_row <= len(template):
            problems.append(f'{row_id}: csv_row {csv_row} outside 1..{len(template)}')
            continue
        label = row_by_id[row_id]
        status = (label['gold_status'] or '').strip()
        if status not in VALID_STATUS:
            problems.append(f'{row_id}: bad gold_status "{status}"')
        target = template[csv_row - 1]
        for column in GOLD_COLUMNS:
            target[column] = label[column]
        filled += 1
        if status != 'found' and (label['gold_value'] or '').strip():
            problems.append(f'{row_id}: status {status} but gold_value is not empty')

    unlabeled = [str(index + 1) for index, row in enumerate(template)
                 if not (row.get('gold_status') or '').strip()]
    if unlabeled:
        problems.append(f'{len(unlabeled)} template row(s) still empty (csv rows {", ".join(unlabeled[:8])})')
    if problems:
        raise SystemExit('label merge refused:\n  - ' + '\n  - '.join(problems))

    fieldnames = list(template[0].keys())
    with TEMPLATE.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(template)

    from collections import Counter
    statuses = Counter(row['gold_status'] for row in template)
    by_field = Counter(row['field'] for row in template)
    print(f'gold_template.csv merged: {filled}/80 rows filled')
    print('  statuses:', dict(statuses))
    print('  by field:', dict(by_field))


if __name__ == '__main__':
    main()
