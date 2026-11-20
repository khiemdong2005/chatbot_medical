"""Tìm và cào ảnh cho các món Cooky từ kho Món Ngon Mỗi Ngày."""
import json
import os
import re
import urllib.parse
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

OUTPUT_DIR = os.path.join("static", "images", "recipes")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_query(title):
    # Strip parentheses, extra spaces, 'chuẩn vị', 'đơn giản', 'tại nhà'
    t = re.sub(r"\(.*?\)", "", title)
    t = re.sub(r"\b(?:chuẩn\s+vị|tại\s+nhà|đơn\s+giản|thơm\s+ngon|siêu\s+dễ|ngon\s+chuẩn\s+vị|cho\s+bé)\b", "", t, flags=re.IGNORECASE)
    return " ".join(t.split())

def search_and_download(recipe):
    rid = recipe["id"]
    target_path = os.path.join(OUTPUT_DIR, f"{rid}.jpg")
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1024:
        return rid, recipe["title"], True, "cached"

    dish_title = recipe["title"]
    q = clean_query(dish_title)
    encoded = urllib.parse.quote(q)
    url = f"https://monngonmoingay.com/?s={encoded}"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code != 200:
            return rid, dish_title, False, "search_failed"
        
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = soup.find_all("article") or soup.find_all("div", class_="post-item")
        
        best_img = None
        best_score = 0.0
        
        for p in posts[:4]:
            h = p.find("h2") or p.find("h3") or p.find("a")
            img = p.find("img")
            if h and img:
                cand_title = h.get_text(strip=True)
                img_src = img.get("src") or img.get("data-src")
                score = SequenceMatcher(None, q.lower(), cand_title.lower()).ratio()
                if score > best_score and score >= 0.5:
                    best_score = score
                    best_img = img_src
                    
        if best_img:
            # Download image
            img_resp = requests.get(best_img, headers=HEADERS, timeout=8)
            if img_resp.status_code == 200 and len(img_resp.content) > 1024:
                with open(target_path, "wb") as f:
                    f.write(img_resp.content)
                return rid, dish_title, True, f"match_{best_score:.2f}"
                
        return rid, dish_title, False, "no_match"
    except Exception as e:
        return rid, dish_title, False, type(e).__name__

def crawl_missing_images():
    with open(os.path.join("data", "recipes", "vifoodrec", "recipes.json"), encoding="utf-8") as f:
        recipes = json.load(f)

    # Filter recipes that don't have local image yet
    missing = []
    for r in recipes:
        rid = r["id"]
        target_path = os.path.join(OUTPUT_DIR, f"{rid}.jpg")
        if not (os.path.exists(target_path) and os.path.getsize(target_path) > 1024):
            missing.append(r)

    print(f"Tổng số món cần cào bổ sung ảnh: {len(missing)} món.")
    if not missing:
        print("Đã có đủ ảnh cho tất cả món!")
        return

    success = 0
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(search_and_download, r): r for r in missing}
        for future in concurrent.futures.as_completed(futures):
            rid, title, ok, note = future.result()
            if ok:
                success += 1
            else:
                failed += 1
            if (success + failed) % 100 == 0 or (success + failed) == len(missing):
                print(f"Tiến độ cào ảnh: {success + failed}/{len(missing)} (Tìm thấy và tải: {success}, Chưa có: {failed})")

    print(f"Hoàn tất cào ảnh bù! Tải thêm được: {success} ảnh món ăn thật.")

if __name__ == "__main__":
    crawl_missing_images()

