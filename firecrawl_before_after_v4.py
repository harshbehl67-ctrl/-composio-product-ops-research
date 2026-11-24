"""Compare direct retrieval with Firecrawl-through-Composio on hard MCP pages.

Run after authorizing Firecrawl in the current Composio session:
    python firecrawl_before_after_v4.py

The runner checks connection state before executing Firecrawl. It writes only
aggregate quote-match outcomes and page metadata, never page bodies or secrets.
"""
from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from pathlib import Path

import httpx2
import requests
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import verify_checked_sources as verifier

ROOT = Path(__file__).resolve().parent
SESSION_FILE = ROOT / 'composio_session_check.json'
DATASET_FILE = ROOT / 'checked_dataset_v4.json'
OUTPUT_FILE = ROOT / 'firecrawl_before_after_v4.json'
TARGET_APPS = ('Google Ads', 'Brex', 'Lark (Larksuite)', 'Pinterest', 'NotebookLM', 'Shopify')
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; ProductOpsResearch/4.0)'}


def parse_result(result):
    for item in result.content or []:
        if getattr(item, 'type', None) == 'text':
            try:
                return json.loads(item.text)
            except json.JSONDecodeError:
                continue
    return {}


def find_auth_link(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in ('auth_link', 'redirect_url', 'connection_url') and isinstance(item, str):
                return item
            found = find_auth_link(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_auth_link(item)
            if found:
                return found
    return None


def remote_result_code(file_path, targets):
    target_json = json.dumps(targets, ensure_ascii=True)
    return f'''import html, json, re, unicodedata
targets = json.loads({target_json!r})
payload = json.load(open({file_path!r}, encoding="utf-8"))
def normalize(text):
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("’", "'").replace("“", "\\\"").replace("”", "\\\"").replace("–", "-").replace("—", "-").replace("\\u2011", "-")
    text = re.sub(r"!?\\[([^\\]]+)\\]\\([^)]*\\)", r"\\1", text)
    return re.sub(r"\\s+", " ", text).strip()
def tokens(text):
    return re.findall(r"[^\\W_] +".replace(" ", ""), normalize(text).lower(), re.UNICODE)
def contains(page, quote):
    a, b = tokens(page), tokens(quote)
    return bool(b) and any(a[i:i+len(b)] == b for i in range(len(a)-len(b)+1))
rows = payload.get("results") or []
out = {{}}
for target in targets:
    match = next((row for row in rows if row.get("index") == targets.index(target)), None)
    response = (match or {{}}).get("response") or {{}}
    body = response.get("data") or {{}}
    body = body.get("data") or body
    markdown = body.get("markdown") or ""
    metadata = body.get("metadata") or {{}}
    out[target["app"]] = {{"status": metadata.get("statusCode"), "title": metadata.get("title"),
                          "content_chars": len(markdown), "quote_found": contains(markdown, target.get("quote", ""))}}
print(json.dumps(out))
'''


def make_targets():
    apps = json.loads(DATASET_FILE.read_text(encoding='utf-8'))
    by_name = {row['app']: row for row in apps}
    targets = []
    for name in TARGET_APPS:
        row = by_name[name]
        claim = row['fields']['official_mcp']
        evidence = next((source for source in claim.get('evidence', [])
                         if source.get('url') and source.get('quote')),
                        next((source for source in claim.get('evidence', []) if source.get('url')), None))
        if not evidence:
            raise ValueError(f'No official MCP source is recorded for {name}')
        targets.append({'app': name, 'url': evidence['url'], 'quote': evidence.get('quote', '')})
    return targets


def direct_check(target):
    row = {'status': None, 'quote_found': False}
    try:
        response = requests.get(target['url'], headers=HEADERS, timeout=30, allow_redirects=True)
        row['status'] = response.status_code
        row['final_url'] = response.url
        if response.status_code == 200 and target['quote']:
            page = verifier.visible_text(verifier.decoded_text(response))
            quote = verifier.normalize(target['quote'])
            row['quote_found'] = bool(quote and (
                quote in page or verifier.contains_tokens(verifier.tokens(page), verifier.tokens(quote))))
        row['final_url'] = response.url
        response.close()
    except Exception as exc:  # Network failures are recorded as outcomes.
        row['error_type'] = type(exc).__name__
    return row


async def main():
    load_dotenv(ROOT / '.env')
    state = json.loads(SESSION_FILE.read_text(encoding='utf-8'))
    session_id = (state.get('session') or {}).get('session_id')
    if not session_id:
        raise SystemExit('No Composio MCP session found; run composio_session_research.py first.')

    targets = make_targets()
    from composio import Composio
    endpoint = Composio().sessions.use(session_id, mcp=True).mcp
    if not endpoint.url or not endpoint.headers:
        raise SystemExit('Composio session did not return MCP connection credentials.')

    async with httpx2.AsyncClient(headers=endpoint.headers, timeout=120) as http_client:
        async with streamable_http_client(endpoint.url, http_client=http_client,
                                          terminate_on_close=False) as (read, write):
            async with ClientSession(read, write) as mcp_session:
                await mcp_session.initialize()
                tools = {tool.name for tool in (await mcp_session.list_tools()).tools}
                if 'COMPOSIO_SEARCH_TOOLS' not in tools:
                    raise SystemExit('Composio MCP search meta-tool is unavailable.')
                search_result = await mcp_session.call_tool('COMPOSIO_SEARCH_TOOLS', arguments={
                    'queries': [{'use_case': 'Scrape official MCP documentation URLs with Firecrawl for a research quote comparison.'}],
                    'session': {'generate_id': True}, 'search_strategy': 'tool_search',
                })
                search = parse_result(search_result).get('data') or {}
                workflow_session_id = ((search.get('session') or {}).get('id') or session_id)
                discovered = {slug for item in search.get('results', [])
                              for slug in (item.get('primary_tool_slugs') or [])
                              + (item.get('related_tool_slugs') or [])}
                connections = search.get('toolkit_connection_statuses') or []
                firecrawl_status = next((item for item in connections
                                         if (item.get('toolkit') or '').casefold() == 'firecrawl'), {})
                if not firecrawl_status.get('has_active_connection'):
                    manage = await mcp_session.call_tool('COMPOSIO_MANAGE_CONNECTIONS', arguments={
                        'toolkits': ['firecrawl'], 'session_id': session_id,
                    })
                    managed = parse_result(manage).get('data') or {}
                    OUTPUT_FILE.write_text(json.dumps({
                        'completed': False,
                        'reason': 'Firecrawl connection requires user authorization in Composio.',
                        'tool_discovered': 'FIRECRAWL_SCRAPE' in discovered,
                    }, ensure_ascii=False, indent=2), encoding='utf-8')
                    print('Firecrawl connection is not active; authorize this temporary Composio link, then rerun:')
                    print(find_auth_link(managed) or 'No link returned; inspect the Composio connection response.')
                    return

                if 'FIRECRAWL_SCRAPE' not in discovered:
                    raise SystemExit('Composio search did not return the Firecrawl scrape tool.')
                schema_result = await mcp_session.call_tool('COMPOSIO_GET_TOOL_SCHEMAS', arguments={
                    'tool_slugs': ['FIRECRAWL_SCRAPE'],
                    'include': ['input_schema'], 'session_id': workflow_session_id,
                })
                schemas = (parse_result(schema_result).get('data') or {}).get('tool_schemas') or {}
                scrape_schema = schemas.get('FIRECRAWL_SCRAPE', {}).get('input_schema') or {}
                if 'url' not in scrape_schema.get('properties', {}):
                    raise SystemExit('Firecrawl scrape schema did not include the required URL field.')

                before = {row['app']: direct_check(row) for row in targets}
                executions = []
                for target in targets:
                    executions.append({'tool_slug': 'FIRECRAWL_SCRAPE', 'arguments': {
                        'url': target['url'], 'formats': ['markdown'], 'onlyMainContent': True,
                    }})
                firecrawl_result = await mcp_session.call_tool('COMPOSIO_MULTI_EXECUTE_TOOL', arguments={
                    'tools': executions,
                    'thought': 'Compare direct retrieval and Firecrawl on the recorded first-party MCP evidence pages.',
                    'sync_response_to_workbench': True,
                    'current_step': 'SCRAPING_MCP_EVIDENCE',
                    'current_step_metric': f'{len(executions)}/{len(targets)} pages',
                    'session_id': workflow_session_id,
                })
                response = parse_result(firecrawl_result)
                remote_path = ((response.get('data') or {}).get('remote_file_info') or {}).get('file_path')
                if not remote_path:
                    raise RuntimeError('Composio did not return a workbench file for the full Firecrawl results.')
                workbench = await mcp_session.call_tool('COMPOSIO_REMOTE_WORKBENCH', arguments={
                    'code_to_execute': remote_result_code(remote_path, targets),
                    'thought': 'Compute quote-match outcomes from Firecrawl output; return counts and metadata only.',
                    'current_step': 'SCORING_FIRECRAWL_RESULTS',
                    'current_step_metric': f'{len(targets)}/{len(targets)} pages',
                    'session_id': workflow_session_id,
                })
                workbench_data = parse_result(workbench).get('data') or {}
                try:
                    after = json.loads(workbench_data.get('stdout') or '{}')
                except json.JSONDecodeError as exc:
                    raise RuntimeError('Could not parse the aggregate Firecrawl results from the Composio workbench.') from exc
    report = {
        'completed': len(after) == len(targets),
        'transport': 'Composio MCP → Firecrawl FIRECRAWL_SCRAPE',
        'apps': list(TARGET_APPS),
        'before': before,
        'after': after,
        'summary': {
            'direct_quote_matches': sum(bool(row.get('quote_found')) for row in before.values()),
            'firecrawl_quote_matches': sum(bool(row.get('quote_found')) for row in after.values()),
            'pages': len(targets),
        },
    }
    OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['summary'] | {'completed': report['completed']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
