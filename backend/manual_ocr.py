from app.services.ocr import extract_text


image_path = r"frames\1\frame_0.00.jpg"

print("Running OCR...")
print()

text = extract_text(
    image_path
)

print("Detected text:")
print("------------------------")
print(text)
print("------------------------")