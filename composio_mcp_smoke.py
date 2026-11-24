"""Connect to the current Composio session MCP endpoint and make a read-only call.

The session endpoint and auth header are retrieved at runtime and never printed
or saved. `composio_session_research.py` must create the session first.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx2
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from composio import Composio

ROOT = Path(__file__).resolve().parent
SESSION_FILE = ROOT / 'composio_session_check.json'
QUERY = ('Search for first-party API documentation and authentication requirements for Fanbasis, '
         'now Commas, to resolve whether a public API exists and how developers obtain access.')


async def main() -> None:
    load_dotenv(ROOT / '.env')
    state = json.loads(SESSION_FILE.read_text(encoding='utf-8'))
    session_id = (state.get('session') or {}).get('session_id')
    if not session_id:
        raise SystemExit('No Composio MCP session found; run composio_session_research.py first.')

    composio = Composio()
    session = composio.sessions.use(session_id, mcp=True)
    endpoint = session.mcp
    if not endpoint.url or not endpoint.headers:
        raise SystemExit('The Composio session did not return MCP connection credentials.')

    async with httpx2.AsyncClient(headers=endpoint.headers, timeout=45) as http_client:
        async with streamable_http_client(endpoint.url, http_client=http_client,
                                          terminate_on_close=False) as (read, write):
            async with ClientSession(read, write) as mcp_session:
                initialized = await mcp_session.initialize()
                tool_result = await mcp_session.list_tools()
                tool_names = [tool.name for tool in tool_result.tools]
                if 'COMPOSIO_SEARCH_WEB' not in tool_names:
                    result = await mcp_session.call_tool(
                        'COMPOSIO_SEARCH_TOOLS',
                        arguments={
                            'queries': [{'use_case': QUERY}],
                            'session': {'generate_id': True},
                            'search_strategy': 'tool_search',
                        },
                    )
                else:
                    result = await mcp_session.call_tool(
                        'COMPOSIO_SEARCH_WEB', arguments={'query': QUERY})

    text_parts = [item.text for item in (result.content or [])
                  if getattr(item, 'type', None) == 'text']
    response = {}
    if text_parts:
        try:
            response = json.loads('\n'.join(text_parts))
        except json.JSONDecodeError:
            response = {}
    response_data = response.get('data') or {}
    discovered = response_data.get('results') or []
    candidate_slugs = sorted({slug for item in discovered
                              for slug in (item.get('primary_tool_slugs') or [])
                              + (item.get('related_tool_slugs') or [])})
    connection_states = response_data.get('toolkit_connection_statuses') or []
    safe_report = {
        'connected': True,
        'transport': 'Composio hosted Streamable HTTP MCP',
        'server_name': getattr(initialized.server_info, 'name', None),
        'server_version': getattr(initialized.server_info, 'version', None),
        'tools_listed': len(tool_names),
        'tool_names': tool_names,
        'search_tool_available': 'COMPOSIO_SEARCH_WEB' in tool_names,
        'search_path': ('direct web search' if 'COMPOSIO_SEARCH_WEB' in tool_names
                        else 'Composio MCP search meta-tool'),
        'search_call_error': bool(result.is_error),
        'search_meta_call_successful': response.get('successful'),
        'query': QUERY,
        'discovered_tool_slugs': candidate_slugs,
        'toolkits_without_active_connection': [item.get('toolkit') for item in connection_states
                                               if not item.get('has_active_connection')],
    }
    print(json.dumps(safe_report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
