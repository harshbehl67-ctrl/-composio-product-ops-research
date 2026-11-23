"""Resolve unambiguous catalog names; preserve the original catalog snapshot."""
import json
from pathlib import Path

catalog = json.loads(Path('catalog_snapshot.json').read_text(encoding='utf-8'))
by_slug = {item['slug']: item for item in catalog['catalog']}
# These names are explicit catalog labels for the same branded product. Entries
# with an MCP suffix are Composio catalog entries, not proof of a vendor server.
aliases = {
    'Pylon': 'PYLON_MCP', 'WhatsApp Business': 'WHATSAPP',
    'GoHighLevel': 'HIGHLEVEL_LOCATION', 'Threads (Meta)': 'THREADS',
    'DataForSEO': 'DATAFORSEO', 'Ahrefs': 'AHREFS', 'MrScraper': 'MRSCRAPER',
    'Apify': 'APIFY', 'Firecrawl': 'FIRECRAWL', 'Bright Data': 'BRIGHTDATA',
    'Clay': 'CLAY', 'Netlify': 'NETLIFY_MCP', 'Monday.com': 'MONDAY',
    'Otter AI': 'OTTER_AI_MCP', 'Devin': 'DEVIN_MCP', 'higgsfield': 'HIGGSFIELD',
}
resolved = []
for app, slug in aliases.items():
    item = by_slug[slug]
    resolved.append({'app': app, 'catalog_name': item['name'], 'slug': slug,
                     'url': item['url'], 'basis': 'Composio catalog product label; verify scope for intended integration',
                     'vendor_mcp': 'unknown'})
Path('catalog_aliases.json').write_text(json.dumps(resolved, indent=2), encoding='utf-8')
print(f'{len(resolved)} alias matches saved; {39-len(resolved)} unresolved')
