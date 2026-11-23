"""Read selected OCR text boxes with an optional local VietOCR model."""

import logging
import math
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock


logger = logging.getLogger(__name__)
_model_lock = Lock()
_default_model_dir = Path(__file__).resolve().parents[2] / "models" / "vietocr"


@lru_cache(maxsize=1)
def _load_reader(model_dir):
    weights = model_dir / "vgg_seq2seq.pth"
    base = model_dir / "base.yml"
    variant = model_dir / "vgg-seq2seq.yml"
    if not all(path.is_file() for path in (weights, base, variant)):
        return None
    try:
        import yaml
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        config = yaml.safe_load(base.read_text(encoding="utf-8"))
        config.update(yaml.safe_load(variant.read_text(encoding="utf-8")))
        config["device"] = "cpu"
        config["weights"] = str(weights.resolve())
        config["cnn"]["pretrained"] = False
        config["predictor"]["beamsearch"] = False
        return Predictor(Cfg(config))
    except Exception as exc:
        logger.warning("Local VietOCR initialization failed (%s).", type(exc).__name__)
        return None


def reread_name_cells(image_path):
    """Read up to eight uncertain cells without opening an image on the fast path."""
    remaining = 8
    image = None
    model_dir = Path(os.environ.get("MEDIMIND_VIETOCR_DIR") or _default_model_dir)

    def read(box):
        nonlocal image, remaining
        if len(box) != 4 or remaining <= 0:
            return ""
        remaining -= 1
        try:
            with _model_lock:
                reader = _load_reader(model_dir)
            if reader is None:
                remaining = 0
                return ""

            import torch
            from PIL import Image

            if image is None:
                with Image.open(image_path) as opened:
                    image = opened.convert("RGB")
            xs, ys = zip(*box)
            x1, y1 = max(0, math.floor(min(xs)) - 4), max(0, math.floor(min(ys)) - 3)
            x2 = min(image.width, math.ceil(max(xs)) + 4)
            y2 = min(image.height, math.ceil(max(ys)) + 3)
            if x2 - x1 < 10 or y2 - y1 < 8:
                return ""
            with _model_lock, torch.inference_mode():
                return reader.predict(image.crop((x1, y1, x2, y2))).strip()
        except Exception as exc:
            logger.warning("Local VietOCR name reread failed (%s).", type(exc).__name__)
            remaining = 0
            return ""

    return read
