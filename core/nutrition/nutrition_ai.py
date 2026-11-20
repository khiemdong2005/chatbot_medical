"""OpenRouter ranks supplied recipes; it cannot create or alter ingredients."""
import json
import os
import re
from typing import Any, Dict, List



class NutritionAIError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_selection(value: Any, recipes: List[Dict], source_count: int) -> Dict:
    if not isinstance(value, dict) or type(value.get("needs_clarification")) is not bool:
        raise NutritionAIError("invalid_response")
    choices = value.get("recommendations")
    question = value.get("clarification_question", "")
    if question is None and not value["needs_clarification"]:
        question = ""
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

        # Món phụ tuyệt đối không trùng nguyên liệu đạm/thành phần chính với món chính hoặc món canh
        if side_cand and (main_cand or soup_cand):
            from core.nutrition_options import _extract_main_ingredient_tags
            s_tags = _extract_main_ingredient_tags(side_cand)
            m_tags = _extract_main_ingredient_tags(main_cand) if main_cand else set()
            sp_tags = _extract_main_ingredient_tags(soup_cand) if soup_cand else set()
            if s_tags and ((s_tags & m_tags) or (s_tags & sp_tags)):
                side_cand = None
                side_id = None

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


def select_recipes(condition: str, recipe_type: str, recipes: List[Dict], guidance: List[Dict],
                   personalization: Dict | None = None) -> Dict:
    from core.llm_provider import llm_provider
    use_groq = llm_provider.is_groq_active()
    if use_groq:
        key = (os.getenv("GROQ_API_KEY") or "").strip()
        model = (os.getenv("GROQ_NUTRITION_MODEL") or "openai/gpt-oss-20b").strip()
        active_provider = "groq"
        want_json_mode = True
    else:
        key = (os.getenv("OPENROUTER_NUTRITION_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "").strip()
        model = (os.getenv("OPENROUTER_NUTRITION_MODEL") or os.getenv("OPENROUTER_MODEL") or "openrouter/free").strip()
        active_provider = "openrouter"
        want_json_mode = False
    if not key or key.startswith("YOUR_") or len(key) <= 10:
        raise NutritionAIError("not_configured")
    if not model or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", model):
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
            }}
        }, "required": ["needs_clarification", "clarification_question", "recommendations"]
    }
    if recipe_type == "food":
        schema["properties"]["full_meal_set"] = {
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

    fms_format = """  "full_meal_set": {
    "title": "string",
    "meal_time": "string",
    "rationale": "string",
    "main_recipe_id": "string",
    "soup_recipe_id": "string",
    "side_recipe_id": "string",
    "staple_text": "string"
  }""" if recipe_type == "food" else '  "full_meal_set": null'

    fms_rule = "7. Với thức ăn, nếu tạo full_meal_set, chọn một món chính, một món canh và có thể thêm một món rau/phụ từ candidates; ID khác nhau, không lặp với recommendations. Món rau/phụ TUYỆT ĐỐI KHÔNG TRÙNG NGUYÊN LIỆU ĐẠM HOẶC THÀNH PHẦN CHÍNH với món chính hoặc món canh trong thực đơn." if recipe_type == "food" else "7. Với thức uống, không tạo full_meal_set (đặt full_meal_set = null)."

    instruction = f"""Bạn chọn công thức tham khảo từ danh mục MediMind theo mô tả của người dùng.
Chỉ chọn recipe_id có trong candidates. Không thêm, đổi nguyên liệu, cách nấu, số kcal hay chỉ số dinh dưỡng.

CẤU TRÚC PHẢN HỒI JSON BẮT BUỘC:
{{
  "needs_clarification": boolean,
  "clarification_question": "string (nếu cần clarification)",
  "recommendations": [
    {{
      "recipe_id": "string",
      "display_title": "string",
      "meal_time": "string (breakfast|lunch|dinner|snack)",
      "dish_role": "string (main|soup|side|staple|drink)",
      "key_nutrients": "string",
      "reason": "string (10-500 chars)",
      "caution": "string (<= 400 chars)",
      "source_ids": [int]
    }}
  ],
{fms_format}
}}

QUY TẮC:
1. Các món đã qua bộ lọc nguyên liệu, điều kiện được hỗ trợ và dị ứng đã khai báo.
2. Ưu tiên đúng yêu cầu ăn uống. Với 'ít đường', so sánh số sugar của những món có dữ liệu theo hướng tương đối; thiếu số liệu là chưa biết, không phải ít đường. Không đặt ngưỡng y khoa.
3. BMI chỉ là ngữ cảnh tham khảo ở người lớn. Không suy diễn nhu cầu năng lượng, mục tiêu giảm cân hay giới hạn 2.000 kcal/ngày từ BMI. Kcal nguồn chưa được kiểm chứng lâm sàng.
4. Giải thích bằng nguyên liệu, kết cấu và cách chế biến thật sự có trong công thức. Không bịa vi chất, cơ chế chữa bệnh, tác dụng điều trị hoặc độ an toàn dị ứng tuyệt đối.
5. source_ids là chỉ số 0-based của guidance thực sự hỗ trợ lý do; dùng [] nếu không có nguồn phù hợp.
6. Với thức ăn, recommendations chọn các món ăn trọn vị có is_one_dish=true, đa dạng bữa (sáng, trưa, tối), tối đa 5-6 món. Tuyệt đối không chọn chè ngọt, đồ ngọt tráng miệng làm bữa ăn chính cho người bệnh. Đồ uống chọn từ ứng viên thức uống.
{fms_rule}
8. Bỏ trống staple_text để hệ thống nhắc người dùng chọn tinh bột phù hợp dị ứng.
9. Nếu không thể chọn món phù hợp, trả needs_clarification=true, recommendations=[] và một câu hỏi ngắn.
10. Nội dung trả về bằng tiếng Việt.
"""
    from core.circuit_breaker import CircuitBreakerOpenError, get_circuit_breaker
    from core.retry_policy import ErrorClassification
    from core.llm_provider import LLMProviderError

    nutrition_breaker = get_circuit_breaker("nutrition")
    if not nutrition_breaker.can_execute():
        raise NutritionAIError("unavailable")

    try:
        gen_timeout = float(os.getenv("OPENROUTER_NUTRITION_TIMEOUT_SECONDS", "90"))
        if not 10 <= gen_timeout <= 180:
            raise ValueError("timeout out of range")
    except ValueError:
        raise NutritionAIError("configuration") from None
    from core.recipe_catalog import classify_dish_role, is_standalone_one_dish
    for r in recipes:
        if "dish_role" not in r:
            r["dish_role"] = classify_dish_role(r)
        r["is_one_dish"] = is_standalone_one_dish(r)

    personalization = personalization or {}
    model_context = {
        "allergen_codes": [code for code in personalization.get("allergen_codes", []) if code in
                           {"egg", "milk", "soy", "gluten", "shrimp", "crab", "shellfish", "seafood", "fish", "peanut", "tree_nut", "sesame"}],
        "bmi_category": personalization.get("bmi_category") if personalization.get("bmi_category") in
                        {"Thiếu cân", "Trong khoảng tham chiếu", "Thừa cân", "Béo phì"} else None,
        "diet_preferences": [value for value in personalization.get("diet_preferences", []) if value in
                             {"no_added_sugar", "not_spicy", "not_fried", "low_salt"}],
    }
    if use_groq:
        # Groq Free Tier giới hạn 8,000 TPM/request (tránh HTTP 413 Payload Too Large):
        # Giữ tối đa 16 món cân bằng giữa one-dish, main, soup, side và bỏ `steps` dài dòng
        # (validate_selection sẽ ghép lại toàn bộ steps/ingredients chuẩn từ catalog gốc).
        one_dishes = [r for r in recipes if r.get("is_one_dish")]
        soups = [r for r in recipes if r.get("dish_role") == "soup" and r not in one_dishes]
        mains = [r for r in recipes if r.get("dish_role") == "main" and r not in one_dishes]
        sides = [r for r in recipes if r.get("dish_role") == "side" and r not in one_dishes]
        others = [r for r in recipes if r not in one_dishes and r not in soups and r not in mains and r not in sides]
        picked: List[Dict] = []
        for pool, cap in ((one_dishes, 8), (mains, 4), (soups, 4), (sides, 3), (others, 4)):
            for item in pool[:cap]:
                if item not in picked and len(picked) < 16:
                    picked.append(item)
        if not picked:
            picked = recipes[:16]
        compact_fields = ("id", "title", "dish_role", "is_one_dish", "ingredients",
                          "rule_tags", "calories", "sugar", "fat", "fiber", "protein")
        compact_candidates = []
        for recipe in picked:
            entry = {k: recipe[k] for k in compact_fields if k in recipe}
            if isinstance(entry.get("ingredients"), list):
                entry["ingredients"] = [str(x)[:60] for x in entry["ingredients"][:10]]
            compact_candidates.append(entry)
        compact_guidance = [
            {k: (str(v)[:200] if isinstance(v, str) else v) for k, v in g.items()}
            for g in (guidance or [])[:4]
        ]
        payload = json.dumps({"user_input": condition, "recipe_type": recipe_type,
                              "guidance": compact_guidance, "personalization": model_context,
                              "candidates": compact_candidates}, ensure_ascii=False)
    else:
        payload = json.dumps({"user_input": condition, "recipe_type": recipe_type,
                             "guidance": guidance, "personalization": model_context,
                             "candidates": [{k: recipe[k] for k in
                                 ("id", "title", "dish_role", "is_one_dish", "ingredients", "steps", "rule_tags", "declared_allergens", "metadata_note", "calories", "sugar", "fat", "fiber", "protein")
                                 if k in recipe} for recipe in recipes]}, ensure_ascii=False)

    # This model may not support JSON Schema or JSON-mode parameters. Prompt
    # for JSON and validate the parsed selection against the canonical catalog.
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
            api_key=key,
            provider=active_provider,
            json_mode=want_json_mode,
            reasoning_enabled=False,
        )
        result = validate_selection(raw_result, recipes, len(guidance))
        if recipe_type == "drink":
            result["full_meal_set"] = None
        result["model"] = model
        return result
    except NutritionAIError:
        raise
    except CircuitBreakerOpenError:
        raise NutritionAIError("unavailable") from None
    except LLMProviderError as lpe:
        if lpe.classification == ErrorClassification.RATE_LIMIT:
            reason = "quota"
        elif lpe.classification == ErrorClassification.AUTH_ERROR:
            reason = "credentials_or_access"
        elif lpe.classification == ErrorClassification.BAD_REQUEST or getattr(lpe.original_exception, "status_code", None) == 404:
            reason = "configuration"
        elif lpe.classification == ErrorClassification.SCHEMA_ERROR:
            reason = "invalid_response"
        else:
            reason = "unavailable"
        raise NutritionAIError(reason) from None
    except Exception as error:
        code = getattr(error, "code", None)
        reason = "invalid_response" if isinstance(error, (ValueError, TypeError, AttributeError)) else "unavailable"
        if code in (400, 404):
            reason = "configuration"
        elif code in (401, 403):
            reason = "credentials_or_access"
        elif code == 429:
            reason = "quota"
        raise NutritionAIError(reason) from None
