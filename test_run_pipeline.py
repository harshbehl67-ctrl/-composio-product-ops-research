"""Offline and orchestration tests for the reproducible one-app runner."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_one
import run_pipeline as pipeline


class PipelineSelection(unittest.TestCase):
    def test_named_app_and_limit_selection(self):
        self.assertEqual([x['name'] for x in pipeline.select_apps('Google Ads', None)], ['Google Ads'])
        self.assertEqual(len(pipeline.select_apps(None, 3)), 3)
        with self.assertRaises(ValueError):
            pipeline.select_apps('not assigned', None)
        with self.assertRaises(ValueError):
            pipeline.select_apps(None, 101)

    def test_discovery_summary_keeps_unknowns_and_review_boundary(self):
        app = pipeline.APPS[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{app['number']:03}.json"
            path.write_text(json.dumps({
                'search_results': [{'url': 'https://example.org'}],
                'retrievals': [{'status': 200}],
                'errors': [],
                'first_pass': {'auth': 'unknown'},
                'validation_errors': ['review required'],
            }), encoding='utf-8')
            summary = pipeline.summarize_discovery(path, app, 'test')
        self.assertEqual(summary['first_pass_claims']['auth'], 'unknown')
        self.assertTrue(summary['manual_review_required'])
        self.assertTrue(summary['claims_require_manual_review'])

    def test_offline_run_calls_only_cached_verifier(self):
        app = next(x for x in pipeline.APPS if x['name'] == 'Google Ads')
        payload = {
            'verification': {'urls_checked': 3, 'urls_live': 0, 'first_party_urls': 3,
                             'quotes_checked': 2, 'quotes_reproduced': 0},
            'composio_catalog': {'in_composio': True},
            'auth_crosscheck': {'comparison': 'agree'},
        }
        completed = type('Completed', (), {'stdout': json.dumps(payload)})()
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline.subprocess, 'run', return_value=completed) as mocked_run:
            result, code = pipeline.run_app(app, 'offline', Path(directory), False)
            self.assertEqual(code, 0)
            self.assertEqual(len(mocked_run.call_args.args[0]), 5)
            self.assertIn('--offline', mocked_run.call_args.args[0])
            self.assertNotIn('research.py', ' '.join(mocked_run.call_args.args[0]))
            saved = json.loads((Path(directory) / 'google-ads.json').read_text(encoding='utf-8'))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(saved['checked_claim_verification']['urls_live_200'], 0)
        self.assertIn('does not validate the fresh discovery text', saved['checked_claim_verification']['interpretation'])

    def test_live_run_keeps_discovery_and_saved_verification_separate(self):
        app = next(x for x in pipeline.APPS if x['name'] == 'Google Ads')
        verify_payload = {
            'verification': {'urls_checked': 1, 'urls_live': 1, 'first_party_urls': 1,
                             'quotes_checked': 1, 'quotes_reproduced': 1},
            'composio_catalog': {'in_composio': True},
            'auth_crosscheck': {'comparison': 'agree'},
        }
        def fake_run(command, cwd, check, capture_output, text):
            if 'research.py' in command[1]:
                out_index = command.index('--output-dir') + 1
                output_dir = Path(command[out_index])
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / f"{app['number']:03}.json").write_text(json.dumps({
                    'search_results': [], 'retrievals': [], 'errors': [],
                    'first_pass': {'auth': 'unknown'}, 'validation_errors': ['review required'],
                }), encoding='utf-8')
                return type('Completed', (), {'stdout': ''})()
            return type('Completed', (), {'stdout': json.dumps(verify_payload)})()
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline.subprocess, 'run', side_effect=fake_run):
            result, code = pipeline.run_app(app, 'live', Path(directory), False)
            self.assertEqual(code, 0)
        self.assertEqual(result['discovery']['status'], 'collected')
        self.assertEqual(result['checked_claim_verification']['basis'], 'existing checked_dataset_v4.json record')
        self.assertTrue(result['human_review_required'])


class OfflineNetworkBoundary(unittest.TestCase):
    def test_run_one_offline_does_not_make_http_requests(self):
        stdout = io.StringIO()
        with patch('sys.argv', ['run_one.py', '--app', 'Google Ads', '--offline']), \
                patch.object(run_one.requests, 'get', side_effect=AssertionError('offline made a request')):
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(run_one.main(), 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload['verification']['offline'])
        self.assertEqual(payload['verification']['urls_live'], 0)


if __name__ == '__main__':
    unittest.main()
