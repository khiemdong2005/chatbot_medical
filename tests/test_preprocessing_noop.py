import cv2
import numpy as np

from core.preprocessing_service import preprocess_lightweight


def test_unmodified_small_jpeg_is_not_reencoded(tmp_path):
    image_path = tmp_path / "prescription.jpg"
    image = np.full((80, 120, 3), 255, dtype=np.uint8)
    assert cv2.imwrite(str(image_path), image)
    original_bytes = image_path.read_bytes()

    result = preprocess_lightweight(str(image_path), need_clahe=False)

    assert result["processed_path"] == str(image_path)
    assert result["orig_shape"] == result["current_shape"] == (120, 80)
    assert result["to_original"] == np.eye(3).tolist()
    assert image_path.read_bytes() == original_bytes
    assert not (tmp_path / "prescription_prepped.jpg").exists()
