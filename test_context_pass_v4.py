import unittest

import context_pass_v4 as pipeline
import verify_checked_sources as source_check


class ContextValidationV4(unittest.TestCase):
    def test_negated_vendor_server_is_not_positive(self):
        value, _, _ = pipeline.classify_mcp('Aircall MCP FAQ', "As of this writing we don't offer an MCP server.", 'Aircall')
        self.assertEqual(value, 'no_vendor_server_documented')

    def test_postposed_negation_is_not_positive(self):
        value, _, _ = pipeline.classify_mcp('Aircall MCP server', 'The Aircall MCP server is not available.', 'Aircall')
        self.assertEqual(value, 'no_vendor_server_documented')

    def test_external_client_is_not_vendor_server(self):
        value, _, _ = pipeline.classify_mcp('Zendesk MCP client', 'Connect Zendesk to an MCP server from other vendors.', 'Zendesk')
        self.assertEqual(value, 'client_only')

    def test_notion_agent_connection_is_client_only(self):
        value, _, _ = pipeline.classify_mcp('Connect MCP Servers to your Notion Agent', 'Connect to external MCP servers.', 'Notion')
        self.assertEqual(value, 'client_only')

    def test_explicit_vendor_server_positive(self):
        value, _, _ = pipeline.classify_mcp('Slack MCP server overview', 'The Slack MCP server enables workspace actions.', 'Slack')
        self.assertEqual(value, 'vendor_server')

    def test_client_negation_does_not_negate_vendor_server(self):
        text = 'The GitHub MCP Server is available. If your MCP host does not support remote MCP servers, use the local version.'
        value, _, _ = pipeline.classify_mcp('GitHub MCP server', text, 'GitHub')
        self.assertEqual(value, 'vendor_server')

    def test_composio_source_cannot_establish_vendor_mcp(self):
        value, _, _ = pipeline.classify_mcp('Slack toolkit', 'The Slack MCP server enables actions.', 'Slack', 'https://docs.composio.dev/toolkits/slack')
        self.assertEqual(value, 'unknown')

    def test_api_negation_and_breadth(self):
        text = "While it's not a REST API, the HTTP API supports users, messages, channels, files, projects, issues, tasks, events and payments."
        self.assertEqual(pipeline.api_types(text), ['HTTP API'])
        self.assertEqual(pipeline.api_breadth(text, pipeline.api_types(text)), 'broad')

    def test_no_review_required_is_not_an_approval_gate(self):
        self.assertEqual(pipeline.credential_gate('You can build a private app and it does not require a review.'), [])

    def test_requestbin_example_is_not_vendor_auth(self):
        methods = pipeline.auth_methods('Use OAuth 2.0. RequestBin accepts a Bearer token and an API key from your RequestBin account.')
        self.assertEqual(methods, ['OAuth 2.0'])

    def test_comparison_blog_gate_is_not_attributed(self):
        app = next(app for app in pipeline.prior.APPS if app['name'] == 'Plain')
        page = {'status': 200, 'url': 'https://www.plain.com/blog/api-first-support-platforms', 'title': 'API comparison',
                'text': 'Plain, Zendesk and Intercom comparison. 7-day free trial. Zendesk REST API.'}
        self.assertEqual(pipeline.extract(app, [page])['credential_gate']['value'], 'unknown')

    def test_official_pricing_page_is_allowed(self):
        self.assertTrue(pipeline.official_source('https://www.pipedrive.com/en/pricing', 'Pipedrive', 'credential_gate'))

    def test_checked_claim_requires_official_evidence(self):
        record = {'number': 1, 'app': 'Salesforce', 'category': 'CRM and Sales', 'summary': 'CRM platform.',
                  'fields': {field: {'value': 'unknown', 'status': 'unknown', 'reason': 'Targeted official documentation did not resolve this field.',
                                     'evidence': [{'url': 'https://www.salesforce.com/', 'quote': ''}]} for field in pipeline.FIELDS},
                  'blocker': 'Documentation review incomplete.', 'next_action': 'Open the official API authentication guide.'}
        record['fields']['auth'].update(value=['OAuth 2.0'], status='checked', reason='OAuth is documented.',
            evidence=[{'url': 'https://example.com/auth', 'quote': 'OAuth 2.0 is supported.', 'published_at': None, 'published_label': None}])
        errors = pipeline.validate_record(record)
        self.assertTrue(any('not recognized as official' in error for error in errors))

    def test_unknown_requires_specific_reason_and_attempt(self):
        record = {'number': 1, 'app': 'Salesforce', 'category': 'CRM and Sales', 'summary': 'CRM platform.',
                  'fields': {field: {'value': 'unknown', 'status': 'unknown', 'reason': 'No docs.', 'evidence': []} for field in pipeline.FIELDS},
                  'blocker': 'Unknown.', 'next_action': 'Research.'}
        errors = pipeline.validate_record(record)
        self.assertTrue(any('reason is not specific' in error for error in errors))
        self.assertTrue(any('lacks attempted-source' in error for error in errors))

    def test_unknown_status_cannot_retain_positive_classification_metadata(self):
        record = {'number': 1, 'app': 'Salesforce', 'category': 'CRM and Sales', 'summary': 'CRM platform.',
                  'fields': {field: {'value': 'unknown', 'status': 'unknown', 'reason': 'Targeted official documentation did not resolve this field.',
                                     'evidence': [{'url': 'https://www.salesforce.com/', 'quote': ''}]} for field in pipeline.FIELDS},
                  'blocker': 'Unknown.', 'next_action': 'Research official documentation.'}
        record['fields']['credential_gate']['gate_class'] = 'paid_plan'
        record['fields']['api_surface'].update(api_types=['REST'], breadth='broad')
        errors = pipeline.validate_record(record)
        self.assertTrue(any('positive gate_class' in error for error in errors))
        self.assertTrue(any('cannot retain API types' in error for error in errors))
        self.assertTrue(any('positive breadth' in error for error in errors))

    def test_vendor_mcp_contradiction_is_rejected(self):
        record = {'number': 11, 'app': 'Zendesk', 'category': 'Support and Helpdesk', 'summary': 'Support platform.',
                  'fields': {field: {'value': 'unknown', 'status': 'unknown', 'reason': 'Targeted official documentation did not resolve this field.',
                                     'evidence': [{'url': 'https://www.zendesk.com/', 'quote': ''}]} for field in pipeline.FIELDS},
                  'blocker': 'None documented.', 'next_action': 'Validate OAuth credentials.'}
        record['fields']['official_mcp'].update(value='vendor_server', status='checked', mcp_mode='remote',
            reason='The page is undated; checked on 2026-11-24.', evidence=[{'url': 'https://developer.zendesk.com/mcp-client',
            'title': 'Zendesk MCP client', 'quote': 'Connect Zendesk to an MCP server from other vendors.',
            'published_at': None, 'published_label': None}])
        errors = pipeline.validate_record(record)
        self.assertTrue(any('contradicts client-only' in error for error in errors))

    def test_credential_shaped_quote_is_rejected(self):
        record = {'number': 1, 'app': 'Salesforce', 'category': 'CRM and Sales', 'summary': 'CRM platform.',
                  'fields': {field: {'value': 'unknown', 'status': 'unknown', 'reason': 'Targeted official documentation did not resolve this field.',
                                     'evidence': [{'url': 'https://www.salesforce.com/', 'quote': ''}]} for field in pipeline.FIELDS},
                  'blocker': 'None documented.', 'next_action': 'Validate credentials.'}
        record['fields']['auth'].update(value=['Bearer token'], status='checked', reason='Bearer authentication is documented.',
            evidence=[{'url': 'https://www.salesforce.com/', 'quote': 'Authorization: Bearer ' + 'A' * 32,
            'retrieved_at': '2026-11-24', 'published_at': None, 'published_label': None}])
        errors = pipeline.validate_record(record)
        self.assertTrue(any('credential-shaped bearer' in error for error in errors))

    def test_checked_verdict_requires_three_inputs(self):
        record = {'number': 1, 'app': 'Salesforce', 'category': 'CRM and Sales', 'summary': 'CRM platform.',
                  'fields': {field: {'value': 'unknown', 'status': 'unknown', 'reason': 'Targeted official documentation did not resolve this field.',
                                     'evidence': [{'url': 'https://www.salesforce.com/', 'quote': ''}]} for field in pipeline.FIELDS},
                  'blocker': 'None documented.', 'next_action': 'Validate credentials.'}
        record['fields']['verdict'].update(value='documented_build_candidate', status='checked',
            reason='The source is undated; checked on 2026-11-24.', evidence=[{'url': 'https://www.salesforce.com/',
            'quote': 'Developer access is documented.', 'published_at': None, 'published_label': None}])
        errors = pipeline.validate_record(record)
        self.assertTrue(any('requires checked auth, gate and API' in error for error in errors))
    def test_verified_official_docs_domains_and_repositories(self):
        self.assertTrue(pipeline.official_source('https://raw.githubusercontent.com/firecrawl/firecrawl-docs/main/billing.mdx', 'Firecrawl', 'credential_gate'))
        self.assertFalse(pipeline.official_source('https://raw.githubusercontent.com/example/firecrawl-docs/main/billing.mdx', 'Firecrawl', 'credential_gate'))
        self.assertTrue(pipeline.official_source('https://docs.superhuman.com/api-reference', 'Coda', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://help.getharvest.com/api-v2/', 'Harvest', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://developers.fathom.ai/api-overview', 'Fathom', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://mermaid.js.org/config/mermaidCLI.html', 'Mermaid CLI', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://sherlockproject.xyz/installation', 'Sherlock', 'auth'))
        self.assertTrue(pipeline.official_source('https://mcp.sentry.dev/', 'Sentry', 'official_mcp'))
        self.assertFalse(pipeline.official_source('https://www.paygent.com', 'Paygent Connect', 'auth'))
        self.assertTrue(pipeline.official_source('https://www.gopaygent.com/developers/docs', 'Paygent Connect', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://marketplace.gohighlevel.com/docs/', 'GoHighLevel', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://dev.frontapp.com/docs/mcp-server', 'Front', 'official_mcp'))
        self.assertTrue(pipeline.official_source('https://www.progress.com/podio/documentation/using-podio/ai-and-mcp/podio-mcp-server-integration-guide', 'Podio', 'official_mcp'))
        self.assertTrue(pipeline.official_source('https://www.aboutamazon.com/news/innovation-at-amazon/seller-assistant-plugin-amazon-quick-claude', 'Amazon Selling Partner', 'official_mcp'))
        self.assertTrue(pipeline.official_source('https://developer.amazonservices.com/amazon-selling-partner-plugin', 'Amazon Selling Partner', 'official_mcp'))
        self.assertTrue(pipeline.official_source('https://www.twilio.com/docs/ai/mcp', 'SendGrid', 'official_mcp'))
        self.assertTrue(pipeline.official_source('https://commas.com/fanbasis-is-now-commas', 'fanbasis', 'auth'))

    def test_shared_code_hosts_require_exact_official_ownership(self):
        self.assertFalse(pipeline.official_source('https://attacker.github.io/docs', 'Binance', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://binance-docs.github.io/docs', 'Binance', 'api_surface'))
        self.assertFalse(pipeline.official_source('https://github.com/sherlock-project/sherlock-evil', 'Sherlock', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://github.com/sherlock-project/sherlock', 'Sherlock', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://api.github.com/repos/sherlock-project/sherlock/git/trees/master?recursive=1', 'Sherlock', 'api_surface'))
        self.assertFalse(pipeline.official_source('https://api.github.com/repos/sherlock-project/sherlock-evil', 'Sherlock', 'api_surface'))
        self.assertFalse(pipeline.official_source('https://github.com/mermaid-js/mermaid-cli-evil', 'Mermaid CLI', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://docs.github.com/rest', 'GitHub', 'api_surface'))
        self.assertTrue(pipeline.official_source('https://github.com/intuit/quickbooks-online-mcp-server', 'QuickBooks', 'official_mcp'))
        self.assertFalse(pipeline.official_source('https://github.com/intuit/quickbooks-online-mcp-server-evil', 'QuickBooks', 'official_mcp'))

    def test_source_quote_match_ignores_markup_and_punctuation_spacing(self):
        page = 'The API uses OAuth 2.0. Open the developer console. Use `Authorization` headers.'
        quote = 'The API uses OAuth 2.0. Open the developer console . Use Authorization headers.'
        self.assertTrue(source_check.contains_tokens(source_check.tokens(page), source_check.tokens(quote)))

    def test_source_quote_match_ignores_markdown_links_and_hyphen_variants(self):
        page = 'The REST API provides developer-friendly access to meeting insights.'
        quote = 'The [REST](https://example.com/rest) API provides developer‑friendly access to meeting insights.'
        self.assertTrue(source_check.contains_tokens(source_check.tokens(page), source_check.tokens(quote)))

    def test_source_quote_match_does_not_accept_changed_words(self):
        page = 'The API uses OAuth 2.0 and requires a bearer token.'
        quote = 'The API uses OAuth 2.0 and requires an API key.'
        self.assertFalse(source_check.contains_tokens(source_check.tokens(page), source_check.tokens(quote)))

    def test_markdown_fallback_preserves_query_and_skips_markdown_urls(self):
        self.assertEqual(source_check.markdown_url('https://example.com/docs/api?version=2'),
                         'https://example.com/docs/api.md?version=2')
        self.assertIsNone(source_check.markdown_url('https://example.com/docs/api.md'))

    def test_quote_verification_excludes_hidden_html_and_raw_scripts(self):
        page = source_check.visible_text('<main>Visible API sentence.</main><p hidden>Hidden sentence.</p>'
                                         '<p style="display:none">Styled hidden sentence.</p>'
                                         '<p class="js-hidden">Class hidden sentence.</p>'
                                         '<p aria-hidden="true">ARIA hidden sentence.</p>'
                                         '<script>Script sentence.</script>')
        self.assertEqual(page, 'Visible API sentence.')
        self.assertFalse(source_check.raw_artifact_allowed('https://example.com/docs', 'text/html'))
        self.assertTrue(source_check.raw_artifact_allowed('https://example.com/docs.md', 'text/html'))
        self.assertTrue(source_check.raw_artifact_allowed('https://example.com/docs', 'text/markdown'))
        self.assertTrue(source_check.raw_artifact_allowed('https://example.com/health', 'application/json'))
        self.assertTrue(source_check.raw_artifact_allowed('https://example.com/sitemap.xml', 'application/xml'))
        self.assertFalse(source_check.raw_artifact_allowed('https://example.com/docs', 'text/html'))

    def test_non_200_source_passes_only_when_all_checked_uses_are_browser_kept(self):
        kept = {'app': 'Example', 'field': 'auth', 'claim_status': 'checked',
                'manual_review': {'decision': 'keep'}}
        unreviewed = {'app': 'Example', 'field': 'api_surface', 'claim_status': 'checked'}
        self.assertFalse(source_check.checked_http_failure({'status': 403, 'uses': [kept]}))
        self.assertTrue(source_check.checked_http_failure({'status': 403, 'uses': [kept, unreviewed]}))

    def test_source_decode_uses_utf8_when_server_omits_charset(self):
        response = source_check.requests.Response()
        response._content = 'Cloudflare — MCP server'.encode('utf-8')
        response.headers['content-type'] = 'text/html'
        response.encoding = 'ISO-8859-1'
        self.assertEqual(source_check.decoded_text(response), 'Cloudflare — MCP server')

    def test_scoped_documentation_review_supports_no_vendor_server(self):
        record = {'number': 1, 'app': 'Salesforce', 'category': 'CRM and Sales', 'summary': 'CRM platform.',
                  'fields': {field: {'value': 'unknown', 'status': 'unknown', 'reason': 'Targeted official documentation did not resolve this field.',
                                     'evidence': [{'url': 'https://www.salesforce.com/', 'quote': ''}]} for field in pipeline.FIELDS},
                  'blocker': 'Unknown.', 'next_action': 'Research official documentation.'}
        record['fields']['composio_toolkit']['evidence'] = [{'url': 'https://docs.composio.dev/toolkits.md', 'quote': ''}]
        record['fields']['official_mcp'].update(value='no_vendor_server_documented', status='checked', mcp_mode='unknown',
            review_basis='scoped_documentation_review',
            reason='Scoped documentation review found no vendor server documented in the reviewed official pages; this is not a universal absence claim. Sources are undated.',
            evidence=[{'url': 'https://www.salesforce.com/docs', 'title': 'API reference', 'quote': 'The API reference documents REST endpoints.',
                       'retrieved_at': '2026-11-24', 'published_at': None, 'published_label': 'undated'},
                      {'url': 'https://www.salesforce.com/auth', 'title': 'Authentication', 'quote': 'The authentication guide documents OAuth.',
                       'retrieved_at': '2026-11-24', 'published_at': None, 'published_label': 'undated'}])
        self.assertEqual(pipeline.validate_record(record), [])
        del record['fields']['official_mcp']['review_basis']
        self.assertTrue(any('review_basis' in error for error in pipeline.validate_record(record)))
        record['fields']['official_mcp']['review_basis'] = 'scoped_documentation_review'
        record['fields']['official_mcp']['evidence'][0].update(title='Salesforce MCP server', quote='The Salesforce MCP server enables CRM actions.')
        self.assertTrue(any('contradicts vendor-server' in error for error in pipeline.validate_record(record)))

    def test_not_listed_requires_complete_catalog_evidence(self):
        record = {'number': 1, 'app': 'Salesforce', 'category': 'CRM and Sales', 'summary': 'CRM platform.',
                  'fields': {field: {'value': 'unknown', 'status': 'unknown', 'reason': 'Targeted official documentation did not resolve this field.',
                                     'evidence': [{'url': 'https://www.salesforce.com/', 'quote': ''}]} for field in pipeline.FIELDS},
                  'blocker': 'None documented.', 'next_action': 'Validate official documentation.'}
        source = {'url': 'https://docs.composio.dev/toolkits.md', 'title': 'Complete Composio toolkit catalog',
                  'quote': 'Composio supports 1841 toolkits for building AI agents.', 'retrieved_at': '2026-11-24',
                  'published_at': None, 'published_label': 'undated'}
        record['fields']['composio_toolkit'].update(value='not_listed', status='checked',
            reason='The complete official catalog was searched for exact and alias names; no listing was found. The catalog is undated.',
            evidence=[source])
        self.assertEqual(pipeline.validate_record(record), [])
        record['fields']['composio_toolkit']['evidence'] = [dict(source, url='https://docs.composio.dev/toolkits/salesforce')]
        self.assertTrue(any('complete-catalog evidence' in error for error in pipeline.validate_record(record)))

    def test_checked_no_public_api_does_not_require_api_types(self):
        record = {'number': 1, 'app': 'Salesforce', 'category': 'CRM and Sales', 'summary': 'CRM platform.',
                  'fields': {field: {'value': 'unknown', 'status': 'unknown', 'reason': 'Targeted official documentation did not resolve this field.',
                                     'evidence': []} for field in pipeline.FIELDS},
                  'blocker': 'No documented public API.', 'next_action': 'Confirm whether a partner API exists.'}
        source = {'url': 'https://www.salesforce.com/', 'title': 'Salesforce API policy',
                  'quote': 'No public API is documented for this product.', 'retrieved_at': '2026-11-24',
                  'published_at': None, 'published_label': None}
        record['fields']['auth'].update(value=['No public API documented'], status='checked', reason='No public API is documented.', evidence=[source])
        record['fields']['credential_gate'].update(value='no_public_api', gate_class='no_public_api', status='checked',
            reason='The official page is undated; checked on 2026-11-24.', evidence=[source])
        record['fields']['api_surface'].update(value='No public API documented', api_types=[], breadth='no_public_api', status='checked',
            reason='No public API is documented.', evidence=[source])
        record['fields']['composio_toolkit']['evidence'] = [{'url': 'https://composio.dev/', 'quote': ''}]
        record['fields']['official_mcp']['evidence'] = [{'url': 'https://www.salesforce.com/', 'quote': ''}]
        record['fields']['verdict'].update(value='no_public_api', status='checked', reason='The official page is undated; checked on 2026-11-24.', evidence=[source])
        self.assertEqual(pipeline.validate_record(record), [])


if __name__ == '__main__':
    unittest.main()
