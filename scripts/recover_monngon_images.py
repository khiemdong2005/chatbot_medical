"""Recover missing photos from public Mon Ngon Moi Ngay recipe pages."""
import csv, hashlib, io, json, shutil, time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
import requests
from bs4 import BeautifulSoup
from PIL import Image
from recover_recipe_images import slug

root = Path(__file__).resolve().parent.parent
data = root / 'data/recipes/vifoodrec'
recipes = json.loads((data / 'recipes.json').read_text(encoding='utf-8'))
pages = json.loads((root / 'scratch/monngon-sitemap.json').read_text(encoding='utf-8'))
jobs = [r for r in recipes if r.get('source_image_url', '').endswith('.svg') and slug(r['title']) in pages]
session = requests.Session()
session.headers['User-Agent'] = 'MediMindResearch/1.0 (recipe image verification)'
results = []
for r in jobs:
    page = pages[slug(r['title'])]
    out = {'id': r['id'], 'title': r['title'], 'page': page, 'status': 'unmatched'}
    try:
        time.sleep(.2)
        response = session.get(page, timeout=15); response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        heading = soup.find('h1')
        if not heading or slug(heading.get_text(' ', strip=True)) != slug(r['title']):
            out['status'] = 'title_mismatch'; results.append(out); continue
        image = soup.find('meta', property='og:image')
        url = image.get('content', '') if image else ''
        if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'monngonmoingay.com':
            out['status'] = 'no_image'; results.append(out); continue
        response = session.get(url, timeout=20); response.raise_for_status()
        if len(response.content) > 8000000: raise ValueError('image too large')
        with Image.open(io.BytesIO(response.content)) as im:
            fmt, size = im.format, im.size; im.verify()
        ext = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(fmt)
        if not ext or min(size) < 100: raise ValueError('image invalid')
        dest = root / 'static/images/recipes' / (r['id'] + '.' + ext)
        if dest.exists(): raise FileExistsError(dest)
        dest.write_bytes(response.content)
        out.update(status='recovered', image=url, local='/static/images/recipes/' + dest.name)
    except (requests.RequestException, OSError, ValueError) as e:
        out['status'] = type(e).__name__
    results.append(out)
    print(r['title'], out['status'], flush=True)

report = root / 'scratch/monngon-image-audit.json'
report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
recovered = {r['id']: r for r in results if r['status'] == 'recovered'}
if recovered:
    backup = data / ('image-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir()
    for name in ('recipes.json', 'foods.csv', 'manifest.json'): shutil.copy2(data / name, backup / name)
    for r in recipes:
        if r['id'] in recovered:
            x = recovered[r['id']]
            r.update(source_image_url=x['local'], image_link=x['local'], image_type='Ảnh tham khảo cùng tên món',
                     image_source_page=x['page'], image_original_url=x['image'], image_match_method='exact_normalized_title', image_license='not_declared')
    (data / 'recipes.json').write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (data / 'foods.csv').open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
    for row in rows:
        if 'vifoodrec_' + row['food_id'] in recovered: row['image_link'] = recovered['vifoodrec_' + row['food_id']]['local']
    with (data / 'foods.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
    for name in ('recipes.json', 'foods.csv'): manifest['sha256'][name] = hashlib.sha256((data / name).read_bytes()).hexdigest()
    (data / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Recovered:', len(recovered), 'out of', len(jobs), flush=True)
