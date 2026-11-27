"""Clinical nutrition options and analysis routes."""

import json
import logging

from flask import jsonify, request, session

from core.shared.models import User, db

logger = logging.getLogger("MediMindApp")


def _require_authenticated_nutrition_user():
    """Bắt buộc người dùng đã đăng nhập hợp lệ trước khi dùng tính năng dinh dưỡng."""
    user_id = session.get("user_id")
    if not user_id:
        return None, (
            jsonify({
                "success": False,
                "error": "Vui lòng đăng nhập để sử dụng tính năng dinh dưỡng.",
                "auth_required": True,
            }),
            401,
        )
    return user_id, None


def register_nutrition_routes(app):
    @app.route("/api/nutrition/options", methods=["POST"])
    def nutrition_options():
        """Trả về danh sách món hoặc thức uống để người dùng tự chọn."""
        user_id, auth_error = _require_authenticated_nutrition_user()
        if auth_error:
            return auth_error
        payload = request.get_json(silent=True) or {}
        condition = str(payload.get("condition") or "").strip()
        recipe_type = payload.get("recipe_type") or "food"
        if not condition:
            return jsonify({"success": False, "error": "Vui lòng nhập tình trạng sức khỏe hoặc nhu cầu ăn uống."}), 400
        if len(condition) > 500:
            return jsonify({"success": False, "error": "Vui lòng mô tả tình trạng trong tối đa 500 ký tự."}), 400
        if recipe_type != "food":
            return jsonify({"success": False, "error": "Hiện chỉ hỗ trợ gợi ý món ăn."}), 400
        exclude_ids = payload.get("exclude_recipe_ids", [])
        if (not isinstance(exclude_ids, list) or len(exclude_ids) > 5000
                or any(not isinstance(item, str) or len(item) > 100 for item in exclude_ids)):
            return jsonify({"success": False, "error": "Danh sách món đã xem không hợp lệ."}), 400
        profile, dob = {}, None
        user = db.session.get(User, user_id)
        if user:
            try:
                stored = json.loads(user.clinical_profile or "{}")
                if isinstance(stored, dict):
                    profile = {key: stored.get(key) for key in ("allergies", "height", "weight")}
                dob = user.dob
            except (TypeError, ValueError):
                pass
        from core.nutrition.nutrition_options import get_nutrition_options
        return jsonify({"success": True, "data": get_nutrition_options(
            condition, recipe_type, exclude_ids, profile=profile, dob=dob)}), 200

    @app.route("/api/nutrition/meal-plan", methods=["POST"])
    def nutrition_meal_plan():
        """Lập thực đơn theo thể trạng (BMR/TDEE), bệnh nền & dị ứng (Món lẻ + Combo)."""
        _, auth_error = _require_authenticated_nutrition_user()
        if auth_error:
            return auth_error
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "error": "Dữ liệu khảo sát không hợp lệ."}), 400
        from core.nutrition.nutrition_meal_planner import build_production_meal_plan
        result = build_production_meal_plan(payload)
        return jsonify(result), 200

    @app.route("/api/nutrition/recipe-catalog", methods=["GET"])
    def nutrition_recipe_catalog():
        """Tìm kiếm, lọc và phân trang danh mục 2.500+ công thức Món Ngon Mỗi Ngày."""
        _, auth_error = _require_authenticated_nutrition_user()
        if auth_error:
            return auth_error
        from core.nutrition.monngonmoingay_catalog import search_recipes
        return jsonify(search_recipes(request.args)), 200

    @app.route("/api/nutrition/analyze", methods=["POST"])
    def analyze_nutrition():
        """
        API Phân tích Dinh dưỡng Lâm sàng & Pha chế Bữa ăn Trị liệu theo Thể trạng.
        Nhận vào tên bệnh hoặc thể trạng (từ người dùng nhập) và trả về:
        - foods_to_eat (Nên nạp)
        - foods_to_avoid (Nên né)
        - recipe (Công thức 3 bước)
        """
        _, auth_error = _require_authenticated_nutrition_user()
        if auth_error:
            return auth_error
        data = request.get_json(silent=True) or {}
        condition = (data.get("condition") or data.get("query") or "").strip()
        recipe_type = "food"
        if not condition:
            return jsonify({"success": False, "error": "Vui lòng nhập tên bệnh lý hoặc thể trạng."}), 400

        from core.nutrition.nutrition_service import get_nutrition_recommendation
        try:
            result = get_nutrition_recommendation(condition, recipe_type)
            return jsonify({"success": True, "data": result}), 200
        except Exception as e:
            logger.error(f"Lỗi phân tích dinh dưỡng: {e}")
            return jsonify({"success": False, "error": "Không thể phân tích dinh dưỡng lúc này."}), 500

    # ==============================================================
    # QUẢN LÝ DỮ LIỆU CƠ SỞ Y TẾ (CSKCB REST API)
