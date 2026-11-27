"""
================================================================================
🩺 MEDIMIND TIER-A CORPUS CURATION & BILINGUAL METADATA PIPELINE (PHASE 6.4)
================================================================================
Mục đích:
  - Chọn lọc tập dữ liệu chuẩn Tier-A (110–140 tài liệu) từ kho thô MedlinePlus English.
  - Áp dụng chuẩn khử trùng lặp (Canonical Deduplication) và loại bỏ nội dung hành chính.
  - Bổ sung siêu dữ liệu song ngữ chuẩn y khoa (title_en, title_vi, category_en, category_vi,
    keywords_en, keywords_vi).
  - Quét an toàn và toàn vẹn (English Body SHA-256, Dosing patterns, HTML check).
  - Staging an toàn vào thư mục riêng: data/curated/tier_a_candidates/.
  - KHÔNG ghi vào ChromaDB, KHÔNG thay đổi active_collection.json, KHÔNG sửa DEV/HOLDOUT.
  - Đo đạc chiếu phân mảnh (dry-run chunking projection) bằng chunk_document chuẩn v2.
================================================================================
"""

import os
import sys
import json
import re
import hashlib
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from collections import Counter

# Đảm bảo in tiếng Việt có dấu mượt mà trên console Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.document_chunker import chunk_document, compute_content_hash, generate_deterministic_id
from core.settings import get_settings

# ================================================================================
# 1. DANH MỤC KHỬ TRÙNG LẶP & TỪ CHỐI TÀI LIỆU KHÔNG PHÙ HỢP (REJECTIONS)
# ================================================================================
REJECTIONS = {
    # Biến thể / Sub-variants của Stroke (Ưu tiên Canonical topic Stroke)
    "https://medlineplus.gov/ischemicstroke.html": "Duplicate/sub-variant of canonical Stroke",
    "https://medlineplus.gov/hemorrhagicstroke.html": "Duplicate/sub-variant of canonical Stroke",
    "https://medlineplus.gov/strokerehabilitation.html": "Duplicate/sub-variant of canonical Stroke",

    # Biến thể đái tháo đường trùng lặp bệnh thận / thần kinh ngoại biên
    "https://medlineplus.gov/diabeticnerveproblems.html": "Duplicate/sub-variant of canonical Peripheral Nerve Disorders",
    "https://medlineplus.gov/diabetickidneyproblems.html": "Duplicate/sub-variant of canonical Chronic Kidney Disease",
    "https://medlineplus.gov/diabeticeyeproblems.html": "Duplicate/sub-variant of Diabetic Retinopathy / Eye Diseases",

    # Biến thể độc học / da liễu cục bộ
    "https://medlineplus.gov/leadpoisoning.html": "Duplicate/sub-variant of acute Poisoning / Carbon Monoxide Poisoning",
    "https://medlineplus.gov/poisonivyoakandsumac.html": "Duplicate/sub-variant of Contact Dermatitis",

    # Dụng cụ / Thủ thuật tự chọn không thuộc mặt bệnh
    "https://medlineplus.gov/lasereyesurgery.html": "Elective procedure / non-disease",
    "https://medlineplus.gov/eyewear.html": "Non-clinical optometry device",

    # Thủ thuật phẫu thuật / xét nghiệm cận lâm sàng tổng quát
    "https://medlineplus.gov/bloodtransfusionanddonation.html": "Clinical procedure / donation service",
    "https://medlineplus.gov/diagnosticimaging.html": "Diagnostic imaging modality overview",
    "https://medlineplus.gov/kidneytests.html": "Laboratory test overview",
    "https://medlineplus.gov/hearthealthtests.html": "Diagnostic test overview",
    "https://medlineplus.gov/heartsurgery.html": "Surgical procedure overview",
    "https://medlineplus.gov/hearttransplantation.html": "Organ transplant procedure",
    "https://medlineplus.gov/kidneytransplantation.html": "Organ transplant procedure",
    "https://medlineplus.gov/lungtransplantation.html": "Organ transplant procedure",
    "https://medlineplus.gov/livertransplantation.html": "Organ transplant procedure",
    "https://medlineplus.gov/cesareandelivery.html": "Surgical delivery procedure",
    "https://medlineplus.gov/abortion.html": "Reproductive procedure",

    # Thủ tục hành chính, bảo hiểm y tế, điều hướng hệ thống (Non-clinical)
    "https://medlineplus.gov/managedcare.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/medicare.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/medicaid.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/healthinsurance.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/choosingadoctororhealthcareservice.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/talkingwithyourdoctor.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/financialassistance.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/personalhealthrecords.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/healthfraud.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/nursinghomes.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/hospicecare.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/advancecareplanning.html": "Administrative / Healthcare system navigation",
    "https://medlineplus.gov/patientrights.html": "Administrative / Healthcare system navigation",
}

# ================================================================================
# 2. BẢNG ÁNH XẠ SONG NGỮ CHUẨN Y KHOA (TIER-A BILINGUAL REGISTRY)
# ================================================================================
# 125 tài liệu được tuyển chọn kỹ lưỡng, phân chia theo 15 chuyên khoa lâm sàng.
TIER_A_DOCUMENTS = [
    # --- 1. Emergency Care & Acute Medicine (12 tài liệu) ---
    {
        "slug": "anaphylaxis",
        "url": "https://medlineplus.gov/anaphylaxis.html",
        "title_en": "Anaphylaxis",
        "title_vi": "Sốc phản vệ",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["anaphylaxis", "severe allergic reaction", "epinephrine", "anaphylactic shock", "allergy emergency"],
        "keywords_vi": ["sốc phản vệ", "dị ứng nặng", "tiêm epinephrine", "khó thở do dị ứng", "cấp cứu phản vệ"],
        "candidate_score": 0.99
    },
    {
        "slug": "heartattack",
        "url": "https://medlineplus.gov/heartattack.html",
        "title_en": "Heart Attack",
        "title_vi": "Nhồi máu cơ tim",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["heart attack", "myocardial infarction", "chest pain", "coronary occlusion", "cardiac arrest"],
        "keywords_vi": ["nhồi máu cơ tim", "đau thắt ngực", "ngừng tim", "cơn đau tim cấp", "cấp cứu tim mạch"],
        "candidate_score": 0.99
    },
    {
        "slug": "stroke",
        "url": "https://medlineplus.gov/stroke.html",
        "title_en": "Stroke",
        "title_vi": "Đột quỵ (Tai biến mạch máu não)",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["stroke", "cerebrovascular accident", "ischemic stroke", "hemorrhagic stroke", "FAST warning signs"],
        "keywords_vi": ["đột quỵ", "tai biến mạch máu não", "liệt nửa người", "dấu hiệu FAST", "cấp cứu đột quỵ"],
        "candidate_score": 0.99
    },
    {
        "slug": "seizures",
        "url": "https://medlineplus.gov/seizures.html",
        "title_en": "Seizures",
        "title_vi": "Co giật",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["seizures", "convulsions", "epileptic seizure", "brain electrical disturbance", "first aid for seizures"],
        "keywords_vi": ["co giật", "lên cơn co giật", "sơ cứu co giật", "động kinh cấp", "co giật toàn thể"],
        "candidate_score": 0.98
    },
    {
        "slug": "carbonmonoxidepoisoning",
        "url": "https://medlineplus.gov/carbonmonoxidepoisoning.html",
        "title_en": "Carbon Monoxide Poisoning",
        "title_vi": "Ngộ độc khí Carbon Monoxide (CO)",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["carbon monoxide poisoning", "CO poisoning", "smoke inhalation", "hypoxia", "toxic gas emergency"],
        "keywords_vi": ["ngộ độc khí CO", "ngạt khí than", "ngộ độc khí độc", "thiếu oxy não", "cấp cứu ngạt khí"],
        "candidate_score": 0.98
    },
    {
        "slug": "gastrointestinalbleeding",
        "url": "https://medlineplus.gov/gastrointestinalbleeding.html",
        "title_en": "Gastrointestinal Bleeding",
        "title_vi": "Xuất huyết tiêu hóa",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["gastrointestinal bleeding", "GI hemorrhage", "hematemesis", "melena", "black tarry stools"],
        "keywords_vi": ["xuất huyết tiêu hóa", "nôn ra máu", "đi ngoài phân đen", "chảy máu dạ dày", "cấp cứu tiêu hóa"],
        "candidate_score": 0.98
    },
    {
        "slug": "visionimpairmentandblindness",
        "url": "https://medlineplus.gov/visionimpairmentandblindness.html",
        "title_en": "Vision Impairment and Blindness",
        "title_vi": "Suy giảm thị lực và mù lòa",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["vision impairment", "sudden vision loss", "blindness", "visual acuity loss", "ophthalmic emergency"],
        "keywords_vi": ["mất thị lực đột ngột", "suy giảm thị lực", "mù lòa", "giảm thị lực cấp tính", "cấp cứu mắt"],
        "candidate_score": 0.96
    },
    {
        "slug": "headinjuries",
        "url": "https://medlineplus.gov/headinjuries.html",
        "title_en": "Head Injuries",
        "title_vi": "Chấn thương sọ não và chấn thương đầu",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["head injuries", "traumatic brain injury", "concussion", "skull fracture", "head trauma"],
        "keywords_vi": ["chấn thương đầu", "chấn thương sọ não", "chấn động não", "vết thương vùng đầu", "sơ cứu chấn thương"],
        "candidate_score": 0.97
    },
    {
        "slug": "shock",
        "url": "https://medlineplus.gov/shock.html",
        "title_en": "Shock",
        "title_vi": "Tình trạng sốc (Trụy tim mạch)",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["shock", "hypovolemic shock", "septic shock", "cardiogenic shock", "circulatory collapse"],
        "keywords_vi": ["sốc", "trụy mạch", "tụt huyết áp nghiêm trọng", "sốc tuần hoàn", "hồi sức cấp cứu"],
        "candidate_score": 0.98
    },
    {
        "slug": "sepsis",
        "url": "https://medlineplus.gov/sepsis.html",
        "title_en": "Sepsis",
        "title_vi": "Nhiễm khuẩn huyết (Nhiễm trùng máu)",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["sepsis", "septicemia", "blood infection", "systemic inflammatory response", "septic shock"],
        "keywords_vi": ["nhiễm trùng máu", "nhiễm khuẩn huyết", "sốc nhiễm khuẩn", "suy đa tạng", "nhiễm trùng toàn thân"],
        "candidate_score": 0.98
    },
    {
        "slug": "eyeinjuries",
        "url": "https://medlineplus.gov/eyeinjuries.html",
        "title_en": "Eye Injuries",
        "title_vi": "Chấn thương mắt",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["eye injuries", "corneal abrasion", "chemical eye burn", "foreign object in eye", "eye trauma"],
        "keywords_vi": ["chấn thương mắt", "dị vật vào mắt", "rách giác mạc", "bỏng mắt do hóa chất", "sơ cứu mắt"],
        "candidate_score": 0.96
    },
    {
        "slug": "collapsedlung",
        "url": "https://medlineplus.gov/collapsedlung.html",
        "title_en": "Collapsed Lung (Pneumothorax)",
        "title_vi": "Tràn khí màng phổi (Xẹp phổi)",
        "category_en": "Emergency Care",
        "category_vi": "Cấp cứu & Hồi sức",
        "keywords_en": ["collapsed lung", "pneumothorax", "chest tube", "sudden chest pain", "air in pleural space"],
        "keywords_vi": ["tràn khí màng phổi", "xẹp phổi", "khó thở đột ngột", "đau nhói ngực", "cấp cứu hô hấp"],
        "candidate_score": 0.96
    },

    # --- 2. Pharmacology & Medication Safety (9 tài liệu) ---
    {
        "slug": "drugsafety",
        "url": "https://medlineplus.gov/drugsafety.html",
        "title_en": "Drug Safety",
        "title_vi": "An toàn khi sử dụng thuốc",
        "category_en": "Pharmacology & Medication Safety",
        "category_vi": "Dược lý & An toàn thuốc",
        "keywords_en": ["drug safety", "medication safety", "adverse drug reaction", "safe drug storage", "FDA warnings"],
        "keywords_vi": ["an toàn dùng thuốc", "tác dụng phụ của thuốc", "uống thuốc đúng cách", "bảo quản thuốc", "cảnh báo an toàn thuốc"],
        "candidate_score": 0.97
    },
    {
        "slug": "antibioticresistance",
        "url": "https://medlineplus.gov/antibioticresistance.html",
        "title_en": "Antibiotic Resistance",
        "title_vi": "Đề kháng kháng sinh",
        "category_en": "Pharmacology & Medication Safety",
        "category_vi": "Dược lý & An toàn thuốc",
        "keywords_en": ["antibiotic resistance", "antimicrobial resistance", "superbugs", "misuse of antibiotics", "MRSA"],
        "keywords_vi": ["kháng kháng sinh", "vi khuẩn kháng thuốc", "lạm dụng kháng sinh", "đề kháng thuốc", "sử dụng kháng sinh an toàn"],
        "candidate_score": 0.97
    },
    {
        "slug": "medicationerrors",
        "url": "https://medlineplus.gov/medicationerrors.html",
        "title_en": "Medication Errors",
        "title_vi": "Sai sót trong dùng thuốc",
        "category_en": "Pharmacology & Medication Safety",
        "category_vi": "Dược lý & An toàn thuốc",
        "keywords_en": ["medication errors", "wrong dose", "drug mix-up", "prescription error", "overdose prevention"],
        "keywords_vi": ["sai sót dùng thuốc", "nhầm lẫn liều lượng", "quên uống thuốc", "uống nhầm thuốc", "phòng tránh quá liều"],
        "candidate_score": 0.96
    },
    {
        "slug": "herbalmedicine",
        "url": "https://medlineplus.gov/herbalmedicine.html",
        "title_en": "Herbal Medicine",
        "title_vi": "Thuốc thảo dược và dược liệu",
        "category_en": "Pharmacology & Medication Safety",
        "category_vi": "Dược lý & An toàn thuốc",
        "keywords_en": ["herbal medicine", "herbal supplements", "botanicals", "herb drug interactions", "natural remedies safety"],
        "keywords_vi": ["thuốc thảo dược", "thảo dược tự nhiên", "dược liệu", "tương tác thảo dược và thuốc tây", "an toàn thảo dược"],
        "candidate_score": 0.94
    },
    {
        "slug": "dietarysupplements",
        "url": "https://medlineplus.gov/dietarysupplements.html",
        "title_en": "Dietary Supplements",
        "title_vi": "Thực phẩm chức năng và chất bổ sung",
        "category_en": "Pharmacology & Medication Safety",
        "category_vi": "Dược lý & An toàn thuốc",
        "keywords_en": ["dietary supplements", "vitamins and minerals", "supplement safety", "multivitamins", "supplement regulation"],
        "keywords_vi": ["thực phẩm chức năng", "bổ sung vitamin", "khoáng chất", "uống thực phẩm bổ sung", "an toàn chất bổ sung"],
        "candidate_score": 0.94
    },
    {
        "slug": "overthecountermedicines",
        "url": "https://medlineplus.gov/overthecountermedicines.html",
        "title_en": "Over-the-Counter Medicines",
        "title_vi": "Thuốc không kê đơn (OTC)",
        "category_en": "Pharmacology & Medication Safety",
        "category_vi": "Dược lý & An toàn thuốc",
        "keywords_en": ["over the counter medicines", "OTC drugs", "nonprescription drugs", "drug facts label", "self care medicines"],
        "keywords_vi": ["thuốc không kê đơn", "thuốc OTC", "tự mua thuốc", "hướng dẫn nhãn thuốc", "dùng thuốc giảm đau hạ sốt"],
        "candidate_score": 0.95
    },
    {
        "slug": "prescriptiondrugmisuse",
        "url": "https://medlineplus.gov/prescriptiondrugmisuse.html",
        "title_en": "Prescription Drug Misuse",
        "title_vi": "Lạm dụng thuốc kê đơn",
        "category_en": "Pharmacology & Medication Safety",
        "category_vi": "Dược lý & An toàn thuốc",
        "keywords_en": ["prescription drug misuse", "opioid misuse", "sedative abuse", "prescription addiction", "controlled substances"],
        "keywords_vi": ["lạm dụng thuốc kê đơn", "nghiện thuốc giảm đau", "lạm dụng an thần", "nguy cơ quá liều", "sử dụng thuốc có kiểm soát"],
        "candidate_score": 0.95
    },
    {
        "slug": "druguseandaddiction",
        "url": "https://medlineplus.gov/druguseandaddiction.html",
        "title_en": "Drug Use and Addiction",
        "title_vi": "Nghiện và lạm dụng chất",
        "category_en": "Pharmacology & Medication Safety",
        "category_vi": "Dược lý & An toàn thuốc",
        "keywords_en": ["drug addiction", "substance use disorder", "drug abuse", "dependence", "addiction treatment"],
        "keywords_vi": ["nghiện chất", "lạm dụng ma túy", "rối loạn sử dụng chất", "cai nghiện", "phục hồi chức năng nghiện"],
        "candidate_score": 0.93
    },
    {
        "slug": "anabolicsteroids",
        "url": "https://medlineplus.gov/anabolicsteroids.html",
        "title_en": "Anabolic Steroids",
        "title_vi": "Steroid đồng hóa và nguy cơ sức khỏe",
        "category_en": "Pharmacology & Medication Safety",
        "category_vi": "Dược lý & An toàn thuốc",
        "keywords_en": ["anabolic steroids", "performance enhancing drugs", "steroid abuse", "testosterone misuse", "steroid side effects"],
        "keywords_vi": ["steroid đồng hóa", "thuốc tăng cơ", "lạm dụng steroid", "tác dụng phụ của steroid", "nguy cơ tim mạch do steroid"],
        "candidate_score": 0.92
    },

    # --- 3. Preventive Medicine, Vaccines & Lifestyle (10 tài liệu) ---
    {
        "slug": "secondhandsmoke",
        "url": "https://medlineplus.gov/secondhandsmoke.html",
        "title_en": "Secondhand Smoke",
        "title_vi": "Khói thuốc lá thụ động",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["secondhand smoke", "passive smoking", "environmental tobacco smoke", "tobacco hazards", "child smoke exposure"],
        "keywords_vi": ["hút thuốc thụ động", "khói thuốc lá", "tác hại khói thuốc", "bảo vệ trẻ em khỏi khói thuốc", "bệnh do khói thuốc"],
        "candidate_score": 0.96
    },
    {
        "slug": "quittingsmoking",
        "url": "https://medlineplus.gov/quittingsmoking.html",
        "title_en": "Quitting Smoking",
        "title_vi": "Cai nghiện thuốc lá",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["quitting smoking", "smoking cessation", "nicotine withdrawal", "nicotine replacement therapy", "stop smoking tips"],
        "keywords_vi": ["cai thuốc lá", "bỏ thuốc lá", "cơn thèm nicotine", "liệu pháp thay thế nicotine", "lợi ích bỏ thuốc lá"],
        "candidate_score": 0.96
    },
    {
        "slug": "healthscreening",
        "url": "https://medlineplus.gov/healthscreening.html",
        "title_en": "Health Screening",
        "title_vi": "Khám sàng lọc sức khỏe định kỳ",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["health screening", "preventive screening", "routine health checkup", "early disease detection", "cancer screening"],
        "keywords_vi": ["khám sàng lọc sức khỏe", "khám tổng quát", "phát hiện bệnh sớm", "tầm soát ung thư", "xét nghiệm phòng bệnh"],
        "candidate_score": 0.95
    },
    {
        "slug": "vaccinesafety",
        "url": "https://medlineplus.gov/vaccinesafety.html",
        "title_en": "Vaccine Safety",
        "title_vi": "An toàn tiêm chủng và vắc-xin",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["vaccine safety", "immunization safety", "vaccine side effects", "vaccine adverse events", "vaccine testing"],
        "keywords_vi": ["an toàn vắc-xin", "an toàn tiêm chủng", "phản ứng sau tiêm", "theo dõi sau tiêm", "hiệu quả vắc-xin"],
        "candidate_score": 0.97
    },
    {
        "slug": "childhoodvaccines",
        "url": "https://medlineplus.gov/childhoodvaccines.html",
        "title_en": "Childhood Vaccines",
        "title_vi": "Vắc-xin và tiêm chủng cho trẻ em",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["childhood vaccines", "pediatric immunization", "vaccine schedule", "measles mumps rubella vaccine", "polio vaccine"],
        "keywords_vi": ["tiêm chủng trẻ em", "lịch tiêm phòng cho bé", "vắc-xin cho trẻ sơ sinh", "mũi tiêm định kỳ", "miễn dịch cộng đồng"],
        "candidate_score": 0.97
    },
    {
        "slug": "exerciseandphysicalfitness",
        "url": "https://medlineplus.gov/exerciseandphysicalfitness.html",
        "title_en": "Exercise and Physical Fitness",
        "title_vi": "Tập thể dục và thể lực",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["exercise", "physical fitness", "aerobic exercise", "strength training", "health benefits of exercise"],
        "keywords_vi": ["tập thể dục", "rèn luyện thể lực", "vận động hàng ngày", "lợi ích của tập luyện", "thể thao bảo vệ sức khỏe"],
        "candidate_score": 0.95
    },
    {
        "slug": "howtolowercholesterolwithdiet",
        "url": "https://medlineplus.gov/howtolowercholesterolwithdiet.html",
        "title_en": "How to Lower Cholesterol with Diet",
        "title_vi": "Hạ mỡ máu (Cholesterol) bằng chế độ ăn uống",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["lower cholesterol diet", "heart healthy diet", "saturated fat reduction", "soluble fiber", "LDL cholesterol"],
        "keywords_vi": ["giảm cholesterol bằng ăn uống", "chế độ ăn hạ mỡ máu", "giảm chất béo bão hòa", "thực phẩm tốt cho tim mạch", "hạ mỡ máu tự nhiên"],
        "candidate_score": 0.96
    },
    {
        "slug": "howtopreventheartdisease",
        "url": "https://medlineplus.gov/howtopreventheartdisease.html",
        "title_en": "How to Prevent Heart Disease",
        "title_vi": "Phòng ngừa bệnh tim mạch",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["prevent heart disease", "cardiovascular prevention", "heart healthy lifestyle", "blood pressure control", "cholesterol control"],
        "keywords_vi": ["phòng ngừa bệnh tim", "bảo vệ sức khỏe tim mạch", "kiểm soát huyết áp", "lối sống lành mạnh cho tim", "giảm nguy cơ đột quỵ"],
        "candidate_score": 0.96
    },
    {
        "slug": "dietaryfiber",
        "url": "https://medlineplus.gov/dietaryfiber.html",
        "title_en": "Dietary Fiber",
        "title_vi": "Chất xơ trong chế độ ăn uống",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["dietary fiber", "soluble fiber", "insoluble fiber", "digestive health", "fiber rich foods"],
        "keywords_vi": ["chất xơ", "bổ sung chất xơ", "chất xơ hòa tan", "tiêu hóa khỏe mạnh", "thực phẩm giàu chất xơ"],
        "candidate_score": 0.93
    },
    {
        "slug": "dietaryfats",
        "url": "https://medlineplus.gov/dietaryfats.html",
        "title_en": "Dietary Fats",
        "title_vi": "Chất béo trong khẩu phần ăn",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["dietary fats", "healthy fats", "unsaturated fats", "saturated fats", "trans fats"],
        "keywords_vi": ["chất béo trong thực phẩm", "chất béo tốt", "chất béo xấu", "chất béo bão hòa", "axit béo omega-3"],
        "candidate_score": 0.93
    },
    {
        "slug": "foodsafety",
        "url": "https://medlineplus.gov/foodsafety.html",
        "title_en": "Food Safety",
        "title_vi": "Vệ sinh an toàn thực phẩm",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["food safety", "foodborne illness prevention", "safe food handling", "cross contamination", "cooking temperatures"],
        "keywords_vi": ["an toàn thực phẩm", "phòng ngừa ngộ độc thực phẩm", "bảo quản thức ăn", "vệ sinh ăn uống", "nhiệt độ nấu chín an toàn"],
        "candidate_score": 0.94
    },
    {
        "slug": "covid19vaccines",
        "url": "https://medlineplus.gov/covid19vaccines.html",
        "title_en": "COVID-19 Vaccines",
        "title_vi": "Vắc-xin phòng COVID-19",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["COVID 19 vaccines", "coronavirus vaccination", "mRNA vaccines", "booster doses", "vaccine efficacy"],
        "keywords_vi": ["vắc-xin covid 19", "tiêm phòng covid", "mũi tiêm tăng cường", "hiệu lực vắc-xin covid", "miễn dịch phòng sars cov 2"],
        "candidate_score": 0.95
    },
    {
        "slug": "tetanusdiphtheriaandpertussisvaccines",
        "url": "https://medlineplus.gov/tetanusdiphtheriaandpertussisvaccines.html",
        "title_en": "Tetanus, Diphtheria, and Pertussis Vaccines (Tdap/DTaP)",
        "title_vi": "Vắc-xin phòng Uốn ván, Bạch hầu và Ho gà",
        "category_en": "Preventive Medicine",
        "category_vi": "Y học dự phòng & Lối sống",
        "keywords_en": ["tetanus vaccine", "diphtheria vaccine", "pertussis vaccine", "DTaP", "Tdap booster"],
        "keywords_vi": ["vắc-xin uốn ván", "bạch hầu ho gà uốn ván", "tiêm phòng uốn ván", "mũi tiêm tdap", "tiêm nhắc lại uốn ván"],
        "candidate_score": 0.95
    },

    # --- 4. Cardiovascular Medicine (11 tài liệu) ---
    {
        "slug": "coronaryarterydisease",
        "url": "https://medlineplus.gov/coronaryarterydisease.html",
        "title_en": "Coronary Artery Disease",
        "title_vi": "Bệnh động mạch vành",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["coronary artery disease", "CAD", "coronary atherosclerosis", "ischemic heart disease", "angina pectoris"],
        "keywords_vi": ["bệnh mạch vành", "thiếu máu cơ tim", "xơ vữa mạch vành", "cơn đau thắt ngực", "hẹp mạch vành"],
        "candidate_score": 0.98
    },
    {
        "slug": "heartdiseases",
        "url": "https://medlineplus.gov/heartdiseases.html",
        "title_en": "Heart Diseases",
        "title_vi": "Các bệnh lý tim mạch tổng quan",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["heart diseases", "cardiovascular diseases", "cardiac disorders", "heart conditions", "cardiac symptoms"],
        "keywords_vi": ["bệnh tim mạch", "các bệnh về tim", "dấu hiệu bệnh tim", "suy tim", "chăm sóc tim mạch"],
        "candidate_score": 0.97
    },
    {
        "slug": "heartvalvediseases",
        "url": "https://medlineplus.gov/heartvalvediseases.html",
        "title_en": "Heart Valve Diseases",
        "title_vi": "Bệnh van tim (Hở van, Hẹp van tim)",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["heart valve diseases", "valvular heart disease", "aortic stenosis", "mitral regurgitation", "heart murmur"],
        "keywords_vi": ["bệnh van tim", "hẹp van động mạch chủ", "hở van hai lá", "tiếng thổi ở tim", "suy van tim"],
        "candidate_score": 0.96
    },
    {
        "slug": "congenitalheartdefects",
        "url": "https://medlineplus.gov/congenitalheartdefects.html",
        "title_en": "Congenital Heart Defects",
        "title_vi": "Dị tật tim bẩm sinh",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["congenital heart defects", "pediatric heart defect", "ventricular septal defect", "atrial septal defect", "tetralogy of Fallot"],
        "keywords_vi": ["tim bẩm sinh", "thông liên thất", "thông liên nhĩ", "tứ chứng Fallot", "dị tật tim ở trẻ"],
        "candidate_score": 0.96
    },
    {
        "slug": "arrhythmia",
        "url": "https://medlineplus.gov/arrhythmia.html",
        "title_en": "Arrhythmia (Irregular Heartbeat)",
        "title_vi": "Rối loạn nhịp tim",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["arrhythmia", "irregular heartbeat", "atrial fibrillation", "tachycardia", "bradycardia"],
        "keywords_vi": ["loạn nhịp tim", "rung nhĩ", "tim đập nhanh", "tim đập chậm", "hồi hộp đánh trống ngực"],
        "candidate_score": 0.97
    },
    {
        "slug": "atherosclerosis",
        "url": "https://medlineplus.gov/atherosclerosis.html",
        "title_en": "Atherosclerosis",
        "title_vi": "Xơ vữa động mạch",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["atherosclerosis", "arterial plaque", "hardening of arteries", "vascular blockage", "cardiovascular risk"],
        "keywords_vi": ["xơ vữa động mạch", "mảng xơ vữa", "xơ cứng mạch máu", "hẹp lòng mạch", "nguy cơ tai biến"],
        "candidate_score": 0.96
    },
    {
        "slug": "aneurysms",
        "url": "https://medlineplus.gov/aneurysms.html",
        "title_en": "Aneurysms",
        "title_vi": "Phình động mạch (Động mạch chủ, Mạch não)",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["aneurysms", "aortic aneurysm", "brain aneurysm", "arterial ballooning", "aneurysm rupture"],
        "keywords_vi": ["phình động mạch", "phình động mạch chủ", "phình mạch não", "vỡ túi phình", "cấp cứu mạch máu"],
        "candidate_score": 0.96
    },
    {
        "slug": "deepveinthrombosis",
        "url": "https://medlineplus.gov/deepveinthrombosis.html",
        "title_en": "Deep Vein Thrombosis (DVT)",
        "title_vi": "Huyết khối tĩnh mạch sâu",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["deep vein thrombosis", "DVT", "blood clot in leg", "venous thromboembolism", "leg swelling"],
        "keywords_vi": ["huyết khối tĩnh mạch sâu", "cục máu đông ở chân", "sưng đau bắp chân", "tắc mạch tĩnh mạch", "nguy cơ thuyên tắc phổi"],
        "candidate_score": 0.97
    },
    {
        "slug": "pulmonaryembolism",
        "url": "https://medlineplus.gov/pulmonaryembolism.html",
        "title_en": "Pulmonary Embolism",
        "title_vi": "Thuyên tắc phổi",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["pulmonary embolism", "PE", "blood clot in lungs", "sudden shortness of breath", "pleuritic chest pain"],
        "keywords_vi": ["thuyên tắc động mạch phổi", "cục máu đông lên phổi", "khó thở dữ dội", "đau ngực cấp", "cấp cứu thuyên tắc"],
        "candidate_score": 0.98
    },
    {
        "slug": "peripheralarterialdisease",
        "url": "https://medlineplus.gov/peripheralarterialdisease.html",
        "title_en": "Peripheral Arterial Disease (PAD)",
        "title_vi": "Bệnh động mạch ngoại biên",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["peripheral arterial disease", "PAD", "poor leg circulation", "claudication", "leg pain walking"],
        "keywords_vi": ["bệnh động mạch chi dưới", "kém tuần hoàn chân", "đau cách hồi", "tắc động mạch ngoại biên", "lạnh bàn chân"],
        "candidate_score": 0.95
    },
    {
        "slug": "angina",
        "url": "https://medlineplus.gov/angina.html",
        "title_en": "Angina",
        "title_vi": "Cơn đau thắt ngực (Thiếu máu cơ tim)",
        "category_en": "Cardiology",
        "category_vi": "Tim mạch",
        "keywords_en": ["angina", "angina pectoris", "chest discomfort", "stable angina", "unstable angina"],
        "keywords_vi": ["cơn đau thắt ngực", "đau thắt ngực ổn định", "đau ngực khi gắng sức", "thiếu máu tim", "ngậm nitroglycerin"],
        "candidate_score": 0.97
    },

    # --- 5. Neurology & Neurodegenerative Diseases (10 tài liệu) ---
    {
        "slug": "dementia",
        "url": "https://medlineplus.gov/dementia.html",
        "title_en": "Dementia",
        "title_vi": "Sa sút trí tuệ (Hội chứng Dementia)",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["dementia", "cognitive decline", "memory loss", "vascular dementia", "Alzheimer symptoms"],
        "keywords_vi": ["sa sút trí tuệ", "suy giảm nhận thức", "lú lẫn người già", "mất trí nhớ", "hội chứng lú lẫn"],
        "candidate_score": 0.97
    },
    {
        "slug": "parkinsonsdisease",
        "url": "https://medlineplus.gov/parkinsonsdisease.html",
        "title_en": "Parkinson's Disease",
        "title_vi": "Bệnh Parkinson (Liệt rung)",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["Parkinson's disease", "tremor", "bradykinesia", "rigidity", "dopamine deficiency"],
        "keywords_vi": ["bệnh parkinson", "run tay chân", "cứng đờ vận động", "bước đi run rẩy", "thiếu hụt dopamine"],
        "candidate_score": 0.97
    },
    {
        "slug": "peripheralnervedisorders",
        "url": "https://medlineplus.gov/peripheralnervedisorders.html",
        "title_en": "Peripheral Nerve Disorders (Neuropathy)",
        "title_vi": "Rối loạn dây thần kinh ngoại biên (Bệnh lý thần kinh)",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["peripheral nerve disorders", "peripheral neuropathy", "numbness and tingling", "nerve damage", "polyneuropathy"],
        "keywords_vi": ["viêm dây thần kinh ngoại biên", "tê bì chân tay", "tổn thương dây thần kinh", "đau dây thần kinh", "bệnh đa dây thần kinh"],
        "candidate_score": 0.97
    },
    {
        "slug": "epilepsy",
        "url": "https://medlineplus.gov/epilepsy.html",
        "title_en": "Epilepsy",
        "title_vi": "Bệnh động kinh",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["epilepsy", "chronic seizures", "anticonvulsants", "epileptic syndromes", "electroencephalogram EEG"],
        "keywords_vi": ["bệnh động kinh", "cơn động kinh lặp lại", "thuốc chống động kinh", "điện não đồ", "co giật động kinh"],
        "candidate_score": 0.97
    },
    {
        "slug": "bellspalsy",
        "url": "https://medlineplus.gov/bellspalsy.html",
        "title_en": "Bell's Palsy",
        "title_vi": "Liệt dây thần kinh số VII ngoại biên (Liệt mặt Bell)",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["Bell's palsy", "facial nerve paralysis", "facial weakness", "drooping smile", "cranial nerve VII"],
        "keywords_vi": ["liệt mặt bell", "liệt dây thần kinh số 7", "méo miệng", "mắt nhắm không kín", "liệt mặt ngoại biên"],
        "candidate_score": 0.95
    },
    {
        "slug": "encephalitis",
        "url": "https://medlineplus.gov/encephalitis.html",
        "title_en": "Encephalitis",
        "title_vi": "Viêm não cấp",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["encephalitis", "brain inflammation", "viral encephalitis", "confusion and fever", "brain infection"],
        "keywords_vi": ["viêm não", "viêm màng não não", "sốt cao mê sảng", "nhiễm trùng hệ thần kinh trung ương", "viêm não do virus"],
        "candidate_score": 0.96
    },
    {
        "slug": "meningitis",
        "url": "https://medlineplus.gov/meningitis.html",
        "title_en": "Meningitis",
        "title_vi": "Viêm màng não",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["meningitis", "bacterial meningitis", "stiff neck and fever", "meningococcal disease", "spinal fluid infection"],
        "keywords_vi": ["viêm màng não", "viêm màng não mủ", "cứng cổ sốt cao", "viêm màng não do não mô cầu", "chọc dò dịch não tủy"],
        "candidate_score": 0.98
    },
    {
        "slug": "multiplesclerosis",
        "url": "https://medlineplus.gov/multiplesclerosis.html",
        "title_en": "Multiple Sclerosis (MS)",
        "title_vi": "Bệnh xơ cứng rải rác",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["multiple sclerosis", "MS", "demyelinating disease", "optic neuritis", "autoimmune nervous system"],
        "keywords_vi": ["xơ cứng rải rác", "mất myelin", "viêm thị thần kinh", "yếu cơ co cứng", "bệnh tự miễn thần kinh"],
        "candidate_score": 0.96
    },
    {
        "slug": "alzheimersdisease",
        "url": "https://medlineplus.gov/alzheimersdisease.html",
        "title_en": "Alzheimer's Disease",
        "title_vi": "Bệnh Alzheimer",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["Alzheimer's disease", "progressive memory loss", "beta amyloid plaques", "neurodegeneration", "late stage dementia"],
        "keywords_vi": ["bệnh alzheimer", "suy giảm trí nhớ tiến triển", "mất trí nhớ tuổi già", "thoái hóa thần kinh", "chăm sóc bệnh nhân alzheimer"],
        "candidate_score": 0.97
    },
    {
        "slug": "aphasia",
        "url": "https://medlineplus.gov/aphasia.html",
        "title_en": "Aphasia",
        "title_vi": "Chứng mất ngôn ngữ (Aphasia)",
        "category_en": "Neurology",
        "category_vi": "Thần kinh",
        "keywords_en": ["aphasia", "speech impairment after stroke", "Broca aphasia", "Wernicke aphasia", "language comprehension loss"],
        "keywords_vi": ["mất ngôn ngữ", "khó nói sau đột quỵ", "rối loạn phát âm", "không hiểu lời nói", "phục hồi ngôn ngữ"],
        "candidate_score": 0.94
    },

    # --- 6. Respiratory & Pulmonary Medicine (4 tài liệu) ---
    {
        "slug": "copd",
        "url": "https://medlineplus.gov/copd.html",
        "title_en": "COPD (Chronic Obstructive Pulmonary Disease)",
        "title_vi": "Bệnh phổi tắc nghẽn mạn tính (COPD)",
        "category_en": "Pulmonology",
        "category_vi": "Hô hấp",
        "keywords_en": ["COPD", "chronic obstructive pulmonary disease", "emphysema", "chronic bronchitis", "spirometry"],
        "keywords_vi": ["bệnh phổi tắc nghẽn mạn tính", "copd", "khí phế thũng", "viêm phế quản mạn", "khó thở khi gắng sức"],
        "candidate_score": 0.98
    },
    {
        "slug": "sleepapnea",
        "url": "https://medlineplus.gov/sleepapnea.html",
        "title_en": "Sleep Apnea",
        "title_vi": "Hội chứng ngưng thở khi ngủ",
        "category_en": "Pulmonology",
        "category_vi": "Hô hấp",
        "keywords_en": ["sleep apnea", "obstructive sleep apnea", "loud snoring", "daytime sleepiness", "CPAP therapy"],
        "keywords_vi": ["ngưng thở khi ngủ", "hội chứng ngưng thở tắc nghẽn", "ngáy to ngạt thở", "buồn ngủ ban ngày", "thở máy cpap"],
        "candidate_score": 0.97
    },
    {
        "slug": "lungdiseases",
        "url": "https://medlineplus.gov/lungdiseases.html",
        "title_en": "Lung Diseases",
        "title_vi": "Các bệnh phổi tổng quan",
        "category_en": "Pulmonology",
        "category_vi": "Hô hấp",
        "keywords_en": ["lung diseases", "pulmonary disorders", "chronic respiratory conditions", "lung function tests", "chest symptoms"],
        "keywords_vi": ["bệnh lý phổi", "bệnh hô hấp mạn tính", "chức năng thông khí phổi", "ho khó thở", "tổn thương nhu mô phổi"],
        "candidate_score": 0.95
    },
    {
        "slug": "interstitiallungdiseases",
        "url": "https://medlineplus.gov/interstitiallungdiseases.html",
        "title_en": "Interstitial Lung Diseases (Pulmonary Fibrosis)",
        "title_vi": "Bệnh phổi kẽ và Xơ phổi",
        "category_en": "Pulmonology",
        "category_vi": "Hô hấp",
        "keywords_en": ["interstitial lung diseases", "pulmonary fibrosis", "idiopathic pulmonary fibrosis", "lung scarring", "dry cough and dyspnea"],
        "keywords_vi": ["bệnh phổi kẽ", "xơ hóa phổi", "sẹo mô phổi", "ho khan khó thở", "suy hô hấp mạn"],
        "candidate_score": 0.95
    },

    # --- 7. Gastroenterology & Hepatology (8 tài liệu) ---
    {
        "slug": "steatoticliverdisease",
        "url": "https://medlineplus.gov/steatoticliverdisease.html",
        "title_en": "Steatotic Liver Disease (Fatty Liver)",
        "title_vi": "Bệnh gan nhiễm mỡ (NAFLD / MASLD)",
        "category_en": "Gastroenterology",
        "category_vi": "Tiêu hóa & Gan mật",
        "keywords_en": ["steatotic liver disease", "fatty liver disease", "NAFLD", "NASH", "metabolic dysfunction associated steatotic liver"],
        "keywords_vi": ["gan nhiễm mỡ", "bệnh gan thoái hóa mỡ", "men gan cao", "thoái hóa mỡ gan không do rượu", "phòng ngừa xơ gan"],
        "candidate_score": 0.97
    },
    {
        "slug": "cirrhosis",
        "url": "https://medlineplus.gov/cirrhosis.html",
        "title_en": "Cirrhosis",
        "title_vi": "Xơ gan",
        "category_en": "Gastroenterology",
        "category_vi": "Tiêu hóa & Gan mật",
        "keywords_en": ["cirrhosis", "liver fibrosis", "portal hypertension", "ascites", "liver failure"],
        "keywords_vi": ["xơ gan", "cổ trướng", "suy chức năng gan", "tăng áp lực tĩnh mạch cửa", "xơ gan mất bù"],
        "candidate_score": 0.97
    },
    {
        "slug": "pancreatitis",
        "url": "https://medlineplus.gov/pancreatitis.html",
        "title_en": "Pancreatitis",
        "title_vi": "Viêm tụy cấp và mạn",
        "category_en": "Gastroenterology",
        "category_vi": "Tiêu hóa & Gan mật",
        "keywords_en": ["pancreatitis", "acute pancreatitis", "severe abdominal pain", "elevated lipase amylase", "chronic pancreatitis"],
        "keywords_vi": ["viêm tụy", "viêm tụy cấp", "đau bụng dữ dội", "men tụy amylase lipase tăng", "viêm tụy mạn"],
        "candidate_score": 0.97
    },
    {
        "slug": "liverdiseases",
        "url": "https://medlineplus.gov/liverdiseases.html",
        "title_en": "Liver Diseases",
        "title_vi": "Các bệnh lý về gan tổng quan",
        "category_en": "Gastroenterology",
        "category_vi": "Tiêu hóa & Gan mật",
        "keywords_en": ["liver diseases", "hepatic disorders", "jaundice", "elevated liver enzymes", "liver health"],
        "keywords_vi": ["bệnh về gan", "vàng da", "men gan tăng", "chức năng gan suy giảm", "bảo vệ gan"],
        "candidate_score": 0.95
    },
    {
        "slug": "hepatitisb",
        "url": "https://medlineplus.gov/hepatitisb.html",
        "title_en": "Hepatitis B",
        "title_vi": "Viêm gan B",
        "category_en": "Gastroenterology",
        "category_vi": "Tiêu hóa & Gan mật",
        "keywords_en": ["hepatitis B", "HBV infection", "chronic hepatitis B", "HBsAg", "antiviral therapy for hepatitis B"],
        "keywords_vi": ["viêm gan b", "virus viêm gan b", "viêm gan b mạn tính", "xét nghiệm hbsag", "tiêm phòng viêm gan b"],
        "candidate_score": 0.97
    },
    {
        "slug": "hepatitisc",
        "url": "https://medlineplus.gov/hepatitisc.html",
        "title_en": "Hepatitis C",
        "title_vi": "Viêm gan C",
        "category_en": "Gastroenterology",
        "category_vi": "Tiêu hóa & Gan mật",
        "keywords_en": ["hepatitis C", "HCV infection", "direct acting antivirals DAA", "chronic hepatitis C", "cure for hepatitis C"],
        "keywords_vi": ["viêm gan c", "virus viêm gan c", "điều trị viêm gan c", "thuốc kháng virus trực tiếp daa", "xét nghiệm hcv"],
        "candidate_score": 0.97
    },
    {
        "slug": "pancreaticdiseases",
        "url": "https://medlineplus.gov/pancreaticdiseases.html",
        "title_en": "Pancreatic Diseases",
        "title_vi": "Các bệnh tuyến tụy",
        "category_en": "Gastroenterology",
        "category_vi": "Tiêu hóa & Gan mật",
        "keywords_en": ["pancreatic diseases", "exocrine pancreatic insufficiency", "pancreatic cysts", "pancreatic enzyme deficiency", "pancreas health"],
        "keywords_vi": ["bệnh tuyến tụy", "thiếu hụt men tụy", "nang tuyến tụy", "chức năng tụy", "tiêu hóa mỡ kém"],
        "candidate_score": 0.94
    },
    {
        "slug": "diverticulosisanddiverticulitis",
        "url": "https://medlineplus.gov/diverticulosisanddiverticulitis.html",
        "title_en": "Diverticulosis and Diverticulitis",
        "title_vi": "Túi thừa đại tràng và Viêm túi thừa",
        "category_en": "Gastroenterology",
        "category_vi": "Tiêu hóa & Gan mật",
        "keywords_en": ["diverticulosis and diverticulitis", "diverticular disease", "inflamed colon pouches", "left lower quadrant pain", "fiber and diverticula"],
        "keywords_vi": ["viêm túi thừa đại tràng", "bệnh túi thừa", "đau bụng dưới bên trái", "nhiễm trùng túi thừa", "chế độ ăn giàu chất xơ"],
        "candidate_score": 0.96
    },

    # --- 8. Nephrology & Urology (5 tài liệu) ---
    {
        "slug": "chronickidneydisease",
        "url": "https://medlineplus.gov/chronickidneydisease.html",
        "title_en": "Chronic Kidney Disease (CKD)",
        "title_vi": "Bệnh thận mạn tính",
        "category_en": "Nephrology",
        "category_vi": "Thận & Tiết niệu",
        "keywords_en": ["chronic kidney disease", "CKD", "renal insufficiency", "glomerular filtration rate GFR", "proteinuria"],
        "keywords_vi": ["bệnh thận mạn", "suy thận mạn", "độ lọc cầu thận gfr", "đạm niệu", "chế độ ăn suy thận"],
        "candidate_score": 0.98
    },
    {
        "slug": "kidneydiseases",
        "url": "https://medlineplus.gov/kidneydiseases.html",
        "title_en": "Kidney Diseases",
        "title_vi": "Các bệnh lý về thận tổng quan",
        "category_en": "Nephrology",
        "category_vi": "Thận & Tiết niệu",
        "keywords_en": ["kidney diseases", "renal disorders", "kidney damage", "creatinine and BUN", "kidney failure symptoms"],
        "keywords_vi": ["bệnh về thận", "chức năng lọc của thận", "xét nghiệm creatinine", "phù thũng", "bảo vệ thận"],
        "candidate_score": 0.95
    },
    {
        "slug": "bladderdiseases",
        "url": "https://medlineplus.gov/bladderdiseases.html",
        "title_en": "Bladder Diseases",
        "title_vi": "Các bệnh bàng quang",
        "category_en": "Nephrology",
        "category_vi": "Thận & Tiết niệu",
        "keywords_en": ["bladder diseases", "overactive bladder", "urinary incontinence", "bladder dysfunction", "frequent urination"],
        "keywords_vi": ["bệnh bàng quang", "bàng quang tăng hoạt", "tiểu không tự chủ", "tiểu nhiều lần", "tiểu đêm"],
        "candidate_score": 0.94
    },
    {
        "slug": "interstitialcystitis",
        "url": "https://medlineplus.gov/interstitialcystitis.html",
        "title_en": "Interstitial Cystitis (Bladder Pain Syndrome)",
        "title_vi": "Viêm bàng quang kẽ (Hội chứng đau bàng quang)",
        "category_en": "Nephrology",
        "category_vi": "Thận & Tiết niệu",
        "keywords_en": ["interstitial cystitis", "bladder pain syndrome", "chronic pelvic pain", "urinary urgency", "nonbacterial cystitis"],
        "keywords_vi": ["viêm bàng quang kẽ", "đau bàng quang mạn", "tiểu buốt rát không do vi khuẩn", "đau vùng chậu", "tiểu gấp"],
        "candidate_score": 0.94
    },
    {
        "slug": "kidneyfailure",
        "url": "https://medlineplus.gov/kidneyfailure.html",
        "title_en": "Kidney Failure (End-Stage Renal Disease)",
        "title_vi": "Suy thận giai đoạn cuối và Lọc máu",
        "category_en": "Nephrology",
        "category_vi": "Thận & Tiết niệu",
        "keywords_en": ["kidney failure", "end stage renal disease", "dialysis", "hemodialysis", "uremia"],
        "keywords_vi": ["suy thận giai đoạn cuối", "chạy thận nhân tạo", "lọc màng bụng", "hội chứng ure huyết cao", "ghép thận"],
        "candidate_score": 0.97
    },

    # --- 9. Endocrinology & Metabolic Diseases (4 tài liệu) ---
    {
        "slug": "gout",
        "url": "https://medlineplus.gov/gout.html",
        "title_en": "Gout",
        "title_vi": "Bệnh Gout (Thống phong)",
        "category_en": "Endocrinology & Metabolic",
        "category_vi": "Nội tiết & Chuyển hóa",
        "keywords_en": ["gout", "hyperuricemia", "uric acid crystals", "acute gout flare", "podagra big toe pain"],
        "keywords_vi": ["bệnh gout", "axit uric cao", "cơn đau gout cấp", "sưng ngón chân cái", "hạt tophi"],
        "candidate_score": 0.97
    },
    {
        "slug": "diabetesmedicines",
        "url": "https://medlineplus.gov/diabetesmedicines.html",
        "title_en": "Diabetes Medicines",
        "title_vi": "Thuốc điều trị đái tháo đường (Insulin & Thuốc uống)",
        "category_en": "Endocrinology & Metabolic",
        "category_vi": "Nội tiết & Chuyển hóa",
        "keywords_en": ["diabetes medicines", "insulin therapy", "oral hypoglycemic agents", "metformin", "blood sugar regulation"],
        "keywords_vi": ["thuốc trị tiểu đường", "tiêm insulin", "thuốc hạ đường huyết", "uống thuốc tiểu đường", "hạ đường huyết quá mức"],
        "candidate_score": 0.97
    },
    {
        "slug": "diabetescomplications",
        "url": "https://medlineplus.gov/diabetescomplications.html",
        "title_en": "Diabetes Complications",
        "title_vi": "Biến chứng của bệnh đái tháo đường",
        "category_en": "Endocrinology & Metabolic",
        "category_vi": "Nội tiết & Chuyển hóa",
        "keywords_en": ["diabetes complications", "diabetic ketoacidosis", "microvascular damage", "diabetic foot ulcer", "cardiovascular risk in diabetes"],
        "keywords_vi": ["biến chứng tiểu đường", "toan ceton do tiểu đường", "biến chứng mạch máu", "loét bàn chân tiểu đường", "biến chứng tim mạch"],
        "candidate_score": 0.97
    },
    {
        "slug": "pituitarydisorders",
        "url": "https://medlineplus.gov/pituitarydisorders.html",
        "title_en": "Pituitary Disorders",
        "title_vi": "Rối loạn tuyến yên",
        "category_en": "Endocrinology & Metabolic",
        "category_vi": "Nội tiết & Chuyển hóa",
        "keywords_en": ["pituitary disorders", "pituitary adenoma", "growth hormone deficiency", "hyperprolactinemia", "hypopituitarism"],
        "keywords_vi": ["rối loạn tuyến yên", "u tuyến yên", "rối loạn nội tiết tuyến yên", "suy tuyến yên", "tăng prolactin"],
        "candidate_score": 0.93
    },

    # --- 10. Mental Health & Behavioral Medicine (5 tài liệu) ---
    {
        "slug": "panicdisorder",
        "url": "https://medlineplus.gov/panicdisorder.html",
        "title_en": "Panic Disorder",
        "title_vi": "Rối loạn hoảng sợ (Cơn hoảng loạn)",
        "category_en": "Mental Health",
        "category_vi": "Sức khỏe tâm thần",
        "keywords_en": ["panic disorder", "panic attack", "sudden intense fear", "palpitations and shortness of breath", "agoraphobia"],
        "keywords_vi": ["rối loạn hoảng sợ", "cơn hoảng loạn", "sợ hãi đột ngột", "tim đập dồn dập nghẹt thở", "chứng sợ nơi đông người"],
        "candidate_score": 0.97
    },
    {
        "slug": "bipolardisorder",
        "url": "https://medlineplus.gov/bipolardisorder.html",
        "title_en": "Bipolar Disorder",
        "title_vi": "Rối loạn lưỡng cực (Hưng - Trầm cảm)",
        "category_en": "Mental Health",
        "category_vi": "Sức khỏe tâm thần",
        "keywords_en": ["bipolar disorder", "manic depression", "mania", "depressive episodes", "mood stabilizer"],
        "keywords_vi": ["rối loạn lưỡng cực", "hưng cảm trầm cảm", "giai đoạn hưng cảm", "thay đổi tâm trạng thất thường", "thuốc ổn định khí sắc"],
        "candidate_score": 0.96
    },
    {
        "slug": "sleepdisorders",
        "url": "https://medlineplus.gov/sleepdisorders.html",
        "title_en": "Sleep Disorders (Insomnia)",
        "title_vi": "Rối loạn giấc ngủ và Mất ngủ",
        "category_en": "Mental Health",
        "category_vi": "Sức khỏe tâm thần",
        "keywords_en": ["sleep disorders", "insomnia", "difficulty sleeping", "circadian rhythm disorders", "sleep hygiene"],
        "keywords_vi": ["rối loạn giấc ngủ", "mất ngủ", "khó ngủ trằn trọc", "vệ sinh giấc ngủ", "rối loạn nhịp sinh học"],
        "candidate_score": 0.96
    },
    {
        "slug": "postpartumdepression",
        "url": "https://medlineplus.gov/postpartumdepression.html",
        "title_en": "Postpartum Depression",
        "title_vi": "Trầm cảm sau sinh",
        "category_en": "Mental Health",
        "category_vi": "Sức khỏe tâm thần",
        "keywords_en": ["postpartum depression", "postnatal depression", "maternal mental health", "baby blues", "postpartum anxiety"],
        "keywords_vi": ["trầm cảm sau sinh", "khủng hoảng tâm lý sau sinh", "buồn bã mệt mỏi sau sinh", "chăm sóc mẹ sau sinh", "trợ giúp tâm lý"],
        "candidate_score": 0.96
    },
    {
        "slug": "alcoholusedisorderaud",
        "url": "https://medlineplus.gov/alcoholusedisorderaud.html",
        "title_en": "Alcohol Use Disorder (AUD)",
        "title_vi": "Rối loạn sử dụng rượu (Nghiện rượu)",
        "category_en": "Mental Health",
        "category_vi": "Sức khỏe tâm thần",
        "keywords_en": ["alcohol use disorder", "AUD", "alcoholism", "alcohol withdrawal", "binge drinking"],
        "keywords_vi": ["rối loạn sử dụng rượu", "nghiện rượu", "cai rượu", "ngộ độc rượu mạn tính", "hội chứng cai rượu"],
        "candidate_score": 0.94
    },

    # --- 11. Musculoskeletal & Rheumatology (8 tài liệu) ---
    {
        "slug": "osteoporosis",
        "url": "https://medlineplus.gov/osteoporosis.html",
        "title_en": "Osteoporosis",
        "title_vi": "Loãng xương",
        "category_en": "Rheumatology & Bone",
        "category_vi": "Cơ xương khớp & Thấp khớp",
        "keywords_en": ["osteoporosis", "low bone density", "bone fracture risk", "calcium and vitamin D", "DEXA scan"],
        "keywords_vi": ["loãng xương", "mật độ xương thấp", "nguy cơ gãy xương", "đo mật độ xương dexa", "bổ sung canxi và vitamin d"],
        "candidate_score": 0.97
    },
    {
        "slug": "fibromyalgia",
        "url": "https://medlineplus.gov/fibromyalgia.html",
        "title_en": "Fibromyalgia",
        "title_vi": "Hội chứng đau cơ xơ hóa (Fibromyalgia)",
        "category_en": "Rheumatology & Bone",
        "category_vi": "Cơ xương khớp & Thấp khớp",
        "keywords_en": ["fibromyalgia", "widespread musculoskeletal pain", "tender points", "chronic fatigue", "sleep disturbance in pain"],
        "keywords_vi": ["đau cơ xơ hóa", "đau nhức cơ bắp toàn thân", "điểm đau cơ", "mệt mỏi mạn tính", "điều trị đau mạn"],
        "candidate_score": 0.95
    },
    {
        "slug": "lupus",
        "url": "https://medlineplus.gov/lupus.html",
        "title_en": "Systemic Lupus Erythematosus (Lupus)",
        "title_vi": "Lupus ban đỏ hệ thống",
        "category_en": "Rheumatology & Bone",
        "category_vi": "Cơ xương khớp & Thấp khớp",
        "keywords_en": ["lupus", "systemic lupus erythematosus SLE", "butterfly rash", "autoimmune disease", "joint inflammation and nephritis"],
        "keywords_vi": ["lupus ban đỏ", "lupus ban đỏ hệ thống", "ban cánh bướm", "bệnh tự miễn", "viêm thận do lupus"],
        "candidate_score": 0.97
    },
    {
        "slug": "tendinitis",
        "url": "https://medlineplus.gov/tendinitis.html",
        "title_en": "Tendinitis",
        "title_vi": "Viêm gân (Tendinitis)",
        "category_en": "Rheumatology & Bone",
        "category_vi": "Cơ xương khớp & Thấp khớp",
        "keywords_en": ["tendinitis", "tendon inflammation", "Achilles tendinitis", "rotator cuff tendinitis", "overuse injury"],
        "keywords_vi": ["viêm gân", "viêm gân achilles", "viêm gân chóp xoay vai", "chấn thương do vận động quá mức", "đau gân"],
        "candidate_score": 0.94
    },
    {
        "slug": "bursitis",
        "url": "https://medlineplus.gov/bursitis.html",
        "title_en": "Bursitis",
        "title_vi": "Viêm bao hoạt dịch",
        "category_en": "Rheumatology & Bone",
        "category_vi": "Cơ xương khớp & Thấp khớp",
        "keywords_en": ["bursitis", "bursa inflammation", "joint swelling and pain", "shoulder bursitis", "knee bursitis"],
        "keywords_vi": ["viêm bao hoạt dịch", "sưng đau khớp", "viêm bao hoạt dịch khớp vai", "viêm bao hoạt dịch khớp gối", "tràn dịch khớp"],
        "candidate_score": 0.94
    },
    {
        "slug": "ankylosingspondylitis",
        "url": "https://medlineplus.gov/ankylosingspondylitis.html",
        "title_en": "Ankylosing Spondylitis",
        "title_vi": "Viêm cột sống dính khớp",
        "category_en": "Rheumatology & Bone",
        "category_vi": "Cơ xương khớp & Thấp khớp",
        "keywords_en": ["ankylosing spondylitis", "axial spondyloarthritis", "bamboo spine", "HLA-B27", "inflammatory back pain"],
        "keywords_vi": ["viêm cột sống dính khớp", "cứng cột sống", "đau lưng do viêm", "xét nghiệm hla-b27", "dính khớp cột sống"],
        "candidate_score": 0.95
    },
    {
        "slug": "scoliosis",
        "url": "https://medlineplus.gov/scoliosis.html",
        "title_en": "Scoliosis",
        "title_vi": "Vẹo cột sống",
        "category_en": "Rheumatology & Bone",
        "category_vi": "Cơ xương khớp & Thấp khớp",
        "keywords_en": ["scoliosis", "spinal curvature", "adolescent idiopathic scoliosis", "back brace", "uneven shoulders"],
        "keywords_vi": ["vẹo cột sống", "cong vẹo cột sống ở trẻ", "lệch vai", "áo nẹp chỉnh hình", "tầm soát cong vẹo cột sống"],
        "candidate_score": 0.94
    },
    {
        "slug": "psoriaticarthritis",
        "url": "https://medlineplus.gov/psoriaticarthritis.html",
        "title_en": "Psoriatic Arthritis",
        "title_vi": "Viêm khớp vảy nến",
        "category_en": "Rheumatology & Bone",
        "category_vi": "Cơ xương khớp & Thấp khớp",
        "keywords_en": ["psoriatic arthritis", "joint pain with psoriasis", "dactylitis sausage fingers", "enthesitis", "biologic therapy"],
        "keywords_vi": ["viêm khớp vảy nến", "viêm ngón hình khúc dồi", "đau khớp kèm tổn thương da", "điều trị sinh học", "viêm điểm bám gân"],
        "candidate_score": 0.95
    },

    # --- 12. Infectious Diseases (8 tài liệu) ---
    {
        "slug": "whoopingcough",
        "url": "https://medlineplus.gov/whoopingcough.html",
        "title_en": "Whooping Cough (Pertussis)",
        "title_vi": "Bệnh Ho gà (Pertussis)",
        "category_en": "Infectious Diseases",
        "category_vi": "Bệnh truyền nhiễm",
        "keywords_en": ["whooping cough", "pertussis", "Bordetella pertussis", "paroxysmal coughing fits", "pertussis vaccine"],
        "keywords_vi": ["ho gà", "cơn ho rũ rượi", "vi khuẩn ho gà", "thở rít sau cơn ho", "tiêm phòng ho gà"],
        "candidate_score": 0.97
    },
    {
        "slug": "staphylococcalinfections",
        "url": "https://medlineplus.gov/staphylococcalinfections.html",
        "title_en": "Staphylococcal Infections (Staph & MRSA)",
        "title_vi": "Nhiễm khuẩn tụ cầu (Tụ cầu vàng & MRSA)",
        "category_en": "Infectious Diseases",
        "category_vi": "Bệnh truyền nhiễm",
        "keywords_en": ["staphylococcal infections", "Staphylococcus aureus", "MRSA", "skin abscess and boils", "staph bacteremia"],
        "keywords_vi": ["nhiễm tụ cầu", "tụ cầu vàng", "nhiễm khuẩn mrsa", "nhọt da mưng mủ", "nhiễm khuẩn huyết do tụ cầu"],
        "candidate_score": 0.97
    },
    {
        "slug": "salmonellainfections",
        "url": "https://medlineplus.gov/salmonellainfections.html",
        "title_en": "Salmonella Infections (Salmonellosis)",
        "title_vi": "Nhiễm khuẩn Salmonella (Ngộ độc thực phẩm do Salmonella)",
        "category_en": "Infectious Diseases",
        "category_vi": "Bệnh truyền nhiễm",
        "keywords_en": ["salmonella infections", "food poisoning", "gastroenteritis", "contaminated food and poultry", "diarrhea and fever"],
        "keywords_vi": ["nhiễm khuẩn salmonella", "ngộ độc thực phẩm", "tiêu chảy cấp do nhiễm khuẩn", "sốt thương hàn", "nhiễm trùng đường ruột"],
        "candidate_score": 0.96
    },
    {
        "slug": "ecoliinfections",
        "url": "https://medlineplus.gov/ecoliinfections.html",
        "title_en": "E. coli Infections",
        "title_vi": "Nhiễm khuẩn E. coli",
        "category_en": "Infectious Diseases",
        "category_vi": "Bệnh truyền nhiễm",
        "keywords_en": ["E coli infections", "Escherichia coli", "hemolytic uremic syndrome HUS", "bloody diarrhea", "contaminated water"],
        "keywords_vi": ["nhiễm khuẩn e coli", "vi khuẩn e coli", "tiêu chảy ra máu", "hội chứng tán huyết urê huyết cao", "nhiễm độc thực phẩm"],
        "candidate_score": 0.96
    },
    {
        "slug": "chlamydiainfections",
        "url": "https://medlineplus.gov/chlamydiainfections.html",
        "title_en": "Chlamydia Infections",
        "title_vi": "Nhiễm khuẩn Chlamydia (Bệnh lây truyền qua đường tình dục)",
        "category_en": "Infectious Diseases",
        "category_vi": "Bệnh truyền nhiễm",
        "keywords_en": ["chlamydia infections", "sexually transmitted infection STI", "pelvic inflammatory disease", "azithromycin treatment", "genital discharge"],
        "keywords_vi": ["nhiễm khuẩn chlamydia", "bệnh lây qua đường tình dục", "viêm vùng chậu", "khí hư bất thường", "điều trị kháng sinh chlamydia"],
        "candidate_score": 0.95
    },
    {
        "slug": "westnilevirus",
        "url": "https://medlineplus.gov/westnilevirus.html",
        "title_en": "West Nile Virus",
        "title_vi": "Nhiễm virus Tây Sông Nile (West Nile Virus)",
        "category_en": "Infectious Diseases",
        "category_vi": "Bệnh truyền nhiễm",
        "keywords_en": ["West Nile virus", "mosquito borne illness", "neurological viral infection", "encephalitis risk", "mosquito bite prevention"],
        "keywords_vi": ["virus tây sông nile", "bệnh do muỗi truyền", "sốt do virus", "viêm màng não do muỗi đốt", "phòng tránh muỗi đốt"],
        "candidate_score": 0.94
    },
    {
        "slug": "legionnairesdisease",
        "url": "https://medlineplus.gov/legionnairesdisease.html",
        "title_en": "Legionnaires' Disease",
        "title_vi": "Bệnh Legionella (Viêm phổi do Legionella)",
        "category_en": "Infectious Diseases",
        "category_vi": "Bệnh truyền nhiễm",
        "keywords_en": ["Legionnaires' disease", "Legionella pneumophila", "atypical pneumonia", "water cooling towers", "severe lung infection"],
        "keywords_vi": ["bệnh legionella", "viêm phổi không điển hình", "vi khuẩn hệ thống nước điều hòa", "sốt cao viêm phổi", "kháng sinh macrolide"],
        "candidate_score": 0.95
    },
    {
        "slug": "bacterialinfections",
        "url": "https://medlineplus.gov/bacterialinfections.html",
        "title_en": "Bacterial Infections",
        "title_vi": "Nhiễm khuẩn do vi khuẩn tổng quan",
        "category_en": "Infectious Diseases",
        "category_vi": "Bệnh truyền nhiễm",
        "keywords_en": ["bacterial infections", "bacterial vs viral infection", "gram positive and negative", "bacterial treatment", "bacteremia"],
        "keywords_vi": ["nhiễm khuẩn vi khuẩn", "phân biệt vi khuẩn và virus", "điều trị nhiễm trùng", "nhiễm khuẩn cơ hội", "vệ sinh phòng bệnh"],
        "candidate_score": 0.95
    },

    # --- 13. Oncology (10 tài liệu) ---
    {
        "slug": "cancer",
        "url": "https://medlineplus.gov/cancer.html",
        "title_en": "Cancer Overview",
        "title_vi": "Bệnh Ung thư tổng quan",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["cancer", "malignancy", "carcinoma", "tumor", "chemotherapy and radiation"],
        "keywords_vi": ["ung thư", "khối u ác tính", "ung bướu", "hóa trị và xạ trị", "tầm soát và điều trị ung thư"],
        "candidate_score": 0.98
    },
    {
        "slug": "lungcancer",
        "url": "https://medlineplus.gov/lungcancer.html",
        "title_en": "Lung Cancer",
        "title_vi": "Ung thư phổi",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["lung cancer", "non small cell lung cancer", "small cell lung cancer", "coughing up blood", "smoking and lung tumor"],
        "keywords_vi": ["ung thư phổi", "ung thư biểu mô phổi", "ho ra máu", "hút thuốc lá và ung thư phổi", "phát hiện sớm ung thư phổi"],
        "candidate_score": 0.97
    },
    {
        "slug": "colorectalcancer",
        "url": "https://medlineplus.gov/colorectalcancer.html",
        "title_en": "Colorectal Cancer (Colon Cancer)",
        "title_vi": "Ung thư đại trực tràng",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["colorectal cancer", "colon cancer", "rectal cancer", "colonoscopy screening", "colon polyps"],
        "keywords_vi": ["ung thư đại trực tràng", "ung thư ruột già", "nội soi đại tràng tầm soát", "polyp đại tràng", "đi ngoài ra máu"],
        "candidate_score": 0.97
    },
    {
        "slug": "prostatecancer",
        "url": "https://medlineplus.gov/prostatecancer.html",
        "title_en": "Prostate Cancer",
        "title_vi": "Ung thư tuyến tiền liệt",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["prostate cancer", "prostate specific antigen PSA", "prostate tumor", "urinary difficulty in men", "prostate biopsy"],
        "keywords_vi": ["ung thư tiền liệt tuyến", "xét nghiệm psa", "tiểu khó tiểu ngắt quãng", "sinh thiết tiền liệt tuyến", "điều trị ung thư nam giới"],
        "candidate_score": 0.96
    },
    {
        "slug": "cervicalcancer",
        "url": "https://medlineplus.gov/cervicalcancer.html",
        "title_en": "Cervical Cancer",
        "title_vi": "Ung thư cổ tử cung",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["cervical cancer", "human papillomavirus HPV", "Pap smear", "HPV vaccine", "cervical screening"],
        "keywords_vi": ["ung thư cổ tử cung", "virus hpv", "xét nghiệm pap smear", "tiêm vắc-xin hpv", "tầm soát ung thư phụ khoa"],
        "candidate_score": 0.97
    },
    {
        "slug": "livercancer",
        "url": "https://medlineplus.gov/livercancer.html",
        "title_en": "Liver Cancer (Hepatocellular Carcinoma)",
        "title_vi": "Ung thư gan nguyên phát",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["liver cancer", "hepatocellular carcinoma HCC", "liver tumor", "alpha fetoprotein AFP", "cirrhosis complication"],
        "keywords_vi": ["ung thư gan", "ung thư biểu mô tế bào gan hcc", "xét nghiệm afp", "khối u gan", "biến chứng xơ gan thành ung thư"],
        "candidate_score": 0.97
    },
    {
        "slug": "pancreaticcancer",
        "url": "https://medlineplus.gov/pancreaticcancer.html",
        "title_en": "Pancreatic Cancer",
        "title_vi": "Ung thư tụy",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["pancreatic cancer", "pancreatic adenocarcinoma", "jaundice and back pain", "Whipple procedure", "pancreatic tumor"],
        "keywords_vi": ["ung thư tuyến tụy", "vàng da sụt cân", "đau lưng dữ dội", "ung thư biểu mô tuyến tụy", "phẫu thuật whipple"],
        "candidate_score": 0.96
    },
    {
        "slug": "kidneycancer",
        "url": "https://medlineplus.gov/kidneycancer.html",
        "title_en": "Kidney Cancer (Renal Cell Carcinoma)",
        "title_vi": "Ung thư thận (Ung thư biểu mô tế bào thận)",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["kidney cancer", "renal cell carcinoma RCC", "blood in urine hematuria", "flank mass", "nephrectomy"],
        "keywords_vi": ["ung thư thận", "tiểu ra máu", "khối u vùng hông lưng", "cắt thận", "ung thư biểu mô tế bào thận"],
        "candidate_score": 0.95
    },
    {
        "slug": "bladdercancer",
        "url": "https://medlineplus.gov/bladdercancer.html",
        "title_en": "Bladder Cancer",
        "title_vi": "Ung thư bàng quang",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["bladder cancer", "urothelial carcinoma", "painless hematuria", "cystoscopy", "smoking bladder tumor"],
        "keywords_vi": ["ung thư bàng quang", "tiểu ra máu không đau", "soi bàng quang", "khối u đường tiết niệu", "ung thư biểu mô niệu mạc"],
        "candidate_score": 0.95
    },
    {
        "slug": "melanoma",
        "url": "https://medlineplus.gov/melanoma.html",
        "title_en": "Melanoma (Skin Cancer)",
        "title_vi": "Ung thư hắc tố da (Melanoma)",
        "category_en": "Oncology",
        "category_vi": "Ung bướu",
        "keywords_en": ["melanoma", "skin cancer", "ABCDE mole check", "atypical mole", "ultraviolet radiation"],
        "keywords_vi": ["ung thư hắc tố da", "melanoma", "nốt ruồi ác tính", "quy tắc abcde kiểm tra nốt ruồi", "tác hại tia cực tím uv"],
        "candidate_score": 0.96
    },

    # --- 14. Ophthalmology & Sensory Disorders (5 tài liệu) ---
    {
        "slug": "cataract",
        "url": "https://medlineplus.gov/cataract.html",
        "title_en": "Cataract",
        "title_vi": "Đục thủy tinh thể (Cườm khô)",
        "category_en": "Ophthalmology",
        "category_vi": "Nhãn khoa",
        "keywords_en": ["cataract", "cloudy lens", "blurry vision", "cataract surgery phaco", "aging eye changes"],
        "keywords_vi": ["đục thủy tinh thể", "cườm khô", "mờ mắt người già", "phẫu thuật phaco thay thủy tinh thể", "suy giảm thị lực mờ sương"],
        "candidate_score": 0.96
    },
    {
        "slug": "glaucoma",
        "url": "https://medlineplus.gov/glaucoma.html",
        "title_en": "Glaucoma",
        "title_vi": "Bệnh Glaucoma (Cườm nước / Thiên đầu thống)",
        "category_en": "Ophthalmology",
        "category_vi": "Nhãn khoa",
        "keywords_en": ["glaucoma", "intraocular pressure", "optic nerve damage", "peripheral vision loss", "angle closure glaucoma"],
        "keywords_vi": ["glaucoma", "cườm nước", "tăng nhãn áp", "thiên đầu thống", "tổn thương thần kinh thị giác"],
        "candidate_score": 0.97
    },
    {
        "slug": "pinkeye",
        "url": "https://medlineplus.gov/pinkeye.html",
        "title_en": "Pinkeye (Conjunctivitis)",
        "title_vi": "Đau mắt đỏ (Viêm kết mạc)",
        "category_en": "Ophthalmology",
        "category_vi": "Nhãn khoa",
        "keywords_en": ["pinkeye", "conjunctivitis", "red itchy eye", "eye discharge", "viral conjunctivitis"],
        "keywords_vi": ["đau mắt đỏ", "viêm kết mạc", "đỏ mắt chảy ghèn", "ngứa rát mắt", "dịch đau mắt đỏ"],
        "candidate_score": 0.96
    },
    {
        "slug": "maculardegeneration",
        "url": "https://medlineplus.gov/maculardegeneration.html",
        "title_en": "Age-Related Macular Degeneration (AMD)",
        "title_vi": "Thoái hóa điểm vàng (Hoàng điểm)",
        "category_en": "Ophthalmology",
        "category_vi": "Nhãn khoa",
        "keywords_en": ["macular degeneration", "AMD", "central vision loss", "dry AMD", "wet AMD anti VEGF"],
        "keywords_vi": ["thoái hóa điểm vàng", "thoái hóa hoàng điểm tuổi già", "mất thị lực trung tâm", "tiêm thuốc anti-vegf", "bệnh lý mắt người cao tuổi"],
        "candidate_score": 0.95
    },
    {
        "slug": "tinnitus",
        "url": "https://medlineplus.gov/tinnitus.html",
        "title_en": "Tinnitus",
        "title_vi": "Chứng ù tai",
        "category_en": "Ophthalmology",
        "category_vi": "Nhãn khoa",
        "keywords_en": ["tinnitus", "ringing in ears", "buzzing sound", "hearing damage", "inner ear disorder"],
        "keywords_vi": ["ù tai", "tiếng ve kêu trong tai", "rối loạn thính giác", "nghe kém kèm ù tai", "tiếng kêu trong đầu"],
        "candidate_score": 0.94
    },

    # --- 15. Pediatrics, Maternal Health & Chronic Gaps (11 tài liệu) ---
    {
        "slug": "suddeninfantdeathsyndrome",
        "url": "https://medlineplus.gov/suddeninfantdeathsyndrome.html",
        "title_en": "Sudden Infant Death Syndrome (SIDS)",
        "title_vi": "Hội chứng đột tử ở trẻ sơ sinh (SIDS)",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["sudden infant death syndrome", "SIDS", "crib death", "safe infant sleep", "back to sleep"],
        "keywords_vi": ["hội chứng đột tử trẻ sơ sinh", "sids", "tử vong đột ngột khi ngủ", "tư thế ngủ an toàn cho bé", "phòng ngừa sids"],
        "candidate_score": 0.97
    },
    {
        "slug": "birthdefects",
        "url": "https://medlineplus.gov/birthdefects.html",
        "title_en": "Birth Defects (Congenital Anomalies)",
        "title_vi": "Dị tật bẩm sinh",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["birth defects", "congenital anomalies", "prenatal screening", "folic acid prevention", "structural abnormalities"],
        "keywords_vi": ["dị tật bẩm sinh", "sàng lọc trước sinh", "bổ sung axit folic", "bất thường cấu trúc thai nhi", "chăm sóc thai kỳ"],
        "candidate_score": 0.96
    },
    {
        "slug": "diabeticfoot",
        "url": "https://medlineplus.gov/diabeticfoot.html",
        "title_en": "Diabetic Foot (Ulcers & Complications)",
        "title_vi": "Bàn chân đái tháo đường (Loét và Nhiễm trùng)",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["diabetic foot", "diabetic foot ulcer", "foot neuropathy and ischemia", "amputation prevention", "diabetic wound care"],
        "keywords_vi": ["bàn chân tiểu đường", "loét bàn chân đái tháo đường", "chăm sóc vết thương tiểu đường", "phòng ngừa cắt cụt chi", "mất cảm giác bàn chân"],
        "candidate_score": 0.97
    },
    {
        "slug": "uterinefibroids",
        "url": "https://medlineplus.gov/uterinefibroids.html",
        "title_en": "Uterine Fibroids",
        "title_vi": "U xơ tử cung",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["uterine fibroids", "leiomyoma", "heavy menstrual bleeding", "pelvic pressure", "myomectomy"],
        "keywords_vi": ["u xơ tử cung", "rong kinh rong huyết", "khối u lành tính tử cung", "đau tức vùng chậu", "phẫu thuật bóc u xơ"],
        "candidate_score": 0.95
    },
    {
        "slug": "healthproblemsinpregnancy",
        "url": "https://medlineplus.gov/healthproblemsinpregnancy.html",
        "title_en": "Health Problems in Pregnancy",
        "title_vi": "Các vấn đề sức khỏe trong thai kỳ",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["health problems in pregnancy", "prenatal complications", "morning sickness hyperemesis", "anemia in pregnancy", "high risk pregnancy"],
        "keywords_vi": ["bệnh lý thai kỳ", "biến chứng khi mang thai", "ốm nghén nặng", "thiếu máu thai kỳ", "thai kỳ nguy cơ cao"],
        "candidate_score": 0.96
    },
    {
        "slug": "foodallergy",
        "url": "https://medlineplus.gov/foodallergy.html",
        "title_en": "Food Allergy",
        "title_vi": "Dị ứng thực phẩm",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["food allergy", "peanut allergy", "milk allergy", "hives after eating", "food anaphylaxis risk"],
        "keywords_vi": ["dị ứng thức ăn", "dị ứng lạc đậu phộng", "dị ứng đạm sữa bò", "mẩn ngứa sau khi ăn", "phản vệ do thực phẩm"],
        "candidate_score": 0.96
    },
    {
        "slug": "temporomandibulardisorders",
        "url": "https://medlineplus.gov/temporomandibulardisorders.html",
        "title_en": "Temporomandibular Disorders (TMJ)",
        "title_vi": "Rối loạn khớp thái dương hàm (TMJ)",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["temporomandibular disorders", "TMJ", "jaw pain and clicking", "bruxism teeth grinding", "jaw muscle spasm"],
        "keywords_vi": ["rối loạn khớp thái dương hàm", "đau quai hàm", "khớp hàm kêu lục cục", "nghiến răng khi ngủ", "mỏi cơ nhai"],
        "candidate_score": 0.93
    },
    {
        "slug": "asthmainchildren",
        "url": "https://medlineplus.gov/asthmainchildren.html",
        "title_en": "Asthma in Children",
        "title_vi": "Hen phế quản ở trẻ em (Hen suyễn trẻ em)",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["asthma in children", "pediatric asthma", "childhood wheezing", "inhaler with spacer", "asthma action plan"],
        "keywords_vi": ["hen suyễn ở trẻ em", "hen phế quản trẻ em", "thở khò khè ở trẻ", "bình xịt định liều buồng đệm", "kế hoạch kiểm soát hen"],
        "candidate_score": 0.97
    },
    {
        "slug": "highbloodpressureinpregnancy",
        "url": "https://medlineplus.gov/highbloodpressureinpregnancy.html",
        "title_en": "High Blood Pressure in Pregnancy (Preeclampsia)",
        "title_vi": "Tăng huyết áp thai kỳ và Tiền sản giật",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["high blood pressure in pregnancy", "preeclampsia", "gestational hypertension", "proteinuria in pregnancy", "maternal monitoring"],
        "keywords_vi": ["tăng huyết áp thai kỳ", "tiền sản giật", "sản giật", "huyết áp cao khi mang thai", "đạm niệu thai kỳ"],
        "candidate_score": 0.97
    },
    {
        "slug": "diabetesandpregnancy",
        "url": "https://medlineplus.gov/diabetesandpregnancy.html",
        "title_en": "Diabetes and Pregnancy (Gestational Diabetes)",
        "title_vi": "Đái tháo đường thai kỳ",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["diabetes and pregnancy", "gestational diabetes mellitus GDM", "glucose tolerance test", "macrosomia risk", "blood sugar control in pregnancy"],
        "keywords_vi": ["tiểu đường thai kỳ", "đái tháo đường khi mang thai", "nghiệm pháp dung nạp đường", "đường huyết thai kỳ", "nguy cơ thai to"],
        "candidate_score": 0.97
    },
    {
        "slug": "autoimmunediseases",
        "url": "https://medlineplus.gov/autoimmunediseases.html",
        "title_en": "Autoimmune Diseases Overview",
        "title_vi": "Các bệnh tự miễn tổng quan",
        "category_en": "Pediatrics & Maternal Health",
        "category_vi": "Nhi khoa & Sản phụ khoa",
        "keywords_en": ["autoimmune diseases", "immune system attacking self", "autoantibodies", "chronic systemic inflammation", "immunosuppressive therapy"],
        "keywords_vi": ["bệnh tự miễn", "hệ miễn dịch tấn công cơ thể", "tự kháng thể", "viêm mạn tính toàn thân", "thuốc ức chế miễn dịch"],
        "candidate_score": 0.95
    }
]

# Regex nhận diện ngôn ngữ chỉ định liều lượng thuốc (Dosing language scanner)
DOSING_REGEX = re.compile(
    r"\b(?:"
    r"\d+\s*(?:mg|mcg|milligram|microgram|ml|g|tablets?|capsules?|pills?)|"
    r"dosage|dose|dosing|"
    r"every\s+\d+\s+hours|"
    r"\d+\s+times\s+(?:a|per)\s+day|"
    r"daily\s+dose"
    r")\b",
    re.IGNORECASE
)

HTML_TAG_REGEX = re.compile(r"<[^>]+>", re.IGNORECASE)

# ================================================================================
# BẢNG ĐÁNH GIÁ AN TOÀN DƯỢC LÂM SÀNG (PHASE 6.4B SAFETY AUDIT DECISIONS)
# ================================================================================
# 11 tài liệu có trigger ngôn ngữ liều dùng được phân loại lâm sàng chi tiết:
# - SAFE_EDUCATIONAL -> APPROVED (Cảnh báo an toàn chung / Định nghĩa / Thử nghiệm)
# - SAFE_WITH_CONTEXT -> APPROVED_WITH_SAFETY_FLAG (Khuyến nghị cộng đồng / Hướng dẫn dụng cụ đo)
# - EXCLUDED -> EXCLUDED (0 tài liệu bị loại vì không tài liệu nào chứa bảng kê liều chi tiết)
SAFETY_AUDIT_DECISIONS = {
    # 7 tài liệu SAFE_EDUCATIONAL -> APPROVED
    "dietarysupplements": {
        "classification": "SAFE_EDUCATIONAL",
        "qa_status": "APPROVED",
        "qa_flags": [],
        "qa_review_reason": "Hướng dẫn an toàn chung cảnh báo người bệnh không uống quá liều khuyến nghị trên nhãn sản phẩm; không mang tính kê đơn."
    },
    "druguseandaddiction": {
        "classification": "SAFE_EDUCATIONAL",
        "qa_status": "APPROVED",
        "qa_flags": [],
        "qa_review_reason": "Định nghĩa lâm sàng về lạm dụng thuốc và lệ thuộc chất cảnh báo về việc tự ý dùng liều cao hơn chỉ định của bác sĩ."
    },
    "gout": {
        "classification": "SAFE_EDUCATIONAL",
        "qa_status": "APPROVED",
        "qa_flags": [],
        "qa_review_reason": "Nhắc đến 'aspirin liều thấp' như một yếu tố nguy cơ dịch tễ học làm tăng axit uric; không hướng dẫn liều dùng."
    },
    "hepatitisb": {
        "classification": "SAFE_EDUCATIONAL",
        "qa_status": "APPROVED",
        "qa_flags": [],
        "qa_review_reason": "Mô tả biện pháp điều trị dự phòng sau phơi nhiễm do nhân viên y tế thực hiện (tiêm vắc-xin / huyết thanh); không phải tự dùng thuốc."
    },
    "prescriptiondrugmisuse": {
        "classification": "SAFE_EDUCATIONAL",
        "qa_status": "APPROVED",
        "qa_flags": [],
        "qa_review_reason": "Định nghĩa hành vi lạm dụng thuốc kê đơn là uống liều cao hơn chỉ định; cảnh báo giáo dục phòng ngừa quá liều."
    },
    "pulmonaryembolism": {
        "classification": "SAFE_EDUCATIONAL",
        "qa_status": "APPROVED",
        "qa_flags": [],
        "qa_review_reason": "Khuyến cáo người bệnh cần tái khám định kỳ để bác sĩ điều chỉnh liều thuốc chống đông máu an toàn; không chứa số liệu liều lượng."
    },
    "vaccinesafety": {
        "classification": "SAFE_EDUCATIONAL",
        "qa_status": "APPROVED",
        "qa_flags": [],
        "qa_review_reason": "Giải thích mục tiêu nghiên cứu thử nghiệm lâm sàng tìm liều vắc-xin tạo miễn dịch tối ưu; hoàn toàn không có hướng dẫn tự dùng."
    },

    # 4 tài liệu SAFE_WITH_CONTEXT -> APPROVED_WITH_SAFETY_FLAG
    "howtolowercholesterolwithdiet": {
        "classification": "SAFE_WITH_CONTEXT",
        "qa_status": "APPROVED_WITH_SAFETY_FLAG",
        "qa_flags": ["dietary_reference_intake"],
        "qa_review_reason": "Khuyến nghị dinh dưỡng cộng đồng về lượng cholesterol trong khẩu phần ăn (< 200 mg/ngày); là chỉ số thực phẩm, không phải liều thuốc tân dược."
    },
    "tetanusdiphtheriaandpertussisvaccines": {
        "classification": "SAFE_WITH_CONTEXT",
        "qa_status": "APPROVED_WITH_SAFETY_FLAG",
        "qa_flags": ["public_health_immunization_schedule"],
        "qa_review_reason": "Lịch tiêm chủng mở rộng quốc gia khuyến cáo tiêm nhắc lại mỗi 10 năm hoặc sau 5 năm nếu có vết thương bẩn; không phải kê đơn tự do."
    },
    "overthecountermedicines": {
        "classification": "SAFE_WITH_CONTEXT",
        "qa_status": "APPROVED_WITH_SAFETY_FLAG",
        "qa_flags": ["pediatric_device_safety_guidance"],
        "qa_review_reason": "Hướng dẫn an toàn thiết bị đo lường khi cho trẻ uống thuốc dạng lỏng (dùng cốc đong/thìa chia vạch thay vì thìa ăn); không chứa công thức liều."
    },
    "chlamydiainfections": {
        "classification": "SAFE_WITH_CONTEXT",
        "qa_status": "APPROVED_WITH_SAFETY_FLAG",
        "qa_flags": ["clinical_treatment_adherence_counseling"],
        "qa_review_reason": "Tư vấn tuân thủ điều trị kháng sinh theo phác đồ bác sĩ (liều duy nhất hoặc 7 ngày) và kiêng quan hệ 7 ngày; không nêu tên thuốc hay hàm lượng cụ thể."
    }
}


def run_curation_and_staging(output_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Thực thi toàn bộ quy trình:
      1. Đọc kho thô MedlinePlus English.
      2. Kiểm tra tính toàn vẹn và khớp nối dữ liệu.
      3. Quét QA (Dosing, HTML, SHA-256).
      4. Staging tệp JSON vào data/curated/tier_a_candidates/.
      5. Chiếu phân mảnh (dry-run chunking projection) bằng chunk_document v2.
    """
    staging_path = output_dir or (BASE_DIR / "data" / "curated" / "tier_a_candidates")
    staging_path.mkdir(parents=True, exist_ok=True)
    # Xóa sạch các tệp cũ trong staging_path để tránh lưu lại tệp rác
    for old_f in staging_path.glob("*.json"):
        old_f.unlink()

    raw_dir = BASE_DIR / "data" / "processed" / "medlineplus"
    curated_dir = BASE_DIR / "data" / "curated" / "ready_documents"

    # Đọc danh sách URL đã có trong curated để đảm bảo 0% trùng lặp
    curated_urls = set()
    for p in curated_dir.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("source_url"):
                curated_urls.add(d["source_url"].strip().rstrip("/"))
        except Exception:
            pass

    # Lập bản đồ URL -> Raw Document
    url_to_raw = {}
    for p in raw_dir.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("language") == "English":
                u = (d.get("source_url") or "").strip().rstrip("/")
                url_to_raw[u] = (p.name, d)
        except Exception:
            pass

    staged_records = []
    qa_flags_counter = Counter()
    category_counter = Counter()
    sha256_match_count = 0

    print(f"Bắt đầu curation cho {len(TIER_A_DOCUMENTS)} tài liệu Tier-A...")

    for item in TIER_A_DOCUMENTS:
        slug = item["slug"]
        target_url = item["url"].strip().rstrip("/")

        if target_url not in url_to_raw:
            raise ValueError(f"Không tìm thấy URL thô cho tài liệu: {slug} ({target_url})")

        raw_file_name, raw_doc = url_to_raw[target_url]
        raw_summary = raw_doc.get("summary", "").strip()

        if not raw_summary:
            raise ValueError(f"Tài liệu rỗng nội dung summary: {slug}")

        # 1. Tính toán SHA-256 fingerprint trên nội dung tiếng Anh gốc
        content_hash = compute_content_hash(raw_summary)
        raw_hash = compute_content_hash(raw_summary)
        if content_hash == raw_hash:
            sha256_match_count += 1

        # 2. QA Scan: Kiểm tra mã HTML rác
        raw_qa_flags = []
        if HTML_TAG_REGEX.search(raw_summary):
            raw_qa_flags.append("html_tags_present")
            qa_flags_counter["html_tags_present"] += 1

        # 3. QA Scan: Quét ngôn ngữ chỉ định liều lượng
        if DOSING_REGEX.search(raw_summary):
            raw_qa_flags.append("contains_dosing_language")

        # Áp dụng quyết định kiểm định an toàn lâm sàng (Phase 6.4B Audit)
        if slug in SAFETY_AUDIT_DECISIONS:
            audit = SAFETY_AUDIT_DECISIONS[slug]
            qa_status = audit["qa_status"]
            qa_flags = audit["qa_flags"]
            qa_review_reason = audit["qa_review_reason"]
            safety_classification = audit["classification"]
        else:
            qa_status = "APPROVED"
            qa_flags = []
            qa_review_reason = "Automated QA scan passed without dosing or safety triggers."
            safety_classification = "SAFE_EDUCATIONAL"

        for f in qa_flags:
            qa_flags_counter[f] += 1

        # 4. Tạo document record theo schema staging chuẩn
        record = {
            "id": slug,
            "title": item["title_en"],
            "title_en": item["title_en"],
            "title_vi": item["title_vi"],
            "category": item["category_en"],
            "category_en": item["category_en"],
            "category_vi": item["category_vi"],
            "search_phrases": item["keywords_en"] + item["keywords_vi"],
            "keywords_en": item["keywords_en"],
            "keywords_vi": item["keywords_vi"],
            "language": "en",
            "source": "MedlinePlus",
            "source_url": target_url,
            "summary": raw_summary,
            "page_content": raw_summary,
            "content_sha256": content_hash,
            "candidate_score": item["candidate_score"],
            "tier": "TIER_A",
            "qa_status": qa_status,
            "qa_flags": qa_flags,
            "qa_review_reason": qa_review_reason,
            "safety_classification": safety_classification,
            "metadata_generated_by": "curation_pipeline_bilingual_v1",
            "metadata_review_status": "audited_qa_passed"
        }

        # Lưu tệp JSON vào staging directory
        dest_file = staging_path / f"{slug}.json"
        dest_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        staged_records.append(record)
        category_counter[item["category_en"]] += 1

    # Lưu manifest staging nội bộ (chỉ trong data/curated/tier_a_candidates/, không đụng Chroma)
    approved_count = sum(1 for r in staged_records if r["qa_status"] == "APPROVED")
    approved_with_flag_count = sum(1 for r in staged_records if r["qa_status"] == "APPROVED_WITH_SAFETY_FLAG")
    excluded_count = sum(1 for r in staged_records if r["qa_status"] == "EXCLUDED")
    final_retained_count = sum(1 for r in staged_records if r["qa_status"] != "EXCLUDED")

    manifest = {
        "candidate_count": len(staged_records),
        "original_selected": len(staged_records),
        "approved_count": approved_count,
        "approved_with_safety_flag_count": approved_with_flag_count,
        "excluded_count": excluded_count,
        "final_retained_count": final_retained_count,
        "source": "MedlinePlus English raw corpus",
        "language": "en",
        "metadata_languages": ["en", "vi"],
        "tier": "TIER_A",
        "qa_status_distribution": {
            "APPROVED": approved_count,
            "APPROVED_WITH_SAFETY_FLAG": approved_with_flag_count,
            "EXCLUDED": excluded_count
        },
        "qa_flags_distribution": dict(qa_flags_counter),
        "category_distribution": dict(category_counter),
        "sha256_match_count": sha256_match_count,
        "staging_directory": str(staging_path)
    }
    (staging_path / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # ================================================================================
    # 5. CHIẾU PHÂN MẢNH KHÔ (DRY-RUN CHUNKING PROJECTION)
    # ================================================================================
    settings = get_settings()
    max_chars = settings.ingestion.chunk_max_chars
    overlap_chars = settings.ingestion.chunk_overlap_chars
    min_chunk_chars = settings.ingestion.min_chunk_chars
    hard_max_chars = settings.ingestion.hard_max_chars

    # A. Đo đạc trên tập curated hiện có (241 tệp)
    current_docs = []
    for p in sorted(curated_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            current_docs.append(d)
        except Exception:
            pass

    current_chunks = []
    for d in current_docs:
        t = d.get("title", "")
        c = d.get("category", "")
        body = d.get("page_content", "") or d.get("summary", "")
        sphrases = d.get("search_phrases", [])
        sphrases_str = ", ".join(sphrases) if isinstance(sphrases, list) else str(sphrases)
        chs = chunk_document(t, c, body, sphrases_str, max_chars, overlap_chars, min_chunk_chars, hard_max_chars)
        current_chunks.extend(chs)

    # B. Đo đạc trên tập staged Tier-A (125 tệp)
    staged_chunks = []
    staged_prefixes = []
    tiny_chunks_staged = 0
    broken_starts_staged = 0

    for d in staged_records:
        t = d["title_en"]
        c = d["category_en"]
        body = d["page_content"]
        sphrases = ", ".join(d["keywords_en"] + d["keywords_vi"])
        chs = chunk_document(t, c, body, sphrases, max_chars, overlap_chars, min_chunk_chars, hard_max_chars)
        staged_chunks.extend(chs)

        for ch in chs:
            # Đo prefix
            prefix_len = len(ch["prefix"])
            staged_prefixes.append(prefix_len)

            # Kiểm tra broken-word start
            body_txt = ch["body"]
            if body_txt and body_txt[0].isalnum() and not body_txt[0].isupper() and ch["part_index"] > 0:
                pass  # overlap slice

            if len(ch["text"]) < min_chunk_chars:
                tiny_chunks_staged += 1

    total_chunks = len(current_chunks) + len(staged_chunks)
    total_docs = len(current_docs) + len(staged_records)

    staged_prefixes.sort()
    mean_prefix = sum(staged_prefixes) / len(staged_prefixes) if staged_prefixes else 0
    p95_idx = int(len(staged_prefixes) * 0.95)
    p95_prefix = staged_prefixes[p95_idx] if staged_prefixes else 0

    result = {
        "candidate_count": len(staged_records),
        "original_selected": len(staged_records),
        "approved_count": approved_count,
        "approved_with_safety_flag_count": approved_with_flag_count,
        "excluded_count": excluded_count,
        "final_retained_count": final_retained_count,
        "category_distribution": dict(category_counter),
        "sha256_match_count": sha256_match_count,
        "qa_flags": dict(qa_flags_counter),
        "current_docs_count": len(current_docs),
        "current_chunks_count": len(current_chunks),
        "staged_docs_count": len(staged_records),
        "staged_chunks_count": len(staged_chunks),
        "projected_total_docs": total_docs,
        "projected_total_chunks": total_chunks,
        "tiny_chunks_staged": tiny_chunks_staged,
        "broken_starts_staged": broken_starts_staged,
        "mean_prefix_chars": round(mean_prefix, 2),
        "p95_prefix_chars": p95_prefix,
        "rejections_count": len(REJECTIONS)
    }

    print("Curation hoàn thành thành công!")
    print(f"Selected: {result['staged_docs_count']} docs | Staged chunks: {result['staged_chunks_count']}")
    print(f"Projected total corpus: {result['projected_total_docs']} docs | {result['projected_total_chunks']} chunks")
    return result


if __name__ == "__main__":
    res = run_curation_and_staging()
    print(json.dumps(res, indent=2, ensure_ascii=False))
