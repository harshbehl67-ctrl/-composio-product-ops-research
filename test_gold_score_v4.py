"""Tests for gold-set scoring semantics and grader behavior.

Guards the two fixes requested for Phase 3a:

1. A truth row carries no rating column; a rating judges the agent, not the truth.
2. composio_toolkit is scored against the catalog snapshot and verdict is derived
   by a written rule, so they are never graded opinion against opinion.

The graders return a single rating string ('correct' | 'partial' | 'incorrect' |
'abstained' | 'unresolved'); a 'partial' is what lands in the adjudication queue.
"""
import csv
import json
import unittest
from pathlib import Path

import gold_score_v4 as gs
import gold_set_v4 as gset

ROOT = Path(__file__).resolve().parent


class GoldTemplateSchema(unittest.TestCase):
    def test_only_four_judgment_fields_are_hand_labeled(self):
        self.assertEqual(gset.JUDGMENT_FIELDS,
                         ('auth', 'credential_gate', 'api_surface', 'official_mcp'))

    def test_gold_columns_are_truth_only_with_no_rating(self):
        self.assertEqual(gset.GOLD_COLUMNS,
                         ('gold_value', 'gold_status', 'gold_evidence_quote', 'labeler_note'))
        self.assertNotIn('gold_rating', gset.GOLD_COLUMNS)

    def test_machine_scored_fields_are_not_in_the_template_questions(self):
        for field in ('composio_toolkit', 'verdict'):
            self.assertNotIn(field, gset.JUDGMENT_FIELDS)
            self.assertNotIn(field, gset.QUESTIONS)


class JudgmentGrader(unittest.TestCase):
    def test_unknown_agent_abstains(self):
        self.assertEqual(gs.grade_judgment('unknown', 'OAuth 2.0', 'found', 'auth'), 'abstained')

    def test_gold_not_found_is_unresolved(self):
        self.assertEqual(gs.grade_judgment('OAuth 2.0', '', 'not_stated_in_docs', 'auth'), 'unresolved')

    def test_identical_auth_is_correct(self):
        self.assertEqual(gs.grade_judgment('OAuth 2.0', 'OAuth 2.0', 'found', 'auth'), 'correct')

    def test_disjoint_auth_is_incorrect(self):
        self.assertEqual(gs.grade_judgment('Basic authentication', 'OAuth 2.0', 'found', 'auth'),
                         'incorrect')

    def test_narrower_api_surface_is_partial(self):
        self.assertEqual(gs.grade_judgment('REST API', 'REST and GraphQL API, broad', 'found', 'api_surface'),
                         'partial')

    def test_api_surface_match_is_correct(self):
        self.assertEqual(gs.grade_judgment('REST API, broad', 'REST API, broad', 'found', 'api_surface'),
                         'correct')

    def test_sdk_only_gold_does_not_contradict_another_source_protocol_claim(self):
        self.assertEqual(gs.grade_judgment('REST API, broad', 'SDK', 'found', 'api_surface'),
                         'partial')

    def test_explicitly_rejected_protocol_is_incorrect(self):
        self.assertEqual(gs.grade_judgment('REST API', 'broad', 'found', 'api_surface',
                                           "The excerpt says it's not a REST API."), 'incorrect')

    def test_http_alone_is_not_a_protocol_label(self):
        self.assertEqual(gs.grade_judgment('HTTP API', 'REST API', 'found', 'api_surface'), 'partial')

    def test_mcp_server_presence_compared(self):
        self.assertEqual(gs.grade_judgment('vendor_server', 'hosted with actions', 'found', 'official_mcp'),
                         'correct')
        self.assertEqual(gs.grade_judgment('vendor_server', 'none', 'found', 'official_mcp'),
                         'incorrect')


class ComposioGrader(unittest.TestCase):
    def test_listed_matches_catalog(self):
        self.assertEqual(gs.grade_composio('listed_exact', {'in_composio': True, 'claim': 'listed_exact'}),
                         'correct')

    def test_not_listed_matches_catalog(self):
        self.assertEqual(gs.grade_composio('not_listed', {'in_composio': False, 'claim': 'not_listed'}),
                         'correct')

    def test_listed_against_absent_catalog_is_incorrect(self):
        self.assertEqual(gs.grade_composio('listed', {'in_composio': False, 'claim': 'not_listed'}),
                         'incorrect')

    def test_exact_versus_alias_is_partial(self):
        self.assertEqual(gs.grade_composio('listed_exact', {'in_composio': True, 'claim': 'listed_alias'}),
                         'partial')

    def test_unknown_agent_abstains(self):
        self.assertEqual(gs.grade_composio('unknown', {'in_composio': True, 'claim': 'listed_exact'}),
                         'abstained')


class VerdictRule(unittest.TestCase):
    def _gold(self, auth, api, access):
        return {'auth': {'gold_status': auth},
                'api_surface': {'gold_status': api, 'gold_value': 'REST API, broad'},
                'credential_gate': {'gold_status': 'found', 'gold_value': access}}

    def test_missing_auth_is_unknown(self):
        verdict, _ = gs.derive_verdict(self._gold('not_stated_in_docs', 'found', 'self-serve free'))
        self.assertEqual(verdict, 'unknown')

    def test_missing_gate_evidence_is_unknown(self):
        fields = self._gold('found', 'found', 'self-serve free')
        fields['credential_gate']['gold_status'] = 'unresolved'
        verdict, _ = gs.derive_verdict(fields)
        self.assertEqual(verdict, 'unknown')

    def test_partner_gate_is_partner_outreach(self):
        verdict, _ = gs.derive_verdict(self._gold('found', 'found', 'requires partner agreement'))
        self.assertEqual(verdict, 'partner_outreach')

    def test_self_serve_and_broad_is_documented(self):
        verdict, _ = gs.derive_verdict(self._gold('found', 'found', 'self-serve free tier'))
        self.assertEqual(verdict, 'documented_build_candidate')

    def test_no_self_serve_is_gated(self):
        verdict, _ = gs.derive_verdict(self._gold('found', 'found', 'admin approval required'))
        self.assertEqual(verdict, 'gated_build_candidate')

    def test_missing_api_breadth_does_not_imply_access_gate(self):
        fields = self._gold('found', 'found', 'self-serve free')
        fields['api_surface']['gold_value'] = 'SDK'
        verdict, _ = gs.derive_verdict(fields)
        self.assertEqual(verdict, 'unknown')

    def test_grade_verdict_match_and_mismatch(self):
        self.assertEqual(gs.grade_verdict('documented_build_candidate', 'documented_build_candidate'),
                         'correct')
        self.assertEqual(gs.grade_verdict('gated_build_candidate', 'documented_build_candidate'),
                         'incorrect')

    def test_grade_verdict_unknown_agent_abstains(self):
        self.assertEqual(gs.grade_verdict('unknown', 'documented_build_candidate'), 'abstained')


class GoldMetrics(unittest.TestCase):
    def test_published_scoreable_rubric_matches_four_field_denominator(self):
        self.assertEqual(
            gs.RUBRIC['scoreable_coverage'],
            'For the four judgment fields, answered / rows with gold_status="found"; '
            'not_stated_in_docs and unresolved rows are gold-unscoreable and excluded. '
            'For the two rule fields, all sampled rows are scoreable by convention: '
            'Composio toolkit status comes from the saved catalog snapshot and verdict is rule-derived.'
        )
        with (ROOT / 'gold_template.csv').open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        found_only = sum(row['gold_status'] == 'found' for row in rows)
        self.assertEqual(found_only, 60)

        published = json.loads((ROOT / 'gold_ratings_v4.json').read_text(encoding='utf-8'))
        self.assertEqual(published['rubric']['scoreable_coverage'], gs.RUBRIC['scoreable_coverage'])
        final = published['overall']['pass3']['judgment_fields']
        self.assertEqual((final['total'], final['scoreable'], final['answered']), (80, found_only, 60))
        self.assertEqual(published['per_field']['pass3']['composio_toolkit']['scoreable'], 20)
        self.assertEqual(published['per_field']['pass3']['verdict']['scoreable'], 20)

    def test_sampled_and_scoreable_denominators_are_distinct(self):
        ratings = ['correct'] * 37 + ['partial'] * 23 + ['unresolved'] * 20
        result = gs.summarise(ratings, scoreable_total=60)
        self.assertEqual((result['total'], result['scoreable'], result['answered']), (80, 60, 60))
        self.assertEqual(result['coverage'], 0.75)
        self.assertEqual(result['scoreable_coverage'], 1.0)
        self.assertAlmostEqual(result['precision_strict'], 37 / 60, places=3)
        self.assertEqual(result['precision_half'], 0.8083)
        self.assertEqual(result['fixed_half'], 0.6062)
        self.assertEqual(result['incorrect'], 0)
        self.assertIsNone(result['half_ci'])

    def test_zero_answer_metrics_are_defined_without_division_by_zero(self):
        result = gs.summarise(['abstained'] * 60 + ['unresolved'] * 20, scoreable_total=60)
        self.assertEqual(result['coverage'], 0.0)
        self.assertEqual(result['scoreable_coverage'], 0.0)
        self.assertIsNone(result['precision_strict'])
        self.assertIsNone(result['precision_half'])
        self.assertEqual(result['strict_ci'], [None, None])


if __name__ == '__main__':
    unittest.main()
