import json,re,requests,datetime
from pathlib import Path
from bs4 import BeautifulSoup
url='https://docs.composio.dev/toolkits';r=requests.get(url,timeout=60);r.raise_for_status();s=BeautifulSoup(r.text,'html.parser');catalog=[]
for a in s.select('a[href^="/toolkits/"]'):
 t=a.get_text(' ',strip=True); m=re.match(r'^(.*?)\s+([A-Z][A-Z0-9_]*)\s+(\d+)\s+(\d+)$',t)
 if m:catalog.append({'name':m.group(1),'slug':m.group(2),'url':'https://docs.composio.dev'+a['href'],'tools':int(m.group(3)),'triggers':int(m.group(4))})
assert len(catalog)>1000
apps=json.loads(Path('apps.json').read_text(encoding='utf-8')); norm=lambda x:re.sub(r'[^a-z0-9]','',x.casefold()); result=[]
for app in apps:
 matches=[x for x in catalog if norm(x['name'])==norm(app['name'])]
 result.append({'app':app['name'],'status':'listed' if matches else 'unknown','matches':matches,'note':'Exact display-name match' if matches else 'No exact match; aliases and omissions not independently checked'})
Path('catalog_snapshot.json').write_text(json.dumps({'source':url,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'catalog_count':len(catalog),'catalog':catalog,'results':result},ensure_ascii=False,indent=2),encoding='utf-8');print('catalog entries',len(catalog),'exact matches',sum(x['status']=='listed' for x in result))
