import unittest
from app import create_app
from core.nutrition_service import get_nutrition_recommendation, find_preset_condition


class NutritionStudioTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
        self.client = self.app.test_client()

    def test_preset_dau_bung_kinh_matches(self):
        res = find_preset_condition("đau bụng kinh")
        self.assertIsNotNone(res)
        self.assertEqual(res["condition_name"], "Đau bụng kinh")
        self.assertEqual(len(res["foods_to_eat"]), 4)
        self.assertEqual(len(res["foods_to_avoid"]), 3)
        self.assertEqual(res["recipe"]["title"], "Canh khoai lang hạt dẻ hầm")

    def test_preset_nhiet_mieng_matches(self):
        res = find_preset_condition("nhiệt miệng")
        self.assertIsNotNone(res)
        self.assertEqual(res["condition_name"], "Nhiệt miệng")
        self.assertIn("foods_to_eat", res)
        self.assertIn("recipe", res)

    def test_api_nutrition_analyze_valid_preset(self):
        res = self.client.post("/api/nutrition/analyze", json={"condition": "đau bụng kinh"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["condition_name"], "Đau bụng kinh")
        self.assertEqual(data["data"]["recipe"]["title"], "Canh khoai lang hạt dẻ hầm")

    def test_api_nutrition_analyze_empty_input(self):
        res = self.client.post("/api/nutrition/analyze", json={"condition": "   "})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("Vui lòng nhập", data["error"])

    def test_api_nutrition_analyze_custom_fallback(self):
        res = self.client.post("/api/nutrition/analyze", json={"condition": "mỏi cổ vai gáy cấp"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("foods_to_eat", data["data"])
        self.assertIn("foods_to_avoid", data["data"])
        self.assertIn("recipe", data["data"])


if __name__ == "__main__":
    unittest.main()
