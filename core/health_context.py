"""Bounded, user-declared context for one chat; never an official medical record."""
import re

TEXT_FIELDS = {"allergies", "medications", "conditions"}
CHOICES = {
    "gender": {"female", "male", "other", "unspecified"},
    "pregnancy": {"pregnant", "breastfeeding", "not_pregnant", "unspecified"},
}


def validate_health_context(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Thông tin sức khỏe phải là một đối tượng hợp lệ.")
    if set(value) - (TEXT_FIELDS | set(CHOICES) | {"age"}):
        raise ValueError("Thông tin sức khỏe chứa trường chưa được hỗ trợ.")
    result = {}
    if value.get("age") not in (None, ""):
        age = value["age"]
        if type(age) is not int or not 0 <= age <= 120:
            raise ValueError("Tuổi phải là số nguyên từ 0 đến 120.")
        result["age"] = age
    for key, allowed in CHOICES.items():
        item = value.get(key, "unspecified")
        if not isinstance(item, str) or item not in allowed:
            raise ValueError("Lựa chọn thông tin sức khỏe không hợp lệ.")
        if item != "unspecified":
            result[key] = item
    for key in TEXT_FIELDS:
        text = value.get(key, "")
        if not isinstance(text, str) or len(text) > 600:
            raise ValueError("Mỗi mục dị ứng, thuốc hoặc bệnh nền tối đa 600 ký tự.")
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
            raise ValueError("Thông tin sức khỏe chứa ký tự không hợp lệ.")
        if text.strip():
            result[key] = text.strip()
    return result


def validate_chat_request(data):
    """Reject malformed input before any session or provider side effects."""
    if not isinstance(data, dict):
        raise ValueError("Nội dung yêu cầu phải là đối tượng JSON.")
    message = data.get("message", "")
    if not isinstance(message, str) or len(message) > 2000:
        raise ValueError("Tin nhắn phải là văn bản, tối đa 2.000 ký tự.")
    history = data.get("history", [])
    if not isinstance(history, list) or len(history) > 100:
        raise ValueError("Lịch sử hội thoại không hợp lệ.")
    clean_history = []
    for turn in history:
        if (not isinstance(turn, dict) or turn.get("role") not in ("user", "assistant")
                or not isinstance(turn.get("content"), str) or len(turn["content"]) > 12000):
            raise ValueError("Mỗi lượt lịch sử phải là tin nhắn người dùng hoặc trợ lý hợp lệ.")
        clean_history.append({"role": turn["role"], "content": turn["content"]})
    image = data.get("image")
    if image is not None and not isinstance(image, str):
        raise ValueError("Ảnh đính kèm không hợp lệ.")
    lang = data.get("lang", "vi")
    if lang not in ("vi", "en"):
        raise ValueError("Ngôn ngữ chưa được hỗ trợ.")
    cid = data.get("conversation_id")
    if cid is not None and (not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", cid)):
        raise ValueError("Mã cuộc trò chuyện không hợp lệ.")
    return {"message": message.strip(), "history": clean_history[-20:], "image": image,
            "lang": lang, "conversation_id": cid,
            "health_context": validate_health_context(data.get("health_context"))}
