"""Build the four-field gold template for the held-out verification sample.

Phase 3a of the assignment: a stratified, seeded sample (one app per category
plus a random holdout, seed 20261124, app level) with empty gold columns and
official docs links. This template alone cannot establish who labeled it or
whether earlier chat labels were excluded.

Only the four *judgment* fields are hand-labeled:

    auth, credential_gate, api_surface, official_mcp

The other two six-field claims are machine-scored, so grading them by hand would
be opinion against opinion:

    composio_toolkit  -> scored against the Composio catalog API (composio_catalog.json,
                         with its fetched_at timestamp)
    verdict           -> derived from the four gold fields by a written rule
                         (self-serve access + documented broad/moderate API)

A gold row contains truth only, never a rating: a rating judges the agent's
answer. The stored provenance for the filled rows is documented separately.
The gold columns are

    gold_value           what the docs say
    gold_status          found | not_stated_in_docs | unresolved
    gold_evidence_quote  a short quote (under 15 words) from the first-party page
    labeler_note         free text

The rating is computed by gold_score_v4.py by comparing saved labels with each pass.

This script never writes a gold label. It only copies the *questions* and the
first-party docs link the research already collected, leaving the gold columns
blank.

Outputs gold_template.csv (one row per app x judgment field) and prints a
summary.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Hand-labeled judgment fields only. composio_toolkit and verdict are scored by
# rule (gold_score_v4.py), not by hand.
JUDGMENT_FIELDS = ('auth', 'credential_gate', 'api_surface', 'official_mcp')

QUESTIONS = {
    'auth': 'Which mechanisms authenticate API callers? (oauth2 user, oauth2 client credentials, api key / PAT, basic, JWT-signed, none)',
    'credential_gate': 'What does it take to get credentials, for a prototype and for production? (self_serve_free, self_serve_trial, paid_plan, admin_approval, app_review, partner_or_sales, unknown)',
    'api_surface': 'What API surface exists and how broad is it? (REST / GraphQL / SOAP / WebSocket / SDK; narrow, moderate, broad)',
    'official_mcp': 'Does the vendor ship an MCP server, and is it hosted with actions, read-only/docs, local only, beta/EAP/closed, prelaunch, or none?',
}

STATUS_OPTIONS = 'found | not_stated_in_docs | unresolved'
GOLD_COLUMNS = ('gold_value', 'gold_status', 'gold_evidence_quote', 'labeler_note')


def load_json(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def field_docs(row, field):
    """First-party docs link saved for this field, else the app evidence link."""
    evidence = (row.get('fields', {}).get(field) or {}).get('evidence') or []
    for item in evidence:
        if item.get('url'):
            return item['url']
    return row.get('evidence_url') or ''


def main():
    selection = load_json('holdout_selection_v4.json')
    data = load_json('data.json')
    by_name = {row['app']: row for row in data}

    rows = []
    for app_name in selection['selected_sample']:
        rows.append(('selected_sample', app_name))
    for item in selection['random_holdout']:
        rows.append(('random_holdout', item['app']))

    header = ['sample', 'number', 'app', 'category', 'field', 'question',
              'status_options', 'docs_url'] + list(GOLD_COLUMNS)
    out = ROOT / 'gold_template.csv'
    with out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for sample, app_name in rows:
            row = by_name[app_name]
            for field in JUDGMENT_FIELDS:
                writer.writerow([
                    sample,
                    row['number'],
                    row['app'],
                    row['category'],
                    field,
                    QUESTIONS[field],
                    STATUS_OPTIONS,
                    field_docs(row, field),
                    '',  # gold_value           (human only)
                    '',  # gold_status          (human only)
                    '',  # gold_evidence_quote  (human only)
                    '',  # labeler_note         (human only)
                ])

    print('gold_template.csv written')
    print('  sample apps:', len(rows), '(10 selected + 10 holdout)')
    print('  judgment fields:', ', '.join(JUDGMENT_FIELDS))
    print('  rows:', len(rows) * len(JUDGMENT_FIELDS), '(app x judgment field)')
    print('  machine-scored, not hand-labeled: composio_toolkit (catalog API), verdict (derived rule)')
    print('  gold columns left empty:', ', '.join(GOLD_COLUMNS))
    print('  gold_status values:', STATUS_OPTIONS)
    print('  seed:', selection['seed'])


if __name__ == '__main__':
    main()
