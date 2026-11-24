"""Phase 3 checks: verification.json is well-formed and self-consistent."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERIFICATION = json.loads((ROOT / 'verification.json').read_text(encoding='utf-8'))
FIELDS = ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')


class VerificationV4(unittest.TestCase):
    def test_labels_are_present_and_disclosed(self):
        labels = VERIFICATION['labels']
        self.assertNotIn('blind', labels)
        self.assertEqual(labels['provenance']['gold_labels']['actor_type'], 'AI')
        self.assertEqual(labels['provenance']['gold_labels']['labeler_identity'], 'not recorded')
        self.assertFalse(labels['provenance']['gold_labels']['agent_answer_exposure']['independently_verified'])
        self.assertEqual(labels['provenance']['gold_labels']['earlier_chat_label_exclusion']['status'], 'unverified')
        self.assertIn('model and session identities were not recorded', labels['disclosure'])
        self.assertEqual(labels['gold_rows_filled'], labels['gold_rows_total'])
        self.assertEqual(labels['n'], 120)
        self.assertEqual(labels['selected'] + labels['holdout'], 120)

    def test_three_passes_over_120_claims(self):
        self.assertEqual(set(VERIFICATION['passes']), {'pass1', 'pass2', 'pass3'})
        for source in ('pass1', 'pass2', 'pass3'):
            combined = VERIFICATION['passes'][source]['combined']
            self.assertEqual(combined['n'], 120)
            counts = combined['counts']
            self.assertEqual(sum(counts.values()), 120)
            self.assertEqual(combined['answered'] + counts['abstained'], 120)
            self.assertEqual(combined['resolved'], counts['correct'] + counts['partial'] + counts['incorrect'])
            self.assertEqual(combined['answered'] - counts['unresolved'], combined['resolved'])

    def test_per_field_and_per_cohort_cover_twenty_and_sixty(self):
        for source in ('pass1', 'pass2', 'pass3'):
            entry = VERIFICATION['passes'][source]
            self.assertEqual(set(entry['by_field']), set(FIELDS))
            for field, summary in entry['by_field'].items():
                self.assertEqual(summary['n'], 20, field)
            for cohort, summary in entry['by_cohort'].items():
                self.assertEqual(summary['n'], 60, cohort)

    def test_wilson_intervals_are_valid(self):
        for source in ('pass1', 'pass2', 'pass3'):
            summary = VERIFICATION['passes'][source]['combined']
            for key in ('coverage', 'precision_strict_resolved', 'overall_fixed_strict'):
                value = summary[key]
                ci = summary[f'{key}_ci95']
                self.assertIsNotNone(value)
                self.assertEqual(len(ci), 2)
                self.assertLessEqual(ci[0], value + 1e-9)
                self.assertGreaterEqual(ci[1], value - 1e-9)
                self.assertGreaterEqual(ci[0], 0.0)
                self.assertLessEqual(ci[1], 1.0)

    def test_six_loops_are_logged_with_artifacts(self):
        loops = VERIFICATION['loops']
        self.assertEqual({loop['id'] for loop in loops}, {'i', 'ii', 'iii', 'iv', 'v', 'vi'})
        for loop in loops:
            self.assertTrue(loop['artifact'])
            self.assertIn(loop['kind'], ('automated', 'saved_review_record'))
            self.assertIn(loop['actor_type'], ('script', 'not recorded'))
        saved_review = next(loop for loop in loops if loop['id'] == 'iv')
        self.assertEqual(saved_review['actor_type'], 'not recorded')
        self.assertNotIn('Independent verifier agent', saved_review['name'])
        self.assertIn('reviewer identity is not recorded', saved_review['result'])
        self.assertNotIn('human', saved_review['kind'])

    def test_failure_taxonomy_has_causes_and_loops(self):
        taxonomy = VERIFICATION['failure_taxonomy']
        self.assertTrue(taxonomy)
        for entry in taxonomy:
            self.assertIn(entry['final_rating'], ('partial', 'incorrect'))
            self.assertTrue(entry['cause'])
            self.assertTrue(entry['fixed_by_loop'])

    def test_surprise_audit_covers_ten_live_checks(self):
        audit = VERIFICATION['surprise_audit']
        self.assertEqual(len(audit), 10)
        for entry in audit:
            self.assertTrue(entry['app'])
            self.assertIn('live', entry)
            self.assertIn(entry['live'].get('reproduced'), (True, False, None))

    def test_every_summary_number_is_derivable(self):
        # precision and overall must equal the integer counts they claim to come from.
        for source in ('pass1', 'pass2', 'pass3'):
            combined = VERIFICATION['passes'][source]['combined']
            counts = combined['counts']
            self.assertAlmostEqual(combined['coverage'], combined['answered'] / 120)
            self.assertAlmostEqual(combined['precision_strict_resolved'],
                                   counts['correct'] / combined['resolved'])
            self.assertAlmostEqual(combined['overall_fixed_strict'], counts['correct'] / 120)
            self.assertAlmostEqual(combined['overall_fixed_half'],
                                   (counts['correct'] + 0.5 * counts['partial']) / 120)

    def test_label_provenance_and_coverage_wording_do_not_claim_verified_blinding(self):
        self.assertNotIn('blind', VERIFICATION['labels'])
        self.assertIn('answered/80', VERIFICATION['wilson_note'])
        self.assertIn('six unresolved gold rows', VERIFICATION['wilson_note'])


if __name__ == '__main__':
    unittest.main()
