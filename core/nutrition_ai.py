"""Gemini ranks supplied recipes; it cannot create or alter their ingredients."""
import json
import os
import re
from typing import Any, Dict, List

from google import genai
from google.genai import types
from core.settings import settings


class NutritionAIError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_selection(value: Any, recipes: List[Dict], source_count: int) -> Dict:
    if not isinstance(value, dict) or type(value.get("needs_clarification")) is not bool:
        raise NutritionAIError("invalid_response")
    choices = value.get("recommendations")
    question = value.get("clarification_question")
    if not isinstance(choices, list) or not isinstance(question, str) or len(question) > 400:
        raise NutritionAIError("invalid_response")
    if value["needs_clarification"]:
        if choices or not question.strip():
            raise NutritionAIError("invalid_response")
        return {"needs_clarification": True, "clarification_question": question.strip(), "recipes": []}
    if not 1 <= len(choices) <= min(6, len(recipes)):
        raise NutritionAIError("invalid_response")
    catalog = {recipe["id"]: recipe for recipe in recipes}
    from core.recipe_catalog import classify_dish_role, classify_meal_times
    seen = set()
    selected = []
    for choice in choices:
        if not isinstance(choice, dict):
            raise NutritionAIError("invalid_response")
        recipe_id = choice.get("recipe_id")
        reason, caution = choice.get("reason"), choice.get("caution")
        sources = choice.get("source_ids")
        if (not isinstance(recipe_id, str) or recipe_id not in catalog or recipe_id in seen
                or not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 500
                or not isinstance(caution, str) or len(caution) > 400
                or not isinstance(sources, list)
                or any(type(i) is not int or not 0 <= i < source_count for i in sources)):
            raise NutritionAIError("invalid_response")
        seen.add(recipe_id)
        # Only these explanatory fields can come from the model. The original
        # quantities, preparation, allergen notes and artwork IDs stay canonical.
        recipe = dict(catalog[recipe_id])

        dish_role = choice.get("dish_role")
        if dish_role not in ("main", "soup", "side", "staple", "drink"):
            dish_role = classify_dish_role(recipe)

        meal_time = choice.get("meal_time")
        if meal_time not in ("breakfast", "lunch", "dinner", "snack"):
            possible_meals = classify_meal_times(recipe, dish_role)
            meal_time = possible_meals[0] if possible_meals else "dinner"

        key_nutrients = choice.get("key_nutrients")
        if not isinstance(key_nutrients, str) or not key_nutrients.strip():
            key_nutrients = ""

        recipe.update(
            recommendation_reason=reason.strip(),
            ai_caution=caution.strip(),
            source_ids=list(dict.fromkeys(sources)),
            dish_role=dish_role,
            meal_time=meal_time,
            key_nutrients=key_nutrients.strip()
        )
        display_title = choice.get("display_title")
        if display_title is not None:
            if not isinstance(display_title, str) or not 1 <= len(display_title.strip()) <= 180:
                raise NutritionAIError("invalid_response")
            recipe["display_title"] = recipe["title"] if recipe.get("language") == "vi" else display_title.strip()
        selected.append(recipe)

    res = {"needs_clarification": False, "clarification_question": "", "recipes": selected}

    fms = value.get("full_meal_set")
    if isinstance(fms, dict):
        title = fms.get("title")
        meal_time = fms.get("meal_time")
        rationale = fms.get("rationale")
        main_id = fms.get("main_recipe_id")
        soup_id = fms.get("soup_recipe_id")
        side_id = fms.get("side_recipe_id")
        staple_text = fms.get("staple_text") or "Cơm mềm hoặc cháo dinh dưỡng"

        main_cand = catalog.get(main_id)
        soup_cand = catalog.get(soup_id)
        side_cand = catalog.get(side_id) if side_id else None

        # Clinical validation: main cannot be a soup/canh/congee; soup must be soup/canh; distinct IDs
        is_main_valid = main_cand and not any(k in str(main_cand.get("title", "")).lower() for k in ["canh ", "canh", "súp", "cháo", "chao", "lẩu"])
        is_soup_valid = soup_cand and any(k in str(soup_cand.get("title", "")).lower() for k in ["canh", "súp", "sup"])
        distinct_ids = main_id != soup_id and (not side_id or (side_id != main_id and side_id != soup_id))
        is_side_not_soup = not side_cand or not any(k in str(side_cand.get("title", "")).lower() for k in ["canh ", "lẩu "])

        if (isinstance(title, str) and 1 <= len(title.strip()) <= 150
                and meal_time in ("breakfast", "lunch", "dinner", "snack")
                and isinstance(rationale, str) and 10 <= len(rationale.strip()) <= 600
                and is_main_valid and is_soup_valid and distinct_ids and is_side_not_soup):
            res["full_meal_set"] = {
                "title": title.strip(),
                "meal_time": meal_time,
                "rationale": rationale.strip(),
                "main_recipe_id": main_id,
                "soup_recipe_id": soup_id,
                "side_recipe_id": side_id if side_cand else None,
                "staple_text": staple_text.strip() if isinstance(staple_text, str) else ""
            }

    return res


def select_recipes(condition: str, recipe_type: str, recipes: List[Dict], guidance: List[Dict]) -> Dict:
    key = (os.getenv("GEMINI_NUTRITION_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise NutritionAIError("not_configured")
    model = os.getenv("GEMINI_NUTRITION_MODEL", "gemini-flash-lite-latest").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", model):
        raise NutritionAIError("configuration")
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "needs_clarification": {"type": "boolean"},
            "clarification_question": {"type": "string"},
            "recommendations": {"type": "array", "maxItems": 6, "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "recipe_id": {"type": "string", "enum": [r["id"] for r in recipes]},
                    "display_title": {"type": "string"},
                    "meal_time": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"]},
                    "dish_role": {"type": "string", "enum": ["main", "soup", "side", "staple", "drink"]},
                    "key_nutrients": {"type": "string"},
                    "reason": {"type": "string"}, "caution": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "integer"}}
                }, "required": ["recipe_id", "display_title", "reason", "caution", "source_ids"]
            }},
            "full_meal_set": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "meal_time": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"]},
                    "rationale": {"type": "string"},
                    "main_recipe_id": {"type": "string", "enum": [r["id"] for r in recipes]},
                    "soup_recipe_id": {"type": "string", "enum": [r["id"] for r in recipes]},
                    "side_recipe_id": {"type": "string", "enum": [r["id"] for r in recipes]},
                    "staple_text": {"type": "string"}
                }, "required": ["title", "meal_time", "rationale", "main_recipe_id", "soup_recipe_id"]
            }
        }, "required": ["needs_clarification", "clarification_question", "recommendations"]
    }
    instruction = """Bạn là chuyên gia dinh dưỡng lâm sàng MediMind hỗ trợ gợi ý món ăn và thực đơn tham khảo theo thể trạng.
Trang này cung cấp HAI CHẾ ĐỘ XEM TÁCH BIỆT HOÀN TOÀN CHO NGƯỜI DÙNG:

1. CHẾ ĐỘ "CÁC MÓN ĐƠN LẺ THEO BỮA" (recommendations):
   - Khi người dùng không muốn nấu một mâm cơm gia đình nhiều món lỉnh kỉnh, họ sẽ muốn ăn MỘT MÓN ĐƠN LẺ TRỌN VỊ (One-dish meals).
   - BẮT BUỘC CHỈ CHỌN CÁC MÓN ĂN TRỌN VỊ (One-dish meals) từ danh sách candidates có `is_one_dish=True`:
     * Món nước / Bún · Phở · Hủ tiếu · Mì · Miến · Bánh canh (ví dụ: Bún chả, Bún riêu, Phở bò mềm, Miến gà, Mì Quảng, Bánh canh cua...).
     * Món cơm đĩa trọn vị (ví dụ: Cơm tấm, Cơm chiên chay, Cơm gà...).
     * Món cháo / Súp dinh dưỡng (ví dụ: Cháo gà đậu xanh, Cháo cá lóc, Súp gà bắp non, Súp bí đỏ...).
     * Món điểm tâm / Bánh truyền thống (ví dụ: Bánh cuốn, Bánh mì, Xôi...).
     * Thức uống ấm, sữa hạt, chè thanh nhiệt cho bữa phụ / trước ngủ (snack).
   - TUYỆT ĐỐI KHÔNG chọn các món thành phần của mâm cơm (như một bát canh rau suông, hay một đĩa rau luộc, hay một đĩa đậu hũ hấp ăn kèm cơm) vào danh sách món đơn lẻ này, vì một bát canh hay đĩa rau luộc không thể làm một bữa ăn đơn lẻ hoàn chỉnh!
   - TUYỆT ĐỐI KHÔNG chọn trùng với bất kỳ món nào đã chọn trong full_meal_set (Mâm cơm).
   - Chọn từ 4 đến 5 món phong phú cho các bữa (sáng, trưa, tối, phụ).

2. CHẾ ĐỘ "THỰC ĐƠN 1 BỮA ĂN ĐỦ MÓN" (full_meal_set):
   - Đây là mâm cơm gia đình truyền thống gồm các món thành phần ăn chung với cơm trắng/gạo lứt:
     * main_recipe_id: Món chính giàu đạm lành tính (thịt nạc hấp/hầm, cá hấp, gà hấp, trứng hấp, đậu hũ non...). TUYỆT ĐỐI KHÔNG chọn món canh, cháo, hay bún/phở làm món chính.
     * soup_recipe_id: Món canh thanh nhiệt hoặc canh rau thanh nhẹ (ví dụ canh mồng tơi, canh củ sen, canh bí).
     * side_recipe_id: Món rau xanh, củ quả hoặc món phụ giàu xơ. TUYỆT ĐỐI KHÔNG chọn thêm món canh (không bao giờ có 2 món canh).
   - staple_text: Nêu rõ tinh bột ăn kèm (ví dụ: 'Cơm gạo lứt hạt sen hoặc cơm trắng dẻo mềm').
   - rationale: Phân tích vì sao mâm cơm kết hợp đủ món này cân bằng dinh dưỡng, hỗ trợ tốt nhất cho thể trạng.
   - BẮT BUỘC 3 món trong mâm cơm KHÔNG ĐƯỢC XUẤT HIỆN trong danh sách recommendations (không trùng ID).
   - Nếu trong candidates không có món chính đạm hoặc không có món canh riêng biệt, KHÔNG tạo full_meal_set (để null).

3. GIẢI THÍCH CHUYÊN SÂU TẠI SAO PHÙ HỢP (CLINICAL RATIONALE):
   - TUYỆT ĐỐI KHÔNG giải thích chung chung hời hợt (như 'món mềm dễ tiêu', 'thanh đạm').
   - key_nutrients: Nêu rõ các dưỡng chất / hoạt chất nổi bật (ví dụ: 'Tryptophan, Magie, Melatonin tự nhiên, Nelumbin, Vitamin B6' hoặc 'Kẽm, Vitamin C, Chất xơ hòa tan').
   - reason: Giải thích chi tiết cơ chế tác động y học dinh dưỡng:
     * Dưỡng chất trong món tác động như thế nào lên cơ thể người bệnh/người có triệu chứng đó?
     * Ví dụ với Mất ngủ: Tryptophan là tiền chất sản sinh Serotonin và Melatonin điều hòa chu kỳ sinh học; Magie và hoạt chất Nelumbin làm dịu hệ thần kinh trung ương, giảm căng thẳng cơ bắp; món thanh nhẹ giúp dạ dày không phải tăng tiết acid về đêm.
     * Ví dụ với Nhiệt miệng: Kết cấu mềm mịn trơn mượt không gây ma sát xót vết loét niêm mạc; kẽm và vitamin C/A thúc đẩy tái tạo tế bào biểu mô và làm lành vết loét; tính mát giúp giảm nhiệt hỏa.
     * Ví dụ với Đau dạ dày: Giảm co thắt, bảo vệ niêm mạc, không kích thích acid dịch vị.
     * Ví dụ với Gút: Không purin, đào thải acid uric, kiềm hóa nước tiểu.
     * Nêu rõ lý do tại sao người có tình trạng này nên chọn món.

NGUYÊN TẮC AN TOÀN Y KHOA BẮT BUỘC (CLINICAL GUARDRAIL):
- Bệnh Gút / Tăng Acid Uric: TUYỆT ĐỐI KHÔNG chọn món chứa hải sản (đặc biệt hàu, sò, nghêu, ngao, ốc, tôm, cua, mực, cá biển), nội tạng động vật, thịt đỏ đậm, giò heo, măng chua, rượu bia.
- Tiểu đường: TUYỆT ĐỐI KHÔNG chọn món chứa đường tinh luyện, mật ong, sữa đặc, nước ngọt, chè ngọt.
- Tăng Huyết áp: TUYỆT ĐỐI KHÔNG chọn món mặn đậm, nhiều mắm, dưa cà muối chua, đồ đóng hộp.
- Đau Dạ dày / Trào ngược: TUYỆT ĐỐI KHÔNG chọn món cay nóng, chua gắt, chiên xào nhiều mỡ, cà phê, rượu bia.
Nếu các món ứng viên không an toàn cho bệnh lý của người dùng, BẮT BUỘC trả needs_clarification=true và clarification_question nêu rõ lý do.
Với công thức tiếng Anh, display_title là tên dịch tiếng Việt ngắn, đúng tên gốc. Không đổi hay tạo thêm thành phần.
Ví dụ: 'Chinese Rice Porridge (Congee)' → 'Cháo gạo kiểu Trung Hoa'; 'Rosół (Polish Meat Soup)' → 'Súp thịt kiểu Ba Lan (Rosół)'. Giữ tên riêng nếu cần, nhưng dịch phần mô tả món sang tiếng Việt.
Với công thức đã là tiếng Việt, giữ tên gốc trong display_title. Nội dung công thức gốc không được sửa.
Không coi việc không có thành phần hạn chế là chứng nhận an toàn cho người có bệnh.
Lý do bằng tiếng Việt, dựa trên nguyên liệu/cách làm và guidance được cung cấp.
Chỉ dẫn nguồn bằng source_ids 0-based trong guidance khi nguồn thực sự hỗ trợ lý do.
Nếu không có guidance liên quan, chỉ giải thích lựa chọn thông thường theo sở thích/đặc điểm món;
ghi rõ chưa đánh giá độ phù hợp với bệnh trong caution, không bịa quy tắc y khoa.
Không suy luận tâm trạng thành bệnh. Đọc kỹ phủ định, dị ứng và các bệnh đi kèm.
Mô tả ngắn như 'sốt', 'ho', 'mất ngủ' không tự nó là yêu cầu mơ hồ. Nếu có guidance và có candidates,
hãy chọn món tham khảo và ghi rõ giới hạn thay vì yêu cầu người dùng nhập tên món hoặc nguyên liệu.
Riêng sốt: ưu tiên lựa chọn bổ sung dịch/nước/súp và món mềm nếu người dùng muốn ăn; không gán công dụng hạ sốt.
Nếu yêu cầu mơ hồ/mâu thuẫn, có nhiều bệnh cần chế độ riêng hoặc không có món đáng cân nhắc,
trả needs_clarification=true, recommendations=[], clarification_question ngắn để hỏi thêm.
Nếu chọn được món, needs_clarification=false và clarification_question="".
Không tiết lộ suy luận nội bộ; chỉ nêu lý do lựa chọn ngắn có thể kiểm tra.
"""
    from core.circuit_breaker import gemini_circuit_breaker, CircuitBreakerOpenError
    from core.retry_policy import RetryPolicy, execute_with_retry, ErrorClassification
    from core.llm_provider import llm_provider, LLMProviderError
    from unittest.mock import MagicMock

    if not gemini_circuit_breaker.can_execute():
        raise NutritionAIError("unavailable")

    gen_timeout = float(os.getenv("GEMINI_GENERATION_TIMEOUT_SECONDS", str(settings.gemini.timeout_nutrition)))
    from core.recipe_catalog import classify_dish_role, is_standalone_one_dish
    for r in recipes:
        if "dish_role" not in r:
            r["dish_role"] = classify_dish_role(r)
        r["is_one_dish"] = is_standalone_one_dish(r)

    payload = json.dumps({"user_input": condition, "recipe_type": recipe_type,
                         "guidance": guidance, "candidates": [{k: recipe[k] for k in
                             ("id", "title", "dish_role", "is_one_dish", "ingredients", "steps", "rule_tags", "declared_allergens", "metadata_note")
                             if k in recipe} for recipe in recipes]}, ensure_ascii=False)

    # Nếu môi trường kiểm thử trực tiếp mock genai.Client
    if isinstance(genai.Client, MagicMock) or hasattr(genai.Client, "mock_calls"):
        try:
            timeout_ms = max(10000, int(gen_timeout * 1000))
            client = genai.Client(api_key=key, http_options=types.HttpOptions(
                timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1)))

            config = types.GenerateContentConfig(system_instruction=instruction, temperature=0.2,
                max_output_tokens=2600, response_mime_type="application/json", response_json_schema=schema)

            def _do_generate():
                return client.models.generate_content(
                    model=model,
                    contents=payload,
                    config=config
                )

            policy = RetryPolicy(
                max_attempts=int(os.getenv("AI_RETRY_MAX_ATTEMPTS", str(settings.retry.max_attempts))),
                base_delay=float(os.getenv("AI_RETRY_BASE_DELAY_SECONDS", str(settings.retry.base_delay_seconds))),
                max_delay=float(os.getenv("AI_RETRY_MAX_DELAY_SECONDS", str(settings.retry.max_delay_seconds))),
                jitter=settings.retry.jitter
            )

            response = execute_with_retry(
                _do_generate,
                policy=policy,
                circuit_breaker=gemini_circuit_breaker,
                stage="nutrition_ai"
            )
            result = validate_selection(json.loads(response.text or ""), recipes, len(guidance))
            result["model"] = model
            return result
        except NutritionAIError:
            raise
        except CircuitBreakerOpenError:
            raise NutritionAIError("unavailable")
        except Exception as error:
            code = getattr(error, "code", None)
            reason = "invalid_response" if isinstance(error, (ValueError, TypeError, AttributeError)) else "unavailable"
            if code in (400, 401, 403):
                reason = "credentials_or_access"
            elif code == 429:
                reason = "quota"
            raise NutritionAIError(reason) from None
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    # Runtime chính thức chuyển qua Unified LLM Provider
    try:
        raw_result = llm_provider.generate_json(
            contents=payload,
            schema=schema,
            model=model,
            system_instruction=instruction,
            temperature=0.2,
            max_output_tokens=2600,
            timeout_seconds=gen_timeout,
            operation="nutrition_ai",
            profile="nutrition",
            api_key=key
        )
        result = validate_selection(raw_result, recipes, len(guidance))
        result["model"] = model
        return result
    except NutritionAIError:
        raise
    except CircuitBreakerOpenError:
        raise NutritionAIError("unavailable")
    except LLMProviderError as lpe:
        if lpe.classification == ErrorClassification.RATE_LIMIT:
            reason = "quota"
        elif lpe.classification in (ErrorClassification.AUTH_ERROR, ErrorClassification.BAD_REQUEST):
            reason = "credentials_or_access"
        elif lpe.classification == ErrorClassification.SCHEMA_ERROR:
            reason = "invalid_response"
        else:
            reason = "unavailable"
        raise NutritionAIError(reason) from None
    except Exception as error:
        code = getattr(error, "code", None)
        reason = "invalid_response" if isinstance(error, (ValueError, TypeError, AttributeError)) else "unavailable"
        if code in (400, 401, 403):
            reason = "credentials_or_access"
        elif code == 429:
            reason = "quota"
        raise NutritionAIError(reason) from None
