import logging
import re

import cv2
import pytesseract

from ..config import TESSERACT_PATH, VIDEO_ANALYSIS_MAX_FRAME_DIMENSION


if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


OCR_MAX_DIMENSION = VIDEO_ANALYSIS_MAX_FRAME_DIMENSION
OCR_TIMEOUT_SECONDS = 10
logger = logging.getLogger(__name__)


def resize_for_ocr(image):
    height, width = image.shape[:2]

    max_dimension = max(height, width)

    if max_dimension <= OCR_MAX_DIMENSION:
        return image

    scale = OCR_MAX_DIMENSION / max_dimension

    new_width = int(width * scale)
    new_height = int(height * scale)

    return cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_AREA,
    )


def is_reasonable_text(text: str) -> bool:
    text = text.strip()

    if not text:
        return False

    if len(text) < 4:
        return False

    letters = sum(
        char.isalpha()
        for char in text
    )

    alphanumeric = sum(
        char.isalnum()
        for char in text
    )

    if letters < 2:
        return False

    ratio = alphanumeric / len(text)

    if ratio < 0.50:
        return False

    garbage_patterns = [
        r"^[<>@+\-_=~|]+$",
        r"^[A-Z]{1,3}$",
        r"^[a-z]{1,2}$",
    ]

    for pattern in garbage_patterns:
        if re.match(pattern, text):
            return False

    return True


def extract_text(image_path: str, video_id: int | None = None) -> str:
    try:
        return _extract_text(image_path)
    except Exception as error:
        logger.warning(
            "[analysis] video=%s stage=ocr failed error_type=%s; "
            "continuing_without_ocr=true",
            video_id if video_id is not None else "unknown",
            type(error).__name__,
        )
        return ""


def _extract_text(image_path: str) -> str:
    image = cv2.imread(image_path)
    if image is None:
        return ""

    gray = processed = None
    try:
        image = resize_for_ocr(image)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        processed = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )[1]
        data = pytesseract.image_to_data(
            processed,
            lang="eng",
            config="--psm 11",
            output_type=pytesseract.Output.DICT,
            timeout=OCR_TIMEOUT_SECONDS,
        )
    finally:
        del image, gray, processed

    lines = {}

    total = len(data["text"])

    for i in range(total):

        text = data["text"][i].strip()

        if not text:
            continue

        try:
            confidence = float(
                data["conf"][i]
            )
        except (ValueError, TypeError):
            continue

        if confidence < 55:
            continue

        key = (
            data["block_num"][i],
            data["par_num"][i],
            data["line_num"][i],
        )

        if key not in lines:
            lines[key] = []

        lines[key].append(
            {
                "text": text,
                "confidence": confidence,
                "left": data["left"][i],
            }
        )

    valid_lines = []

    for words in lines.values():

        words.sort(
            key=lambda item: item["left"]
        )

        line_text = " ".join(
            item["text"]
            for item in words
        )

        average_confidence = (
            sum(
                item["confidence"]
                for item in words
            )
            / len(words)
        )

        if average_confidence < 55:
            continue

        if not is_reasonable_text(line_text):
            continue

        valid_lines.append(line_text)

    unique_lines = []
    seen = set()

    for line in valid_lines:

        normalized = re.sub(
            r"\s+",
            " ",
            line,
        ).strip()

        key = normalized.lower()

        if key in seen:
            continue

        seen.add(key)
        unique_lines.append(normalized)

    return "\n".join(unique_lines)
