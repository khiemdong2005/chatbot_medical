"""The prescription vision call receives a full page and a readable crop."""

from unittest.mock import patch

from PIL import Image

from core.groq_schema_service import extract_with_groq_schema
from core.llm_provider import llm_provider


def test_prescription_sends_full_image_and_crop_in_one_call(tmp_path):
    image = tmp_path / "rx.jpg"
    Image.new("RGB", (400, 600), "white").save(image)
    rows = [
        {"text": "ĐƠN THUỐC", "y_min": 100, "y_max": 120},
        {"text": "1. Thuốc A 20mg", "y_min": 220, "y_max": 245},
        {"text": "2. Thuốc B 10mg", "y_min": 310, "y_max": 335},
        {"text": "Tái khám", "y_min": 450, "y_max": 475},
    ]
    with (patch.object(llm_provider, "resolve_api_key", return_value="test-key"),
          patch.object(llm_provider, "is_configured", return_value=True),
          patch.object(llm_provider, "generate_json", return_value={"medications": []}) as generate):
        extract_with_groq_schema(str(image), ocr_result={"rows": rows, "lines": []})

    contents = generate.call_args.kwargs["contents"]
    assert len(contents) == 3  # full image, crop, prompt: one generate call
    assert contents[0]["image_url"]["url"].startswith("data:image/jpeg")
    assert contents[1]["image_url"]["url"].startswith("data:image/jpeg")
    assert not list(tmp_path.glob("*_med_crop.jpg"))


def test_prescription_without_reliable_crop_sends_only_full_image(tmp_path):
    image = tmp_path / "rx.jpg"
    Image.new("RGB", (400, 600), "white").save(image)
    with (patch.object(llm_provider, "resolve_api_key", return_value="test-key"),
          patch.object(llm_provider, "is_configured", return_value=True),
          patch.object(llm_provider, "generate_json", return_value={"medications": []}) as generate):
        extract_with_groq_schema(str(image), ocr_result={"rows": [], "lines": []})

    assert len(generate.call_args.kwargs["contents"]) == 2
