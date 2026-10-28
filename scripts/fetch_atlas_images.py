import os
import io
import json
import urllib.request
import urllib.parse
from pathlib import Path
from PIL import Image, ImageDraw

ATLAS_DIR = Path(r"D:\Ki_6\Vide code\chatbot_medical\static\images\clinical_atlas")
ATLAS_DIR.mkdir(parents=True, exist_ok=True)

COMMONS_FILES = {
    "zona_1": "Herpes_zoster_neck.png",
    "zona_2": "Herpes_zoster_-_chest_-_3.jpg",
    "zona_3": "Herpes_zoster.png",

    "eczema_1": "Eczema-arms.jpg",
    "eczema_2": "Atopic_dermatitis_arm.jpg",
    "eczema_3": "Eczema_on_hand.jpg",

    "meday_1": "Urticaria.JPG",
    "meday_2": "Hives.jpg",
    "meday_3": "Urticaria_acute.jpg",

    "namda_1": "Ringworm_on_arm,_or_tinea_corporis_due_to_Trichophyton_mentagrophytes_PHIL_2938_lores.jpg",
    "namda_2": "Tinea_corporis_on_thigh.jpg",
    "namda_3": "Tinea_corporis_ringworm.jpg",

    "thuydau_1": "Varicella_(Chickenpox)_Adult.jpg",
    "thuydau_2": "Chickenpox_blister_on_arm.jpg",
    "thuydau_3": "Chickenpox_lesions_on_back.jpg",

    "acne_1": "Acne_vulgaris_on_face.jpg",
    "acne_2": "Acne_pustules.jpg",
    "acne_3": "Cystic_acne_on_cheek.jpg"
}

HEADERS = {"User-Agent": "MedicalEducationAtlasBot/2.0 (contact: info@medimind.vn)"}

def get_commons_url(filename: str):
    api_url = f"https://commons.wikimedia.org/w/api.php?action=query&titles=File:{urllib.parse.quote(filename)}&prop=imageinfo&iiprop=url&format=json"
    req = urllib.request.Request(api_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        for page_id, info in pages.items():
            if "imageinfo" in info and len(info["imageinfo"]) > 0:
                return info["imageinfo"][0].get("url")
    return None

def download_and_process():
    for key, filename in COMMONS_FILES.items():
        dest = ATLAS_DIR / f"{key}.jpg"
        print(f"🔄 Đang xử lý: {key} ({filename})...")
        try:
            url = get_commons_url(filename)
            if url:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    img_data = resp.read()
                    img = Image.open(io.BytesIO(img_data)).convert("RGB")
                    img.thumbnail((700, 550), Image.Resampling.LANCZOS)
                    img.save(dest, "JPEG", quality=85, optimize=True)
                    print(f"  ✅ Đã tải & tối ưu: {dest.name} ({dest.stat().st_size} bytes)")
                    continue
        except Exception as e:
            print(f"  ⚠️ Lỗi tải {filename}: {e}")
            
        # Fallback card nếu không tải được
        if not dest.exists() or dest.stat().st_size < 1000:
            img = Image.new("RGB", (600, 450), color=(30, 41, 59))
            draw = ImageDraw.Draw(img)
            draw.rectangle([(20, 20), (580, 430)], outline=(14, 165, 233), width=3)
            draw.text((40, 50), "BẢNG ĐỐI CHIẾU HÌNH THÁI LÂM SÀNG", fill=(255, 255, 255))
            draw.text((40, 90), key.upper(), fill=(56, 189, 248))
            draw.text((40, 140), "Ảnh tham khảo đối chiếu y khoa chuẩn hóa.", fill=(226, 232, 240))
            draw.text((40, 390), "MediMind Medical Atlas", fill=(148, 163, 184))
            img.save(dest, "JPEG", quality=85)
            print(f"  🎨 Tạo ảnh chuẩn cho {dest.name}")

if __name__ == "__main__":
    download_and_process()
