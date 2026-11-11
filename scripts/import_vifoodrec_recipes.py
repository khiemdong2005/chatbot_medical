"""Import the author's ViFoodRec foods table for a local research prototype.

Only foods.csv is fetched. Ratings, people, remote code and images are not read.
The authors publish the data for research access, but no explicit reuse license
is declared in the repository. This importer does not invent a license or claim
that Vietnamese language, nutrients or recipe features establish medical safety.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import html
import io
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data/recipes/vifoodrec"
REPOSITORY = "https://github.com/QuocAn55/A-New-Dataset-and-Empirical-Evaluation-for-Vietnamese-Food-Recommendation-System"
DATASET_URL = REPOSITORY + "/blob/main/Data/Clean%20Dataset/foods.csv"
DOWNLOAD_URL = "https://raw.githubusercontent.com/QuocAn55/A-New-Dataset-and-Empirical-Evaluation-for-Vietnamese-Food-Recommendation-System/main/Data/Clean%20Dataset/foods.csv"
PAPER_URL = "https://aclanthology.org/2024.paclic-1.4/"
REQUIRED = {"food_id", "dish_name", "ingredients", "cooking_method", "dish_type"}


def normalized(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return " ".join("".join(c for c in text if unicodedata.category(c) != "Mn").replace("đ", "d").split())


def tidy(value):
    # Never execute or interpret source markup. Plain text is escaped by the UI.
    return " ".join(html.unescape(str(value or "")).split()).strip()


def has(pattern, text):
    return bool(re.search(r"\b(?:" + pattern + r")\b", text))


FOREIGN = (
    r"pizza|pasta|spaghetti|lasagna|lasagne|carbonara|bolognese|fettuccine|macaroni|"
    r"sushi|sashimi|kimbap|gimbap|kim ?chi|tokbokki|tteokbokki|ramen|udon|soba|"
    r"teriyaki|bulgogi|miso|takoyaki|okonomiyaki|bingsu|dalgona|matcha|macchiato|"
    r"cold brew|latte|cappuccino|espresso|mojito|mocktail|cocktail|"
    r"hamburger|burger|sandwich|hot ?dog|taco|burrito|nachos|tortilla|salsa|"
    r"salad|caesar|croissant|brownie|cheesecake|tiramisu|panna cotta|crepe|muffin|"
    r"waffle|pancake|scone|cupcake|donut|doughnut|sukiyaki|sorbet|"
    r"han quoc|nhat ban|hong kong|singapore|sing ga po|mexico|mexican|"
    r"kieu (?:han|nhat|thai|phap|y|au|an|nga|trung)|mi y|mi han|mi nhat|"
    r"cari nhat|ca ri nhat|ca ri an do|banh gao han|au chau|"
    r"lau thai|sup thai|canh chua thai|tom yum|pad thai"
)
DRINK = (
    r"^(?:sinh to\b|tra\b|ca phe\b|sua (?:dau|hat|gao|bap|ngo|me|yen mach|chua uong)\b|"
    r"nuoc (?:ep|sam|chanh|dua|mat|rau ma|gao|le|dau|atiso|at -?i -?so|tia to)\b)"
)
VN_FAMILY = (
    r"chao|canh|com|bun|pho(?! mai)|mien|hu tieu|xoi|che|nem|cha|chao tom|"
    r"goi|dua mon|dua gia|dua cai|rau muong|tao pho|tau hu|dau hu|dau phu|"
    r"banh (?:canh|cuon|duc|beo|bot loc|nam|ram|it|gio|xep|khot|xeo|tet|chung|day|giay|ran|tro|u|gai|trang|mi)|"
    r"thit (?:kho|luoc)|ca kho|bo la lot|bo luc lac|lau|mam|ruoc|chao long"
)
VN_PROTEIN = r"ga|vit|ngan|bo|heo|lon|suon|thit|ca|tom|tep|muc|ech|luon|cua|ghe|ngheu|so|oc|hau|dau hu|dau phu|rau|nam|trung|khoai|bap|mit|chuoi|bi|muop|bau"
VN_METHOD = r"kho|hap|luoc|rang|rim|xao|chien|nuong|om|um|ham|tron|cuon|nau|xaot|xot|sot|chien"
ALCOHOL = r"ruou|bia|vodka|whisk(?:y|ey)|brandy|rum|gin|tequila|wine|beer|sake|cognac|liqueur|bourbon"
RAW_TITLE = r"tiet canh|goi ca|ca song|bo tai|tai chanh|tartare|sashimi|ceviche|trung song"
MEDICAL_TITLE = r"chua benh|tri benh|ha sot|giai ruou|giam can|detox|cho be|an dam|tre so sinh"
FERMENTED_TITLE = r"len men|com ruou|sua chua|dua muoi|dua cai|dua gia|mam song"


def classify_title(title):
    """Common Vietnamese home-cooking heuristic, not origin certification."""
    value = normalized(title)
    # Accent folding makes bánh cuộn (often sponge roll cake) indistinguishable
    # from bánh cuốn (Vietnamese rice rolls). Keep this unresolved rather than
    # certifying the former through the familiar-dish allowlist.
    if re.search(r"\bbánh\s+cuộn\b", unicodedata.normalize("NFC", str(title)).lower()):
        return None, "cuisine_unresolved"
    if has(FOREIGN, value):
        return None, "explicit_foreign_dish"
    if has(RAW_TITLE, value):
        return None, "raw_hazard_title"
    if has(MEDICAL_TITLE, value):
        return None, "medical_or_infant_title"
    if has(FERMENTED_TITLE, value):
        return None, "fermented_recipe_title"
    if re.search(DRINK, value):
        return "drink", None
    if has(VN_FAMILY, value) or (has(VN_PROTEIN, value) and has(VN_METHOD, value)):
        return "food", None
    return None, "cuisine_unresolved"


DESCRIPTOR_ONLY = re.compile(r"^(?:dap dap|bam|bam nho|bam nhuyen|thai lat|cat lat|cat nho|cat soi|rua sach|lam sach|bo vo|bo hat|de rao|tuy thich|tuy khau vi|de trang tri|khong bat buoc)(?:\b|$)")


def ingredient_lines(value):
    """Split only the source separators; never infer amount or serving units."""
    text = tidy(value).replace("muỗnguỗng", "muỗng")
    result = []
    for part in re.split(r"[,;\n]+", text):
        part = part.strip()
        if not part:
            continue
        if result and DESCRIPTOR_ONLY.match(normalized(part)):
            result[-1] += ", " + part
        else:
            result.append(part)
    return result


def procedure_lines(value):
    text = tidy(value).replace("muỗnguỗng", "muỗng")
    text = re.sub(r"([.!?]),\s*", r"\1 ", text)
    # Keep numerical decimals and fractions intact. This is presentation only;
    # the original complete prose is stored alongside the extracted sentences.
    result = []
    for part in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ỸĐ])", text):
        part = part.strip()
        if not part:
            continue
        plain = normalized(part)
        # Keep actual preparation intact, but don't display standalone source
        # advertising as medical benefits of a recipe. Full prose stays in raw.
        claim = has(r"giai cam|ha sot|chua benh|tri benh|tot cho suc khoe|tang suc de khang|phong benh|ngan ngua benh", plain)
        cooking = has(r"nau|dun|hap|luoc|ninh|ham|chien|xao|nuong|rua|ngam|got|bam|thai|cat|nem|khuay|vo gao", plain)
        if claim and not cooking:
            continue
        result.append(part)
    return result


def normalize_recipe(row):
    row_id = tidy(row.get("food_id"))
    title = tidy(row.get("dish_name"))
    if not re.fullmatch(r"\d{1,12}", row_id) or not 2 <= len(title) <= 180:
        return None, "invalid_id_or_title"
    recipe_type, reason = classify_title(title)
    if reason:
        return None, reason
    original_ingredients = tidy(row.get("ingredients"))
    original_method = tidy(row.get("cooking_method"))
    if any(not value or normalized(value) in ("nan", "none", "null") for value in (original_ingredients, original_method)):
        return None, "missing_recipe_parts"
    parts = ingredient_lines(original_ingredients)
    steps = procedure_lines(original_method)
    if not 1 <= len(parts) <= 70 or not 1 <= len(steps) <= 70 or any(len(part) > 2400 for part in parts + steps):
        return None, "oversized_recipe_parts"
    if has(ALCOHOL, normalized(original_ingredients)) or has(ALCOHOL, normalized(title)):
        return None, "alcohol_ingredient"
    if recipe_type == "drink" and has(r"len men|u men|men ruou", normalized(original_method)):
        return None, "fermented_drink"
    image = tidy(row.get("image_link"))
    image_url = image if urlparse(image).scheme == "https" and urlparse(image).hostname in ("monngonmoingay.com", "www.monngonmoingay.com", "image.cooky.vn", "media.cooky.vn", "img.cooky.vn") else ""
    time = tidy(row.get("cooking_time"))
    if re.fullmatch(r"\d+(?:\.\d+)?", time):
        time = time + " phút"
    if normalized(time) in ("nan", "none", "null"):
        time = ""
    servings = tidy(row.get("serving_size"))
    if normalized(servings) in ("nan", "none", "null"):
        servings = ""
    categories = [tidy(row.get("dish_type"))] + [tidy(tag) for tag in tidy(row.get("dish_tags")).split(",") if tidy(tag)]
    return {
        "id": "vifoodrec_" + row_id, "source_row_id": row_id,
        "title": title, "recipe_type": recipe_type, "language": "vi", "cuisine": "VN",
        "cuisine_basis": "Heuristic: familiar Vietnamese home-cooking dish family or preparation; geographic origin is not independently certified.",
        "ingredients": [{"name": name, "amount": "", "unit": ""} for name in parts],
        "steps": steps, "original_ingredients": original_ingredients,
        "original_cooking_method": original_method, "categories": categories,
        "cooking_time": time, "servings": servings,
        "subtitle": "Công thức tiếng Việt · ViFoodRec",
        "benefit": "Công thức nấu ăn tham khảo; chưa xác minh giá trị dinh dưỡng hoặc độ phù hợp theo bệnh cho từng món.",
        "avoid": ["Kiểm tra nguyên liệu, dị ứng, gia vị và khẩu phần theo hướng dẫn ăn uống cá nhân."],
        "source_url": DATASET_URL, "dataset_url": DATASET_URL, "repository_url": REPOSITORY,
        "paper_url": PAPER_URL, "source_provider": "ViFoodRec", "source_name": "ViFoodRec",
        "source_title": "ViFoodRec — foods.csv — food_id " + row_id,
        "source_original_publishers": ["Cooky", "Món Ngon Mỗi Ngày"],
        "source_image_url": image_url,
        "attribution": "ViFoodRec research authors; underlying recipe text collected from Cooky and Món Ngon Mỗi Ngày. Dataset row " + row_id + ".",
        "license": "not_declared", "license_note": "No explicit data reuse license found in the author repository. Authors describe free research-community access; production redistribution rights are not verified.",
        "changes": "Selected Vietnamese home-cooking titles by documented heuristic; split source ingredient separators and procedure sentences; repaired duplicated muỗnguỗng unit typo; omitted standalone non-procedural health advertising from displayed steps. Original complete text preserved; no ingredient or quantity generated.",
        "imported": True,
    }, None


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Rebuild only from already downloaded foods.csv")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw_path = OUTPUT / "foods.csv"
    if not args.offline:
        response = requests.get(DOWNLOAD_URL, timeout=60, headers={"User-Agent": "MediMind-ViFoodRec-Importer/1.0 (local research prototype)"})
        response.raise_for_status()
        if len(response.content) > 20_000_000:
            raise ValueError("Unexpectedly large foods table")
        temporary = raw_path.with_suffix(".csv.tmp")
        temporary.write_bytes(response.content)
        temporary.replace(raw_path)
    raw = raw_path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not REQUIRED.issubset(reader.fieldnames or []):
        raise ValueError("foods.csv does not have the expected ViFoodRec schema")
    records, rejected, seen, input_count = [], Counter(), set(), 0
    fingerprints = set()
    for row in reader:
        input_count += 1
        recipe, reason = normalize_recipe(row)
        if reason:
            rejected[reason] += 1
            continue
        fingerprint = (normalized(recipe["title"]), normalized(recipe["original_ingredients"]), normalized(recipe["original_cooking_method"]))
        if recipe["id"] in seen or fingerprint in fingerprints:
            rejected["duplicate_recipe"] += 1
            continue
        seen.add(recipe["id"])
        fingerprints.add(fingerprint)
        records.append(recipe)
    write_json(OUTPUT / "recipes.json", records)
    manifest = {
        "source": "ViFoodRec", "repository_url": REPOSITORY, "dataset_url": DATASET_URL,
        "download_url": DOWNLOAD_URL, "paper_url": PAPER_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "input_count": input_count, "total": len(records),
        "counts": dict(Counter(r["recipe_type"] for r in records)), "rejected": dict(rejected),
        "language": "vi", "cuisine_scope": "Vietnamese home-cooking candidates selected heuristically, not certified geographic origin",
        "license": "not_declared", "license_note": "No explicit data reuse license found. Free research access described in the paper does not verify production redistribution rights.",
        "images_downloaded": False, "ratings_downloaded": False,
        "nutrient_values_used": False, "clinical_labels_inferred": False,
        "limitations": [f"This downloaded clean foods.csv has {input_count} rows; 5509 in the paper describes the earlier full collection.",
                        "Titles and complete source ingredients/method are retained; no quantities or nutrients inferred.",
                        "Vietnamese home-cooking classification is a documented title heuristic, not independent origin verification.",
                        "Recipes, allergen absence and medical suitability are not independently verified."],
        "sha256": {name: hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() for name in ("foods.csv", "recipes.json")},
        "status": "complete", "extraction_version": 2,
    }
    write_json(OUTPUT / "manifest.json", manifest)
    print(json.dumps({"input_count": input_count, "total": len(records), "counts": manifest["counts"], "rejected": dict(rejected)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
