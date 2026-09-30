from app.services.ocr import extract_text
from app.services.ocr_cleaner import clean_ocr_text
from app.services.evidence_classifier import (
    classify_evidence,
    get_evidence_confidence,
)


import glob
import os


frames = sorted(
    glob.glob(
        "frames/step_test/*.jpg"
    )
)


print(
    "FRAMES FOUND:",
    len(frames),
)

print("=" * 70)


results = []

for filepath in frames:

    text = extract_text(
        filepath
    )

    text = clean_ocr_text(
        text
    )

    if not text:
        continue

    evidence_type = classify_evidence(
        text
    )

    confidence = get_evidence_confidence(
        evidence_type
    )

    filename = os.path.basename(
        filepath
    )

    results.append(
        {
            "filepath": filepath,
            "filename": filename,
            "text": text,
            "evidence_type": evidence_type,
            "confidence": confidence,
        }
    )


print(
    "USEFUL OCR RESULTS:",
    len(results),
)

print("=" * 70)


for result in results:

    print(
        f"FRAME: {result['filename']}"
    )

    print(
        f"TYPE: {result['evidence_type']}"
    )

    print(
        f"CONFIDENCE: {result['confidence']}"
    )

    print(
        "TEXT:"
    )

    print(
        result["text"]
    )

    print("-" * 70)