"""Find same-name reference photos through public recipe search results."""
import concurrent.futures, csv, hashlib, io, ipaddress, json, re, shutil, threading, time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import requests
from bs4 import BeautifulSoup
from PIL import Image
from recover_recipe_images import slug

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data/recipes/vifoodrec'
IMG = ROOT / 'static/images/recipes'
REPORT = ROOT / 'scratch/search-photo-audit.csv'
THREAD = threading.local()

def session():
    if not hasattr(THREAD, 's'):
        THREAD.s = requests.Session()
        THREAD.s.headers['User-Agent'] = 'MediMindResearch/1.0 (public recipe search)'
    return THREAD.s

def match(title, candidate):
    a, b = slug(title), slug(candidate)
    # A complete name with extra descriptive words is allowed, but no single-word match.
    if len(a.split('-')) < 2: return False
    return b == a or b.startswith(a + '-') or b.endswith('-' + a)

def fetch(recipe):
    out = {'id':recipe['id'], 'ten_mon':recipe['title'], 'trang_thai':'khong_tim_thay', 'ten_nguon':'', 'trang_nguon':'', 'url_anh':'', 'anh_cuc_bo':'', 'ghi_chu':''}
    try:
        time.sleep(.3)
        resp = session().get('https://naungon.com/index.php', params={'q':recipe['title']}, timeout=(5,15));resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')
        cards = soup.select('li.media')
        for card in cards:
            heading = card.select_one('h4.media-heading a'); img = card.select_one('img[itemprop=image]')
            if not heading or not img or not match(recipe['title'], heading.get_text(' ',strip=True)): continue
            page = heading.get('href',''); url = img.get('src',''); p = urlsplit(url)
            if p.scheme not in ('http','https') or not p.hostname or p.hostname.lower() in ('image.cooky.vn','naungon.com','www.naungon.com'): continue
            try: ipaddress.ip_address(p.hostname); continue
            except ValueError: pass
            url = urlunsplit(('https',p.netloc,p.path,p.query,''))
            try:
                response = session().get(url,timeout=(5,12),stream=True,allow_redirects=True)
                response.raise_for_status()
                if not response.headers.get('content-type','').lower().startswith('image/'): response.close();continue
                data=bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data)>8000000:raise ValueError('image too large')
                response.close()
                with Image.open(io.BytesIO(data)) as im: fmt,size=im.format,im.size;im.verify()
                ext={'JPEG':'jpg','PNG':'png','WEBP':'webp'}.get(fmt)
                if not ext or min(size)<100:continue
                dest=IMG / (recipe['id']+'.'+ext)
                if any((IMG / (recipe['id']+'.'+e)).exists() for e in ('jpg','jpeg','png','webp')):out['ghi_chu']='existing file';break
                dest.write_bytes(data)
                out.update(trang_thai='anh_tai_duoc_ten_tuong_ung',ten_nguon=heading.get_text(' ',strip=True),trang_nguon=page,url_anh=response.url,anh_cuc_bo='/static/images/recipes/'+dest.name,ghi_chu=f'{fmt} {size[0]}x{size[1]}; chua_xac_minh_giay_phep')
                break
            except (requests.RequestException,OSError,ValueError): continue
    except (requests.RequestException,OSError,ValueError) as e: out.update(trang_thai='loi_tim_kiem',ghi_chu=type(e).__name__)
    return out

recipes=json.loads((DATA/'recipes.json').read_text(encoding='utf-8'))
jobs=[r for r in recipes if r.get('source_image_url','').endswith('.svg')]
print('Can tim:',len(jobs),flush=True)
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for i,result in enumerate(pool.map(fetch,jobs),1):
        results.append(result)
        if i%25==0 or i==len(jobs):print('Da tim',i,'/',len(jobs),'anh',sum(x['trang_thai']=='anh_tai_duoc_ten_tuong_ung' for x in results),flush=True)
REPORT.parent.mkdir(exist_ok=True)
with REPORT.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
found={x['id']:x for x in results if x['trang_thai']=='anh_tai_duoc_ten_tuong_ung'}
if found:
    backup=DATA/('image-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir()
    for name in ('recipes.json','foods.csv','manifest.json'):shutil.copy2(DATA/name,backup/name)
    for recipe in recipes:
        x=found.get(recipe['id'])
        if x:recipe.update(source_image_url=x['anh_cuc_bo'],image_link=x['anh_cuc_bo'],image_type='Ảnh tham khảo cùng tên món',image_source_page=x['trang_nguon'],image_original_url=x['url_anh'],image_match_method='reference_title_match',image_license='not_declared')
    tmp=DATA/'recipes.json.tmp';tmp.write_text(json.dumps(recipes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(DATA/'recipes.json')
    with (DATA/'foods.csv').open(encoding='utf-8-sig',newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
    for row in rows:
        x=found.get('vifoodrec_'+row['food_id'])
        if x:row['image_link']=x['anh_cuc_bo']
    tmp=DATA/'foods.csv.tmp'
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    tmp.replace(DATA/'foods.csv')
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    for name in ('recipes.json','foods.csv'):manifest['sha256'][name]=hashlib.sha256((DATA/name).read_bytes()).hexdigest()
    tmp=DATA/'manifest.json.tmp';tmp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(DATA/'manifest.json')
    print('Da them',len(found),'backup',backup,flush=True)
