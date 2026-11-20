"""Cập nhật đường dẫn ảnh chuẩn vào dataset foods.csv và recipes.json."""
import os
import json
import shutil
import re
import hashlib
from datetime import datetime
import pandas as pd

IMAGES_DIR = os.path.join("static", "images", "recipes")
RECIPES_JSON_PATH = os.path.join("data", "recipes", "vifoodrec", "recipes.json")
FOODS_CSV_PATH = os.path.join("data", "recipes", "vifoodrec", "foods.csv")
FOODS_XLSX_PATH = os.path.join("data", "recipes", "vifoodrec", "foods.xlsx")
CLEAN_XLSX_PATH = os.path.join("data", "recipes", "vifoodrec", "recipes_clean.xlsx")

def match_artwork(title, ingredients_text, recipe_type="food"):
    if recipe_type == "drink":
        t = title.lower()
        if re.search(r"gừng|ginger", t): return "drink-ginger"
        if re.search(r"hoa cúc|cúc", t): return "drink-chamomile"
        if re.search(r"chanh sả|sả", t): return "drink-lemongrass"
        if re.search(r"trà xanh|matcha|chè xanh", t): return "drink-greentea"
        if re.search(r"atiso|artichoke", t): return "drink-artichoke"
        if re.search(r"thảo mộc|thảo dược", t): return "drink-herbal"
        return "category-drink"
    
    text = (title + " " + ingredients_text).lower()
    if re.search(r"khoai lang|sweet potato", text): return "sweet_potato"
    if re.search(r"bí đỏ|pumpkin", text): return "pumpkin_soup"
    if re.search(r"cháo gà|thịt gà", text): return "chicken_congee"
    if re.search(r"đậu hũ|tàu hũ|tofu", text): return "tofu_pumpkin"
    if re.search(r"cháo|súp|canh", text): return "rice_carrot"
    if re.search(r"trứng|egg", text): return "soft_egg"
    if re.search(r"yến mạch|oat", text): return "oat_porridge"
    return "category-food"

def update_dataset():
    local_files = set(os.listdir(IMAGES_DIR))
    print(f"Tổng số ảnh thực tế trong {IMAGES_DIR}: {len(local_files)} file")

    # 1. Update recipes.json
    backup_dir = os.path.join('data', 'recipes', 'vifoodrec', 'image-sync-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    os.makedirs(backup_dir, exist_ok=False)
    for path in (RECIPES_JSON_PATH, FOODS_CSV_PATH, os.path.join('data', 'recipes', 'vifoodrec', 'manifest.json')):
        if os.path.isfile(path): shutil.copy2(path, backup_dir)
    with open(RECIPES_JSON_PATH, "r", encoding="utf-8") as f:
        recipes = json.load(f)

    photo_count = 0
    svg_count = 0
    clean_excel_rows = []

    for r in recipes:
        rid = r.get("id", "")
        title = r.get("title", "")
        recipe_type = r.get("recipe_type", "food")
        ing_text = " ".join([i.get("name", "") for i in r.get("ingredients", [])])
        
        # Retain the current photo and its provenance; recovered files may be PNG/WebP.
        current = r.get("source_image_url", "")
        current_file = current.rsplit("/", 1)[-1] if current.startswith("/static/images/recipes/") else ""
        expected_img = current_file if current_file in local_files else next((f"{rid}.{ext}" for ext in ("jpg", "jpeg", "png", "webp") if f"{rid}.{ext}" in local_files), "")
        if expected_img:
            correct_url = f"/static/images/recipes/{expected_img}"
            image_type = r.get("image_type") or "Ảnh chụp thật (offline)"
            photo_count += 1
        else:
            svg_name = match_artwork(title, ing_text, recipe_type)
            correct_url = f"/static/images/nutrition/{svg_name}.svg"
            image_type = "Ảnh vector minh họa"
            svg_count += 1

        r["source_image_url"] = correct_url
        r["image_link"] = correct_url
        r["image_type"] = image_type

        clean_excel_rows.append({
            "ID": rid,
            "Tên món": title,
            "Loại": "Món ăn" if recipe_type == "food" else "Đồ uống",
            "Thời gian nấu": r.get("cooking_time", ""),
            "Khẩu phần": r.get("servings", ""),
            "Link ảnh chuẩn": correct_url,
            "Loại ảnh": image_type,
            "Nguyên liệu": "\n".join([f"- {i.get('name', '')}" for i in r.get("ingredients", [])]),
            "Cách chế biến": "\n".join([f"{idx+1}. {s}" for idx, s in enumerate(r.get("steps", []))]),
            "Lưu ý dinh dưỡng": " | ".join(r.get("avoid", []))
        })

    with open(RECIPES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(recipes, f, ensure_ascii=False, indent=2)
    print(f"Đã cập nhật recipes.json: {photo_count} ảnh chụp thật, {svg_count} ảnh vector chuẩn.")

    # 2. Update foods.csv
    df = pd.read_csv(FOODS_CSV_PATH, encoding="utf-8")
    by_id = {r['id']: r['source_image_url'] for r in recipes}
    updated_links = []
    for idx, row in df.iterrows():
        fid = row["food_id"]
        active_image = by_id.get(f"vifoodrec_{fid}")
        if active_image:
            updated_links.append(active_image)
        else:
            old_link = str(row.get("image_link", ""))
            if old_link and old_link.lower() != 'nan':
                updated_links.append(old_link)
            else:
                title = str(row.get("dish_name", ""))
                ing = str(row.get("ingredients", ""))
                svg_name = match_artwork(title, ing)
                updated_links.append(f"/static/images/nutrition/{svg_name}.svg")

    df["image_link"] = updated_links
    
    # Try writing to foods.csv, if locked write to foods_clean.csv
    csv_saved = False
    try:
        df.to_csv(FOODS_CSV_PATH, index=False, encoding="utf-8")
        print(f"Đã cập nhật trực tiếp vào {FOODS_CSV_PATH}")
        csv_saved = True
    except PermissionError:
        alt_csv = os.path.join("data", "recipes", "vifoodrec", "foods_clean.csv")
        df.to_csv(alt_csv, index=False, encoding="utf-8")
        print(f"[LƯU Ý] File foods.csv đang được mở trong Excel nên đã lưu sang {alt_csv}")

    # 3. Export foods.xlsx / foods_clean.xlsx
    try:
        df.to_excel(FOODS_XLSX_PATH, index=False, engine="openpyxl")
        print("Đã cập nhật foods.xlsx.")
    except PermissionError:
        alt_xlsx = os.path.join("data", "recipes", "vifoodrec", "foods_clean.xlsx")
        df.to_excel(alt_xlsx, index=False, engine="openpyxl")
        print(f"[LƯU Ý] File foods.xlsx đang bị khóa nên đã lưu sang {alt_xlsx}")

    manifest_path = os.path.join('data', 'recipes', 'vifoodrec', 'manifest.json')
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding='utf-8') as f: manifest = json.load(f)
        for path in (RECIPES_JSON_PATH, FOODS_CSV_PATH):
            with open(path, 'rb') as f: manifest.setdefault('sha256', {})[os.path.basename(path)] = hashlib.sha256(f.read()).hexdigest()
        with open(manifest_path, 'w', encoding='utf-8') as f: json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 4. Re-export recipes_clean.xlsx
    try:
        df_clean = pd.DataFrame(clean_excel_rows)
        df_clean.to_excel(CLEAN_XLSX_PATH, index=False, engine="openpyxl")
        print("Đã cập nhật recipes_clean.xlsx.")
    except PermissionError:
        alt_clean = os.path.join("data", "recipes", "vifoodrec", "recipes_clean_v2.xlsx")
        df_clean.to_excel(alt_clean, index=False, engine="openpyxl")
        print(f"[LƯU Ý] File đang bị khóa nên đã lưu sang {alt_clean}")

if __name__ == "__main__":
    update_dataset()
