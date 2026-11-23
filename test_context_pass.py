import unittest
import context_pass


class ContextValidation(unittest.TestCase):
    def test_negated_vendor_server_is_not_positive(self):
        result, _, _ = context_pass.classify_mcp('Aircall MCP FAQ', "As of this writing we don't offer an MCP servier.", 'Aircall')
        self.assertTrue(result.startswith('no'))

    def test_postposed_negation_is_not_positive(self):
        result, _, _ = context_pass.classify_mcp('Aircall MCP server', 'The Aircall MCP server is not available.', 'Aircall')
        self.assertTrue(result.startswith('no'))

    def test_external_client_is_not_vendor_server(self):
        result, _, _ = context_pass.classify_mcp('Announcing the general availability of the MCP client', 'Connect Zendesk to an MCP server from other vendors.', 'Zendesk')
        self.assertEqual(result, 'unknown')

    def test_notion_agent_connection_is_not_server(self):
        result, _, _ = context_pass.classify_mcp('Connect MCP Servers to your Notion Agent', 'Connect to external MCP servers.', 'Notion')
        self.assertEqual(result, 'unknown')

    def test_explicit_vendor_server_positive(self):
        result, _, _ = context_pass.classify_mcp('Slack MCP server overview', 'The Slack MCP server enables workspace actions.', 'Slack')
        self.assertTrue(result.startswith('yes'))

    def test_client_negation_does_not_negate_vendor_server(self):
        text = "The GitHub MCP Server is available. If your MCP host does not support remote MCP servers, use the local version."
        result, _, _ = context_pass.classify_mcp('GitHub MCP server', text, 'GitHub')
        self.assertTrue(result.startswith('yes'))

    def test_catalog_does_not_establish_vendor_mcp(self):
        app = next(a for a in context_pass.prior.APPS if a['name'] == 'Slack')
        fields = context_pass.extract(app, [])
        self.assertEqual(fields['composio_toolkit']['value'], 'listed')
        self.assertEqual(fields['official_mcp']['value'], 'unknown')

    def test_graphql_admin_api_and_scoped_basic(self):
        app = next(a for a in context_pass.prior.APPS if a['name'] == 'Slack')
        page = {'status': 200, 'url': 'https://docs.slack.dev/authentication/test', 'title': 'Authentication API',
                'text': 'GraphQL Admin API. Use Basic authentication for OAuth client_id and client_secret.'}
        fields = context_pass.extract(app, [page])
        self.assertIn('GraphQL', fields['api_surface']['value'])
        self.assertIn('Basic authentication (OAuth client or endpoint-specific)', fields['auth']['value'])

    def test_negated_rest_is_not_classified_as_rest(self):
        app = next(a for a in context_pass.prior.APPS if a['name'] == 'Slack')
        page = {'status': 200, 'url': 'https://docs.slack.dev/apis/web-api/', 'title': 'Slack Web API',
                'text': "While it's not a REST API, it uses HTTP."}
        fields = context_pass.extract(app, [page])
        self.assertEqual(fields['api_surface']['value'], 'unknown')

    def test_no_review_required_is_not_an_approval_gate(self):
        app = next(a for a in context_pass.prior.APPS if a['name'] == 'Intercom')
        page = {'status': 200, 'url': 'https://developers.intercom.com/docs', 'title': 'Intercom API',
                'text': 'You can build a private app using your Access Token and it does not require a review.'}
        self.assertEqual(context_pass.extract(app, [page])['credential_gate']['value'], 'unknown')

    def test_comparison_blog_does_not_attribute_competitor_trial(self):
        app = next(a for a in context_pass.prior.APPS if a['name'] == 'Plain')
        page = {'status': 200, 'url': 'https://www.plain.com/blog/api-first-support-platforms', 'title': 'API comparison',
                'text': 'Plain, Zendesk and Intercom comparison. 7-day free trial. Zendesk REST API.'}
        self.assertEqual(context_pass.extract(app, [page])['credential_gate']['value'], 'unknown')


if __name__ == '__main__':
    unittest.main()
