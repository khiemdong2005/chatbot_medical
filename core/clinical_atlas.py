"""
================================================================================
🩺 MEDIMIND CLINICAL ATLAS - THƯ VIỆN ĐỐI CHIẾU HÌNH THÁI Y KHOA CHUẨN HÓA
================================================================================
Mục đích:
  - Cung cấp cơ sở dữ liệu ảnh mẫu lâm sàng đối chiếu trực quan (Visual Reference Gallery).
  - Tự động nhận diện bệnh lý da liễu qua từ khóa tiếng Việt / tiếng Anh và bốc đúng 3 ảnh mẫu.
  - Hỗ trợ bệnh nhân quan sát, so sánh hình thái tổn thương (mụn nước, dát đỏ, đóng vảy).
================================================================================
"""

import re
import unicodedata
from typing import Dict, Any, List, Optional

def _normalize_vietnamese(text: str) -> str:
    """Chuyển chuỗi tiếng Việt thành chữ thường không dấu để so khớp linh hoạt."""
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return text

CLINICAL_ATLAS: Dict[str, Dict[str, Any]] = {
    "zona_than_kinh": {
        "id": "zona_than_kinh",
        "disease_name": "Zona thần kinh (Herpes Zoster / Giời leo)",
        "specialist": "Da liễu / Truyền nhiễm",
        "description": "Bệnh do tái hoạt động của virus Varicella-Zoster, đặc trưng bởi các mụn nước căng bóng mọc thành chùm dọc theo đường đi của dây thần kinh (thường chỉ xuất hiện ở 1 bên cơ thể: ngực, liên sườn, cổ hoặc mặt) kèm cảm giác bỏng rát, giật buốt.",
        "keywords": ["zona", "herpes zoster", "gioi leo", "giay leo", "mun nuoc moc chum", "mun nuoc 1 ben", "bong rat mot ben"],
        "images": [
            {
                "url": "/static/images/clinical_atlas/zona_1.jpg",
                "caption": "Mụn nước căng bóng mọc thành chùm phân bố dọc theo dây thần kinh",
                "stage": "Giai đoạn toàn phát",
                "features": "Chùm mụn nước mọc trên nền da đỏ tươi, giới hạn rõ ở một nửa cơ thể"
            },
            {
                "url": "/static/images/clinical_atlas/zona_2.jpg",
                "caption": "Tổn thương ban đầu dạng dát đỏ sưng nề kèm đau rát",
                "stage": "Giai đoạn khởi phát",
                "features": "Vùng da đỏ rát, châm chích buốt nhói trước khi mụn nước trồi lên"
            },
            {
                "url": "/static/images/clinical_atlas/zona_3.jpg",
                "caption": "Mụn nước bắt đầu vỡ, khô se và đóng mài vảy tiết",
                "stage": "Giai đoạn thoái triển / Đóng mài",
                "features": "Vảy tiết màu nâu vàng, cần giữ vệ sinh sạch để tránh nhiễm khuẩn thứ phát"
            }
        ]
    },
    "viem_da_co_dia": {
        "id": "viem_da_co_dia",
        "disease_name": "Viêm da cơ địa / Chàm (Atopic Eczema)",
        "specialist": "Da liễu",
        "description": "Bệnh da viêm mạn tính tái phát, biểu hiện bằng các đám đỏ ngứa dữ dội, da khô ráp, nứt nẻ, có mụn nước nhỏ li ti ở các nếp gấp (khuỷu tay, khoeo chân, cổ) hoặc bàn tay.",
        "keywords": ["viem da co dia", "cham", "eczema", "ngua da", "kho da nut ne", "atopic dermatitis", "da nut ne man tinh"],
        "images": [
            {
                "url": "/static/images/clinical_atlas/eczema_1.jpg",
                "caption": "Mảng hồng ban ranh giới không rõ, da khô tróc vảy mịn",
                "stage": "Giai đoạn bán cấp",
                "features": "Đám đỏ trên da kèm các vảy da nhỏ li ti, cảm giác ngứa tăng về đêm"
            },
            {
                "url": "/static/images/clinical_atlas/eczema_2.jpg",
                "caption": "Tổn thương viêm đỏ, rát ngứa ở nếp gấp khuỷu tay",
                "stage": "Vị trí điển hình nếp gấp",
                "features": "Đặc trưng xuất hiện đối xứng ở các vùng nếp lằn khớp và cổ"
            },
            {
                "url": "/static/images/clinical_atlas/eczema_3.jpg",
                "caption": "Da dày cộm, hằn cổ trâu (lichen hóa) do cào gãi kéo dài",
                "stage": "Giai đoạn mạn tính",
                "features": "Bề mặt da thô ráp, sẫm màu do phản ứng gãi mạn tính"
            }
        ]
    },
    "me_day_di_ung": {
        "id": "me_day_di_ung",
        "disease_name": "Mề đay dị ứng (Urticaria / Hives)",
        "specialist": "Dị ứng - Miễn dịch lâm sàng / Da liễu",
        "description": "Phản ứng mạch máu ở trung bì da, đặc trưng bởi các mảng sẩn phù (phù nề) gồ cao màu hồng hoặc trắng, ngứa ngáy dữ dội, xuất hiện nhanh và lặn trong vòng vài giờ không để lại dấu vết.",
        "keywords": ["me day", "urticaria", "hives", "san phu", "di ung da", "noi man do", "ngua phong", "noi cuc man"],
        "images": [
            {
                "url": "/static/images/clinical_atlas/meday_1.jpg",
                "caption": "Các mảng sẩn phù màu hồng nhạt gồ cao trên mặt da",
                "stage": "Tổn thương sẩn phù điển hình",
                "features": "Ranh giới rõ nét, trung tâm phù nề nhạt màu, viền ngoài đỏ hồng"
            },
            {
                "url": "/static/images/clinical_atlas/meday_2.jpg",
                "caption": "Ban mề đay rải rác khắp vùng cẳng tay và thân mình",
                "stage": "Giai đoạn bùng phát rải rác",
                "features": "Ngứa dữ dội, càng gãi tổn thương càng phù nề và lan rộng"
            },
            {
                "url": "/static/images/clinical_atlas/meday_3.jpg",
                "caption": "Mảng phù hợp lưu lớn sau tiếp xúc tác nhân dị ứng",
                "stage": "Mề đay cấp tính",
                "features": "Các nốt sẩn liên kết thành từng mảng lớn, thường tự lặn sau 24 giờ"
            }
        ]
    },
    "nam_da_hac_lao": {
        "id": "nam_da_hac_lao",
        "disease_name": "Nấm da / Hắc lào (Tinea Corporis / Ringworm)",
        "specialist": "Da liễu",
        "description": "Nhiễm nấm sợi nông trên bề mặt da, biểu hiện bằng các đám tròn hoặc bầu dục hình đồng tiền, rìa bờ gồ cao có mụn nước nhỏ li ti, trung tâm có xu hướng lành dần, ngứa nhiều khi đổ mồ hôi.",
        "keywords": ["nam da", "hac lao", "lac dong tien", "tinea", "ringworm", "hinh dong tien", "nam ben", "nam than"],
        "images": [
            {
                "url": "/static/images/clinical_atlas/namda_1.jpg",
                "caption": "Mảng tròn hình đồng tiền có bờ viền nổi rõ mụn nước nhỏ",
                "stage": "Tổn thương điển hình",
                "features": "Rìa tổn thương gồ cao, nhiều mụn nước li ti, trung tâm nhạt màu"
            },
            {
                "url": "/static/images/clinical_atlas/namda_2.jpg",
                "caption": "Mảng nấm da vùng bẹn hoặc đùi lan rộng khi thời tiết ẩm",
                "stage": "Nấm da lan rộng",
                "features": "Bờ viền hình vòng cung uốn lượn, ngứa rát nhiều khi vận động"
            },
            {
                "url": "/static/images/clinical_atlas/namda_3.jpg",
                "caption": "Tổn thương nhiều vòng tròn đồng tâm liên kết nhau",
                "stage": "Giai đoạn mạn tính",
                "features": "Cần dùng thuốc kháng nấm bôi theo chỉ định bác sĩ, giữ vùng da khô ráo"
            }
        ]
    },
    "thuy_dau": {
        "id": "thuy_dau",
        "disease_name": "Thủy đậu / Trái rạ (Varicella / Chickenpox)",
        "specialist": "Truyền nhiễm / Da liễu",
        "description": "Bệnh truyền nhiễm cấp tính do virus Varicella-Zoster, nổi tiếng với phát ban dạng phỏng nước hình 'giọt sương trên cánh hoa hồng', mọc rải rác khắp người qua nhiều đợt liên tiếp kèm sốt nhẹ.",
        "keywords": ["thuy dau", "trai ra", "chickenpox", "varicella", "bong nuoc giot suong", "phat ban sot"],
        "images": [
            {
                "url": "/static/images/clinical_atlas/thuydau_1.jpg",
                "caption": "Mụn nước hình giọt sương trong suốt trên nền dát đỏ",
                "stage": "Mụn nước mới mọc",
                "features": "Mụn nước trong veo, vỏ mỏng, rất dễ vỡ nếu cào gãi"
            },
            {
                "url": "/static/images/clinical_atlas/thuydau_2.jpg",
                "caption": "Tổn thương đa lứa tuổi rải rác trên cánh tay",
                "stage": "Tổn thương đa thế hệ",
                "features": "Vừa có nốt dát đỏ mới nhú, mụn nước căng và nốt đã khô đóng mài"
            },
            {
                "url": "/static/images/clinical_atlas/thuydau_3.jpg",
                "caption": "Mụn nước lõm ở giữa và khô thành vảy tiết sẫm màu",
                "stage": "Giai đoạn đóng vảy lành bệnh",
                "features": "Không cạy vảy sớm để tránh để lại sẹo lõm vĩnh viễn"
            }
        ]
    },
    "mun_trung_ca": {
        "id": "mun_trung_ca",
        "disease_name": "Mụn trứng cá viêm / Bọc (Acne Vulgaris)",
        "specialist": "Da liễu",
        "description": "Tình trạng viêm nang lông tuyến bã nhờn, biểu hiện qua sẩn đỏ, mụn mủ đầu trắng, mụn bọc nang sâu sưng tấy đau nhức tại vùng mặt, lưng hoặc ngực.",
        "keywords": ["mun trung ca", "mun boc", "mun viem", "mun mu", "acne", "mun dau den", "mun dau trang"],
        "images": [
            {
                "url": "/static/images/clinical_atlas/acne_1.jpg",
                "caption": "Sẩn viêm đỏ và mụn mủ phân bố ở vùng má",
                "stage": "Mụn trứng cá viêm mức độ vừa",
                "features": "Nhiều sẩn đỏ sưng nề kèm các cồi mụn bít tắc lỗ chân lông"
            },
            {
                "url": "/static/images/clinical_atlas/acne_2.jpg",
                "caption": "Mụn mủ đầu trắng sưng tấy chứa dịch mủ vô khuẩn",
                "stage": "Mụn mủ viêm cấp tính",
                "features": "Tuyệt đối không tự ý dùng tay nặn gây viêm nhiễm lan tỏa"
            },
            {
                "url": "/static/images/clinical_atlas/acne_3.jpg",
                "caption": "Mụn bọc dạng nang sâu sưng to đau nhức (Cystic Acne)",
                "stage": "Mụn trứng cá nặng dạng nang",
                "features": "Tổn thương nằm sâu dưới da, cần bác sĩ da liễu kê đơn điều trị chuyên sâu"
            }
        ]
    }
}

def match_clinical_atlas(query: str, extra_context: str = "") -> Optional[Dict[str, Any]]:
    """
    So khớp văn bản truy vấn hoặc chẩn đoán lâm sàng với Thư viện Đối chiếu.
    Nếu tìm thấy bệnh lý phù hợp, trả về cấu trúc gồm 3 ảnh mẫu kèm thông tin chi tiết.
    """
    combined = f"{query} {extra_context}"
    normalized = _normalize_vietnamese(combined)

    best_match = None
    best_score = 0

    for disease_id, data in CLINICAL_ATLAS.items():
        score = 0
        for kw in data["keywords"]:
            norm_kw = _normalize_vietnamese(kw)
            if norm_kw in normalized:
                score += len(norm_kw)
                
        if score > best_score:
            best_score = score
            best_match = data

    if best_match and best_score > 3:
        return {
            "disease_id": best_match["id"],
            "disease_name": best_match["disease_name"],
            "specialist": best_match["specialist"],
            "description": best_match["description"],
            "reference_images": best_match["images"]
        }
    return None
