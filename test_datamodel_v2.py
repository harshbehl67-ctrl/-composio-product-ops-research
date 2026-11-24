import unittest

import datamodel_v2 as model


class DataModelV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.log = model.build()
        cls.counts = model.validate(cls.records)

    def test_validation_passes_and_has_100_apps(self):
        self.assertEqual(len(self.records), 100)
        self.assertEqual(len({record['app'] for record in self.records}), 100)

    def test_controlled_vocabularies(self):
        for record in self.records:
            self.assertIn(record['prototype_access'], model.ACCESS_VALUES)
            self.assertIn(record['production_access'], model.ACCESS_VALUES)
            self.assertIn(record['mcp_tier'], model.MCP_TIERS)
            self.assertIn(record['in_composio'], model.IN_COMPOSIO_VALUES)
            self.assertIn(record['effort_tier'], model.EFFORT_VALUES)
            self.assertIn(record['blocker'], model.BLOCKERS)
            self.assertIn(record['confidence'], model.CONFIDENCE_VALUES)

    def test_category_counts_sum_to_100(self):
        for field in ('prototype_access', 'production_access', 'mcp_tier', 'in_composio',
                      'effort_tier', 'blocker', 'confidence', 'verdict'):
            self.assertEqual(sum(self.counts[field].values()), 100, field)

    def test_documented_candidates_and_easy_wins(self):
        self.assertEqual(self.counts['documented_build_candidate'], 64)
        self.assertEqual(self.counts['easy_wins'], 60)
        self.assertEqual(self.counts['easy_win_excluded'], ['Grain', 'NotebookLM', 'SendGrid', 'Twenty'])

    def test_what_it_does_is_short_and_present(self):
        for record in self.records:
            self.assertTrue(record['what_it_does'])
            self.assertLessEqual(len(record['what_it_does']), 80, record['app'])
            self.assertLessEqual(len(record['what_it_does'].split()), 10, record['app'])

    def test_auth_chips_non_empty(self):
        for record in self.records:
            self.assertTrue(record['auth_chips'])

    def test_build_next_are_easy_wins_missing_from_composio(self):
        rows = model.build_next(self.records)
        self.assertEqual(len(rows), 7)
        for row in rows:
            record = next(item for item in self.records if item['app'] == row['app'])
            self.assertEqual(record['in_composio'], 'none')
            self.assertEqual(record['verdict'], 'documented_build_candidate')
            self.assertIn(record['production_access'], ('self_serve_free', 'self_serve_trial'))

    def test_mixed_apps_are_split_and_logged(self):
        logged = {entry['app'] for entry in self.log if 'prototype_access' in entry['field']}
        self.assertTrue(set(model.MIXED_SPLIT) <= logged)

    def test_mcp_tier_overrides_are_logged(self):
        logged = {entry['app'] for entry in self.log if entry['field'] == 'mcp_tier'}
        self.assertEqual(logged, set(model.MCP_OVERRIDE))

    def test_retiered_mcp_from_saved_evidence(self):
        by_app = {record['app']: record for record in self.records}
        self.assertEqual(by_app['Google Ads']['mcp_tier'], 'local')
        self.assertEqual(by_app['Brex']['mcp_tier'], 'beta')
        self.assertEqual(by_app['Lark (Larksuite)']['mcp_tier'], 'local')
        self.assertEqual(by_app['Pinterest']['mcp_tier'], 'prelaunch')
        self.assertEqual(by_app['NotebookLM']['mcp_tier'], 'beta')
        self.assertEqual(by_app['Shopify']['mcp_tier'], 'local')

    def test_auth_chips_match_named_evidence(self):
        by_app = {record['app']: set(record['auth_chips']) for record in self.records}
        self.assertEqual(by_app['Vercel'], {'api_key_or_pat'})
        self.assertEqual(by_app['Google Ads'], {'oauth2_user', 'oauth2_service_account'})
        self.assertEqual(by_app['Snowflake'], {'api_key_or_pat', 'jwt_signed', 'oauth2_user'})
        self.assertEqual(by_app['Binance'], {'api_key_or_pat', 'signed_request'})
        self.assertEqual(by_app['Amazon Selling Partner'], {'oauth2_user', 'oauth2_client_creds'})
        for name in ('Intercom', 'GoHighLevel', 'Ecwid', 'Gumroad'):
            self.assertIn('api_key_or_pat', by_app[name], name)


if __name__ == '__main__':
    unittest.main()
