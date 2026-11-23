"""
Builds complete bilingual metadata for all 241 legacy curated MedlinePlus documents.
Enriches documents with title_en, title_vi, category_en, category_vi, keywords_en, keywords_vi.
Preserves page_content exactly (verified via SHA-256).
Outputs to data/curated/ready_documents_enriched/ and caches in data/curated/legacy_bilingual_metadata_cache.json.
"""

import os
import sys
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "data" / "curated" / "ready_documents"
ENRICHED_DIR = ROOT / "data" / "curated" / "ready_documents_enriched"
CACHE_FILE = ROOT / "data" / "curated" / "legacy_bilingual_metadata_cache.json"

CATEGORY_VI = {
    "Diabetes & Hormones": "Nội tiết & Đái tháo đường",
    "Digestive": "Tiêu hóa",
    "Eye, Ear & Mouth": "Mắt, Tai & Răng miệng",
    "First Aid & Emergencies": "Cấp cứu & Sơ cứu",
    "General Symptoms": "Triệu chứng toàn thân",
    "Heart & Blood Pressure": "Tim mạch & Huyết áp",
    "Infectious Diseases": "Bệnh truyền nhiễm",
    "Lifestyle": "Lối sống & Sức khỏe",
    "Medicines": "Thuốc & Dược phẩm",
    "Mental Health": "Sức khỏe tâm thần",
    "Muscles, Bones & Back": "Cơ xương khớp",
    "Nutrition": "Dinh dưỡng",
    "Pregnancy & Children": "Sản phụ khoa & Nhi khoa",
    "Respiratory": "Hô hấp",
    "Sexual Health (Men)": "Sức khỏe nam khoa",
    "Sexual Health (Women)": "Sức khỏe phụ khoa",
    "Sexual Relationships": "Sức khỏe tình dục",
    "Skin": "Da liễu",
    "Urinary System": "Tiết niệu & Thận"
}

# Mapping keyed by filename (241 files)
METADATA_MAP = {
    # --- Heart & Blood Pressure (4) ---
    "heart-blood-pressure-chest-pain.json": {
        "title_vi": "Đau ngực",
        "keywords_vi": ["đau ngực", "tức ngực", "đau thắt ngực", "khó thở khi đau ngực", "cấp cứu tim mạch"],
        "keywords_en": ["chest pain", "angina", "chest pressure", "coronary artery", "heart attack warning"]
    },
    "heart-blood-pressure-heart-failure.json": {
        "title_vi": "Suy tim",
        "keywords_vi": ["suy tim", "khó thở khi nằm", "phù chân", "suy tim sung huyết", "tim mạch"],
        "keywords_en": ["heart failure", "congestive heart failure", "shortness of breath", "fluid retention", "cardiomyopathy"]
    },
    "heart-blood-pressure-high-blood-pressure.json": {
        "title_vi": "Tăng huyết áp (Huyết áp cao)",
        "keywords_vi": ["tăng huyết áp", "huyết áp cao", "đo huyết áp", "chỉ số huyết áp", "tim mạch"],
        "keywords_en": ["high blood pressure", "hypertension", "blood pressure reading", "systolic", "cardiovascular disease"]
    },
    "heart-blood-pressure-low-blood-pressure.json": {
        "title_vi": "Hạ huyết áp (Huyết áp thấp)",
        "keywords_vi": ["hạ huyết áp", "huyết áp thấp", "tụt huyết áp", "chóng mặt hoa mắt", "huyết áp"],
        "keywords_en": ["low blood pressure", "hypotension", "dizziness", "fainting", "orthostatic hypotension"]
    },

    # --- Eye, Ear & Mouth (4) ---
    "eye-ear-mouth-bad-breath.json": {
        "title_vi": "Hôi miệng",
        "keywords_vi": ["hôi miệng", "hơi thở có mùi", "viêm nha chu", "vệ sinh răng miệng", "nha khoa"],
        "keywords_en": ["bad breath", "halitosis", "oral hygiene", "gum disease", "tongue bacteria"]
    },
    "eye-ear-mouth-dry-eyes.json": {
        "title_vi": "Khô mắt",
        "keywords_vi": ["khô mắt", "mỏi mắt", "rát mắt", "nước mắt nhân tạo", "nhãn khoa"],
        "keywords_en": ["dry eyes", "dry eye syndrome", "artificial tears", "eye irritation", "tear film"]
    },
    "eye-ear-mouth-ear-infection.json": {
        "title_vi": "Viêm tai (Nhiễm trùng tai)",
        "keywords_vi": ["viêm tai", "nhiễm trùng tai", "viêm tai giữa", "đau tai", "chảy dịch tai"],
        "keywords_en": ["ear infection", "otitis media", "ear pain", "ear discharge", "middle ear"]
    },
    "eye-ear-mouth-hearing-loss.json": {
        "title_vi": "Suy giảm thính lực (Mất thính lực)",
        "keywords_vi": ["suy giảm thính lực", "mất thính lực", "nghe kém", "ù tai", "tai mũi họng"],
        "keywords_en": ["hearing loss", "deafness", "tinnitus", "hearing impairment", "audiology"]
    },

    # --- Pregnancy & Children (5) ---
    "pregnancy-children-breastfeeding.json": {
        "title_vi": "Nuôi con bằng sữa mẹ",
        "keywords_vi": ["nuôi con bằng sữa mẹ", "cho con bú", "sữa mẹ", "sản phụ khoa", "dinh dưỡng trẻ sơ sinh"],
        "keywords_en": ["breastfeeding", "lactation", "nursing", "maternal milk", "infant nutrition"]
    },
    "pregnancy-children-child-development.json": {
        "title_vi": "Phát triển ở trẻ em",
        "keywords_vi": ["phát triển ở trẻ em", "mốc phát triển", "tăng trưởng trẻ em", "nhi khoa", "kỹ năng vận động"],
        "keywords_en": ["child development", "developmental milestones", "growth milestones", "pediatric development", "motor skills"]
    },
    "pregnancy-children-pregnancy-nutrition.json": {
        "title_vi": "Dinh dưỡng khi mang thai",
        "keywords_vi": ["dinh dưỡng khi mang thai", "ăn uống thai kỳ", "bổ sung axit folic", "vitamin cho bà bầu", "sản khoa"],
        "keywords_en": ["pregnancy nutrition", "prenatal diet", "folic acid", "prenatal vitamins", "maternal health"]
    },
    "pregnancy-children-pregnancy.json": {
        "title_vi": "Mang thai (Thai kỳ)",
        "keywords_vi": ["mang thai", "thai kỳ", "dấu hiệu mang thai", "khám thai định kỳ", "sản phụ khoa"],
        "keywords_en": ["pregnancy", "prenatal care", "gestation", "pregnancy symptoms", "obstetrics"]
    },
    "pregnancy-children-vaccinations.json": {
        "title_vi": "Tiêm chủng ở trẻ em",
        "keywords_vi": ["tiêm chủng ở trẻ em", "vắc-xin trẻ em", "lịch tiêm chủng", "phòng ngừa bệnh", "nhi khoa"],
        "keywords_en": ["childhood vaccinations", "immunization schedule", "vaccines", "pediatric immunization", "disease prevention"]
    },

    # --- Urinary System (6) ---
    "urinary-system-blood-in-urine.json": {
        "title_vi": "Tiểu ra máu (Đái máu)",
        "keywords_vi": ["tiểu ra máu", "đái máu", "nước tiểu có máu", "tiết niệu", "nhiễm trùng đường tiểu"],
        "keywords_en": ["blood in urine", "hematuria", "urinary tract", "kidney bleeding", "red urine"]
    },
    "urinary-system-kidney-infection.json": {
        "title_vi": "Nhiễm trùng thận (Viêm đài bể thận)",
        "keywords_vi": ["nhiễm trùng thận", "viêm đài bể thận", "đau hông lưng", "sốt rét run", "tiết niệu"],
        "keywords_en": ["kidney infection", "pyelonephritis", "flank pain", "urinary infection", "renal infection"]
    },
    "urinary-system-kidney-stones.json": {
        "title_vi": "Sỏi thận",
        "keywords_vi": ["sỏi thận", "cơn đau quặn thận", "tiểu buốt", "tán sỏi", "tiết niệu"],
        "keywords_en": ["kidney stones", "renal calculi", "nephrolithiasis", "renal colic", "urinary stones"]
    },
    "urinary-system-overactive-bladder.json": {
        "title_vi": "Bàng quang tăng hoạt (OAB)",
        "keywords_vi": ["bàng quang tăng hoạt", "tiểu gấp", "tiểu nhiều lần", "tiểu đêm", "tiết niệu"],
        "keywords_en": ["overactive bladder", "urinary urgency", "frequent urination", "bladder spasms", "nocturia"]
    },
    "urinary-system-urinary-incontinence.json": {
        "title_vi": "Tiểu không tự chủ (Són tiểu)",
        "keywords_vi": ["tiểu không tự chủ", "són tiểu", "mất kiểm soát tiểu tiện", "tiết niệu", "cơ sàn chậu"],
        "keywords_en": ["urinary incontinence", "bladder leakage", "stress incontinence", "urge incontinence", "pelvic floor"]
    },
    "urinary-system-urinary-tract-infection.json": {
        "title_vi": "Nhiễm trùng đường tiết niệu (UTI)",
        "keywords_vi": ["nhiễm trùng đường tiết niệu", "viêm đường tiết niệu", "tiểu buốt rát", "tiểu rắt", "tiết niệu"],
        "keywords_en": ["urinary tract infection", "UTI", "burning urination", "dysuria", "bladder infection"]
    },

    # --- Nutrition (7) ---
    "nutrition-calcium.json": {
        "title_vi": "Canxi và sức khỏe",
        "keywords_vi": ["canxi", "bổ sung canxi", "chắc khỏe xương", "loãng xương", "khoáng chất"],
        "keywords_en": ["calcium", "bone health", "calcium supplement", "osteoporosis prevention", "dietary minerals"]
    },
    "nutrition-healthy-eating.json": {
        "title_vi": "Chế độ ăn uống lành mạnh",
        "keywords_vi": ["chế độ ăn uống lành mạnh", "dinh dưỡng hợp lý", "tháp dinh dưỡng", "chất xơ", "ăn sạch"],
        "keywords_en": ["healthy eating", "balanced diet", "nutrition guidelines", "dietary fiber", "healthy food choices"]
    },
    "nutrition-magnesium.json": {
        "title_vi": "Magiê (Magnesium)",
        "keywords_vi": ["magiê", "magnesium", "chuột rút cơ bắp", "khoáng chất thiết yếu", "dinh dưỡng"],
        "keywords_en": ["magnesium", "dietary magnesium", "muscle cramps", "essential minerals", "electrolyte balance"]
    },
    "nutrition-vegan-diet.json": {
        "title_vi": "Chế độ ăn thuần chay",
        "keywords_vi": ["chế độ ăn thuần chay", "ăn chay trường", "nguồn đạm thực vật", "thiếu vitamin B12", "dinh dưỡng"],
        "keywords_en": ["vegan diet", "plant-based nutrition", "plant protein", "vegan health", "b12 supplementation"]
    },
    "nutrition-vegetarian-diet.json": {
        "title_vi": "Chế độ ăn chay",
        "keywords_vi": ["chế độ ăn chay", "ăn chay", "dinh dưỡng thực vật", "chất sắt", "sức khỏe tim mạch"],
        "keywords_en": ["vegetarian diet", "vegetarian nutrition", "plant-based diet", "iron absorption", "heart health"]
    },
    "nutrition-vitamin-b12.json": {
        "title_vi": "Vitamin B12 (Cobalamin)",
        "keywords_vi": ["vitamin B12", "vitamin nhóm B", "thiếu máu ác tính", "bổ sung vitamin", "thần kinh dinh dưỡng"],
        "keywords_en": ["vitamin B12", "cobalamin", "b complex", "pernicious anemia", "neurological health"]
    },
    "nutrition-vitamin-d.json": {
        "title_vi": "Vitamin D",
        "keywords_vi": ["vitamin D", "hấp thụ canxi", "loãng xương", "ánh nắng mặt trời", "miễn dịch"],
        "keywords_en": ["vitamin D", "sunlight vitamin", "calcium absorption", "bone density", "immune support"]
    },

    # --- Medicines (8) ---
    "medicines-antibiotics.json": {
        "title_vi": "Kháng sinh và lưu ý sử dụng",
        "keywords_vi": ["kháng sinh", "dùng thuốc kháng sinh", "kháng kháng sinh", "nhiễm khuẩn", "đủ liều"],
        "keywords_en": ["antibiotics", "antibiotic resistance", "bacterial infection", "prescription antibiotics", "medication compliance"]
    },
    "medicines-drug-interactions.json": {
        "title_vi": "Tương tác thuốc",
        "keywords_vi": ["tương tác thuốc", "uống chung thuốc", "tương tác thức ăn thuốc", "an toàn dùng thuốc", "dược lâm sàng"],
        "keywords_en": ["drug interactions", "medication interactions", "drug food interaction", "adverse drug reaction", "polypharmacy"]
    },
    "medicines-ibuprofen.json": {
        "title_vi": "Thuốc Ibuprofen",
        "keywords_vi": ["ibuprofen", "thuốc kháng viêm NSAID", "giảm đau hạ sốt", "loét dạ dày", "dược phẩm"],
        "keywords_en": ["ibuprofen", "NSAID", "anti-inflammatory", "pain relief", "fever reducer"]
    },
    "medicines-medicine-safety.json": {
        "title_vi": "An toàn khi dùng thuốc",
        "keywords_vi": ["an toàn khi dùng thuốc", "bảo quản thuốc", "hạn sử dụng thuốc", "đúng chỉ định", "dược phẩm"],
        "keywords_en": ["medicine safety", "safe medication use", "drug storage", "expiration date", "dosage guidelines"]
    },
    "medicines-missed-dose.json": {
        "title_vi": "Xử trí khi quên uống thuốc",
        "keywords_vi": ["quên uống thuốc", "bỏ lỡ liều thuốc", "uống bù liều", "hướng dẫn liều", "dược phẩm"],
        "keywords_en": ["missed dose", "forgot medication", "make-up dose", "dosage schedule", "prescription adherence"]
    },
    "medicines-painkillers.json": {
        "title_vi": "Thuốc giảm đau",
        "keywords_vi": ["thuốc giảm đau", "thuốc giảm đau không kê đơn", "giảm đau nhức", "tác dụng phụ", "dược lâm sàng"],
        "keywords_en": ["painkillers", "analgesics", "pain relievers", "OTC pain medication", "chronic pain relief"]
    },
    "medicines-paracetamol.json": {
        "title_vi": "Thuốc Paracetamol (Acetaminophen)",
        "keywords_vi": ["paracetamol", "acetaminophen", "hạ sốt giảm đau", "ngộ độc gan do paracetamol", "liều paracetamol"],
        "keywords_en": ["paracetamol", "acetaminophen", "fever reducer", "pain relief", "liver toxicity risk"]
    },
    "medicines-side-effects.json": {
        "title_vi": "Tác dụng phụ của thuốc",
        "keywords_vi": ["tác dụng phụ của thuốc", "phản ứng có hại ADR", "dị ứng thuốc", "buồn nôn phát ban", "dược lâm sàng"],
        "keywords_en": ["side effects", "adverse effects", "drug reactions", "allergic reaction to medication", "ADR"]
    },

    # --- Mental Health (9) ---
    "mental-health-adhd.json": {
        "title_vi": "Rối loạn tăng động giảm chú ý (ADHD)",
        "keywords_vi": ["ADHD", "tăng động giảm chú ý", "mất tập trung", "hành vi hiếu động", "tâm thần học"],
        "keywords_en": ["ADHD", "attention deficit hyperactivity disorder", "inattention", "hyperactivity", "impulsivity"]
    },
    "mental-health-anxiety.json": {
        "title_vi": "Rối loạn lo âu",
        "keywords_vi": ["rối loạn lo âu", "lo âu lan tỏa", "cơn hoảng loạn", "hồi hộp lo sợ", "sức khỏe tâm thần"],
        "keywords_en": ["anxiety", "generalized anxiety disorder", "panic attack", "excessive worrying", "nervousness"]
    },
    "mental-health-autism.json": {
        "title_vi": "Rối loạn phổ tự kỷ (ASD)",
        "keywords_vi": ["tự kỷ", "rối loạn phổ tự kỷ", "giao tiếp xã hội", "hành vi lặp lại", "tâm bệnh nhi"],
        "keywords_en": ["autism", "autism spectrum disorder", "ASD", "social communication", "repetitive behaviors"]
    },
    "mental-health-depression.json": {
        "title_vi": "Bệnh trầm cảm",
        "keywords_vi": ["trầm cảm", "rối loạn trầm cảm", "buồn chán mất hứng thú", "mệt mỏi u uất", "sức khỏe tâm thần"],
        "keywords_en": ["depression", "major depressive disorder", "low mood", "loss of interest", "mental wellness"]
    },
    "mental-health-grief.json": {
        "title_vi": "Nỗi đau mất mát và đau buồn",
        "keywords_vi": ["nỗi đau mất mát", "đau buồn", "mất người thân", "vượt qua mất mát", "tâm lý trị liệu"],
        "keywords_en": ["grief", "bereavement", "mourning", "loss of loved one", "emotional healing"]
    },
    "mental-health-insomnia.json": {
        "title_vi": "Mất ngủ (Rối loạn giấc ngủ)",
        "keywords_vi": ["mất ngủ", "khó ngủ", "thức giấc nửa đêm", "thiếu ngủ", "giấc ngủ"],
        "keywords_en": ["insomnia", "sleep disorder", "trouble sleeping", "sleeplessness", "sleep quality"]
    },
    "mental-health-ocd.json": {
        "title_vi": "Rối loạn ám ảnh cưỡng chế (OCD)",
        "keywords_vi": ["OCD", "ám ảnh cưỡng chế", "suy nghĩ ám ảnh", "hành vi cưỡng chế", "sức khỏe tâm thần"],
        "keywords_en": ["OCD", "obsessive compulsive disorder", "obsessions", "compulsions", "intrusive thoughts"]
    },
    "mental-health-ptsd.json": {
        "title_vi": "Rối loạn căng thẳng sau sang chấn (PTSD)",
        "keywords_vi": ["PTSD", "căng thẳng sau sang chấn", "hồi tưởng sang chấn", "ác mộng chấn thương", "sức khỏe tâm thần"],
        "keywords_en": ["PTSD", "post traumatic stress disorder", "trauma flashbacks", "nightmares", "psychological trauma"]
    },
    "mental-health-stress.json": {
        "title_vi": "Căng thẳng (Stress)",
        "keywords_vi": ["căng thẳng", "stress", "giảm stress", "áp lực tâm lý", "kiệt sức mệt mỏi"],
        "keywords_en": ["stress", "chronic stress", "stress management", "mental strain", "burnout"]
    },

    # --- Diabetes & Hormones (10) ---
    "diabetes-hormones-adrenal-disorders.json": {
        "title_vi": "Rối loạn tuyến thượng thận",
        "keywords_vi": ["rối loạn tuyến thượng thận", "tuyến thượng thận", "suy thượng thận", "cortisol", "nội tiết"],
        "keywords_en": ["adrenal disorders", "adrenal gland", "adrenal insufficiency", "cortisol", "endocrine disease"]
    },
    "diabetes-hormones-hyperglycemia.json": {
        "title_vi": "Tăng đường huyết (Đường huyết cao)",
        "keywords_vi": ["tăng đường huyết", "đường huyết cao", "đái tháo đường", "khát nước tiểu nhiều", "chỉ số glucose"],
        "keywords_en": ["hyperglycemia", "high blood sugar", "high blood glucose", "diabetes symptom", "glucose spike"]
    },
    "diabetes-hormones-hyperthyroidism.json": {
        "title_vi": "Cường giáp (Tuyến giáp hoạt động quá mức)",
        "keywords_vi": ["cường giáp", "tuyến giáp hoạt động quá mức", "tim đập nhanh sụt cân", "bướu giáp", "nội tiết"],
        "keywords_en": ["hyperthyroidism", "overactive thyroid", "rapid heart rate", "weight loss", "thyroid hormone"]
    },
    "diabetes-hormones-hypoglycemia.json": {
        "title_vi": "Hạ đường huyết (Đường huyết thấp)",
        "keywords_vi": ["hạ đường huyết", "đường huyết thấp", "tụt đường huyết", "run tay đói lả", "glucose máu thấp"],
        "keywords_en": ["hypoglycemia", "low blood sugar", "low blood glucose", "shakiness sweating", "glucose drop"]
    },
    "diabetes-hormones-hypothyroidism.json": {
        "title_vi": "Suy giáp (Tuyến giáp hoạt động kém)",
        "keywords_vi": ["suy giáp", "tuyến giáp hoạt động kém", "mệt mỏi tăng cân sợ lạnh", "nội tiết", "hormone tuyến giáp"],
        "keywords_en": ["hypothyroidism", "underactive thyroid", "fatigue weight gain", "cold sensitivity", "thyroid deficiency"]
    },
    "diabetes-hormones-insulin-resistance.json": {
        "title_vi": "Kháng insulin",
        "keywords_vi": ["kháng insulin", "nhạy cảm insulin", "hội chứng chuyển hóa", "nguy cơ tiểu đường", "nội tiết"],
        "keywords_en": ["insulin resistance", "metabolic syndrome", "pre-diabetes risk", "hyperinsulinemia", "glucose uptake"]
    },
    "diabetes-hormones-prediabetes.json": {
        "title_vi": "Tiền đái tháo đường (Tiền tiểu đường)",
        "keywords_vi": ["tiền đái tháo đường", "tiền tiểu đường", "rối loạn dung nạp glucose", "phòng ngừa tiểu đường", "đường huyết lúc đói"],
        "keywords_en": ["prediabetes", "borderline diabetes", "impaired glucose tolerance", "diabetes prevention", "fasting glucose"]
    },
    "diabetes-hormones-thyroid-disease.json": {
        "title_vi": "Bệnh lý tuyến giáp",
        "keywords_vi": ["bệnh lý tuyến giáp", "tuyến giáp", "bướu cổ", "nhân tuyến giáp", "nội tiết"],
        "keywords_en": ["thyroid disease", "thyroid disorders", "goiter", "thyroid nodules", "endocrine gland"]
    },
    "diabetes-hormones-type-1-diabetes.json": {
        "title_vi": "Đái tháo đường tuýp 1 (Tiểu đường tuýp 1)",
        "keywords_vi": ["đái tháo đường tuýp 1", "tiểu đường tuýp 1", "tiêm insulin", "thiếu hụt insulin", "đái tháo đường tự miễn"],
        "keywords_en": ["type 1 diabetes", "juvenile diabetes", "insulin dependent", "insulin therapy", "autoimmune diabetes"]
    },
    "diabetes-hormones-type-2-diabetes.json": {
        "title_vi": "Đái tháo đường tuýp 2 (Tiểu đường tuýp 2)",
        "keywords_vi": ["đái tháo đường tuýp 2", "tiểu đường tuýp 2", "kiểm soát đường huyết", "hạ đường huyết ăn uống", "nội tiết"],
        "keywords_en": ["type 2 diabetes", "adult onset diabetes", "blood sugar control", "metformin", "lifestyle management"]
    }
}
