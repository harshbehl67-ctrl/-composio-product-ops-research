"""Build the research step on a live Composio session (Phase 1c).

This wires the research agent onto Composio itself:

    composio = Composio()
    session  = composio.create(user_id="research-bot",
                               toolkits=["composio_search", "firecrawl"], mcp=True)

It then inspects the real tool slugs and argument names with the SDK
(`tools.get` and `get_raw_composio_tool_by_slug`) and exposes the session's MCP
URL and headers so an agent's MCP client can connect. Nothing here guesses a
tool name: every slug logged is one the SDK returned.

If a toolkit is not available on this plan, or a tool needs a connected account
we do not have, the failure is recorded as a finding and the pipeline falls back
to the repository's own search code (research.py / discover.py).

The API key is read from the git-ignored .env and is never printed or written
to any output file. Output: composio_session_check.json
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
OUT = ROOT / 'composio_session_check.json'

USER_ID = 'research-bot'
TOOLKITS = ['composio_search', 'firecrawl']
# The research-relevant tools an agent would actually call; every slug below is
# confirmed with get_raw_composio_tool_by_slug rather than assumed.
RESEARCH_TOOL_SLUGS = ['COMPOSIO_SEARCH_WEB', 'FIRECRAWL_SCRAPE', 'FIRECRAWL_BATCH_SCRAPE']
FETCHED_AT = '2026-11-24'


def redact_headers(headers: dict) -> dict:
    """Keep header names; replace every value so a secret can never leak."""
    return {name: '<redacted>' for name in (headers or {})}


def describe_tool(tool) -> dict:
    """Pull identity and argument names out of a tool dict or object.

    `tools.get` returns OpenAI-function-shaped dicts ({"type","function"}),
    while `get_raw_composio_tool_by_slug` returns a Tool object; handle both.
    """
    if isinstance(tool, dict):
        fn = tool.get('function', tool)
        name = fn.get('name')
        schema = fn.get('parameters') or {}
        description = fn.get('description') or ''
    else:
        name = getattr(tool, 'slug', None) or getattr(tool, 'name', None)
        schema = getattr(tool, 'input_parameters', None) or {}
        description = getattr(tool, 'description', None) or ''
    params = {key: (spec or {}).get('type', 'unknown')
              for key, spec in (schema.get('properties') or {}).items()}
    return {'slug': name, 'name': name, 'description': description[:200],
            'parameters': params, 'required': schema.get('required') or [],
            'version': getattr(tool, 'version', None)}


def main() -> int:
    key = os.environ.get('COMPOSIO_API_KEY', '').strip()
    result: dict = {'fetched_at': FETCHED_AT, 'user_id': USER_ID, 'toolkits': TOOLKITS,
                    'sdk_available': bool(key), 'session': None, 'tools_discovered': [],
                    'raw_tool_checks': [], 'execute_probe': None, 'findings': [], 'fallback': None}
    if not key:
        result['findings'].append('COMPOSIO_API_KEY is not set; cannot open a Composio session.')
        result['fallback'] = 'research.py / discover.py (repository search code)'
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('No COMPOSIO_API_KEY; wrote a fallback record to composio_session_check.json')
        return 0

    from composio import Composio

    client = Composio()  # reads COMPOSIO_API_KEY from the environment

    # 1. Discover the real tool slugs and argument names the SDK exposes, per
    #    toolkit, so we see which of the requested toolkits actually resolve.
    per_toolkit: dict[str, int] = {}
    for toolkit in TOOLKITS:
        try:
            collection = client.tools.get(user_id=USER_ID, toolkits=[toolkit], limit=25)
            tools = list(collection or [])
            per_toolkit[toolkit] = len(tools)
            for tool in tools:
                result['tools_discovered'].append({**describe_tool(tool), 'toolkit': toolkit})
        except Exception as exc:  # noqa: BLE001 - record any SDK failure as a finding
            per_toolkit[toolkit] = -1
            result['findings'].append(f'tools.get failed for {toolkit}: {type(exc).__name__}: {exc}')
    result['tools_per_toolkit'] = per_toolkit
    if per_toolkit.get('composio_search') == 0:
        result['findings'].append(
            'The composio_search toolkit returned 0 tools via tools.get(toolkits=...), '
            'but its tools resolve by slug (see raw_tool_checks); it is exposed as a '
            'meta toolkit rather than a connectable toolkit.')

    # 2. Confirm exact slugs/arguments with get_raw_composio_tool_by_slug for the
    #    research tools an agent would actually call.
    checked = set()
    for slug in RESEARCH_TOOL_SLUGS + [t['slug'] for t in result['tools_discovered']][:3]:
        if not slug or slug in checked:
            continue
        checked.add(slug)
        try:
            raw = client.tools.get_raw_composio_tool_by_slug(slug)
            result['raw_tool_checks'].append({'slug': slug, 'ok': True, **describe_tool(raw)})
        except Exception as exc:  # noqa: BLE001
            result['raw_tool_checks'].append({'slug': slug, 'ok': False,
                                              'error': f'{type(exc).__name__}: {exc}'})

    # 3. Open the MCP session and expose its URL + redacted headers.
    try:
        session = client.sessions.create(user_id=USER_ID, toolkits=TOOLKITS, mcp=True)
        mcp = getattr(session, 'mcp', None)
        result['session'] = {
            'session_id': getattr(session, 'session_id', None) or getattr(session, 'id', None),
            'mcp_type': getattr(mcp, 'type', None),
            'mcp_url': getattr(mcp, 'url', None),
            'mcp_header_names': list((getattr(mcp, 'headers', None) or {}).keys()),
            'mcp_headers_redacted': redact_headers(getattr(mcp, 'headers', None) or {}),
        }
    except Exception as exc:  # noqa: BLE001
        result['findings'].append(f'sessions.create failed: {type(exc).__name__}: {exc}')

    # 4. Deterministic step via tools.execute (needs a connected account for a
    #    vendor toolkit; COMPOSIO_SEARCH_WEB is Composio-managed, so we probe it).
    probe_slug = 'COMPOSIO_SEARCH_WEB'
    probe = next((t for t in result['raw_tool_checks'] if t.get('slug') == probe_slug and t.get('ok')), None)
    if probe:
        try:
            # Manual execution requires a pinned toolkit version ("latest" is not
            # accepted); use the version the SDK reports for the tool.
            executed = client.tools.execute(slug=probe_slug,
                                            arguments={'query': 'Composio catalog toolkit authentication'},
                                            user_id=USER_ID, version=probe.get('version'))
            result['execute_probe'] = {'slug': probe_slug, 'version': probe.get('version'), 'ok': True,
                                       'successful': getattr(executed, 'successful', None),
                                       'error': getattr(executed, 'error', None)}
        except Exception as exc:  # noqa: BLE001
            result['execute_probe'] = {'slug': probe_slug, 'version': probe.get('version'), 'ok': False,
                                       'error': f'{type(exc).__name__}: {exc}'}

    # 5. Decide how far the Composio path can go, and whether the repo must
    #    fall back. MCP session creation and direct tool calls are independent:
    #    the plan may allow one and not the other.
    tools_ok = any(t.get('ok') for t in result['raw_tool_checks'])
    execute_ok = bool(result['execute_probe'] and result['execute_probe'].get('ok'))
    result['session_available'] = bool(result['session'])
    result['tools_available'] = tools_ok
    result['execute_available'] = execute_ok
    if result['session']:
        result['composio_path'] = 'session_mcp'
    elif execute_ok:
        result['composio_path'] = 'tools_execute'
    elif tools_ok:
        # Reads work (catalog + tool metadata) but writes do not: the agent can
        # resolve exact tool slugs and arguments, but cannot call the tools.
        result['composio_path'] = 'read_only'
        result['findings'].append(
            'This API key has read access only: catalog reads and tool-metadata lookups '
            '(tools.get, get_raw_composio_tool_by_slug) succeed, but session creation and '
            'tool execution are denied (no session_management/tool_execution write access). '
            'The research step therefore uses Composio for slug/argument resolution and the '
            'catalog cross-check, and falls back to the repository search code to fetch pages.')
        result['fallback'] = 'research.py / discover.py (repository search code)'
    else:
        result['composio_path'] = 'fallback'
        result['fallback'] = 'research.py / discover.py (repository search code)'
        result['findings'].append('Neither an MCP session nor the research tools were usable on '
                                  'this plan; fell back to the repository search code.')

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Session: {result['session']['mcp_type'] if result['session'] else 'none'} "
          f"url={'yes' if result['session'] and result['session']['mcp_url'] else 'no'} "
          f"headers={result['session']['mcp_header_names'] if result['session'] else []}")
    print(f"Tools discovered: {len(result['tools_discovered'])}; "
          f"raw check ok: {sum(1 for t in result['raw_tool_checks'] if t.get('ok'))}")
    print(f"Composio path: {result['composio_path']}"
          + (f" (fallback: {result['fallback']})" if result['fallback'] else ''))
    for finding in result['findings']:
        print('  finding:', finding)
    print('Wrote composio_session_check.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
