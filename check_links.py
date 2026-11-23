"""Check HTTP availability of direct claim-specific links in the dataset."""
import concurrent.futures
import json
from pathlib import Path
import requests

rows = json.loads(Path('reviewed_dataset.json').read_text(encoding='utf-8'))
urls = sorted({url for row in rows for field in row['fields'].values() for url in field['sources']})


def check(url):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20, allow_redirects=True, stream=True)
        result = {'url': url, 'status': response.status_code, 'final_url': response.url}
        response.close()
        return result
    except Exception as exc:
        return {'url': url, 'error': str(exc)}


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check, urls))
    Path('link_checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    bad = [r for r in results if r.get('status', 0) >= 400 or 'error' in r]
    print(f'{len(results)} URLs checked; {len(bad)} non-success responses or errors')
    for result in bad:
        print(result)
