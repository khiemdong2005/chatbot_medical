"""Tải và cào ảnh món ăn cho dataset ViFoodRec."""
import os
import re
import json
import time
from urllib.parse import urlparse, quote
import concurrent.futures
import requests
from bs4 import BeautifulSoup
import pandas as pd

OUTPUT_DIR = os.path.join("static", "images", "recipes")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fix_url(url):
    p = urlparse(str(url))
    quoted_path = quote(p.path)
    return p._replace(path=quoted_path).geturl()

def download_single(item):
    fid = item["food_id"]
    name = item["dish_name"]
    url = item["image_link"]
    
    # Target file path
    target_path = os.path.join(OUTPUT_DIR, f"vifoodrec_{fid}.jpg")
    
    # If already downloaded and valid size > 1KB, skip
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1024:
        return fid, name, True, "cached"

    fixed_url = fix_url(url)
    try:
        resp = requests.get(fixed_url, headers=HEADERS, timeout=8)
        if resp.status_code == 200 and len(resp.content) > 1024:
            with open(target_path, "wb") as f:
                f.write(resp.content)
            return fid, name, True, "downloaded"
        return fid, name, False, f"status_{resp.status_code}"
    except Exception as e:
        return fid, name, False, type(e).__name__

def download_monngonmoingay_images():
    csv_path = os.path.join("data", "recipes", "vifoodrec", "foods.csv")
    df = pd.read_csv(csv_path, encoding="utf-8")
    mnmn_items = df[df["image_link"].str.contains("monngonmoingay.com", na=False)].to_dict("records")
    print(f"Bắt đầu tải {len(mnmn_items)} ảnh thật từ Món Ngon Mỗi Ngày...")

    success = 0
    failed = 0
    start = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(download_single, item): item for item in mnmn_items}
        for future in concurrent.futures.as_completed(futures):
            fid, name, ok, note = future.result()
            if ok:
                success += 1
            else:
                failed += 1
            if (success + failed) % 100 == 0 or (success + failed) == len(mnmn_items):
                print(f"Tiến độ: {success + failed}/{len(mnmn_items)} (Thành công: {success}, Lỗi: {failed})")

    elapsed = time.time() - start
    print(f"Hoàn thành tải ảnh Món Ngon Mỗi Ngày trong {elapsed:.2f}s! (Thành công: {success}, Lỗi: {failed})")
    return success

if __name__ == "__main__":
    download_monngonmoingay_images()

