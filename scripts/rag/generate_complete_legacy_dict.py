"""
Generates complete bilingual metadata mapping for all 241 legacy documents.
Validates that every single file in data/curated/ready_documents/ has a valid mapping.
Outputs data/curated/legacy_metadata_full.json.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "data" / "curated" / "legacy_docs_inventory.json"
OUTPUT_PATH = ROOT / "data" / "curated" / "legacy_metadata_full.json"

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

# Accurate Vietnamese medical titles and keywords
TITLE_VI_MAP = {
    # General Symptoms (23)
    "Bad breath": ("Hôi miệng", ["hôi miệng", "hơi thở có mùi", "viêm nha chu", "vệ sinh răng miệng", "nha khoa"], ["bad breath", "halitosis", "oral hygiene", "mouth odor"]),
    "Chills": ("Ớn lạnh (Rét run)", ["ớn lạnh", "rét run", "sốt rét", "nhiễm trùng", "thân nhiệt"], ["chills", "shivering", "fever chills", "cold sensations"]),
    "Confusion": ("Lú lẫn (Rối loạn ý thức)", ["lú lẫn", "mất phương hướng", "rối loạn ý thức", "mê sảng", "thần kinh"], ["confusion", "disorientation", "delirium", "altered mental state"]),
    "Dehydration": ("Mất nước", ["mất nước", "thiếu nước", "khát nước", "bù điện giải", "chống mất nước"], ["dehydration", "fluid loss", "electrolyte imbalance", "rehydration"]),
    "Dry mouth": ("Khô miệng", ["khô miệng", "ít tiết nước bọt", "rát lưỡi", "tuyến nước bọt", "nha khoa"], ["dry mouth", "xerostomia", "salivary glands", "mouth dryness"]),
    "Fainting": ("Ngất xỉu (Bất tỉnh)", ["ngất xỉu", "bất tỉnh", "choáng váng", "tụt huyết áp", "ngất"], ["fainting", "syncope", "loss of consciousness", "lightheadedness"]),
    "Fatigue": ("Mệt mỏi kéo dài (Suy nhược cơ thể)", ["mệt mỏi", "suy nhược cơ thể", "đuối sức", "kiệt sức", "uể oải"], ["fatigue", "chronic fatigue", "exhaustion", "low energy"]),
    "Fever": ("Sốt (Thân nhiệt cao)", ["sốt", "thân nhiệt cao", "cơn sốt", "hạ sốt", "nhiệt độ cơ thể"], ["fever", "high temperature", "pyrexia", "febrile", "antipyretic"]),
    "Headache": ("Đau đầu (Nhức đầu)", ["đau đầu", "nhức đầu", "đau nửa đầu", "căng thẳng đầu", "chóng mặt"], ["headache", "cephalea", "tension headache", "head pain"]),
    "High fever": ("Sốt cao", ["sốt cao", "sốt trên 39 độ", "co giật do sốt", "cấp cứu sốt cao", "hạ sốt nhanh"], ["high fever", "severe fever", "hyperpyrexia", "febrile seizure"]),
    "Hot flashes": ("Bốc hỏa (Cơn nóng bừng)", ["bốc hỏa", "cơn nóng bừng", "tiền mãn kinh", "đổ mồ hôi đêm", "nội tiết nữ"], ["hot flashes", "hot flushes", "night sweats", "menopausal symptom"]),
    "Itching": ("Ngứa ngáy (Ngứa toàn thân)", ["ngứa ngáy", "ngứa da", "dị ứng ngứa", "mẩn ngứa", "da liễu"], ["itching", "pruritus", "itchy skin", "allergic itch"]),
    "Joint pain": ("Đau nhức khớp", ["đau nhức khớp", "viêm khớp", "sưng khớp", "cứng khớp", "cơ xương khớp"], ["joint pain", "arthralgia", "joint stiffness", "joint swelling"]),
    "Low-grade fever": ("Sốt nhẹ", ["sốt nhẹ", "sốt âm ỉ", "nhiễm trùng mạn", "sốt chiều tối", "theo dõi sốt"], ["low-grade fever", "mild fever", "slight fever", "subfebrile"]),
    "Migraine": ("Đau nửa đầu (Migraine)", ["đau nửa đầu", "migraine", "đau đầu giật nhói", "sợ ánh sáng", "buồn nôn đau đầu"], ["migraine", "migraine aura", "unilateral headache", "photophobia"]),
    "Muscle pain": ("Đau cơ (Đau nhức bắp thịt)", ["đau cơ", "đau bắp thịt", "mỏi cơ", "viêm cơ", "cơ xương khớp"], ["muscle pain", "myalgia", "muscle soreness", "muscle aches"]),
    "Swelling": ("Sưng phù (Phù nề)", ["sưng phù", "phù nề", "ứ dịch", "phù chân", "viêm sưng"], ["swelling", "edema", "fluid retention", "puffiness"]),
    "Swollen glands": ("Sưng hạch (Nổi hạch)", ["sưng hạch", "nổi hạch", "hạch cổ", "hạch bạch huyết", "nhiễm trùng hạch"], ["swollen glands", "swollen lymph nodes", "lymphadenopathy", "lymph node swelling"]),
    "Tremor": ("Run tay chân (Run cơ)", ["run tay chân", "run cơ", "run vô căn", "bệnh parkinson", "thần kinh"], ["tremor", "shaking hands", "involuntary shaking", "essential tremor"]),
    "Vertigo": ("Chóng mặt hoa mắt (Chóng mặt kịch phát)", ["chóng mặt", "chóng mặt hoa mắt", "tiền đình", "chóng mặt kịch phát", "mất thăng bằng"], ["vertigo", "dizziness", "vestibular disorder", "spinning sensation"]),
    "Weakness": ("Yếu sức (Yếu cơ)", ["yếu sức", "yếu cơ", "suy nhược", "mất sức lực", "liệt cơ"], ["weakness", "muscle weakness", "asthenia", "lack of strength"]),
    "Weight gain": ("Tăng cân không rõ nguyên nhân", ["tăng cân", "tăng cân nhanh", "tích tụ mỡ", "rối loạn chuyển hóa", "nội tiết"], ["weight gain", "unexplained weight gain", "fluid weight", "metabolic weight"]),
    "Weight loss": ("Sụt cân không rõ nguyên nhân", ["sụt cân", "giảm cân nhanh", "gầy sút", "suy dinh dưỡng", "sụt cân không rõ nguyên nhân"], ["weight loss", "unexplained weight loss", "rapid weight loss", "cachexia"]),

    # Digestive (21)
    "Abdominal pain": ("Đau bụng", ["đau bụng", "đau dạ dày", "đau vùng bụng", "khó tiêu", "co thắt bụng"], ["abdominal pain", "stomach pain", "belly ache", "abdominal cramps"]),
    "Acid reflux": ("Trào ngược axit dạ dày", ["trào ngược axit", "axit dạ dày", "ợ chua", "nóng rát thực quản", "tiêu hóa"], ["acid reflux", "gastric acid", "acid regurgitation", "esophageal burning"]),
    "Appendicitis": ("Viêm ruột thừa", ["viêm ruột thừa", "đau hố chậu phải", "cấp cứu ngoại khoa", "vỡ ruột thừa", "sốt đau bụng"], ["appendicitis", "acute appendicitis", "lower right abdominal pain", "appendectomy"]),
    "Burping": ("Ợ hơi (Ợ chua)", ["ợ hơi", "ợ chua", "đầy hơi", "chướng bụng", "khó tiêu"], ["burping", "belching", "excessive gas", "eructation"]),
    "Celiac disease": ("Bệnh Celiac (Không dung nạp gluten)", ["bệnh celiac", "không dung nạp gluten", "viêm ruột non", "dị ứng lúa mì", "tiêu hóa"], ["celiac disease", "gluten intolerance", "gluten free", "small intestine damage"]),
    "Constipation": ("Táo bón", ["táo bón", "khó đại tiện", "phân khô cứng", "chất xơ", "tiêu hóa"], ["constipation", "infrequent bowel movements", "hard stool", "dietary fiber constipation"]),
    "Crohn's disease": ("Bệnh Crohn (Viêm ruột từng vùng)", ["bệnh crohn", "viêm ruột từng vùng", "viêm đại tràng", "đau bụng tiêu chảy", "bệnh IBD"], ["Crohn's disease", "inflammatory bowel disease", "IBD", "intestinal inflammation"]),
    "Diarrhea": ("Tiêu chảy", ["tiêu chảy", "đi ngoài phân lỏng", "mất nước tiêu chảy", "tiêu chảy nhiễm trùng", "men vi sinh"], ["diarrhea", "loose stools", "watery diarrhea", "gastroenteritis"]),
    "Food poisoning": ("Ngộ độc thực phẩm", ["ngộ độc thực phẩm", "ăn phải thức ăn ôi thiu", "buồn nôn tiêu chảy", "đau bụng cấp", "nhiễm khuẩn đường ruột"], ["food poisoning", "foodborne illness", "food toxicity", "bacterial food contamination"]),
    "Gallstones": ("Sỏi túi mật (Sỏi mật)", ["sỏi túi mật", "sỏi mật", "cơn đau quặn mật", "đau hạ sườn phải", "túi mật"], ["gallstones", "cholelithiasis", "biliary colic", "gallbladder stones"]),
    "Gas": ("Đầy hơi chướng bụng", ["đầy hơi", "chướng bụng", "sinh khí đường ruột", "sình bụng", "khó tiêu"], ["gas", "bloating", "intestinal gas", "flatulence", "abdominal fullness"]),
    "GERD": ("Trào ngược dạ dày thực quản (GERD)", ["trào ngược dạ dày thực quản", "GERD", "ợ nóng ợ chua", "viêm thực quản", "axit dạ dày"], ["GERD", "gastroesophageal reflux", "heartburn", "acid reflux disease"]),
    "Heartburn": ("Ợ nóng (Nóng rát thượng vị)", ["ợ nóng", "nóng rát thượng vị", "nóng sau xương ức", "trào ngược axit", "khó tiêu"], ["heartburn", "pyrosis", "acid indigestion", "burning chest sensation"]),
    "Hemorrhoids": ("Bệnh trĩ", ["bệnh trĩ", "trĩ nội", "trĩ ngoại", "chảy máu hậu môn", "búi trĩ"], ["hemorrhoids", "piles", "rectal bleeding", "anal itching", "hemorrhoidal cushion"]),
    "Hiccups": ("Nấc cụt kéo dài", ["nấc cụt", "cơn nấc", "co thắt cơ hoành", "nấc kéo dài", "tiêu hóa"], ["hiccups", "singultus", "diaphragm spasms", "persistent hiccups"]),
    "IBS": ("Hội chứng ruột kích thích (IBS)", ["hội chứng ruột kích thích", "IBS", "đại tràng co thắt", "rối loạn tiêu hóa", "đau bụng đi ngoài"], ["IBS", "irritable bowel syndrome", "spastic colon", "abdominal cramping"]),
    "Indigestion": ("Chứng khó tiêu (Đầy bụng)", ["khó tiêu", "đầy bụng", "ăn không tiêu", "chậm tiêu", "nặng bụng"], ["indigestion", "dyspepsia", "upset stomach", "bloated feeling"]),
    "Lactose intolerance": ("Chứng không dung nạp đường lactose", ["không dung nạp lactose", "dị ứng sữa", "đau bụng uống sữa", "thiếu hụt lactase", "tiêu chảy sau uống sữa"], ["lactose intolerance", "dairy sensitivity", "lactase deficiency", "milk allergy digestive"]),
    "Stomach ulcer": ("Viêm loét dạ dày tá tràng", ["viêm loét dạ dày", "loét tá tràng", "đau thượng vị", "vi khuẩn HP", "xuất huyết dạ dày"], ["stomach ulcer", "peptic ulcer", "gastric ulcer", "H pylori", "upper abdominal pain"]),
    "Ulcerative colitis": ("Viêm loét đại tràng", ["viêm loét đại tràng", "viêm đại tràng mạn tính", "đi ngoài ra máu", "bệnh IBD", "tiêu hóa"], ["ulcerative colitis", "colitis", "colon inflammation", "bloody diarrhea", "IBD"]),
    "Vomiting": ("Buồn nôn và nôn ói", ["buồn nôn", "nôn ói", "nôn mửa", "chống nôn", "mất nước do nôn"], ["vomiting", "nausea", "emesis", "upset stomach", "rehydration after vomiting"]),

    # Muscles, Bones & Back (20)
    "Ankle pain": ("Đau cổ chân (Đau mắt cá chân)", ["đau cổ chân", "đau mắt cá chân", "trật khớp cổ chân", "bong gân", "chấn thương cổ chân"], ["ankle pain", "sprained ankle", "ankle joint", "ankle swelling"]),
    "Arthritis": ("Viêm khớp", ["viêm khớp", "thoái hóa khớp", "sưng đau khớp", "cứng khớp buổi sáng", "cơ xương khớp"], ["arthritis", "joint inflammation", "joint stiffness", "rheumatic disease"]),
    "Carpal tunnel syndrome": ("Hội chứng ống cổ tay", ["hội chứng ống cổ tay", "tê bàn tay", "chèn ép thần kinh giữa", "đau cổ tay", "tê ngón tay"], ["carpal tunnel syndrome", "median nerve compression", "hand numbness", "wrist pain"]),
    "Frozen shoulder": ("Đông cứng khớp vai (Viêm quanh khớp vai)", ["đông cứng khớp vai", "viêm quanh khớp vai", "kẹt khớp vai", "khó giơ tay", "cơ xương khớp"], ["frozen shoulder", "adhesive capsulitis", "shoulder stiffness", "limited shoulder motion"]),
    "Heavy lifting injuries": ("Chấn thương do mang vác nặng", ["chấn thương mang vác", "căng cơ do vác nặng", "chấn thương lưng", "thoát vị đĩa đệm", "bảo vệ cột sống"], ["heavy lifting injuries", "lifting strain", "back injury", "spine injury", "ergonomics"]),
    "Heel pain": ("Đau gót chân (Viêm cân gan chân)", ["đau gót chân", "viêm cân gan chân", "gai gót chân", "đau bước chân sáng", "bàn chân"], ["heel pain", "plantar fasciitis", "heel spur", "morning heel pain", "foot arch"]),
    "Lower back pain": ("Đau thắt lưng (Đau lưng dưới)", ["đau thắt lưng", "đau lưng dưới", "thoát vị đĩa đệm", "căng cơ thắt lưng", "cột sống lưng"], ["lower back pain", "lumbago", "lumbar strain", "herniated disc", "sciatica back"]),
    "Muscle cramps": ("Chuột rút cơ bắp (Vọp bẻ)", ["chuột rút", "vọp bẻ", "co rút bắp chân", "thiếu canxi magie", "chuột rút ban đêm"], ["muscle cramps", "charley horse", "muscle spasms", "nocturnal leg cramps"]),
    "Muscle stiffness": ("Cứng cơ (Cứng khớp)", ["cứng cơ", "căng cứng bắp thịt", "cứng khớp", "mỏi cơ", "giãn cơ"], ["muscle stiffness", "stiff muscles", "inflexibility", "muscle tightness"]),
    "Muscle strain": ("Căng cơ (Giãn cơ)", ["căng cơ", "giãn cơ", "rách sợi cơ", "chấn thương thể thao", "nghỉ ngơi chườm lạnh"], ["muscle strain", "pulled muscle", "torn muscle", "sports injury strain"]),
    "Neck pain": ("Đau cổ vai gáy", ["đau cổ vai gáy", "thoái hóa đốt sống cổ", "căng cứng cổ", "đau gáy", "cơ xương khớp"], ["neck pain", "cervical spine", "cervical spondylosis", "stiff neck", "neck strain"]),
    "Osteoarthritis": ("Thoái hóa khớp", ["thoái hóa khớp", "mòn sụn khớp", "thoái hóa khớp gối", "đau khớp khi vận động", "khớp thoái hóa"], ["osteoarthritis", "degenerative joint disease", "knee osteoarthritis", "cartilage loss"]),
    "Pain between shoulder blades": ("Đau giữa hai bả vai", ["đau giữa hai bả vai", "đau lưng giữa", "căng cơ liên sườn", "thoái hóa cột sống ngực", "mỏi bả vai"], ["pain between shoulder blades", "interscapular pain", "upper back ache", "rhomboid strain"]),
    "Poor posture": ("Sai tư thế cột sống", ["sai tư thế", "gù lưng", "cong vẹo cột sống", "chỉnh dáng", "tư thế ngồi làm việc"], ["poor posture", "bad posture", "slouching", "spinal alignment", "ergonomic posture"]),
    "Rheumatoid arthritis": ("Viêm khớp dạng thấp", ["viêm khớp dạng thấp", "viêm khớp tự miễn", "biến dạng khớp", "sưng khớp đối xứng", "thấp khớp"], ["rheumatoid arthritis", "autoimmune arthritis", "symmetric joint swelling", "rheumatic disease"]),
    "Sciatica": ("Đau thần kinh tọa", ["đau thần kinh tọa", "đau lan xuống chân", "chèn ép rễ thần kinh", "thoát vị đĩa đệm lưng", "tê chân"], ["sciatica", "sciatic nerve pain", "lumbar radiculopathy", "radiating leg pain"]),
    "Shoulder pain": ("Đau khớp vai", ["đau khớp vai", "viêm gân chóp xoay", "sưng khớp vai", "khó nhấc cánh tay", "chấn thương vai"], ["shoulder pain", "rotator cuff tendinitis", "shoulder impingement", "shoulder joint pain"]),
    "Tennis elbow": ("Viêm lồi cầu ngoài xương cánh tay (Tennis elbow)", ["tennis elbow", "viêm lồi cầu ngoài", "đau khuỷu tay", "chấn thương gân khuỷu", "cơ xương khớp"], ["tennis elbow", "lateral epicondylitis", "elbow tendinitis", "forearm strain"]),
    "Upper back pain": ("Đau lưng trên", ["đau lưng trên", "căng cơ lưng trên", "đau cột sống ngực", "nhức mỏi lưng", "cột sống ngực"], ["upper back pain", "thoracic spine pain", "upper spine ache", "scapular discomfort"]),
    "Work-related muscle pain": ("Đau cơ liên quan đến nghề nghiệp", ["đau cơ nghề nghiệp", "chấn thương vi chấn lặp lại", "mỏi cơ văn phòng", "hội chứng RSI", "lao động nặng"], ["work-related muscle pain", "repetitive strain injury", "RSI", "occupational muscle pain"]),

    # Respiratory (19)
    "Allergic rhinitis": ("Viêm mũi dị ứng", ["viêm mũi dị ứng", "hắt hơi sổ mũi", "nghẹt mũi dị ứng", "dị ứng thời tiết", "tai mũi họng"], ["allergic rhinitis", "nasal allergies", "sneezing runny nose", "allergy congestion"]),
    "Asthma": ("Hen suyễn (Hen phế quản)", ["hen suyễn", "hen phế quản", "cơn khó thở", "khò khè", "thuốc xịt cắt cơn"], ["asthma", "bronchial asthma", "wheezing", "asthma attack", "inhaler"]),
    "Blocked nose": ("Nghẹt mũi (Tắc mũi)", ["nghẹt mũi", "tắc mũi", "ngạt mũi", "khó thở bằng mũi", "viêm mũi"], ["blocked nose", "nasal congestion", "stuffy nose", "sinus blockage"]),
    "Bronchitis": ("Viêm phế quản", ["viêm phế quản", "viêm phế quản cấp", "ho có đờm", "viêm đường hô hấp dưới", "khó thở rát ngực"], ["bronchitis", "acute bronchitis", "chest cold", "coughing mucus", "bronchial tubes"]),
    "Chest pain": ("Đau ngực kiểu màng phổi", ["đau ngực hô hấp", "đau khi hít sâu", "viêm màng phổi", "đau thành ngực", "hô hấp"], ["chest pain respiratory", "pleuritic chest pain", "pain on deep breath", "pleurisy"]),
    "Common cold": ("Cảm lạnh thông thường", ["cảm lạnh thông thường", "cảm lạnh", "sổ mũi hắt hơi", "nghẹt mũi nhẹ", "virus cảm lạnh"], ["common cold", "head cold", "rhinovirus", "runny nose sore throat"]),
    "Cough": ("Ho", ["ho", "cơn ho", "ho kích ứng", "ho khàn tiếng", "đường hô hấp"], ["cough", "tussis", "coughing fit", "respiratory reflex", "cough symptom"]),
    "COVID-19": ("Bệnh COVID-19", ["COVID-19", "nhiễm virus SARS-CoV-2", "mất khứu giác", "sốt ho khó thở", "nhiễm trùng hô hấp"], ["COVID-19", "coronavirus", "SARS-CoV-2", "loss of taste smell", "viral respiratory"]),
    "Dry cough": ("Ho khan", ["ho khan", "ho không có đờm", "rát họng ho khan", "kích ứng phế quản", "thuốc giảm ho"], ["dry cough", "nonproductive cough", "tickly cough", "irritating cough"]),
    "Hay fever": ("Sốt cỏ khô (Dị ứng phấn hoa)", ["sốt cỏ khô", "dị ứng phấn hoa", "ngứa mắt hắt hơi", "chảy nước mũi", "dị ứng theo mùa"], ["hay fever", "pollinosis", "pollen allergy", "seasonal rhinitis"]),
    "Influenza": ("Cúm mùa (Cúm A/B)", ["cúm mùa", "cúm A", "cúm B", "sốt cao đau nhức mình mẩy", "virus cúm"], ["influenza", "flu", "seasonal flu", "flu virus", "body aches fever"]),
    "Nosebleed": ("Chảy máu cam (Xuất huyết mũi)", ["chảy máu cam", "chảy máu mũi", "sơ cứu chảy máu cam", "vỡ mao mạch mũi", "tai mũi họng"], ["nosebleed", "epistaxis", "bleeding from nose", "nasal hemorrhage"]),
    "Persistent cough": ("Ho kéo dài (Ho mạn tính)", ["ho kéo dài", "ho mạn tính", "ho trên 3 tuần", "tầm soát lao phổi", "viêm phế quản mạn"], ["persistent cough", "chronic cough", "lingering cough", "cough lasting weeks"]),
    "Pneumonia": ("Viêm phổi", ["viêm phổi", "nhiễm trùng phổi", "sốt cao khó thở", "đau ngực khi ho", "nhiễm khuẩn hô hấp"], ["pneumonia", "lung infection", "pulmonary infection", "shortness of breath pneumonia"]),
    "Productive cough": ("Ho có đờm", ["ho có đờm", "đờm xanh đờm vàng", "tống đờm", "thuốc long đờm", "hô hấp"], ["productive cough", "wet cough", "cough with phlegm", "expectorant", "mucus cough"]),
    "Seasonal allergies": ("Dị ứng theo mùa", ["dị ứng theo mùa", "viêm mũi mùa xuân", "ngứa mũi mắt", "dị ứng thời tiết", "kháng histamin"], ["seasonal allergies", "seasonal allergic rhinitis", "weather allergy", "antihistamine"]),
    "Shortness of breath": ("Khó thở (Hụt hơi)", ["khó thở", "hụt hơi", "thở dốc", "thiếu oxy", "cấp cứu khó thở"], ["shortness of breath", "dyspnea", "breathlessness", "difficulty breathing"]),
    "Sinusitis": ("Viêm xoang", ["viêm xoang", "viêm xoang mũi", "đau nhức vùng mặt", "chảy dịch mũi vàng", "nghẹt mũi xoang"], ["sinusitis", "sinus infection", "facial pressure", "rhinosinusitis"]),
    "Sore throat": ("Đau họng (Rát họng)", ["đau họng", "rát họng", "viêm họng", "nuốt đau", "nhiễm trùng hầu họng"], ["sore throat", "pharyngitis", "throat pain", "painful swallowing"]),

    # Infectious Diseases (16)
    "AIDS": ("Hội chứng suy giảm miễn dịch mắc phải (AIDS)", ["AIDS", "suy giảm miễn dịch", "giai đoạn cuối HIV", "nhiễm trùng cơ hội", "bệnh truyền nhiễm"], ["AIDS", "acquired immunodeficiency", "advanced HIV", "opportunistic infections"]),
    "Chickenpox": ("Bệnh thủy đậu (Trái rạ)", ["thủy đậu", "trái rạ", "mụn nước thủy đậu", "nhiễm virus varicella", "ngứa phát ban"], ["chickenpox", "varicella", "varicella zoster virus", "blister rash"]),
    "Dengue": ("Sốt xuất huyết Dengue", ["sốt xuất huyết", "sốt dengue", "muỗi vằn truyền bệnh", "giảm tiểu cầu", "sốt xuất huyết cấp"], ["dengue", "dengue fever", "aedes mosquito", "thrombocytopenia", "hemorrhagic fever"]),
    "Gonorrhea": ("Bệnh lậu", ["bệnh lậu", "vi khuẩn lậu cầu", "tiểu buốt ra mủ", "bệnh lây qua đường tình dục", "điều trị lậu"], ["gonorrhea", "neisseria gonorrhoeae", "STI gonorrhea", "urethral discharge"]),
    "Hepatitis": ("Viêm gan (Viêm gan siêu vi)", ["viêm gan", "viêm gan siêu vi", "viêm gan B", "viêm gan C", "men gan tăng vàng da"], ["hepatitis", "viral hepatitis", "liver inflammation", "jaundice", "elevated liver enzymes"]),
    "HIV": ("Nhiễm virus HIV", ["nhiễm HIV", "virus suy giảm miễn dịch", "xét nghiệm HIV", "thuốc ARV", "phòng lây nhiễm HIV"], ["HIV", "human immunodeficiency virus", "HIV testing", "antiretroviral therapy", "ARV"]),
    "HPV": ("Virus u nhú ở người (HPV)", ["HPV", "virus u nhú người", "sùi mào gà", "ung thư cổ tử cung", "tiêm vắc-xin HPV"], ["HPV", "human papillomavirus", "genital warts", "cervical cancer risk", "HPV vaccine"]),
    "Lyme disease": ("Bệnh Lyme", ["bệnh lyme", "bọ ve đốt", "phát ban mắt bò", "nhiễm vi khuẩn borrelia", "đau nhức khớp lyme"], ["Lyme disease", "borrelia infection", "tick bite", "bullseye rash", "erythema migrans"]),
    "Malaria": ("Bệnh sốt rét", ["sốt rét", "ký sinh trùng sốt rét", "muỗi anopheles", "cơn sốt rét run", "phòng chống sốt rét"], ["malaria", "plasmodium parasite", "anopheles mosquito", "malarial paroxysm", "chills fever"]),
    "Measles": ("Bệnh sởi", ["bệnh sởi", "virus sởi", "phát ban sởi", "sốt phát ban ở trẻ", "vắc-xin sởi"], ["measles", "rubeola", "measles rash", "koplik spots", "measles vaccine"]),
    "Mononucleosis": ("Bệnh bạch cầu đơn nhân nhiễm trùng", ["bạch cầu đơn nhân nhiễm trùng", "virus EBV", "bệnh sốt tuyến", "sưng hạch viêm họng", "mệt mỏi kéo dài"], ["mononucleosis", "mono", "Epstein Barr virus", "glandular fever", "swollen tonsils"]),
    "Mumps": ("Bệnh quai bị", ["bệnh quai bị", "viêm tuyến nước bọt mang tai", "sưng mang tai", "biến chứng viêm tinh hoàn", "vắc-xin quai bị"], ["mumps", "parotitis", "swollen salivary glands", "orchitis complication", "mumps vaccine"]),
    "Rubella": ("Bệnh Rubella (Sởi Đức)", ["rubella", "sởi đức", "phát ban rubella", "hội chứng rubella bẩm sinh", "vắc-xin MMR"], ["rubella", "German measles", "rubella rash", "congenital rubella", "MMR vaccine"]),
    "Strep throat": ("Viêm họng do liên cầu khuẩn", ["viêm họng liên cầu", "liên cầu khuẩn nhóm A", "sốt đau rát họng", "kháng sinh viêm họng", "tai mũi họng"], ["strep throat", "streptococcal pharyngitis", "group A strep", "bacterial sore throat"]),
    "Syphilis": ("Bệnh giang mai", ["bệnh giang mai", "xoắn khuẩn giang mai", "săng giang mai", "xét nghiệm giang mai", "bệnh lây qua đường tình dục"], ["syphilis", "treponema pallidum", "chancre", "STI syphilis", "penicillin syphilis"]),
    "Tuberculosis": ("Bệnh lao (Lao phổi)", ["bệnh lao", "lao phổi", "vi khuẩn lao", "ho ra máu gầy sút", "điều trị thuốc lao"], ["tuberculosis", "TB", "pulmonary tuberculosis", "mycobacterium", "coughing blood TB"]),

    # Skin (15)
    "Acne": ("Mụn trứng cá", ["mụn trứng cá", "mụn bọc mụn mủ", "bít tắc lỗ chân lông", "chăm sóc da mụn", "da liễu"], ["acne", "acne vulgaris", "pimples", "blackheads", "skin breakouts"]),
    "Cellulitis": ("Viêm mô tế bào da", ["viêm mô tế bào", "nhiễm trùng da sâu", "sưng nóng đỏ đau da", "kháng sinh điều trị", "da liễu"], ["cellulitis", "bacterial skin infection", "red swollen skin", "skin inflammation"]),
    "Cold sores": ("Mụn rộp môi (Herpes môi)", ["mụn rộp môi", "herpes môi", "virus HSV-1", "mụn nước quanh miệng", "thuốc kháng virus"], ["cold sores", "fever blisters", "herpes simplex 1", "HSV oral", "lip blisters"]),
    "Eczema": ("Chàm da (Eczema / Viêm da cơ địa)", ["chàm da", "viêm da cơ địa", "eczema", "ngứa khô da", "dưỡng ẩm da"], ["eczema", "atopic dermatitis", "dry itchy skin", "skin barrier", "eczema flare"]),
    "Fungal infection": ("Nhiễm nấm da", ["nấm da", "nhiễm nấm ngoài da", "ngứa ngáy vùng nấm", "thuốc kháng nấm bôi", "da liễu"], ["fungal infection", "mycosis", "fungal skin infection", "antifungal cream"]),
    "Hives": ("Mề đay (Mày đay dị ứng)", ["mề đay", "mày đay", "dị ứng nổi sẩn ngứa", "phù mạch", "kháng histamin"], ["hives", "urticaria", "allergic welts", "itchy wheals", "skin rash hives"]),
    "Moles": ("Nốt ruồi và dấu hiệu ung thư da", ["nốt ruồi", "nốt ruồi lạ", "tầm soát ung thư da", "dấu hiệu melanoma ABCDE", "da liễu"], ["moles", "skin nevi", "melanoma warning signs", "ABCDE mole", "dermatology check"]),
    "Psoriasis": ("Bệnh vảy nến", ["vảy nến", "mảng vảy bạc", "viêm da vảy nến", "bệnh da tự miễn", "da liễu"], ["psoriasis", "plaque psoriasis", "silvery scales", "autoimmune skin", "psoriasis flare"]),
    "Ringworm": ("Hắc lào (Lác đồng tiền / Nấm da)", ["hắc lào", "lác đồng tiền", "nấm da hình tròn", "ngứa rát da", "thuốc trị nấm"], ["ringworm", "tinea corporis", "fungal ring rash", "dermatophyte", "itchy ring lesion"]),
    "Rosacea": ("Chứng đỏ mặt (Rosacea)", ["chứng đỏ mặt", "rosacea", "đỏ ửng mặt", "giãn mao mạch da mặt", "da nhạy cảm"], ["rosacea", "facial redness", "flushed skin", "telangiectasia", "sensitive facial skin"]),
    "Scabies": ("Bệnh ghẻ ngứa", ["bệnh ghẻ", "ghẻ ngứa", "cái ghẻ ký sinh", "ngứa dữ dội ban đêm", "lây nhiễm ghẻ"], ["scabies", "sarcoptes scabiei", "itch mite", "severe night itching", "scabies burrow"]),
    "Shingles": ("Bệnh Zona thần kinh", ["zona thần kinh", "bệnh giời leo", "mụn nước đau rát theo dây thần kinh", "virus herpes zoster", "di chứng đau sau zona"], ["shingles", "herpes zoster", "painful nerve rash", "blister band", "postherpetic neuralgia"]),
    "Skin infection": ("Nhiễm trùng da (Viêm da mủ)", ["nhiễm trùng da", "viêm da mủ", "nhọt da", "chốc lở", "nhiễm tụ cầu da"], ["skin infection", "cutaneous infection", "impetigo", "boils", "bacterial derm"]),
    "Sunburn": ("Cháy nắng (Bỏng nắng)", ["cháy nắng", "bỏng nắng", "đỏ rát da do nắng", "tác hại tia UV", "chống nắng"], ["sunburn", "solar erythema", "UV radiation damage", "sun protection", "skin peeling"]),
    "Warts": ("Mụn cóc (Hạt cơm)", ["mụn cóc", "hạt cơm", "mụn cóc do HPV", "mụn cóc lòng bàn chân", "tẩy mụn cóc"], ["warts", "verruca", "plantar warts", "HPV skin lesions", "wart removal"]),

    # First Aid & Emergencies (13)
    "Animal bites": ("Sơ cứu vết động vật cắn", ["vết động vật cắn", "chó cắn mèo cào", "sơ cứu vết cắn", "tiêm phòng dại", "nhiễm trùng vết thương"], ["animal bites", "dog bite", "cat scratch", "rabies prevention", "wound cleaning"]),
    "Bleeding": ("Sơ cứu cầm máu vết thương", ["cầm máu", "chảy máu ngoài", "băng ép cầm máu", "sơ cứu vết thương hở", "mất máu"], ["bleeding", "hemorrhage", "wound care bleeding", "direct pressure", "stop bleeding"]),
    "Broken bone": ("Sơ cứu gãy xương", ["gãy xương", "cố định xương gãy", "sơ cứu chấn thương gãy xương", "bất động chi", "cấp cứu chấn thương"], ["broken bone", "bone fracture", "immobilization fracture", "first aid fracture", "orthopedic emergency"]),
    "Burns": ("Sơ cứu bỏng", ["sơ cứu bỏng", "bỏng nước sôi bỏng lửa", "ngâm nước mát vết bỏng", "phỏng da", "phân độ bỏng"], ["burns", "thermal burn", "burn first aid", "cool water burn", "burn degrees"]),
    "Choking": ("Sơ cứu hóc nghẹn dị vật đường thở", ["hóc dị vật", "nghẹn đường thở", "thủ thuật heimlich", "cấp cứu ngạt thở", "sơ cứu hóc"], ["choking", "airway obstruction", "Heimlich maneuver", "foreign body airway", "first aid choking"]),
    "CPR": ("Hồi sinh tim phổi (CPR)", ["hồi sinh tim phổi", "CPR", "ép tim ngoài lồng ngực", "ngừng tim ngưng thở", "sơ cứu khẩn cấp"], ["CPR", "cardiopulmonary resuscitation", "chest compressions", "cardiac arrest first aid", "rescue breathing"]),
    "Electric shock": ("Sơ cứu giật điện", ["giật điện", "tai nạn điện giật", "sơ cứu bỏng điện", "ngắt nguồn điện", "ngừng tuần hoàn do điện"], ["electric shock", "electrical injury", "first aid electric shock", "power disconnection", "electrocution"]),
    "Heat exhaustion": ("Kiệt sức do nhiệt", ["kiệt sức do nhiệt", "say nắng nhẹ", "mất nước do nóng", "hạ nhiệt nghỉ ngơi", "thân nhiệt cao"], ["heat exhaustion", "heat illness", "dehydration heat", "cool down", "heat fatigue"]),
    "Heat stroke": ("Say nắng say nóng (Sốc nhiệt)", ["say nắng say nóng", "sốc nhiệt", "cấp cứu đột quỵ nhiệt", "hôn mê do nhiệt độ cao", "sơ cứu say nắng"], ["heat stroke", "sunstroke", "severe heat illness", "hyperthermia emergency", "cooling therapy"]),
    "Hypothermia": ("Hạ thân nhiệt", ["hạ thân nhiệt", "nhiễm lạnh nguy hiểm", "thân nhiệt giảm sâu", "ủ ấm cơ thể", "cấp cứu rét buốt"], ["hypothermia", "low body temperature", "cold exposure", "rewarming", "freezing emergency"]),
    "Nosebleed": ("Sơ cứu chảy máu cam", ["chảy máu cam", "chảy máu mũi", "sơ cứu cúi đầu ép mũi", "chảy máu mao mạch mũi", "cầm máu mũi"], ["nosebleed", "epistaxis", "first aid nosebleed", "pinch nose", "nasal bleeding"]),
    "Poisoning": ("Sơ cứu ngộ độc cấp tính", ["ngộ độc cấp", "uống nhầm hóa chất độc", "cấp cứu ngộ độc", "trung tâm chống độc", "sơ cứu nuốt độc"], ["poisoning", "toxic ingestion", "poison control", "accidental poisoning", "first aid toxins"]),
    "Snake bites": ("Sơ cứu rắn cắn", ["rắn cắn", "sơ cứu rắn độc cắn", "bất động chi bị cắn", "huyết thanh kháng nọc rắn", "cấp cứu rắn cắn"], ["snake bites", "venomous snake bite", "immobilize limb", "antivenom", "first aid snake"]),

    # Lifestyle (13)
    "Alcohol": ("Tác hại của rượu bia đối với sức khỏe", ["tác hại rượu bia", "uống rượu có hại", "ngộ độc rượu", "bệnh gan do rượu", "lối sống lành mạnh"], ["alcohol health risks", "alcohol misuse", "liver damage alcohol", "drinking limits", "moderate drinking"]),
    "Energy drinks": ("Nước tăng lực và sức khỏe tim mạch", ["nước tăng lực", "tác hại nước tăng lực", "thừa caffeine", "tim đập nhanh mất ngủ", "nước ngọt có gas"], ["energy drinks", "high caffeine drinks", "heart palpitations caffeine", "energy beverage risk"]),
    "Healthy eating": ("Chế độ ăn uống cân bằng", ["ăn uống cân bằng", "dinh dưỡng khoa học", "bữa ăn lành mạnh", "đủ nhóm chất", "sức khỏe lối sống"], ["healthy eating", "balanced diet", "nutritious food", "daily nutrition", "dietary guidelines"]),
    "Hydration": ("Bổ sung đủ nước cho cơ thể", ["uống đủ nước", "nhu cầu nước hàng ngày", "ngừa mất nước", "lợi ích uống nước", "lối sống khỏe"], ["hydration", "drinking water", "daily fluid intake", "adequate hydration", "water balance"]),
    "Minerals": ("Khoáng chất vi lượng thiết yếu", ["khoáng chất", "khoáng chất vi lượng", "bổ sung khoáng chất", "sắt kẽm magie", "dinh dưỡng vi chất"], ["minerals", "essential minerals", "dietary minerals", "trace elements", "mineral deficiency"]),
    "Obesity": ("Bệnh béo phì và kiểm soát cân nặng", ["béo phì", "thừa cân béo phì", "chỉ số BMI cao", "giảm cân ngừa bệnh", "bệnh chuyển hóa"], ["obesity", "overweight", "high BMI", "weight management", "obesity health risks"]),
    "Protein": ("Nhu cầu protein và dinh dưỡng", ["protein", "nhu cầu chất đạm", "đạm động vật thực vật", "phát triển cơ bắp", "dinh dưỡng hàng ngày"], ["protein", "dietary protein", "protein intake", "muscle synthesis", "daily amino acids"]),
    "Sleep hygiene": ("Vệ sinh giấc ngủ và thói quen ngủ tốt", ["vệ sinh giấc ngủ", "thói quen ngủ tốt", "ngủ đủ giấc", "cải thiện giấc ngủ", "chữa khó ngủ"], ["sleep hygiene", "healthy sleep habits", "better sleep", "sleep schedule", "restful sleep"]),
    "Smoking": ("Tác hại thuốc lá và phương pháp cai nghiện", ["tác hại thuốc lá", "hút thuốc lá có hại", "cai thuốc lá", "ung thư phổi", "chất độc nicotine"], ["smoking hazards", "tobacco risks", "smoking cessation", "quit smoking", "lung cancer prevention"]),
    "Vaping": ("Tác hại của thuốc lá điện tử (Vaping)", ["thuốc lá điện tử", "vaping", "tác hại khói vape", "nghiện nicotine vape", "tổn thương phổi do vape"], ["vaping", "e-cigarettes", "vape health risks", "nicotine addiction vaping", "lung injury vaping"]),
    "Vitamins": ("Các loại vitamin và vai trò sức khỏe", ["vitamin", "các loại vitamin", "bổ sung vitamin", "vai trò vitamin", "thiếu hụt vitamin"], ["vitamins", "essential vitamins", "multivitamin", "vitamin benefits", "vitamin deficiency"]),
    "Weight gain": ("Phương pháp tăng cân an toàn", ["tăng cân lành mạnh", "cách tăng cân an toàn", "người gầy khó tăng cân", "dinh dưỡng tăng cân", "thực đơn giàu năng lượng"], ["weight gain healthy", "healthy weight increase", "underweight diet", "calorie surplus"]),
    "Weight loss": ("Phương pháp giảm cân khoa học", ["giảm cân khoa học", "cách giảm cân an toàn", "thâm hụt calo", "đốt mỡ thừa", "chế độ ăn giảm mỡ"], ["weight loss healthy", "safe weight loss", "calorie deficit", "fat loss diet", "healthy slimming"]),

    # Sexual Relationships (11)
    "Anxiety and sex": ("Lo âu và chức năng tình dục", ["lo âu tình dục", "áp lực tâm lý khi quan hệ", "rối loạn chức năng tình dục", "tâm lý phòng the", "sức khỏe sinh lý"], ["anxiety and sex", "sexual performance anxiety", "psychological sexual issues", "intimacy stress"]),
    "Birth control": ("Các biện pháp tránh thai", ["biện pháp tránh thai", "ngừa thai an toàn", "thuốc tránh thai", "bao cao su", "kế hoạch hóa gia đình"], ["birth control", "contraception", "contraceptive methods", "family planning", "safe sex"]),
    "Communication with partner": ("Giao tiếp về tình dục với bạn đời", ["giao tiếp với bạn đời", "chia sẻ tình cảm", "nói chuyện về tình dục", "hòa hợp tình cảm", "mối quan hệ"], ["communication with partner", "intimate communication", "relationship talk", "sexual communication"]),
    "Different sex drives": ("Sự chênh lệch nhu cầu tình dục", ["chênh lệch nhu cầu tình dục", "khác biệt ham muốn", "hòa hợp tình dục", "giải quyết bất đồng", "quan hệ vợ chồng"], ["different sex drives", "libido mismatch", "sexual desire discrepancy", "partner intimacy"]),
    "Emergency contraception": ("Tránh thai khẩn cấp", ["tránh thai khẩn cấp", "thuốc tránh thai khẩn cấp", "uống thuốc ngừa thai sau quan hệ", "hiệu quả ngừa thai", "sản phụ khoa"], ["emergency contraception", "morning after pill", "post-coital contraception", "emergency birth control"]),
    "High libido": ("Nhu cầu tình dục cao", ["nhu cầu tình dục cao", "ham muốn tình dục cao", "tăng ham muốn", "kiểm soát ham muốn", "sinh lý tình dục"], ["high libido", "increased sexual desire", "hypersexuality", "strong sex drive"]),
    "Masturbation": ("Thủ dâm và sức khỏe sinh lý", ["thủ dâm", "tự sướng", "sức khỏe tình dục", "thủ dâm điều độ", "giải tỏa sinh lý"], ["masturbation", "sexual self-pleasure", "masturbation health", "sexual wellness"]),
    "Partner wants more sex": ("Giải quyết bất đồng nhu cầu tình dục", ["đối tác muốn quan hệ nhiều hơn", "bất đồng ham muốn", "thấu hiểu bạn đời", "cân bằng tình dục", "hạnh phúc lứa đôi"], ["partner wants more sex", "sexual frequency mismatch", "couple sexual harmony", "partner expectations"]),
    "Pornography and sexual function": ("Phim ảnh khiêu dâm và chức năng tình dục", ["phim khiêu dâm", "tác hại phim đen", "ảnh hưởng chức năng tình dục", "nghiện phim khiêu dâm", "tâm lý tình dục"], ["pornography effects", "porn and sexual health", "compulsive sexual behavior", "erectile function porn"]),
    "Relationship intimacy": ("Sự thân mật trong mối quan hệ tình cảm", ["thân mật tình cảm", "gắn kết lứa đôi", "xây dựng mối quan hệ", "hòa hợp cảm xúc", "hạnh phúc gia đình"], ["relationship intimacy", "emotional closeness", "couple bonding", "romantic intimacy"]),
    "STI prevention": ("Phòng ngừa bệnh lây truyền qua đường tình dục (STI)", ["phòng ngừa STI", "bệnh lây qua đường tình dục", "quan hệ tình dục an toàn", "dùng bao cao su", "sức khỏe sinh sản"], ["STI prevention", "safe sex practices", "condom use", "sexually transmitted infections", "sexual protection"]),

    # Sexual Health (Women) (19)
    "Breast pain": ("Đau vú (Đau tức ngực ở nữ giới)", ["đau vú", "tức ngực nữ", "đau tuyến vú", "thay đổi nội tiết vú", "phụ khoa"], ["breast pain", "mastalgia", "breast tenderness", "hormonal breast pain"]),
    "Endometriosis": ("Lạc nội mạc tử cung", ["lạc nội mạc tử cung", "đau bụng kinh dữ dội", "hiếm muộn nữ", "viêm nội mạc", "phụ khoa"], ["endometriosis", "pelvic pain endometriosis", "uterine lining", "painful menstruation"]),
    "Heavy periods": ("Kinh nguyệt ra nhiều (Rong kinh)", ["kinh nguyệt nhiều", "rong kinh", "chảy máu kinh nặng", "thiếu máu do rong kinh", "phụ khoa"], ["heavy periods", "menorrhagia", "heavy menstrual bleeding", "prolonged periods"]),
    "Irregular periods": ("Rối loạn kinh nguyệt (Kinh không đều)", ["kinh nguyệt không đều", "rối loạn kinh nguyệt", "chu kỳ kinh thất thường", "nội tiết nữ", "buồng trứng"], ["irregular periods", "abnormal menstruation", "irregular menstrual cycle", "hormonal imbalance female"]),
    "Late period": ("Chậm kinh (Trễ kinh)", ["chậm kinh", "trễ kinh", "chậm kinh thử que", "nguyên nhân trễ kinh", "nội tiết buồng trứng"], ["late period", "delayed menstruation", "missed period pregnancy test", "menstrual delay"]),
    "Light periods": ("Kinh nguyệt ít (Thiểu kinh)", ["kinh nguyệt ít", "thiểu kinh", "lượng máu kinh ít", "mỏng nội mạc tử cung", "phụ khoa"], ["light periods", "hypomenorrhea", "scant menstrual flow", "short periods"]),
    "Menopause": ("Mãn kinh", ["mãn kinh", "tuổi mãn kinh", "hết kinh", "suy giảm estrogen", "nội tiết tố nữ"], ["menopause", "postmenopause", "cessation of menses", "low estrogen", "female aging"]),
    "Menstrual pain": ("Đau bụng kinh (Thống kinh)", ["đau bụng kinh", "thống kinh", "co thắt tử cung khi có kinh", "giảm đau bụng kinh", "kinh nguyệt"], ["menstrual pain", "dysmenorrhea", "period cramps", "menstrual cramps relief"]),
    "Missed period": ("Mất kinh (Vô kinh)", ["mất kinh", "vô kinh", "không có kinh nguyệt", "kiểm tra thai kỳ", "rối loạn buồng trứng"], ["missed period", "amenorrhea", "absence of menstruation", "missed period evaluation"]),
    "Ovarian cyst": ("U nang buồng trứng", ["u nang buồng trứng", "nang buồng trứng", "đau vùng chậu", "xoắn nang buồng trứng", "phụ khoa"], ["ovarian cyst", "ovarian swelling", "pelvic cyst", "ovarian follicle cyst"]),
    "Pain during sex": ("Đau khi quan hệ tình dục ở nữ (Chứng giao hợp đau)", ["đau khi quan hệ nữ", "chứng giao hợp đau", "khô âm đạo đau rát", "co thắt âm đạo", "phụ khoa"], ["pain during sex female", "dyspareunia", "vaginal dryness pain", "painful intercourse"]),
    "PCOS": ("Hội chứng buồng trứng đa nang (PCOS)", ["buồng trứng đa nang", "PCOS", "rối loạn rụng trứng", "kinh nguyệt thưa rậm lông", "kháng insulin nữ"], ["PCOS", "polycystic ovary syndrome", "anovulation", "hyperandrogenism", "irregular ovulation"]),
    "Pelvic pain": ("Đau vùng chậu ở nữ giới", ["đau vùng chậu nữ", "đau bụng dưới nữ", "viêm vùng chậu PID", "đau mạn tính vùng chậu", "phụ khoa"], ["pelvic pain female", "chronic pelvic pain", "lower abdominal pain female", "pelvic inflammatory"]),
    "Perimenopause": ("Tiền mãn kinh", ["tiền mãn kinh", "giai đoạn tiền mãn kinh", "bốc hỏa mất ngủ", "chu kỳ kinh rối loạn", "nội tiết nữ"], ["perimenopause", "menopausal transition", "premenopausal symptoms", "fluctuating hormones"]),
    "Postpartum care": ("Chăm sóc phụ nữ sau sinh", ["chăm sóc sau sinh", "hậu sản", "phục hồi sau sinh", "trầm cảm sau sinh", "sản phụ khoa"], ["postpartum care", "postnatal recovery", "puerperium", "postpartum wellness", "postpartum depression"]),
    "Pregnancy symptoms": ("Dấu hiệu nhận biết mang thai sớm", ["dấu hiệu mang thai sớm", "triệu chứng có thai", "ốm nghén buồn nôn", "trễ kinh thử thai", "sản khoa"], ["pregnancy symptoms", "early pregnancy signs", "morning sickness", "missed period nausea"]),
    "Vaginal discharge": ("Khí hư bất thường (Huyết trắng)", ["khí hư bất thường", "huyết trắng bệnh lý", "khí hư màu vàng xanh", "viêm âm đạo", "phụ khoa"], ["vaginal discharge", "abnormal discharge", "leukorrhea", "vaginitis discharge", "vaginal health"]),
    "Vaginal itching": ("Ngứa âm đạo", ["ngứa âm đạo", "ngứa vùng kín nữ", "nhiễm nấm candida âm đạo", "rát ngứa phụ khoa", "viêm âm hộ"], ["vaginal itching", "vulvar pruritus", "vaginal yeast infection", "candidiasis vaginal", "vaginal irritation"]),
    "Vaginal odor": ("Mùi hôi âm đạo bất thường", ["mùi hôi âm đạo", "vùng kín có mùi hôi", "viêm âm đạo do vi khuẩn", "mùi tanh cá âm đạo", "phụ khoa"], ["vaginal odor", "foul vaginal smell", "bacterial vaginosis", "fishy odor discharge"]),

    # Sexual Health (Men) (18)
    "Erectile dysfunction": ("Rối loạn cương dương", ["rối loạn cương dương", "liệt dương", "yếu sinh lý nam", "khó cương cứng", "nam khoa"], ["erectile dysfunction", "ED", "impotence", "erectile difficulty", "male sexual performance"]),
    "High libido": ("Nhu cầu tình dục cao ở nam giới", ["nhu cầu tình dục cao nam", "ham muốn tình dục nam giới", "tăng ham muốn sinh lý", "kiểm soát ham muốn nam", "nam khoa"], ["high libido male", "increased male sex drive", "male hypersexuality", "strong libido"]),
    "Hydrocele": ("Tràn dịch màng tinh hoàn", ["tràn dịch màng tinh hoàn", "sưng bìu tinh hoàn", "tụ dịch tinh hoàn", "khối u bìu lành tính", "nam khoa"], ["hydrocele", "scrotal fluid accumulation", "scrotal swelling", "testicular fluid"]),
    "Infertility": ("Vô sinh nam", ["vô sinh nam", "hiếm muộn nam", "tinh trùng yếu", "xét nghiệm tinh dịch đồ", "sinh sản nam"], ["male infertility", "low sperm count", "semen analysis", "male fertility evaluation"]),
    "Male fertility": ("Khả năng sinh sản ở nam giới", ["khả năng sinh sản nam", "chất lượng tinh trùng", "tăng cường sinh sản nam", "tinh trùng khỏe mạnh", "nam khoa"], ["male fertility", "sperm quality", "sperm motility", "reproductive health men"]),
    "Morning erections": ("Hiện tượng cương dương buổi sáng", ["cương dương buổi sáng", "hiện tượng chào cờ", "cương dương sinh lý", "chức năng cương dương", "nam khoa"], ["morning erections", "nocturnal penile tumescence", "NPT", "healthy male erection"]),
    "Pain during erection": ("Đau khi cương cứng", ["đau khi cương cứng", "đau dương vật khi cương", "cong dương vật đau", "viêm thể hang", "nam khoa"], ["pain during erection", "painful erection", "priapism symptom", "penile pain erection"]),
    "Penis discharge": ("Chảy mủ hoặc dịch tiết bất thường ở dương vật", ["chảy mủ dương vật", "tiết dịch niệu đạo nam", "viêm niệu đạo mủ", "dấu hiệu bệnh lậu", "nam khoa"], ["penis discharge", "urethral discharge male", "pus from penis", "urethritis male"]),
    "Penis itching": ("Ngứa đầu dương vật", ["ngứa đầu dương vật", "ngứa bao quy đầu", "nhiễm nấm bao quy đầu", "viêm ngứa quy đầu", "nam khoa"], ["penis itching", "itchy glans", "balanitis itching", "penile yeast infection"]),
    "Penis pain": ("Đau dương vật", ["đau dương vật", "đau buốt dương vật", "chấn thương dương vật", "đau niệu đạo nam", "nam khoa"], ["penis pain", "penile pain", "penile trauma", "genital ache male"]),
    "Penis redness": ("Đỏ da và viêm bao quy đầu", ["đỏ bao quy đầu", "viêm quy đầu", "sưng đỏ đầu dương vật", "kích ứng da quy đầu", "nam khoa"], ["penis redness", "balanitis", "inflamed foreskin", "penile erythema"]),
    "Penis swelling": ("Sưng dương vật", ["sưng dương vật", "phù nề dương vật", "sưng bao quy đầu", "nghẹt bao quy đầu", "nam khoa"], ["penis swelling", "penile edema", "swollen foreskin", "paraphimosis"]),
    "Peyronie's disease": ("Bệnh xơ cứng vật hang (Cong dương vật Peyronie)", ["bệnh peyronie", "cong dương vật", "mảng xơ vật hang", "đau khi cương cong", "nam khoa"], ["Peyronie's disease", "penile curvature", "penile plaque", "bent penis"]),
    "Premature ejaculation": ("Xuất tinh sớm", ["xuất tinh sớm", "chống xuất tinh sớm", "thời gian quan hệ ngắn", "kiểm soát xuất tinh", "nam khoa"], ["premature ejaculation", "rapid ejaculation", "PE male", "ejaculatory latency"]),
    "Prostatitis": ("Viêm tuyến tiền liệt", ["viêm tuyến tiền liệt", "đau vùng đáy chậu", "tiểu buốt tiểu rắt nam", "tuyến tiền liệt sưng", "tiết niệu nam khoa"], ["prostatitis", "prostate inflammation", "pelvic discomfort male", "urinary pain male"]),
    "Testicular pain": ("Đau tinh hoàn", ["đau tinh hoàn", "đau tức bìu", "xoắn tinh hoàn cấp", "viêm mào tinh hoàn", "cấp cứu nam khoa"], ["testicular pain", "scrotal pain", "testicular torsion", "epididymitis", "acute scrotum"]),
    "Varicocele": ("Giãn tĩnh mạch thừng tinh", ["giãn tĩnh mạch thừng tinh", "búi tĩnh mạch bìu", "đau tức tinh hoàn âm ỉ", "ảnh hưởng tinh trùng", "nam khoa"], ["varicocele", "scrotal varicose veins", "scrotal dragging pain", "male subfertility varicocele"]),
    "Weak erection": ("Cương cứng yếu", ["cương cứng yếu", "không đủ độ cứng", "xìu sớm khi quan hệ", "yếu sinh lý nam", "nam khoa"], ["weak erection", "soft erection", "poor erectile rigidity", "mild ED"])
}

def main():
    inv_docs = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    print(f"Tổng số tài liệu cần làm giàu: {len(inv_docs)}")

    missing_keys = []
    enriched_records = {}

    for doc_info in inv_docs:
        fn = doc_info["filename"]
        title = doc_info["title"]
        cat = doc_info["category"]

        # Tìm kiếm trong ENRICHMENT_TABLE hoặc TITLE_VI_MAP
        title_vi, kw_vi, kw_en = None, None, None

        if title in TITLE_VI_MAP:
            t_vi, k_vi, k_en = TITLE_VI_MAP[title]
            title_vi, kw_vi, kw_en = t_vi, k_vi, k_en
        elif fn.startswith("heart-blood-pressure-chest-pain"):
            title_vi = "Đau ngực"
            kw_vi = ["đau ngực", "tức ngực", "đau thắt ngực", "khó thở khi đau ngực", "cấp cứu tim mạch"]
            kw_en = ["chest pain", "angina", "chest pressure", "coronary artery", "heart attack warning"]
        elif fn.startswith("heart-blood-pressure-heart-failure"):
            title_vi = "Suy tim"
            kw_vi = ["suy tim", "khó thở khi nằm", "phù chân", "suy tim sung huyết", "tim mạch"]
            kw_en = ["heart failure", "congestive heart failure", "shortness of breath", "fluid retention", "cardiomyopathy"]
        elif fn.startswith("heart-blood-pressure-high-blood-pressure"):
            title_vi = "Tăng huyết áp (Huyết áp cao)"
            kw_vi = ["tăng huyết áp", "huyết áp cao", "đo huyết áp", "chỉ số huyết áp", "tim mạch"]
            kw_en = ["high blood pressure", "hypertension", "blood pressure reading", "systolic", "cardiovascular disease"]
        elif fn.startswith("heart-blood-pressure-low-blood-pressure"):
            title_vi = "Hạ huyết áp (Huyết áp thấp)"
            kw_vi = ["hạ huyết áp", "huyết áp thấp", "tụt huyết áp", "chóng mặt hoa mắt", "huyết áp"]
            kw_en = ["low blood pressure", "hypotension", "dizziness", "fainting", "orthostatic hypotension"]
        elif fn.startswith("eye-ear-mouth-bad-breath"):
            title_vi = "Hôi miệng"
            kw_vi = ["hôi miệng", "hơi thở có mùi", "viêm nha chu", "vệ sinh răng miệng", "nha khoa"]
            kw_en = ["bad breath", "halitosis", "oral hygiene", "gum disease", "tongue bacteria"]
        elif fn.startswith("eye-ear-mouth-dry-eyes"):
            title_vi = "Khô mắt"
            kw_vi = ["khô mắt", "mỏi mắt", "rát mắt", "nước mắt nhân tạo", "nhãn khoa"]
            kw_en = ["dry eyes", "dry eye syndrome", "artificial tears", "eye irritation", "tear film"]
        elif fn.startswith("eye-ear-mouth-ear-infection"):
            title_vi = "Viêm tai (Nhiễm trùng tai)"
            kw_vi = ["viêm tai", "nhiễm trùng tai", "viêm tai giữa", "đau tai", "chảy dịch tai"]
            kw_en = ["ear infection", "otitis media", "ear pain", "ear discharge", "middle ear"]
        elif fn.startswith("eye-ear-mouth-hearing-loss"):
            title_vi = "Suy giảm thính lực (Mất thính lực)"
            kw_vi = ["suy giảm thính lực", "mất thính lực", "nghe kém", "ù tai", "tai mũi họng"]
            kw_en = ["hearing loss", "deafness", "tinnitus", "hearing impairment", "audiology"]
        elif fn.startswith("pregnancy-children-breastfeeding"):
            title_vi = "Nuôi con bằng sữa mẹ"
            kw_vi = ["nuôi con bằng sữa mẹ", "cho con bú", "sữa mẹ", "sản phụ khoa", "dinh dưỡng trẻ sơ sinh"]
            kw_en = ["breastfeeding", "lactation", "nursing", "maternal milk", "infant nutrition"]
        elif fn.startswith("pregnancy-children-child-development"):
            title_vi = "Phát triển ở trẻ em"
            kw_vi = ["phát triển ở trẻ em", "mốc phát triển", "tăng trưởng trẻ em", "nhi khoa", "kỹ năng vận động"]
            kw_en = ["child development", "developmental milestones", "growth milestones", "pediatric development", "motor skills"]
        elif fn.startswith("pregnancy-children-pregnancy-nutrition"):
            title_vi = "Dinh dưỡng khi mang thai"
            kw_vi = ["dinh dưỡng khi mang thai", "ăn uống thai kỳ", "bổ sung axit folic", "vitamin cho bà bầu", "sản khoa"]
            kw_en = ["pregnancy nutrition", "prenatal diet", "folic acid", "prenatal vitamins", "maternal health"]
        elif fn.startswith("pregnancy-children-pregnancy"):
            title_vi = "Mang thai (Thai kỳ)"
            kw_vi = ["mang thai", "thai kỳ", "dấu hiệu mang thai", "khám thai định kỳ", "sản phụ khoa"]
            kw_en = ["pregnancy", "prenatal care", "gestation", "pregnancy symptoms", "obstetrics"]
        elif fn.startswith("pregnancy-children-vaccinations"):
            title_vi = "Tiêm chủng ở trẻ em"
            kw_vi = ["tiêm chủng ở trẻ em", "vắc-xin trẻ em", "lịch tiêm chủng", "phòng ngừa bệnh", "nhi khoa"]
            kw_en = ["childhood vaccinations", "immunization schedule", "vaccines", "pediatric immunization", "disease prevention"]
        elif fn.startswith("urinary-system-blood-in-urine"):
            title_vi = "Tiểu ra máu (Đái máu)"
            kw_vi = ["tiểu ra máu", "đái máu", "nước tiểu có máu", "tiết niệu", "nhiễm trùng đường tiểu"]
            kw_en = ["blood in urine", "hematuria", "urinary tract", "kidney bleeding", "red urine"]
        elif fn.startswith("urinary-system-kidney-infection"):
            title_vi = "Nhiễm trùng thận (Viêm đài bể thận)"
            kw_vi = ["nhiễm trùng thận", "viêm đài bể thận", "đau hông lưng", "sốt rét run", "tiết niệu"]
            kw_en = ["kidney infection", "pyelonephritis", "flank pain", "urinary infection", "renal infection"]
        elif fn.startswith("urinary-system-kidney-stones"):
            title_vi = "Sỏi thận"
            kw_vi = ["sỏi thận", "cơn đau quặn thận", "tiểu buốt", "tán sỏi", "tiết niệu"]
            kw_en = ["kidney stones", "renal calculi", "nephrolithiasis", "renal colic", "urinary stones"]
        elif fn.startswith("urinary-system-overactive-bladder"):
            title_vi = "Bàng quang tăng hoạt (OAB)"
            kw_vi = ["bàng quang tăng hoạt", "tiểu gấp", "tiểu nhiều lần", "tiểu đêm", "tiết niệu"]
            kw_en = ["overactive bladder", "urinary urgency", "frequent urination", "bladder spasms", "nocturia"]
        elif fn.startswith("urinary-system-urinary-incontinence"):
            title_vi = "Tiểu không tự chủ (Són tiểu)"
            kw_vi = ["tiểu không tự chủ", "són tiểu", "mất kiểm soát tiểu tiện", "tiết niệu", "cơ sàn chậu"]
            kw_en = ["urinary incontinence", "bladder leakage", "stress incontinence", "urge incontinence", "pelvic floor"]
        elif fn.startswith("urinary-system-urinary-tract-infection"):
            title_vi = "Nhiễm trùng đường tiết niệu (UTI)"
            kw_vi = ["nhiễm trùng đường tiết niệu", "viêm đường tiết niệu", "tiểu buốt rát", "tiểu rắt", "tiết niệu"]
            kw_en = ["urinary tract infection", "UTI", "burning urination", "dysuria", "bladder infection"]
        elif fn.startswith("nutrition-calcium"):
            title_vi = "Canxi và sức khỏe"
            kw_vi = ["canxi", "bổ sung canxi", "chắc khỏe xương", "loãng xương", "khoáng chất"]
            kw_en = ["calcium", "bone health", "calcium supplement", "osteoporosis prevention", "dietary minerals"]
        elif fn.startswith("nutrition-healthy-eating"):
            title_vi = "Chế độ ăn uống lành mạnh"
            kw_vi = ["chế độ ăn uống lành mạnh", "dinh dưỡng hợp lý", "tháp dinh dưỡng", "chất xơ", "ăn sạch"]
            kw_en = ["healthy eating", "balanced diet", "nutrition guidelines", "dietary fiber", "healthy food choices"]
        elif fn.startswith("nutrition-magnesium"):
            title_vi = "Magiê (Magnesium)"
            kw_vi = ["magiê", "magnesium", "chuột rút cơ bắp", "khoáng chất thiết yếu", "dinh dưỡng"]
            kw_en = ["magnesium", "dietary magnesium", "muscle cramps", "essential minerals", "electrolyte balance"]
        elif fn.startswith("nutrition-vegan-diet"):
            title_vi = "Chế độ ăn thuần chay"
            kw_vi = ["chế độ ăn thuần chay", "ăn chay trường", "nguồn đạm thực vật", "thiếu vitamin B12", "dinh dưỡng"]
            kw_en = ["vegan diet", "plant-based nutrition", "plant protein", "vegan health", "b12 supplementation"]
        elif fn.startswith("nutrition-vegetarian-diet"):
            title_vi = "Chế độ ăn chay"
            kw_vi = ["chế độ ăn chay", "ăn chay", "dinh dưỡng thực vật", "chất sắt", "sức khỏe tim mạch"]
            kw_en = ["vegetarian diet", "vegetarian nutrition", "plant-based diet", "iron absorption", "heart health"]
        elif fn.startswith("nutrition-vitamin-b12"):
            title_vi = "Vitamin B12 (Cobalamin)"
            kw_vi = ["vitamin B12", "vitamin nhóm B", "thiếu máu ác tính", "bổ sung vitamin", "thần kinh dinh dưỡng"]
            kw_en = ["vitamin B12", "cobalamin", "b complex", "pernicious anemia", "neurological health"]
        elif fn.startswith("nutrition-vitamin-d"):
            title_vi = "Vitamin D"
            kw_vi = ["vitamin D", "hấp thụ canxi", "loãng xương", "ánh nắng mặt trời", "miễn dịch"]
            kw_en = ["vitamin D", "sunlight vitamin", "calcium absorption", "bone density", "immune support"]
        elif fn.startswith("medicines-antibiotics"):
            title_vi = "Kháng sinh và lưu ý sử dụng"
            kw_vi = ["kháng sinh", "dùng thuốc kháng sinh", "kháng kháng sinh", "nhiễm khuẩn", "đủ liều"]
            kw_en = ["antibiotics", "antibiotic resistance", "bacterial infection", "prescription antibiotics", "medication compliance"]
        elif fn.startswith("medicines-drug-interactions"):
            title_vi = "Tương tác thuốc"
            kw_vi = ["tương tác thuốc", "uống chung thuốc", "tương tác thức ăn thuốc", "an toàn dùng thuốc", "dược lâm sàng"]
            kw_en = ["drug interactions", "medication interactions", "drug food interaction", "adverse drug reaction", "polypharmacy"]
        elif fn.startswith("medicines-ibuprofen"):
            title_vi = "Thuốc Ibuprofen"
            kw_vi = ["ibuprofen", "thuốc kháng viêm NSAID", "giảm đau hạ sốt", "loét dạ dày", "dược phẩm"]
            kw_en = ["ibuprofen", "NSAID", "anti-inflammatory", "pain relief", "fever reducer"]
        elif fn.startswith("medicines-medicine-safety"):
            title_vi = "An toàn khi dùng thuốc"
            kw_vi = ["an toàn khi dùng thuốc", "bảo quản thuốc", "hạn sử dụng thuốc", "đúng chỉ định", "dược phẩm"]
            kw_en = ["medicine safety", "safe medication use", "drug storage", "expiration date", "dosage guidelines"]
        elif fn.startswith("medicines-missed-dose"):
            title_vi = "Xử trí khi quên uống thuốc"
            kw_vi = ["quên uống thuốc", "bỏ lỡ liều thuốc", "uống bù liều", "hướng dẫn liều", "dược phẩm"]
            kw_en = ["missed dose", "forgot medication", "make-up dose", "dosage schedule", "prescription adherence"]
        elif fn.startswith("medicines-painkillers"):
            title_vi = "Thuốc giảm đau"
            kw_vi = ["thuốc giảm đau", "thuốc giảm đau không kê đơn", "giảm đau nhức", "tác dụng phụ", "dược lâm sàng"]
            kw_en = ["painkillers", "analgesics", "pain relievers", "OTC pain medication", "chronic pain relief"]
        elif fn.startswith("medicines-paracetamol"):
            title_vi = "Thuốc Paracetamol (Acetaminophen)"
            kw_vi = ["paracetamol", "acetaminophen", "hạ sốt giảm đau", "ngộ độc gan do paracetamol", "liều paracetamol"]
            kw_en = ["paracetamol", "acetaminophen", "fever reducer", "pain relief", "liver toxicity risk"]
        elif fn.startswith("medicines-side-effects"):
            title_vi = "Tác dụng phụ của thuốc"
            kw_vi = ["tác dụng phụ của thuốc", "phản ứng có hại ADR", "dị ứng thuốc", "buồn nôn phát ban", "dược lâm sàng"]
            kw_en = ["side effects", "adverse effects", "drug reactions", "allergic reaction to medication", "ADR"]
        elif fn.startswith("mental-health-adhd"):
            title_vi = "Rối loạn tăng động giảm chú ý (ADHD)"
            kw_vi = ["ADHD", "tăng động giảm chú ý", "mất tập trung", "hành vi hiếu động", "tâm thần học"]
            kw_en = ["ADHD", "attention deficit hyperactivity disorder", "inattention", "hyperactivity", "impulsivity"]
        elif fn.startswith("mental-health-anxiety"):
            title_vi = "Rối loạn lo âu"
            kw_vi = ["rối loạn lo âu", "lo âu lan tỏa", "cơn hoảng loạn", "hồi hộp lo sợ", "sức khỏe tâm thần"]
            kw_en = ["anxiety", "generalized anxiety disorder", "panic attack", "excessive worrying", "nervousness"]
        elif fn.startswith("mental-health-autism"):
            title_vi = "Rối loạn phổ tự kỷ (ASD)"
            kw_vi = ["tự kỷ", "rối loạn phổ tự kỷ", "giao tiếp xã hội", "hành vi lặp lại", "tâm bệnh nhi"]
            kw_en = ["autism", "autism spectrum disorder", "ASD", "social communication", "repetitive behaviors"]
        elif fn.startswith("mental-health-depression"):
            title_vi = "Bệnh trầm cảm"
            kw_vi = ["trầm cảm", "rối loạn trầm cảm", "buồn chán mất hứng thú", "mệt mỏi u uất", "sức khỏe tâm thần"]
            kw_en = ["depression", "major depressive disorder", "low mood", "loss of interest", "mental wellness"]
        elif fn.startswith("mental-health-grief"):
            title_vi = "Nỗi đau mất mát và đau buồn"
            kw_vi = ["nỗi đau mất mát", "đau buồn", "mất người thân", "vượt qua mất mát", "tâm lý trị liệu"]
            kw_en = ["grief", "bereavement", "mourning", "loss of loved one", "emotional healing"]
        elif fn.startswith("mental-health-insomnia"):
            title_vi = "Mất ngủ (Rối loạn giấc ngủ)"
            kw_vi = ["mất ngủ", "khó ngủ", "thức giấc nửa đêm", "thiếu ngủ", "giấc ngủ"]
            kw_en = ["insomnia", "sleep disorder", "trouble sleeping", "sleeplessness", "sleep quality"]
        elif fn.startswith("mental-health-ocd"):
            title_vi = "Rối loạn ám ảnh cưỡng chế (OCD)"
            kw_vi = ["OCD", "ám ảnh cưỡng chế", "suy nghĩ ám ảnh", "hành vi cưỡng chế", "sức khỏe tâm thần"]
            kw_en = ["OCD", "obsessive compulsive disorder", "obsessions", "compulsions", "intrusive thoughts"]
        elif fn.startswith("mental-health-ptsd"):
            title_vi = "Rối loạn căng thẳng sau sang chấn (PTSD)"
            kw_vi = ["PTSD", "căng thẳng sau sang chấn", "hồi tưởng sang chấn", "ác mộng chấn thương", "sức khỏe tâm thần"]
            kw_en = ["PTSD", "post traumatic stress disorder", "trauma flashbacks", "nightmares", "psychological trauma"]
        elif fn.startswith("mental-health-stress"):
            title_vi = "Căng thẳng (Stress)"
            kw_vi = ["căng thẳng", "stress", "giảm stress", "áp lực tâm lý", "kiệt sức mệt mỏi"]
            kw_en = ["stress", "chronic stress", "stress management", "mental strain", "burnout"]
        elif fn.startswith("diabetes-hormones-adrenal-disorders"):
            title_vi = "Rối loạn tuyến thượng thận"
            kw_vi = ["rối loạn tuyến thượng thận", "tuyến thượng thận", "suy thượng thận", "cortisol", "nội tiết"]
            kw_en = ["adrenal disorders", "adrenal gland", "adrenal insufficiency", "cortisol", "endocrine disease"]
        elif fn.startswith("diabetes-hormones-hyperglycemia"):
            title_vi = "Tăng đường huyết (Đường huyết cao)"
            kw_vi = ["tăng đường huyết", "đường huyết cao", "đái tháo đường", "khát nước tiểu nhiều", "chỉ số glucose"]
            kw_en = ["hyperglycemia", "high blood sugar", "high blood glucose", "diabetes symptom", "glucose spike"]
        elif fn.startswith("diabetes-hormones-hyperthyroidism"):
            title_vi = "Cường giáp (Tuyến giáp hoạt động quá mức)"
            kw_vi = ["cường giáp", "tuyến giáp hoạt động quá mức", "tim đập nhanh sụt cân", "bướu giáp", "nội tiết"]
            kw_en = ["hyperthyroidism", "overactive thyroid", "rapid heart rate", "weight loss", "thyroid hormone"]
        elif fn.startswith("diabetes-hormones-hypoglycemia"):
            title_vi = "Hạ đường huyết (Đường huyết thấp)"
            kw_vi = ["hạ đường huyết", "đường huyết thấp", "tụt đường huyết", "run tay đói lả", "glucose máu thấp"]
            kw_en = ["hypoglycemia", "low blood sugar", "low blood glucose", "shakiness sweating", "glucose drop"]
        elif fn.startswith("diabetes-hormones-hypothyroidism"):
            title_vi = "Suy giáp (Tuyến giáp hoạt động kém)"
            kw_vi = ["suy giáp", "tuyến giáp hoạt động kém", "mệt mỏi tăng cân sợ lạnh", "nội tiết", "hormone tuyến giáp"]
            kw_en = ["hypothyroidism", "underactive thyroid", "fatigue weight gain", "cold sensitivity", "thyroid deficiency"]
        elif fn.startswith("diabetes-hormones-insulin-resistance"):
            title_vi = "Kháng insulin"
            kw_vi = ["kháng insulin", "nhạy cảm insulin", "hội chứng chuyển hóa", "nguy cơ tiểu đường", "nội tiết"]
            kw_en = ["insulin resistance", "metabolic syndrome", "pre-diabetes risk", "hyperinsulinemia", "glucose uptake"]
        elif fn.startswith("diabetes-hormones-prediabetes"):
            title_vi = "Tiền đái tháo đường (Tiền tiểu đường)"
            kw_vi = ["tiền đái tháo đường", "tiền tiểu đường", "rối loạn dung nạp glucose", "phòng ngừa tiểu đường", "đường huyết lúc đói"]
            kw_en = ["prediabetes", "borderline diabetes", "impaired glucose tolerance", "diabetes prevention", "fasting glucose"]
        elif fn.startswith("diabetes-hormones-thyroid-disease"):
            title_vi = "Bệnh lý tuyến giáp"
            kw_vi = ["bệnh lý tuyến giáp", "tuyến giáp", "bướu cổ", "nhân tuyến giáp", "nội tiết"]
            kw_en = ["thyroid disease", "thyroid disorders", "goiter", "thyroid nodules", "endocrine gland"]
        elif fn.startswith("diabetes-hormones-type-1-diabetes"):
            title_vi = "Đái tháo đường tuýp 1 (Tiểu đường tuýp 1)"
            kw_vi = ["đái tháo đường tuýp 1", "tiểu đường tuýp 1", "tiêm insulin", "thiếu hụt insulin", "đái tháo đường tự miễn"]
            kw_en = ["type 1 diabetes", "juvenile diabetes", "insulin dependent", "insulin therapy", "autoimmune diabetes"]
        elif fn.startswith("diabetes-hormones-type-2-diabetes"):
            title_vi = "Đái tháo đường tuýp 2 (Tiểu đường tuýp 2)"
            kw_vi = ["đái tháo đường tuýp 2", "tiểu đường tuýp 2", "kiểm soát đường huyết", "hạ đường huyết ăn uống", "nội tiết"]
            kw_en = ["type 2 diabetes", "adult onset diabetes", "blood sugar control", "metformin", "lifestyle management"]

        if not title_vi:
            missing_keys.append((fn, title, cat))
        else:
            cat_vi = CATEGORY_VI.get(cat, cat)
            enriched_records[fn] = {
                "title_en": title,
                "title_vi": title_vi,
                "category_en": cat,
                "category_vi": cat_vi,
                "keywords_en": kw_en,
                "keywords_vi": kw_vi
            }

    print(f"Khớp thành công: {len(enriched_records)} / {len(inv_docs)}")
    if missing_keys:
        print(f"Còn thiếu {len(missing_keys)} tài liệu chưa khớp:")
        for m in missing_keys[:10]:
            print("  ", m)
    else:
        print("TẤT CẢ 241 TÀI LIỆU ĐÃ ĐƯỢC ÁNH XẠ CHUẨN XÁC 100%!")
        OUTPUT_PATH.write_text(json.dumps(enriched_records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã lưu mapping hoàn chỉnh tại: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
