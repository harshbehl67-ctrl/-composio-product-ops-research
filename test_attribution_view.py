"""Reconcile the actor-attribution view against its canonical source records."""
import csv
import json
import unittest
from pathlib import Path

import attribution_view

ROOT = Path(__file__).resolve().parent


class AttributionViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = attribution_view.derive_attribution(ROOT)
        cls.gold = json.loads((ROOT / 'gold_ratings_v4.json').read_text(encoding='utf-8'))
        cls.provenance = json.loads((ROOT / 'gold_provenance_v1.json').read_text(encoding='utf-8'))
        cls.human = json.loads((ROOT / 'human_gold_spotcheck_results_v1.json').read_text(encoding='utf-8'))
        cls.overrides = json.loads((ROOT / 'classification_overrides_v1.json').read_text(encoding='utf-8'))

    def test_agent_and_pipeline_counts_match_sources(self):
        view = self.view
        with (ROOT / 'gold_template.csv').open(encoding='utf-8', newline='') as handle:
            gold_rows = list(csv.DictReader(handle))
        self.assertEqual(view['sources']['label_source'], self.gold['label_source'])
        self.assertEqual(view['sources']['gold_provenance_actor'], self.provenance['gold_labels']['actor_type'])
        self.assertEqual(view['agent_only']['ai_gold_rows'], len(gold_rows))
        self.assertEqual(view['agent_only']['pipeline_derived_app_count'], self.gold['apps'])
        self.assertEqual(view['agent_only']['pipeline_derived_fields'], list(self.gold['rule_scored_fields']))
        self.assertEqual(view['agent_only']['pipeline_derived_rule_rows'],
                         self.gold['apps'] * len(self.gold['rule_scored_fields']))
        authored = [row for row in self.overrides['records']
                    if row.get('actor_type') == 'authored classification override']
        self.assertEqual(view['agent_only']['authored_classification_override_records'], len(authored))

    def test_agent_hits_misses_and_unscoreable_split_match_gold(self):
        outcome = self.view['agent_pass3']
        source = self.gold['overall']['pass3']['judgment_fields']
        quality = self.gold['row_quality']
        self.assertEqual(outcome['total_judgment_rows'], source['total'])
        self.assertEqual(outcome['scoreable_rows'], source['scoreable'])
        self.assertEqual(outcome['answered_scoreable_rows'], source['answered'])
        self.assertEqual((outcome['exact_hits'], outcome['partial'], outcome['incorrect']),
                         (source['correct'], source['partial'], source['incorrect']))
        self.assertEqual(outcome['gold_unscoreable_ratings'], source['unresolved'])
        self.assertEqual(outcome['gold_not_stated'], quality['labeled_not_stated_in_docs'])
        self.assertEqual(outcome['gold_unresolved'], quality['labeled_unresolved'])
        self.assertEqual(outcome['gold_unscoreable_ratings'],
                         outcome['gold_not_stated'] + outcome['gold_unresolved'])

    def test_human_check_is_a_separate_event_not_human_gold(self):
        view = self.view['human_spotcheck']
        source = self.human
        self.assertEqual(view['rows_checked'], len(source['rows']))
        self.assertEqual(view['rows_checked'], source['sample']['n'])
        self.assertEqual((view['selected_rows'], view['holdout_rows']),
                         (source['sample']['selected_rows'], source['sample']['holdout_rows']))
        self.assertEqual((view['hits'], view['clear_misses'], view['weak']),
                         (source['summary']['status_matches'], source['summary']['status_disagreements'],
                          source['summary']['weak_or_ambiguous']))
        self.assertEqual(view['hits'] + view['clear_misses'] + view['weak'], view['rows_checked'])
        self.assertAlmostEqual(view['clear_status_agreement'],
                               view['hits'] / (view['hits'] + view['clear_misses']))
        with (ROOT / 'gold_template.csv').open(encoding='utf-8', newline='') as handle:
            gold_rows = list(csv.DictReader(handle))
        self.assertTrue(all('human_status' not in row for row in gold_rows))
        self.assertEqual(source['summary']['field_scope_mismatches'],
                         len(view['credential_gate_scope_mismatch_rows']))
        self.assertEqual(self.provenance['author_spotcheck']['actor_type'], 'human author')
        self.assertFalse(self.provenance['author_spotcheck']['independent'])
        self.assertFalse(self.provenance['author_spotcheck']['blind_to_saved_labels'])

    def test_human_decision_rows_match_adjudication_and_scope_sources(self):
        needed = self.view['human_decisions_needed']
        self.assertEqual({row['row_id'] for row in needed['pending_adjudications']}, {'R032', 'R059'})
        self.assertEqual({row['row_id'] for row in needed['author_spotcheck_disputes']}, {'R072'})
        self.assertEqual({row['row_id'] for row in needed['credential_gate_scope_mismatch_rows']},
                         {'R002', 'R034', 'R042', 'R054', 'R074'})
        self.assertEqual(needed['gold_unscoreable_rows'],
                         needed['gold_not_stated'] + needed['gold_unresolved'])

    def test_rendered_page_and_readme_use_reconciled_values(self):
        html = attribution_view.render_html(self.view)
        markdown = attribution_view.render_readme(self.view)
        agent = self.view['agent_only']
        scores = self.view['agent_pass3']
        human = self.view['human_spotcheck']
        for value in (agent['ai_gold_rows'], agent['pipeline_derived_rule_rows'],
                      agent['authored_classification_override_records'], scores['exact_hits'],
                      scores['partial'], scores['incorrect'], scores['gold_unscoreable_ratings'],
                      scores['gold_not_stated'], scores['gold_unresolved'], human['rows_checked'],
                      human['selected_rows'], human['holdout_rows'], human['hits'],
                      human['clear_misses'], human['weak']):
            self.assertIn(str(value), html)
            self.assertIn(str(value), markdown)
        self.assertIn('15/23', html)
        self.assertIn('15/23', markdown)
        self.assertIn('R032 Notion', html)
        self.assertIn('R059 YouTube Transcript', markdown)
        self.assertIn('R072 Snowflake', html)

    def test_generated_artifact_and_readme_match_builder_view(self):
        artifact_path = ROOT / 'attribution_view_v1.json'
        self.assertTrue(artifact_path.is_file(), 'run build_case_v4.py before the test suite')
        artifact = json.loads(artifact_path.read_text(encoding='utf-8'))
        self.assertEqual(artifact, self.view)
        page = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn(attribution_view.render_html(self.view), page)
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertEqual(readme.count('<!-- BEGIN GENERATED ACTOR ATTRIBUTION -->'), 1)
        self.assertEqual(readme.count('<!-- END GENERATED ACTOR ATTRIBUTION -->'), 1)
        self.assertIn(attribution_view.render_readme(self.view), readme)


if __name__ == '__main__':
    unittest.main()
