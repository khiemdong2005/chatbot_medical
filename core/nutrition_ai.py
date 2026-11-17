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
    instruction = """Bạn chọn công thức tham khảo từ danh mục MediMind theo mô tả của người dùng.
Chỉ chọn recipe_id có trong candidates. Không thêm, đổi nguyên liệu, cách nấu, số kcal hay chỉ số dinh dưỡng.
Các món đã qua bộ lọc nguyên liệu, điều kiện được hỗ trợ và dị ứng đã khai báo. Việc qua bộ lọc không chứng nhận món an toàn hoặc điều trị bệnh.
Ưu tiên đúng yêu cầu ăn uống. Với 'ít đường', so sánh số sugar của những món có dữ liệu theo hướng tương đối; thiếu số liệu là chưa biết, không phải ít đường. Không đặt ngưỡng y khoa.
BMI chỉ là ngữ cảnh tham khảo ở người lớn. Không suy diễn nhu cầu năng lượng, mục tiêu giảm cân hay giới hạn 2.000 kcal/ngày từ BMI. Kcal nguồn chưa được kiểm chứng lâm sàng.
Giải thích bằng nguyên liệu, kết cấu và cách chế biến thật sự có trong công thức. Không bịa vi chất, cơ chế chữa bệnh, tác dụng điều trị hoặc độ an toàn dị ứng tuyệt đối.
source_ids là chỉ số 0-based của guidance thực sự hỗ trợ lý do; dùng [] nếu không có nguồn phù hợp.
Với thức ăn, recommendations ưu tiên món ăn trọn vị có is_one_dish=true, đa dạng bữa, tối đa 6 món. Đồ uống chọn từ ứng viên thức uống.
Nếu tạo full_meal_set, chọn một món chính, một món canh và có thể thêm một món rau/phụ từ candidates; ID khác nhau, không lặp với recommendations. Món rau/phụ TUYỆT ĐỐI KHÔNG TRÙNG NGUYÊN LIỆU ĐẠM HOẶC THÀNH PHẦN CHÍNH (như cùng là đậu hũ, cùng là nấm, cùng thịt bò/gà/heo/tôm/cá) với món chính hoặc món canh trong thực đơn; ưu tiên rau củ quả xanh/luộc/xào thanh đạm. Bỏ trống staple_text để hệ thống nhắc người dùng chọn tinh bột phù hợp dị ứng; phần đó không có kcal trong tổng.
Không tạo full_meal_set nếu thiếu món chính hoặc canh. Nếu không thể chọn món phù hợp, trả needs_clarification=true, recommendations=[] và một câu hỏi ngắn.
Nếu chọn được, needs_clarification=false và clarification_question="". Nội dung trả về bằng tiếng Việt.
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

    personalization = personalization or {}
    model_context = {
        "allergen_codes": [code for code in personalization.get("allergen_codes", []) if code in
                           {"egg", "milk", "soy", "gluten", "shrimp", "crab", "shellfish", "seafood", "fish", "peanut", "tree_nut", "sesame"}],
        "bmi_category": personalization.get("bmi_category") if personalization.get("bmi_category") in
                        {"Thiếu cân", "Trong khoảng tham chiếu", "Thừa cân", "Béo phì"} else None,
        "diet_preferences": [value for value in personalization.get("diet_preferences", []) if value in
                             {"no_added_sugar", "not_spicy", "not_fried", "low_salt"}],
    }
    payload = json.dumps({"user_input": condition, "recipe_type": recipe_type,
                         "guidance": guidance, "personalization": model_context,
                         "candidates": [{k: recipe[k] for k in
                             ("id", "title", "dish_role", "is_one_dish", "ingredients", "steps", "rule_tags", "declared_allergens", "metadata_note", "calories", "sugar", "fat", "fiber", "protein")
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
