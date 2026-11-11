"""Download reference images discovered by image search, with provenance."""
import concurrent.futures,csv,glob,hashlib,io,json,re,shutil,threading,unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import requests
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent;DATA=ROOT/'data/recipes/vifoodrec';IMG=ROOT/'static/images/recipes'
T=threading.local();LOCK=threading.Lock();ROBOTS={};UA='MediMindResearch'
def session():
    if not hasattr(T,'s'):T.s=requests.Session();T.s.headers['User-Agent']=UA+'/1.0'
    return T.s
def normalized(s):
    s=''.join(c for c in unicodedata.normalize('NFKD',s.lower().replace('đ','d')) if not unicodedata.combining(c))
    s=re.sub(r'\bca\s+cao\b','cacao',s)
    s=re.sub(r'\b(ngo|bap)\b','bap',s)
    s=re.sub(r'\b(tau\s+hu|dau\s+hu|dau\s+phu)\b','tauhu',s)
    s=re.sub(r'\b(thit\s+ba\s+roi|thit\s+ba\s+chi)\b','thitbachi',s)
    s=re.sub(r'\b(dua\s+leo|dua\s+chuot)\b','dualeo',s)
    s=re.sub(r'\b(xa|sa)\b','sa',s)
    return s
IGNORED={'mon','an','cach','lam','ngon','va','voi','nuoc','nau','thom','gion','mat','lanh','ngay','he','don','gian','de','cho','bua','sang','truyen','thong','viet','nam','bang','noi','dien','phien','ban','chong','dinh','het','say','duong'}
def tokens(s):
    return [x for x in re.findall('[a-z0-9]+',normalized(s)) if x not in IGNORED]
def words(s):return set(tokens(s))
def score(a,b):
    ordered=tokens(a);candidate=tokens(b.split('|',1)[0]);a,b=set(ordered),set(candidate)
    # Keep the principal dish name, even when descriptive suffixes are omitted.
    required=ordered[:2]
    if len(ordered)<2 or not any(candidate[i:i+2]==required for i in range(len(candidate)-1)):return 0
    return len(a&b)/len(a) if len(a&b)>=2 else 0
def allowed(url):
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port or p.hostname in ('localhost','127.0.0.1') or p.hostname.endswith(('.local','.internal')):return False
    origin='https://'+p.hostname
    with LOCK:rp=ROBOTS.get(origin)
    if rp is None:
        try:
            response=session().get(origin+'/robots.txt',timeout=(3,6));rp=RobotFileParser();rp.set_url(origin+'/robots.txt')
            if response.status_code==204:rp.parse([])
            elif response.status_code==200:rp.parse(response.text.splitlines())
            elif response.status_code in (404,410):rp.parse([])
            else:return False
            with LOCK:ROBOTS[origin]=rp
        except requests.RequestException:return False
    return rp.can_fetch(UA,url)
def get(item):
    out={'id':item['id'],'ten_mon':item['title'],'trang_thai':'chua_chon_duoc','ten_nguon':'','trang_nguon':'','url_anh':'','anh_cuc_bo':'','ghi_chu':''}
    for c in sorted(item['candidates'], key=lambda x: score(item['title'],x['title']), reverse=True):
        if score(item['title'],c['title'])<.65:continue
        if re.search(r'\b(combo|shopee|mua ngay|san pham|gia si|ban si|thuc don)\b', ' '.join(sorted(words(c['title'])))):continue
        try:
            if not allowed(c['page']) or not allowed(c['image']):continue
            response=session().get(c['image'],timeout=(4,10),stream=True);response.raise_for_status()
            if not response.headers.get('Content-Type','').lower().startswith('image/'):response.close();continue
            b=bytearray()
            for chunk in response.iter_content(65536):
                b.extend(chunk)
                if len(b)>8_000_000:raise ValueError('image too large')
            response.close()
            with Image.open(io.BytesIO(b)) as im:fmt,size=im.format,im.size;im.verify()
            ext={'JPEG':'jpg','PNG':'png','WEBP':'webp'}.get(fmt)
            if not ext or min(size)<100:continue
            if any((IMG/(item['id']+'.'+x)).exists() for x in ('jpg','jpeg','png','webp')):out['ghi_chu']='existing photo';break
            dest=IMG/(item['id']+'.'+ext);dest.write_bytes(b)
            out.update(trang_thai='da_tai_can_xem_lai',ten_nguon=c['title'],trang_nguon=c['page'],url_anh=c['image'],anh_cuc_bo='/static/images/recipes/'+dest.name,ghi_chu=f'{fmt} {size[0]}x{size[1]}; diem_ten={score(item["title"],c["title"]):.2f}; giay_phep_chua_ro')
            break
        except (requests.RequestException,OSError,ValueError):continue
    return out

items=sum((json.loads(Path(f).read_text(encoding='utf8')) for f in glob.glob(str(ROOT/'scratch/image-63-small-*.json'))),[])
recipes=json.loads((DATA/'recipes.json').read_text(encoding='utf8'));missing={r['id'] for r in recipes if r.get('source_image_url','').endswith('.svg')}
jobs=[i for i in items if i['id'] in missing and any(score(i['title'],c['title'])>=.65 for c in i['candidates'])]
print('Ung vien:',len(jobs),'/',len(missing),flush=True);results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    for i,r in enumerate(pool.map(get,jobs),1):
        results.append(r)
        if i%20==0 or i==len(jobs):print('Da kiem tra',i,'anh tai duoc',sum(x['trang_thai']=='da_tai_can_xem_lai' for x in results),flush=True)
if not results:raise SystemExit('No matching candidates')
with (ROOT/'scratch/image-search-audit-63.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
found={x['id']:x for x in results if x['trang_thai']=='da_tai_can_xem_lai'}
if found:
    backup=DATA/('image-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir()
    for n in ('recipes.json','foods.csv','manifest.json'):shutil.copy2(DATA/n,backup/n)
    for r in recipes:
        x=found.get(r['id'])
        if x:r.update(source_image_url=x['anh_cuc_bo'],image_link=x['anh_cuc_bo'],image_type='Ảnh tham khảo cần kiểm tra',image_source_page=x['trang_nguon'],image_original_url=x['url_anh'],image_match_method='approximate_title_match',image_license='not_declared')
    tmp=DATA/'recipes.json.tmp';tmp.write_text(json.dumps(recipes,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp.replace(DATA/'recipes.json')
    with (DATA/'foods.csv').open(encoding='utf-8-sig',newline='') as f:r=csv.DictReader(f);fields=r.fieldnames;rows=list(r)
    for r in rows:
        x=found.get('vifoodrec_'+r['food_id'])
        if x:r['image_link']=x['anh_cuc_bo']
    tmp=DATA/'foods.csv.tmp'
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    tmp.replace(DATA/'foods.csv');m=json.loads((DATA/'manifest.json').read_text(encoding='utf8'))
    for n in ('recipes.json','foods.csv'):m['sha256'][n]=hashlib.sha256((DATA/n).read_bytes()).hexdigest()
    tmp=DATA/'manifest.json.tmp';tmp.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp.replace(DATA/'manifest.json')
    print('Da cap nhat',len(found),'backup',backup,flush=True)
