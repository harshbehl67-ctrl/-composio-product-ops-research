"""Save independently reviewed source text and HTTP errors."""
import hashlib
import json
from pathlib import Path
import requests
from bs4 import BeautifulSoup

reviews = json.loads(Path('review.json').read_text(encoding='utf-8')) + json.loads(Path('extra_review.json').read_text(encoding='utf-8'))
out = Path('data/review_sources')
out.mkdir(exist_ok=True)
for review in reviews:
    url = review['url']
    path = out / (hashlib.sha256(url.encode()).hexdigest()[:16] + '.json')
    if path.exists():
        continue
    result = {'url': url, 'app': review['app'], 'field': review['field']}
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=25)
        result.update(status=response.status_code, final_url=response.url)
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer']):
            tag.decompose()
        result['text'] = soup.get_text(' ', strip=True)[:40000]
    except Exception as exc:
        result['error'] = str(exc)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(review['app'], result.get('status', result.get('error')), flush=True)
