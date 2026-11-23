import argparse,base64,concurrent.futures,datetime,json,re,time,traceback
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parent
APPS=json.loads((ROOT/'apps.json').read_text(encoding='utf-8'))
OUT=ROOT/'data'; OUT.mkdir(exist_ok=True)
HEAD={'User-Agent':'Mozilla/5.0 (compatible; ProductOpsResearch/1.0)'}
def decoded(url):
 q=parse_qs(urlparse(url).query).get('u',[''])[0]
 if q.startswith('a1'):
  try:return base64.urlsafe_b64decode(q[2:]+'===').decode()
  except Exception:pass
 return url
def run(app,force=False):
 path=OUT/f"{app['number']:03}.json"
 if path.exists() and not force:return json.loads(path.read_text(encoding='utf-8'))
 if path.exists() and force:
  archive=OUT/'reruns'; archive.mkdir(exist_ok=True)
  path=archive/f"{app['number']:03}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
 log={'app':app,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'query':f"{app['name']} developer API authentication documentation",'search_results':[],'retrievals':[],'errors':[]}
 try:
  r=requests.get('https://www.bing.com/search',params={'q':log['query'],'count':10},headers=HEAD,timeout=18);r.raise_for_status();s=BeautifulSoup(r.text,'html.parser')
  for li in s.select('li.b_algo'):
   a=li.select_one('h2 a')
   if a:log['search_results'].append({'title':a.get_text(' ',strip=True),'url':decoded(a.get('href','')),'snippet':li.get_text(' ',strip=True)[:1500]})
  if not log['search_results']:log['errors'].append('Search yielded no parseable results')
 except Exception as e:log['errors'].append('Search failed: '+str(e))
 # A matching hint domain is a candidate, not proof of vendor ownership or any claim.
 hint=urlparse('https://'+app['hint'].split(' ')[0]).hostname or ''
 root='.'.join(hint.split('.')[-2:])
 candidates=[x for x in log['search_results'] if (urlparse(x['url']).hostname or '').endswith(root) and re.search(r'doc|develop|api|reference',x['url'],re.I)]
 for c in candidates[:1]:
  try:
   r=requests.get(c['url'],headers=HEAD,timeout=18); soup=BeautifulSoup(r.text,'html.parser')
   for tag in soup(['script','style','nav','footer']):tag.decompose()
   log['retrievals'].append({'url':r.url,'status':r.status_code,'text':soup.get_text(' ',strip=True)[:16000]})
  except Exception as e:log['errors'].append('Document fetch failed: '+str(e))
 if not candidates:log['errors'].append('No candidate documentation on hint domain found; review required')
 # Evidence collection is not enough to infer credential gates or negative MCP claims.
 log['first_pass']={'auth':'unknown','credential_gate':'unknown','api_surface':'unknown','official_mcp':'unknown','composio_toolkit':'unknown','verdict':'unclear','blocker':'Claim-specific documentation not assessed','next_action':'Review official documentation and validate each claim','confidence':'unresolved'}
 log['validation_errors']=['All claim fields require source-specific review']
 path.write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8');return log
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--app');p.add_argument('--limit',type=int);p.add_argument('--force',action='store_true');p.add_argument('--workers',type=int,default=5);a=p.parse_args(); apps=[x for x in APPS if not a.app or x['name'].casefold()==a.app.casefold()];apps=apps[:a.limit] if a.limit else apps
 if not apps:raise SystemExit('No matching app')
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
  for log in ex.map(lambda x:run(x,a.force),apps): print(f"{log['app']['number']:03} {log['app']['name']}: {len(log['search_results'])} results, {len(log['retrievals'])} fetched, {len(log['errors'])} errors",flush=True)
