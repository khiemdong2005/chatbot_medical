"""Fill missing recipe photos from reviewed public image search results.

The candidate list records the source page and image URL for each dish. Photos
are reference images; they are not claimed to depict the source recipe exactly.
"""

import concurrent.futures
import csv
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from PIL import Image
import requests


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/recipes/vifoodrec"
IMAGES = ROOT / "static/images/recipes"
CANDIDATES = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "scratch/reference-photo-candidates.json"
AUDIT = ROOT / "scratch/reference-photo-audit.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MediMindRecipeResearch/1.0)"}


def public_https(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        ipaddress.ip_address(parsed.hostname)
        return False
    except ValueError:
        return not parsed.hostname.endswith((".local", ".internal"))


def fetch(item):
    result = dict(item)
    result.update(status="failed", detail="", local_path="")
    if not public_https(item["image"]) or not public_https(item["page"]):
        result["detail"] = "invalid_url"
        return result
    try:
        response = requests.get(item["image"], headers=HEADERS, timeout=(5, 15), stream=True)
        response.raise_for_status()
        if not public_https(response.url):
            result["detail"] = "invalid_redirect"
            return result
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
        target = IMAGES / f"{item['id']}.{ext}"
        if not item.get("replace_reference") and any(
            (IMAGES / f"{item['id']}.{suffix}").exists()
            for suffix in ("jpg", "jpeg", "png", "webp")
        ):
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
    recipes_path = DATA / "recipes.json"
    recipes = json.loads(recipes_path.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    by_id = {recipe["id"]: recipe for recipe in recipes}
    jobs = [item for item in candidates if item["id"] in by_id and (
        by_id[item["id"]].get("source_image_url", "").endswith(".svg") or
        (item.get("replace_reference") and
         by_id[item["id"]].get("image_match_method") == "reviewed_image_search")
    )]
    if not jobs:
        print("Candidates to apply: 0; downloaded: 0")
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(fetch, jobs))
    AUDIT.parent.mkdir(exist_ok=True)
    with AUDIT.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    recovered = {result["id"]: result for result in results
                 if result["status"] == "downloaded"}
    if recovered:
        for recipe in recipes:
            result = recovered.get(recipe["id"])
            if result:
                recipe.update(source_image_url=result["local_path"],
                              image_link=result["local_path"],
                              image_type="Ảnh tham khảo món tương tự",
                              image_source_page=result["page"],
                              image_original_url=result["image"],
                              image_match_method="reviewed_image_search",
                              image_license="not_declared")
        recipes_path.write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        foods_path = DATA / "foods.csv"
        with foods_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fields, rows = reader.fieldnames, list(reader)
        for row in rows:
            result = recovered.get("vifoodrec_" + row["food_id"])
            if result:
                row["image_link"] = result["local_path"]
        with foods_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        manifest_path = DATA / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name in ("recipes.json", "foods.csv"):
            manifest["sha256"][name] = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Candidates: {len(jobs)}; downloaded: {len(recovered)}; audit: {AUDIT}")


if __name__ == "__main__":
    main()
