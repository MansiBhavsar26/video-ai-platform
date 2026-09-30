from app.services.ocr import extract_text
from app.services.ocr_cleaner import clean_ocr_text


image_path = r"frames\1\frame_0.00.jpg"


print("Running OCR...")
print()

raw_text = extract_text(
    image_path
)

print("RAW OCR")
print("==============================")
print(raw_text)

print()
print()

cleaned_text = clean_ocr_text(
    raw_text
)

print("CLEANED OCR")
print("==============================")
print(cleaned_text)