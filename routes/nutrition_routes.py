"""Clinical Nutrition Options, Meals & Analysis routes."""

import json
import logging
from flask import jsonify, request, session

from core.models import User, db

logger = logging.getLogger("MediMindApp")


def register_nutrition_routes(app):
    @app.route("/api/nutrition/meals", methods=["POST"])
    def nutrition_meals():
        """
        API Đề xuất Bữa ăn Động (Dynamic Meal Composition Engine).
        Trả về 2 nhóm kết quả:
        1. family_combos: Tối đa 6 mâm cơm gia đình 4 món (staple, main, soup, veg).
        2. standalone_meals: Tối đa 6 món ăn độc lập (phở, bún, cháo, hủ tiếu, cơm đĩa, mì).
        """
        payload = request.get_json(silent=True) or {}
        condition = str(payload.get("condition") or payload.get("query") or "").strip()
        if not condition:
            return jsonify({"status": "error", "error": "Vui lòng nhập tình trạng sức khỏe hoặc nhu cầu dinh dưỡng."}), 400
        if len(condition) > 500:
            return jsonify({"status": "error", "error": "Vui lòng mô tả tình trạng trong tối đa 500 ký tự."}), 400

        exclude_ids = payload.get("exclude_recipe_ids", [])
        if (not isinstance(exclude_ids, list) or len(exclude_ids) > 5000
                or any(not isinstance(item, str) or len(item) > 100 for item in exclude_ids)):
            return jsonify({"status": "error", "error": "Danh sách món đã xem không hợp lệ."}), 400

        allergies = payload.get("allergies")
        if allergies is not None and not isinstance(allergies, list):
            return jsonify({"status": "error", "error": "Danh sách dị ứng không hợp lệ."}), 400

        # Trích xuất thông tin hồ sơ người dùng nếu có đăng nhập
        profile = {}
        user_id = session.get("user_id")
        if user_id:
            user = db.session.get(User, user_id)
            if user:
                try:
                    stored = json.loads(user.clinical_profile or "{}")
                    if isinstance(stored, dict):
                        profile = {key: stored.get(key) for key in ("allergies", "height", "weight")}
                except (TypeError, ValueError):
                    pass

        # Ghi đè dị ứng nếu client truyền trực tiếp
        if allergies is not None:
            profile["allergies"] = allergies

        try:
            from core.nutrition.meal_engine_service import MealEngineService
            service = MealEngineService.get_instance()
            result = service.recommend_meals(
                condition=condition,
                allergies=profile.get("allergies"),
                exclude_recipe_ids=exclude_ids,
                profile=profile,
            )
            # Log an toàn (Không log dữ liệu sức khỏe nhạy cảm)
            logger.info(
                f"[NutritionMealsAPI] QueryLen={len(condition)} "
                f"Status={result.get('status')} "
                f"Combos={len(result.get('family_combos', []))} "
                f"Standalones={len(result.get('standalone_meals', []))} "
                f"Latency={result.get('metadata', {}).get('latency_ms')}ms"
            )
            return jsonify(result), 200
        except Exception as e:
            logger.error(f"[NutritionMealsAPI] Error generating meals: {e}")
            return jsonify({
                "status": "error",
                "error": "Không thể tạo đề xuất bữa ăn lúc này. Vui lòng thử lại sau."
            }), 500

    @app.route("/api/nutrition/options", methods=["POST"])
    def nutrition_options():
        """
        API Tương thích ngược: Trả về danh sách món hoặc thức uống để người dùng tự chọn.
        Đối với thức ăn (food): Sử dụng Dynamic Meal Composition Engine.
        Đối với nước uống (drink): Sử dụng quy tắc nước uống chuyên biệt.
        """
        payload = request.get_json(silent=True) or {}
        condition = str(payload.get("condition") or "").strip()
        recipe_type = payload.get("recipe_type")
        if not condition:
            return jsonify({"success": False, "error": "Vui lòng nhập tình trạng sức khỏe hoặc nhu cầu ăn uống."}), 400
        if len(condition) > 500:
            return jsonify({"success": False, "error": "Vui lòng mô tả tình trạng trong tối đa 500 ký tự."}), 400
        if recipe_type not in ("food", "drink"):
            return jsonify({"success": False, "error": "Vui lòng chọn thức ăn hoặc nước uống."}), 400
        exclude_ids = payload.get("exclude_recipe_ids", [])
        if (not isinstance(exclude_ids, list) or len(exclude_ids) > 5000
                or any(not isinstance(item, str) or len(item) > 100 for item in exclude_ids)):
            return jsonify({"success": False, "error": "Danh sách món đã xem không hợp lệ."}), 400

        profile, dob = {}, None
        user_id = session.get("user_id")
        if user_id:
            user = db.session.get(User, user_id)
            if user:
                try:
                    stored = json.loads(user.clinical_profile or "{}")
                    if isinstance(stored, dict):
                        profile = {key: stored.get(key) for key in ("allergies", "height", "weight")}
                    dob = user.dob
                except (TypeError, ValueError):
                    pass

        # Gọi get_nutrition_options chuẩn của hệ thống
        from core.nutrition_options import get_nutrition_options
        try:
            legacy_data = get_nutrition_options(
                condition, recipe_type, exclude_ids, profile=profile, dob=dob
            )
        except Exception as e:
            logger.error(f"[NutritionOptionsAPI] Legacy options error: {e}")
            legacy_data = {"recipes": [], "eligible_count": 0}

        # Nếu là thức ăn (food) và không bị từ chối/cần làm rõ: Bổ sung family_combos & standalone_meals từ MealEngineService
        if recipe_type == "food" and not legacy_data.get("needs_clarification"):
            try:
                from core.nutrition.meal_engine_service import MealEngineService
                service = MealEngineService.get_instance()
                meal_res = service.recommend_meals(
                    condition=condition,
                    allergies=profile.get("allergies") if isinstance(profile.get("allergies"), list) else None,
                    exclude_recipe_ids=exclude_ids,
                    profile=profile,
                )
                if meal_res.get("status") == "success":
                    legacy_data["family_combos"] = meal_res.get("family_combos", [])
                    legacy_data["standalone_meals"] = meal_res.get("standalone_meals", [])
                    if meal_res.get("meal_combos"):
                        legacy_data["meal_combos"] = meal_res.get("meal_combos")
                    legacy_data["safety_status"] = meal_res.get("safety_status")
                    legacy_data["engine_metadata"] = meal_res.get("metadata")
            except Exception as e:
                logger.warning(f"[NutritionOptionsAPI] MealEngineService enrichment notice: {e}")

        return jsonify({"success": True, "data": legacy_data}), 200

    @app.route("/api/nutrition/analyze", methods=["POST"])
    def analyze_nutrition():
        """
        API Phân tích Dinh dưỡng Lâm sàng & Pha chế Bữa ăn Trị liệu theo Thể trạng.
        """
        data = request.get_json(silent=True) or {}
        condition = (data.get("condition") or data.get("query") or "").strip()
        recipe_type = "drink" if data.get("recipe_type") == "drink" else "food"
        if not condition:
            return jsonify({"success": False, "error": "Vui lòng nhập tên bệnh lý hoặc thể trạng."}), 400

        from core.nutrition_service import get_nutrition_recommendation
        try:
            result = get_nutrition_recommendation(condition, recipe_type)
            return jsonify({"success": True, "data": result}), 200
        except Exception as e:
            logger.error(f"Lỗi phân tích dinh dưỡng: {e}")
            return jsonify({"success": False, "error": "Không thể phân tích dinh dưỡng lúc này."}), 500
