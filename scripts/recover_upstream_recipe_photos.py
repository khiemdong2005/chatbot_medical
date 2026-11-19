"""Retry missing ViFoodRec photos from their original dataset URLs.

Only verified images replace illustrations. The audit keeps failed URLs for a
later retry; failed downloads leave the catalog untouched.
"""

import concurrent.futures
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/recipes/vifoodrec"
IMAGES = ROOT / "static/images/recipes"
AUDIT = ROOT / "scratch/upstream-image-audit.csv"
SOURCE = "https://raw.githubusercontent.com/QuocAn55/A-New-Dataset-and-Empirical-Evaluation-for-Vietnamese-Food-Recommendation-System/main/Data/Clean%20Dataset/foods.csv"
HEADERS = {"User-Agent": "MediMindResearch/1.0 (recipe photo recovery)"}


def download(item):
    recipe, url = item
    result = {"id": recipe["id"], "title": recipe["title"], "original_url": url,
              "status": "failed", "detail": "", "local_path": ""}
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "image.cooky.vn", "media.cooky.vn", "img.cooky.vn",
        "monngonmoingay.com", "www.monngonmoingay.com",
    }:
        result["detail"] = "unapproved_source"
        return result
    try:
        response = requests.get(url, headers=HEADERS, timeout=(4, 10), stream=True)
        response.raise_for_status()
        if not response.headers.get("Content-Type", "").lower().startswith("image/"):
            result["detail"] = "not_an_image"
            return result
        content = bytearray()
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content) > 8_000_000:
                result["detail"] = "image_too_large"
                return result
        with Image.open(io.BytesIO(content)) as image:
            fmt, width, height = image.format, image.width, image.height
            image.verify()
        ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt)
        if not ext or min(width, height) < 100:
            result["detail"] = "invalid_image"
            return result
        target = IMAGES / f"{recipe['id']}.{ext}"
        if any((IMAGES / f"{recipe['id']}.{suffix}").exists()
               for suffix in ("jpg", "jpeg", "png", "webp")):
            result["detail"] = "file_already_exists"
            return result
        temp = target.with_name(target.name + ".tmp")
        temp.write_bytes(content)
        temp.replace(target)
        result.update(status="downloaded", detail=f"{fmt} {width}x{height}",
                      local_path=f"/static/images/recipes/{target.name}")
    except (requests.RequestException, OSError, ValueError) as error:
        result["detail"] = type(error).__name__
    return result


def main():
    recipes = json.loads((DATA / "recipes.json").read_text(encoding="utf-8"))
    missing = [recipe for recipe in recipes if recipe.get("source_image_url", "").endswith(".svg")]
    if not missing:
        print("Missing: 0; downloaded: 0")
        return
    response = requests.get(SOURCE, headers=HEADERS, timeout=(5, 30))
    response.raise_for_status()
    source_rows = {row["food_id"]: row for row in
                   csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))}
    jobs = [(recipe, source_rows.get(recipe["source_row_id"], {}).get("image_link", ""))
            for recipe in missing]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(download, jobs))
    AUDIT.parent.mkdir(exist_ok=True)
    with AUDIT.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    recovered = {result["id"]: result for result in results if result["status"] == "downloaded"}
    if recovered:
        for recipe in recipes:
            if recipe["id"] in recovered:
                result = recovered[recipe["id"]]
                recipe.update(source_image_url=result["local_path"], image_link=result["local_path"],
                              image_type="Ảnh gốc bộ dữ liệu", image_original_url=result["original_url"],
                              image_match_method="upstream_food_id", image_license="not_declared")
        (DATA / "recipes.json").write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with (DATA / "foods.csv").open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fields, rows = reader.fieldnames, list(reader)
        for row in rows:
            result = recovered.get("vifoodrec_" + row["food_id"])
            if result:
                row["image_link"] = result["local_path"]
        with (DATA / "foods.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
        for name in ("recipes.json", "foods.csv"):
            manifest["sha256"][name] = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        (DATA / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Missing: {len(missing)}; downloaded: {len(recovered)}; audit: {AUDIT}")


if __name__ == "__main__":
    main()
