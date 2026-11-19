"""Apply a locally reviewed recipe photo and record its provenance."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/recipes/vifoodrec"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe_id")
    parser.add_argument("photo", type=Path)
    parser.add_argument("source_page")
    parser.add_argument("original_url")
    args = parser.parse_args()
    recipes_path = DATA / "recipes.json"
    recipes = json.loads(recipes_path.read_text(encoding="utf-8"))
    recipe = next(recipe for recipe in recipes if recipe["id"] == args.recipe_id)
    if not recipe.get("source_image_url", "").endswith(".svg"):
        raise ValueError("Recipe already has a photo")
    with Image.open(args.photo) as image:
        fmt, width, height = image.format, image.width, image.height
        image.verify()
    ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt)
    if not ext or min(width, height) < 100:
        raise ValueError("Invalid photo")
    target = ROOT / "static/images/recipes" / f"{args.recipe_id}.{ext}"
    if target.exists():
        raise FileExistsError(target)
    shutil.copyfile(args.photo, target)
    local_url = f"/static/images/recipes/{target.name}"
    recipe.update(source_image_url=local_url, image_link=local_url,
                  image_type="Ảnh tham khảo đúng thành phần món",
                  image_source_page=args.source_page,
                  image_original_url=args.original_url,
                  image_match_method="ingredient_and_visual_review",
                  image_license="not_declared")
    recipes_path.write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    foods_path = DATA / "foods.csv"
    with foods_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        if "vifoodrec_" + row["food_id"] == args.recipe_id:
            row["image_link"] = local_url
            break
    with foods_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest_path = DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in ("recipes.json", "foods.csv"):
        manifest["sha256"][name] = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(local_url)


if __name__ == "__main__":
    main()
