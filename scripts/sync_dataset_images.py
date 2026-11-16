import json
import os
import hashlib
import pandas as pd

rec_path = 'data/recipes/vifoodrec/recipes.json'
manifest_path = 'data/recipes/vifoodrec/manifest.json'

with open(rec_path, 'r', encoding='utf-8') as f:
    recipes = json.load(f)

img_dir = 'static/images/recipes'
updated_count = 0

for r in recipes:
    rid = r['id']
    current = r.get('source_image_url', '')
    current_file = current.rsplit('/', 1)[-1] if current.startswith('/static/images/recipes/') else ''
    jpg_file = current_file if current_file and os.path.isfile(os.path.join(img_dir, current_file)) else next((f'{rid}.{ext}' for ext in ('jpg', 'jpeg', 'png', 'webp') if os.path.isfile(os.path.join(img_dir, f'{rid}.{ext}'))), '')
    jpg_path = os.path.join(img_dir, jpg_file)
    if jpg_file and os.path.getsize(jpg_path) > 1024:
        rel_url = f"/static/images/recipes/{jpg_file}"
        if r.get('source_image_url') != rel_url:
            r['source_image_url'] = rel_url
            r['image_link'] = rel_url
            r.setdefault('image_type', 'Ảnh chụp món ăn')
            updated_count += 1

print(f"Updated {updated_count} recipes with local photo URLs.")

with open(rec_path, 'w', encoding='utf-8') as f:
    json.dump(recipes, f, ensure_ascii=False, indent=2)

sha = hashlib.sha256(open(rec_path, 'rb').read()).hexdigest()
with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)

manifest['sha256']['recipes.json'] = sha
with open(manifest_path, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print('Updated manifest sha256 to:', sha)

df = pd.read_csv('data/recipes/vifoodrec/foods_clean.csv')
for i, row in df.iterrows():
    fid = row['food_id']
    rid = f"vifoodrec_{fid}"
    photo = next((r.get('source_image_url') for r in recipes if r['id'] == rid), '')
    if photo and photo.startswith('/static/images/recipes/'):
        df.at[i, 'image_link'] = photo

df.to_csv('data/recipes/vifoodrec/foods_clean.csv', index=False, encoding='utf-8-sig')
try:
    df.to_excel('data/recipes/vifoodrec/foods_clean.xlsx', index=False)
    print('Updated foods_clean.xlsx')
except Exception as e:
    print('Could not update Excel (maybe open in Excel):', e)

print('Sync complete.')

