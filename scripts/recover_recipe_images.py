"""Recover missing local recipe photos using exact-title public recipe pages.

The script never overwrites an existing photo. It keeps a per-recipe audit and
only applies verified matches after backing up the current dataset files.
The photo source has not declared a reusable license; local research use only.
"""
import concurrent.futures
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import threading
import time
import unicodedata
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from PIL import Image
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data/recipes/vifoodrec'
IMAGES = ROOT / 'static/images/recipes'
REPORT = ROOT / 'scratch/recovery-image-audit.csv'
BASE = 'https://kingfoodmart.com'
HEADERS = {'User-Agent': 'MediMindResearch/1.0 (local recipe metadata verification)'}
NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
THREAD = threading.local()


def session():
    if not hasattr(THREAD, 'session'):
        THREAD.session = requests.Session()
        THREAD.session.headers.update(HEADERS)
    return THREAD.session


def slug(text):
    text = unicodedata.normalize('NFKD', str(text).lower().replace('đ', 'd'))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def fetch_map(url):
    try:
        r = session().get(url, timeout=(5, 15))
        r.raise_for_status()
        root = ET.fromstring(r.content)
        return [x.text for x in root.findall('.//s:loc', NS) if x.text]
    except (requests.RequestException, ET.ParseError):
        return []


def valid_photo(path):
    if not path.is_file():
        return False
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except (OSError, ValueError):
        return False


def recover(item):
    recipe, page = item
    rid = recipe['id']
    result = {'id': rid, 'ten_mon': recipe['title'], 'trang_thai': 'khong_khop',
              'trang_nguon': page, 'url_anh': '', 'anh_cuc_bo': '', 'ghi_chu': ''}
    try:
        time.sleep(.15)
        r = session().get(page, timeout=(5, 15))
        r.raise_for_status()
        if urlsplit(r.url).hostname != 'kingfoodmart.com':
            result['ghi_chu'] = 'chuyen_huong_khac_nguon'; return result
        soup = BeautifulSoup(r.content, 'html.parser')
        heading = soup.find('h1')
        if not heading or slug(heading.get_text(' ', strip=True)) != slug(recipe['title']):
            result['ghi_chu'] = 'ten_trang_khong_khop'; return result
        tag = soup.find('meta', property='og:image')
        url = tag.get('content', '') if tag else ''
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'storage.googleapis.com' or not parsed.path.startswith('/onelife-public/'):
            result['ghi_chu'] = 'khong_co_anh_nguon_hop_le'; return result
        img_response = session().get(url, timeout=(5, 20), stream=True)
        img_response.raise_for_status()
        if not img_response.headers.get('Content-Type', '').lower().startswith('image/'):
            img_response.close(); result['ghi_chu'] = 'phan_hoi_khong_phai_anh'; return result
        data = bytearray()
        for chunk in img_response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 8_000_000:
                img_response.close(); result['ghi_chu'] = 'anh_qua_lon'; return result
        img_response.close()
        with Image.open(io.BytesIO(data)) as img:
            fmt, width, height = img.format, img.width, img.height
            img.verify()
        ext = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(fmt)
        if not ext or width < 100 or height < 100:
            result['ghi_chu'] = 'anh_khong_hop_le'; return result
        dest = IMAGES / f'{rid}.{ext}'
        if dest.exists():
            result['ghi_chu'] = 'da_co_tep_khong_ghi_de'; return result
        temp = IMAGES / f'{rid}.{ext}.tmp'
        temp.write_bytes(data)
        temp.replace(dest)
        result.update(trang_thai='ten_trung_anh_doc_duoc', url_anh=url,
                      anh_cuc_bo='/static/images/recipes/' + dest.name,
                      ghi_chu=f'{fmt} {width}x{height}; chua_xac_minh_giay_phep')
    except (requests.RequestException, OSError, ValueError) as error:
        result['trang_thai'] = 'loi_ket_noi_hoac_anh'
        result['ghi_chu'] = type(error).__name__
    return result


def main():
    recipes = json.loads((DATA / 'recipes.json').read_text(encoding='utf-8-sig'))
    missing = [r for r in recipes if not valid_photo(IMAGES / (r['id'] + '.jpg'))
               and not any(valid_photo(IMAGES / (r['id'] + ext)) for ext in ('.jpeg', '.png', '.webp'))]
    print('Mon can anh:', len(missing), flush=True)
    index = session().get(BASE + '/sitemap-all/sitemap-recipes', timeout=(5, 20))
    index.raise_for_status()
    maps = [x.text for x in ET.fromstring(index.content).findall('.//s:loc', NS)
            if x.text and urlsplit(x.text).hostname == 'kingfoodmart.com']
    wanted = {slug(r['title']) for r in missing}
    pages = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, urls in enumerate(pool.map(fetch_map, maps), 1):
            for url in urls:
                parsed = urlsplit(url)
                key = unquote(parsed.path.rsplit('/', 1)[-1])
                if parsed.scheme == 'https' and parsed.hostname == 'kingfoodmart.com' and key in wanted:
                    pages[key] = url
            if i % 50 == 0 or i == len(maps):
                print('Sitemap:', i, '/', len(maps), 'ten trung:', len(pages), flush=True)
    jobs = [(r, pages[slug(r['title'])]) for r in missing if slug(r['title']) in pages]
    out = [{'id': r['id'], 'ten_mon': r['title'], 'trang_thai': 'khong_tim_thay_trang_trung_ten',
            'trang_nguon': '', 'url_anh': '', 'anh_cuc_bo': '', 'ghi_chu': ''}
           for r in missing if slug(r['title']) not in pages]
    print('Trang can doi chieu:', len(jobs), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, result in enumerate(pool.map(recover, jobs), 1):
            out.append(result)
            if i % 50 == 0 or i == len(jobs):
                print('Da kiem tra:', i, '/', len(jobs), 'anh khop:', sum(x['trang_thai'] == 'ten_trung_anh_doc_duoc' for x in out), flush=True)
    REPORT.parent.mkdir(exist_ok=True)
    with REPORT.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['id','ten_mon','trang_thai','trang_nguon','url_anh','anh_cuc_bo','ghi_chu'])
        w.writeheader(); w.writerows(out)
    recovered = {row['id']: row for row in out if row['trang_thai'] == 'ten_trung_anh_doc_duoc'}
    if not recovered:
        print('Khong tim thay anh khop; dataset chua thay doi.', flush=True); return
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = DATA / ('image-backup-' + stamp)
    backup.mkdir()
    for name in ('recipes.json', 'foods.csv', 'manifest.json'):
        shutil.copy2(DATA / name, backup / name)
    for recipe in recipes:
        row = recovered.get(recipe['id'])
        if row:
            recipe.update(source_image_url=row['anh_cuc_bo'], image_link=row['anh_cuc_bo'],
                          image_type='Ảnh tham khảo cùng tên món', image_source_page=row['trang_nguon'],
                          image_original_url=row['url_anh'], image_match_method='exact_normalized_title',
                          image_license='not_declared')
    temp = DATA / 'recipes.json.tmp'
    temp.write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(DATA / 'recipes.json')
    with (DATA / 'foods.csv').open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f); fields = reader.fieldnames; foods = list(reader)
    for row in foods:
        match = recovered.get('vifoodrec_' + row['food_id'])
        if match:
            row['image_link'] = match['anh_cuc_bo']
    temp = DATA / 'foods.csv.tmp'
    with temp.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(foods)
    temp.replace(DATA / 'foods.csv')
    manifest = json.loads((DATA / 'manifest.json').read_text(encoding='utf-8-sig'))
    manifest.setdefault('original_source_sha256', manifest.get('sha256', {}).get('foods.csv'))
    for name in ('recipes.json', 'foods.csv'):
        manifest.setdefault('sha256', {})[name] = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
    manifest['image_recovery'] = {'source': BASE, 'method': 'exact normalized title + verified image',
                                  'recovered': len(recovered), 'license': 'not_declared', 'backup': backup.name}
    temp = DATA / 'manifest.json.tmp'
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(DATA / 'manifest.json')
    print('Da cap nhat:', len(recovered), 'anh; bao cao:', REPORT, 'backup:', backup, flush=True)


if __name__ == '__main__':
    main()
