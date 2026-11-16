"""Recover reference images from previously collected public search results."""
import collections, concurrent.futures, csv, glob, hashlib, io, json, re, shutil, threading, time, unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'data/recipes/vifoodrec'
IMG=ROOT/'static/images/recipes'
UA='MediMindResearch'
THREAD=threading.local()
LOCK=threading.Lock()
ROBOTS={}

def session():
    if not hasattr(THREAD,'s'):
        THREAD.s=requests.Session();THREAD.s.headers['User-Agent']=UA+'/1.0'
    return THREAD.s

def words(value):
    value=unicodedata.normalize('NFKD',value.lower().replace('đ','d'))
    value=''.join(c for c in value if not unicodedata.combining(c))
    return set(re.findall(r'[a-z0-9]+',value))-{'mon','an','cach','lam','nau','ngon','va','voi','thom','gion'}

def matches(name,title):
    a,b=words(name),words(title)
    return len(a)>=2 and len(a&b)/len(a)>=.84

def allowed(url):
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port:return False
    host=p.hostname.lower()
    if host in ('localhost','127.0.0.1') or host.endswith(('.local','.internal')):return False
    origin=f'https://{host}'
    with LOCK: known=ROBOTS.get(origin)
    if known is None:
        try:
            response=session().get(origin+'/robots.txt',timeout=(3,6))
            parser=RobotFileParser();parser.set_url(origin+'/robots.txt')
            if response.status_code==204:parser.parse([])
            elif response.status_code==200:parser.parse(response.text.splitlines())
            elif response.status_code in (404,410):parser.parse([])
            else:return False
            known=parser
            with LOCK:ROBOTS[origin]=parser
        except requests.RequestException:return False
    return known.can_fetch(UA,url)

def recover(item):
    out={'id':item['id'],'ten_mon':item['title'],'trang_thai':'chua_tim_duoc_anh','trang_nguon':'','url_anh':'','anh_cuc_bo':'','ten_trang':'','ghi_chu':''}
    for candidate in item['candidates'][:5]:
        page=candidate['url'];title=candidate['title']
        if not matches(item['title'],title):continue
        try:
            parsed=urlsplit(page)
            if parsed.hostname in ('www.youtube.com','youtube.com') and parsed.path=='/watch':
                video=parse_qs(parsed.query).get('v',[''])[0]
                if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video):continue
                url=f'https://i.ytimg.com/vi/{video}/hqdefault.jpg'
            else:
                if not allowed(page):continue
                resp=session().get(page,timeout=(4,9));resp.raise_for_status()
                if not allowed(resp.url):continue
                soup=BeautifulSoup(resp.content,'html.parser')
                tag=soup.find('meta',property='og:title'); heading=tag.get('content','') if tag else (soup.title.get_text(' ',strip=True) if soup.title else '')
                if not matches(item['title'],heading):continue
                img=soup.find('meta',property='og:image') or soup.find('meta',attrs={'name':'twitter:image'})
                url=img.get('content','') if img else ''
            if not allowed(url):continue
            response=session().get(url,timeout=(4,10),stream=True);response.raise_for_status()
            if not response.headers.get('Content-Type','').lower().startswith('image/'):response.close();continue
            data=bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data)>8_000_000:raise ValueError('image too large')
            response.close()
            with Image.open(io.BytesIO(data)) as im:fmt,size=im.format,im.size;im.verify()
            ext={'JPEG':'jpg','PNG':'png','WEBP':'webp'}.get(fmt)
            if not ext or min(size)<100:continue
            if any((IMG/(item['id']+'.'+x)).exists() for x in ('jpg','jpeg','png','webp')):out['ghi_chu']='existing photo';break
            dest=IMG/(item['id']+'.'+ext);dest.write_bytes(data)
            out.update(trang_thai='da_tai',trang_nguon=page,url_anh=url,anh_cuc_bo='/static/images/recipes/'+dest.name,ten_trang=title,ghi_chu=f'{fmt} {size[0]}x{size[1]}; can_xem_lai; giay_phep_chua_ro')
            break
        except (requests.RequestException,OSError,ValueError):continue
    return out

items=sum((json.loads(Path(f).read_text(encoding='utf8')) for f in glob.glob(str(ROOT/'scratch/photo-search-pass2-*.json'))),[])
recipes=json.loads((DATA/'recipes.json').read_text(encoding='utf8'))
missing={r['id'] for r in recipes if r.get('source_image_url','').endswith('.svg')}
jobs=[x for x in items if x['id'] in missing and any(matches(x['title'],c['title']) for c in x['candidates'])]
print('mon co ung vien:',len(jobs),'/',len(missing),flush=True)
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    for i,result in enumerate(pool.map(recover,jobs),1):
        results.append(result)
        if i%20==0 or i==len(jobs):print('da kiem tra:',i,'anh tai duoc:',sum(x['trang_thai']=='da_tai' for x in results),flush=True)
report=ROOT/'scratch/websearch-photo-audit-pass2.csv'
with report.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
found={r['id']:r for r in results if r['trang_thai']=='da_tai'}
if found:
    backup=DATA/('image-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir()
    for name in ('recipes.json','foods.csv','manifest.json'):shutil.copy2(DATA/name,backup/name)
    for r in recipes:
        x=found.get(r['id'])
        if x:r.update(source_image_url=x['anh_cuc_bo'],image_link=x['anh_cuc_bo'],image_type='Ảnh tham khảo cùng tên món',image_source_page=x['trang_nguon'],image_original_url=x['url_anh'],image_match_method='reference_title_match',image_license='not_declared')
    tmp=DATA/'recipes.json.tmp';tmp.write_text(json.dumps(recipes,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp.replace(DATA/'recipes.json')
    with (DATA/'foods.csv').open(encoding='utf-8-sig',newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
    for row in rows:
        x=found.get('vifoodrec_'+row['food_id'])
        if x:row['image_link']=x['anh_cuc_bo']
    tmp=DATA/'foods.csv.tmp'
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    tmp.replace(DATA/'foods.csv')
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf8'))
    for name in ('recipes.json','foods.csv'):manifest['sha256'][name]=hashlib.sha256((DATA/name).read_bytes()).hexdigest()
    tmp=DATA/'manifest.json.tmp';tmp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp.replace(DATA/'manifest.json')
    print('da cap nhat',len(found),'backup',backup,flush=True)
