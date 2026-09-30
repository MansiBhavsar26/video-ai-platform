import numpy as np

from app.services import ocr


def _recognized_text():
    return {
        "text": ["npm", "install", "react"],
        "conf": ["95", "96", "97"],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 1],
        "left": [0, 30, 80],
    }


def test_ocr_returns_recognized_text_when_tesseract_is_available(monkeypatch):
    monkeypatch.setattr(ocr.cv2, "imread", lambda path: np.zeros((16, 16, 3), dtype=np.uint8))
    monkeypatch.setattr(ocr.pytesseract, "image_to_data", lambda *args, **kwargs: _recognized_text())

    assert ocr.extract_text("frame.jpg") == "npm install react"


def test_ocr_skips_missing_tesseract_without_raising(monkeypatch):
    monkeypatch.setattr(ocr.cv2, "imread", lambda path: np.zeros((16, 16, 3), dtype=np.uint8))

    def missing_tesseract(*args, **kwargs):
        raise FileNotFoundError("private executable path")

    monkeypatch.setattr(ocr.pytesseract, "image_to_data", missing_tesseract)

    assert ocr.extract_text("frame.jpg") == ""


def test_ocr_processing_failure_is_a_degraded_empty_result(monkeypatch):
    monkeypatch.setattr(ocr.cv2, "imread", lambda path: np.zeros((16, 16, 3), dtype=np.uint8))
    monkeypatch.setattr(ocr.cv2, "cvtColor", lambda *args: (_ for _ in ()).throw(RuntimeError("failure")))

    assert ocr.extract_text("frame.jpg") == ""
