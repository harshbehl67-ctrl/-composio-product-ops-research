"""Shared helpers for mapping the 100 apps to their Composio catalog slug.

The dataset records a `composio_toolkit` claim per app (listed_exact,
listed_alias or not_listed) and, for listed apps, points at the Composio toolkit
page in its evidence. This module turns that evidence into the concrete slugs we
should probe, so the catalog fetch and the SDK cross-check agree on the mapping.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
# Slugs are only taken from unambiguous places: markdown links into the toolkit
# catalog (/toolkits/<slug>.md), backticked identifiers, and an explicit
# "Slug: <VALUE>" label. A loose "slug <word>" match would capture prose such as
# "the SALESFORCE slug and OAuth" and treat "and" as a slug.
MD_TOOLKIT = re.compile(r'/toolkits/([A-Za-z0-9_]+)\.md')
BACKTICKED = re.compile(r'`([A-Za-z0-9_]+)`')
SLUG_LABEL = re.compile(r'slug[:\s]+`?([A-Za-z0-9_]+)`?', re.IGNORECASE)
TOOLS_IN_QUOTE = re.compile(r'Tools:\**\s*(\d+)', re.IGNORECASE)


def slugs_in_text(text: str) -> list[str]:
    out: list[str] = []
    for match in MD_TOOLKIT.finditer(text):
        out.append(match.group(1).upper())
    for match in BACKTICKED.finditer(text):
        out.append(match.group(1).upper())
    for match in SLUG_LABEL.finditer(text):
        token = match.group(1)
        if token.isupper():  # a bare "slug and" is prose, not a slug
            out.append(token.upper())
    return out


def load_dataset() -> list[dict]:
    return json.loads((ROOT / 'checked_dataset_v4.json').read_text(encoding='utf-8'))


def normalise(name: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', name.upper())


def slug_from_url(url: str) -> str | None:
    """docs.composio.dev/toolkits/<slug> -> <slug>; the full-catalog page has no slug."""
    if not url:
        return None
    path = urlparse(url).path
    if not path.startswith('/toolkits/'):
        return None
    slug = path[len('/toolkits/'):].strip('/')
    if slug.endswith('.md'):
        slug = slug[:-3]
    if not slug or slug == 'toolkits':
        return None
    return slug.upper()


def candidate_slugs(app: dict) -> list[str]:
    """Every slug this app's evidence points at, most specific first."""
    field = app['fields']['composio_toolkit']
    candidates: list[str] = []
    for ev in field.get('evidence') or []:
        url_slug = slug_from_url(ev.get('url', ''))
        if url_slug:
            candidates.append(url_slug)
        candidates.extend(slugs_in_text(f"{ev.get('quote') or ''} {field.get('reason') or ''}"))
    candidates.append(normalise(app['app']))
    seen: list[str] = []
    for slug in candidates:
        if slug and slug not in seen:
            seen.append(slug)
    return seen


def docs_tools(app: dict) -> int | None:
    for ev in (app['fields']['composio_toolkit'].get('evidence') or []):
        match = TOOLS_IN_QUOTE.search(ev.get('quote') or '')
        if match:
            return int(match.group(1))
    return None
