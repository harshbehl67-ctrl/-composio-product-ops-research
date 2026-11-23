"""Save the public Composio toolkit page for each exact catalog match."""
import concurrent.futures
import datetime
import json
from pathlib import Path
import requests
from bs4 import BeautifulSoup

catalog = json.loads(Path('catalog_snapshot.json').read_text(encoding='utf-8'))
out = Path('data/catalog')
out.mkdir(exist_ok=True)


def fetch(entry):
    match = entry['matches'][0]
    path = out / (match['slug'] + '.json')
    if path.exists():
        return
    result = {'app': entry['app'], 'url': match['url'], 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        response = requests.get(match['url'], timeout=30)
        result['status'] = response.status_code
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer']):
            tag.decompose()
        result['text'] = soup.get_text(' ', strip=True)[:25000]
    except Exception as exc:
        result['error'] = str(exc)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(entry['app'], result.get('status', result.get('error')), flush=True)


if __name__ == '__main__':
    aliases = json.loads(Path('catalog_aliases.json').read_text(encoding='utf-8')) if Path('catalog_aliases.json').exists() else []
    alias_entries = [{'app': x['app'], 'matches': [{'slug': x['slug'], 'url': x['url']}]} for x in aliases]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(fetch, [x for x in catalog['results'] if x['status'] == 'listed'] + alias_entries))
