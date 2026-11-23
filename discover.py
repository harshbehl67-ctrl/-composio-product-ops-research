import base64
import concurrent.futures
import datetime
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

apps = json.loads(Path('apps.json').read_text(encoding='utf-8'))
output = Path('data/discovery')
output.mkdir(exist_ok=True)


def run(app):
    path = output / f"{app['number']:03}.json"
    if path.exists():
        return
    host = urlparse('https://' + app['hint'].split(' ')[0]).hostname or ''
    root = '.'.join(host.split('.')[-2:])
    query = f"site:{root} {app['name']} API developer documentation authentication"
    data = {'app': app['name'], 'query': query, 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'results': [], 'fetches': [], 'errors': []}
    try:
        response = requests.get('https://www.bing.com/search', params={'q': query, 'count': 10}, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for item in soup.select('li.b_algo'):
            tag = item.select_one('h2 a')
            if not tag:
                continue
            url = tag.get('href', '')
            encoded = parse_qs(urlparse(url).query).get('u', [''])[0]
            if encoded.startswith('a1'):
                try:
                    url = base64.urlsafe_b64decode(encoded[2:] + '===').decode()
                except Exception:
                    pass
            data['results'].append({'title': tag.get_text(' ', strip=True), 'url': url, 'snippet': item.get_text(' ', strip=True)[:1000]})
        candidates = [x for x in data['results'] if (urlparse(x['url']).hostname or '') == root or (urlparse(x['url']).hostname or '').endswith('.' + root)]
        for candidate in candidates[:2]:
            try:
                response = requests.get(candidate['url'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
                soup = BeautifulSoup(response.text, 'html.parser')
                for tag in soup(['script', 'style', 'nav', 'footer']):
                    tag.decompose()
                data['fetches'].append({'url': response.url, 'status': response.status_code, 'text': soup.get_text(' ', strip=True)[:20000]})
            except Exception as exc:
                data['errors'].append('fetch: ' + str(exc))
        if not candidates:
            data['errors'].append('No same-hint-domain search result')
    except Exception as exc:
        data['errors'].append('search: ' + str(exc))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(app['number'], app['name'], len(data['results']), len(data['fetches']), flush=True)


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(run, apps))
