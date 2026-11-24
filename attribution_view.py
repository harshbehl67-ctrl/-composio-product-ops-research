"""Presentation-only reconciliation of AI, pipeline, and author contributions.

All counts are derived from the frozen gold, provenance, saved scoring output,
human spot-check, and authored override log. This module does not alter claims,
labels, samples, or scores.
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path


def _read_json(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding='utf-8'))


def derive_attribution(root: Path) -> dict:
    gold = _read_json(root, 'gold_ratings_v4.json')
    provenance = _read_json(root, 'gold_provenance_v1.json')
    human = _read_json(root, 'human_gold_spotcheck_results_v1.json')
    overrides = _read_json(root, 'classification_overrides_v1.json')
    human_log = _read_json(root, 'human_log.json')
    adjudication = _read_json(root, 'current_source_adjudication_v1.json')

    with (root / 'gold_template.csv').open(encoding='utf-8', newline='') as handle:
        gold_rows = list(csv.DictReader(handle))

    labels = provenance['gold_labels']
    human_provenance = provenance['author_spotcheck']
    spot_rows = human['rows']
    spot_summary = human['summary']
    pass3 = gold['overall']['pass3']['judgment_fields']
    quality = gold['row_quality']
    rule_fields = list(gold['rule_scored_fields'])
    override_rows = [row for row in overrides['records']
                     if row.get('actor_type') == 'authored classification override']

    gold_status_counts = {
        status: sum(row.get('gold_status') == status for row in gold_rows)
        for status in ('found', 'not_stated_in_docs', 'unresolved')
    }
    assert len(gold_rows) == quality['total_rows']
    assert gold_status_counts == {
        'found': quality['labeled_found'],
        'not_stated_in_docs': quality['labeled_not_stated_in_docs'],
        'unresolved': quality['labeled_unresolved'],
    }
    assert labels['actor_type'].casefold() == 'ai'
    assert 'gold_template.csv' in gold['label_source']
    assert all('human_status' not in row for row in gold_rows)

    human_matches = sum(row.get('status_agreement') is True for row in spot_rows)
    human_disagreements = sum(row.get('status_agreement') is False for row in spot_rows)
    human_weak = sum(row.get('status_agreement') is None for row in spot_rows)
    assert len(spot_rows) == human['sample']['n'] == human_provenance['sample_size']
    assert human['sample']['selected_rows'] + human['sample']['holdout_rows'] == len(spot_rows)
    assert human['sample']['selected_rows'] == human['sample']['holdout_rows']
    assert (human_matches, human_disagreements, human_weak) == (
        spot_summary['status_matches'], spot_summary['status_disagreements'],
        spot_summary['weak_or_ambiguous'])
    assert human_provenance['actor_type'] == 'human author'
    assert human_provenance['independent'] is False
    assert human_provenance['blind_to_saved_labels'] is False

    pending = [row for row in adjudication['records']
               if 'pending human adjudication' in row.get('disposition', '').lower()
               or 'reviewer decides' in row.get('disposition', '').lower()]
    disputed = [row for row in adjudication['records'] if row.get('author_spotcheck_status')]
    scope_rows = [row for row in spot_rows
                  if row.get('field') == 'credential_gate'
                  and 'addresses authentication' in row.get('note', '').lower()]
    assert len(scope_rows) == spot_summary['field_scope_mismatches']

    return {
        'sources': {
            'label_source': gold['label_source'],
            'gold_provenance_actor': labels['actor_type'],
            'gold_labeler_identity': labels['labeler_identity'],
            'earlier_chat_label_exclusion': labels['earlier_chat_label_exclusion']['status'],
            'human_check_actor': human_provenance['actor_type'],
        },
        'agent_only': {
            'ai_gold_rows': len(gold_rows),
            'pipeline_derived_rule_rows': gold['apps'] * len(rule_fields),
            'pipeline_derived_app_count': gold['apps'],
            'pipeline_derived_fields': rule_fields,
            'authored_classification_override_records': len(override_rows),
            'model_log_decision_records': len(human_log['entries']),
        },
        'agent_pass3': {
            'total_judgment_rows': pass3['total'],
            'scoreable_rows': pass3['scoreable'],
            'answered_scoreable_rows': pass3['answered'],
            'exact_hits': pass3['correct'],
            'partial': pass3['partial'],
            'incorrect': pass3['incorrect'],
            'gold_unscoreable_ratings': pass3['unresolved'],
            'gold_not_stated': gold_status_counts['not_stated_in_docs'],
            'gold_unresolved': gold_status_counts['unresolved'],
        },
        'human_spotcheck': {
            'rows_checked': len(spot_rows),
            'selected_rows': human['sample']['selected_rows'],
            'holdout_rows': human['sample']['holdout_rows'],
            'same_author': not human_provenance['independent'],
            'blind': human_provenance['blind_to_saved_labels'],
            'unit': human_provenance['unit'],
            'hits': human_matches,
            'clear_misses': human_disagreements,
            'weak': human_weak,
            'clear_status_agreement': human_matches / (human_matches + human_disagreements),
            'credential_gate_scope_mismatch_rows': [
                {'row_id': row['row_id'], 'app': row['app']} for row in scope_rows
            ],
        },
        'human_decisions_needed': {
            'gold_unscoreable_rows': pass3['unresolved'],
            'gold_not_stated': gold_status_counts['not_stated_in_docs'],
            'gold_unresolved': gold_status_counts['unresolved'],
            'pending_adjudications': [
                {'row_id': row['row_id'], 'app': row['app'], 'field': row['field'],
                 'issue': row['frozen_record_issue'], 'disposition': row['disposition']}
                for row in pending
            ],
            'author_spotcheck_disputes': [
                {'row_id': row['row_id'], 'app': row['app'], 'field': row['field'],
                 'frozen_gold_status': row['frozen_gold_status'],
                 'author_spotcheck_status': row['author_spotcheck_status'],
                 'disposition': row['disposition']}
                for row in disputed
            ],
            'credential_gate_scope_mismatch_rows': [
                {'row_id': row['row_id'], 'app': row['app']}
                for row in scope_rows
            ],
        },
    }


def render_html(view: dict) -> str:
    esc = html.escape
    agent = view['agent_only']
    scores = view['agent_pass3']
    human = view['human_spotcheck']
    needed = view['human_decisions_needed']
    gold_unscoreable = needed['gold_unscoreable_rows']
    pending_names = ', '.join(f"{row['row_id']} {row['app']}" for row in needed['pending_adjudications'])
    disputed_names = ', '.join(f"{row['row_id']} {row['app']}" for row in needed['author_spotcheck_disputes'])
    scope_names = ', '.join(f"{row['row_id']} {row['app']}" for row in human['credential_gate_scope_mismatch_rows'])
    return (
        '<section id="actor-view"><div class="kicker">03B / Contribution and handoffs</div>'
        '<h2>What the agent produced, what I checked, and what still needs a decision.</h2>'
        '<p class="muted">Counts come from the saved label source, pass-3 ratings, author-check results, override log, and adjudication ledger. '
        'Gold labels and human check events are separate records; a human check does not turn an AI-labeled row into a human label.</p>'
        '<div class="cards"><article class="card"><h3>Agent and pipeline outputs</h3>'
        f'<p><b>{agent["ai_gold_rows"]} AI-attributed gold rows</b> · label_source: '
        f'<code>{esc(view["sources"]["label_source"])}</code>. The project record attributes these labels to AI; '
        f'the model/session identity is not recorded and earlier-chat exclusion is {esc(view["sources"]["earlier_chat_label_exclusion"])}.</p>'
        f'<p><b>{agent["pipeline_derived_rule_rows"]} pipeline-derived rule comparisons</b> · '
        f'{agent["pipeline_derived_app_count"]} apps × {len(agent["pipeline_derived_fields"])} fields '
        f'({esc(", ".join(agent["pipeline_derived_fields"]))}); these are catalog/rule outputs, not human labels.</p>'
        f'<p>The pass-3 agent produced {scores["total_judgment_rows"]} four-field answers: '
        f'{scores["exact_hits"]} exact, {scores["partial"]} partial, {scores["incorrect"]} incorrect; '
        f'{scores["gold_unscoreable_ratings"]} are unscoreable from the frozen reference.</p>'
        '</article><article class="card"><h3>Human-in-the-loop work</h3>'
        f'<p>The author log contains <b>{agent["authored_classification_override_records"]} authored classification overrides</b>; '
        f'these are separate from the gold labels and the spot-check. The {agent["model_log_decision_records"]} decisions in the model log '
        f'and the {agent["authored_classification_override_records"]} authored override records are different record sets.</p>'
        f'<p>The author then checked <b>{human["rows_checked"]} documentation-status rows</b> '
        f'({human["selected_rows"]} selected, {human["holdout_rows"]} holdout). '
        f'This was same-author, non-blind, and status-only: {human["hits"]}/{human["hits"] + human["clear_misses"]} '
        f'clear status matches ({human["clear_status_agreement"]:.1%}): {human["hits"]} agreements, '
        f'{human["clear_misses"]} disagreements with the frozen AI labels, {human["weak"]} ambiguous row. '
        'The check is recorded separately; it did not relabel the gold set.</p>'
        '</article></div>'
        '<h3>Hits and misses by actor</h3><div class="cards">'
        '<article class="card"><h3>Final checked pipeline output</h3>'
        f'<p><b>{scores["exact_hits"]} exact hits</b>; {scores["partial"]} partial answers; '
        f'{scores["incorrect"]} incorrect answers.</p>'
        f'<p><b>{gold_unscoreable} ratings cannot be assessed against this reference; excluded from the accuracy denominator.</b> '
        f'The frozen reference is {scores["gold_not_stated"]} not-stated and {scores["gold_unresolved"]} unresolved rows.</p></article>'
        '<article class="card"><h3>Human status check</h3>'
        f'<p><b>{human["hits"]} agreements</b>, {human["clear_misses"]} disagreements with the frozen AI labels, '
        f'{human["weak"]} ambiguous row '
        f'across {human["rows_checked"]} checks. Agreement uses only clear comparisons: '
        f'{human["hits"]}/{human["hits"] + human["clear_misses"]} = {human["clear_status_agreement"]:.1%}.</p>'
        '</article></div>'
        '<h3>Where a human decision is still needed</h3><ul>'
        f'<li><b>{gold_unscoreable} frozen references cannot score the agent</b>: '
        f'{scores["gold_not_stated"]} are not stated and {scores["gold_unresolved"]} unresolved; decide whether to gather better excerpts or leave these unscored.</li>'
        f'<li><b>Pending gold adjudication:</b> {esc(pending_names)}. Review the frozen status/value conflicts before issuing any corrected-gold version.</li>'
        f'<li><b>Author/gold disagreement:</b> {esc(disputed_names)}; retain the frozen label unless a separately versioned correction is approved.</li>'
        f'<li><b>Credential gate evidence:</b> re-check {len(human["credential_gate_scope_mismatch_rows"])} auth-only quotes '
        f'({esc(scope_names)}); authentication alone does not establish an access gate.</li>'
        '</ul></section>'
    )


def render_readme(view: dict) -> str:
    agent = view['agent_only']
    scores = view['agent_pass3']
    human = view['human_spotcheck']
    needed = view['human_decisions_needed']
    pending_names = ', '.join(f"{row['row_id']} {row['app']}" for row in needed['pending_adjudications'])
    disputed_names = ', '.join(f"{row['row_id']} {row['app']}" for row in needed['author_spotcheck_disputes'])
    scope_names = ', '.join(f"{row['row_id']} {row['app']}" for row in human['credential_gate_scope_mismatch_rows'])
    lines = [
        '<!-- BEGIN GENERATED ACTOR ATTRIBUTION -->',
        '',
        '## Who did what: agent and human contributions',
        '',
        'Counts below are generated from the saved gold source, pass-3 ratings, author-check results, override log, and adjudication ledger. Gold labels and human-check events are separate: a human check does not turn an AI-labeled row into a human label.',
        '',
        '### Agent and pipeline output',
        '',
        f'- **{agent["ai_gold_rows"]} AI-attributed gold rows**; `label_source`: `{view["sources"]["label_source"]}`. The saved record attributes labels to AI; model/session identity is not recorded and earlier-chat exclusion is `{view["sources"]["earlier_chat_label_exclusion"]}`.',
        f'- **{agent["pipeline_derived_rule_rows"]} pipeline-derived rule comparisons** ({agent["pipeline_derived_app_count"]} apps × {len(agent["pipeline_derived_fields"])} fields: {", ".join(agent["pipeline_derived_fields"])}); these are catalog/rule outputs, not human labels.',
        f'- Pass 3 scored {scores["total_judgment_rows"]} four-field answers: **{scores["exact_hits"]} exact, {scores["partial"]} partial, {scores["incorrect"]} incorrect**. Another {scores["gold_unscoreable_ratings"]} ratings are unscoreable from the frozen reference ({scores["gold_not_stated"]} not stated, {scores["gold_unresolved"]} unresolved).',
        '',
        '### Human-in-the-loop work',
        '',
        f'- The author log contains **{agent["authored_classification_override_records"]} authored classification overrides**, separate from the gold labels and the status spot-check. The {agent["model_log_decision_records"]} model-log decisions and {agent["authored_classification_override_records"]} override records are different record sets.',
        f'- The author checked **{human["rows_checked"]} documentation-status rows** ({human["selected_rows"]} selected, {human["holdout_rows"]} holdout), same-author, non-blind, and status-only: **{human["hits"]}/{human["hits"] + human["clear_misses"]} clear matches ({human["clear_status_agreement"]:.1%}), {human["clear_misses"]} disagreements, {human["weak"]} weak row**. This is a separate check event; it did not relabel the gold set.',
        '',
        '### Hits, misses, and decisions still needed',
        '',
        f'- **Final checked pipeline output:** {scores["exact_hits"]} exact hits, {scores["partial"]} partial answers, {scores["incorrect"]} incorrect. The {scores["gold_unscoreable_ratings"]} ratings cannot be assessed against this reference and are excluded from the accuracy denominator ({scores["gold_not_stated"]} not stated, {scores["gold_unresolved"]} unresolved).',
        f'- **Human status check:** {human["hits"]} agreements, {human["clear_misses"]} disagreements with the frozen AI labels, {human["weak"]} ambiguous row across {human["rows_checked"]} checks; clear-only agreement is {human["hits"]}/{human["hits"] + human["clear_misses"]} ({human["clear_status_agreement"]:.1%}).',
        f'- Improve excerpts or leave {needed["gold_unscoreable_rows"]} frozen references unscored ({needed["gold_not_stated"]} not stated, {needed["gold_unresolved"]} unresolved).',
        f'- Adjudicate {pending_names}; review the frozen conflicts before issuing a corrected-gold version.',
        f'- Review the author/gold disagreement for {disputed_names}; do not silently change the frozen label.',
        f'- Re-check {len(human["credential_gate_scope_mismatch_rows"])} credential-gate rows ({scope_names}); auth-only evidence does not establish an access gate.',
        '',
        '<!-- END GENERATED ACTOR ATTRIBUTION -->',
    ]
    return '\n'.join(lines)


def update_readme(root: Path, generated_markdown: str) -> None:
    path = root / 'README.md'
    text = path.read_text(encoding='utf-8')
    start_marker = '<!-- BEGIN GENERATED ACTOR ATTRIBUTION -->'
    end_marker = '<!-- END GENERATED ACTOR ATTRIBUTION -->'
    assert text.count(start_marker) == 1 and text.count(end_marker) == 1
    start = text.index(start_marker)
    end = text.index(end_marker) + len(end_marker)
    generated_start = generated_markdown.index(start_marker)
    generated_end = generated_markdown.index(end_marker) + len(end_marker)
    updated = text[:start] + generated_markdown[generated_start:generated_end] + text[end:]
    path.write_text(updated, encoding='utf-8', newline='\n')
