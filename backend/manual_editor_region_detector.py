from app.services.editor_region_detector import (
    detect_editor_region,
    crop_editor_region,
)


FRAME_PATH = (
    r"test_youtube_app_frames\code_1902.77.jpg"
)

OUTPUT_PATH = (
    r"test_editor_regions\app_1902.77_editor.jpg"
)


region = detect_editor_region(
    FRAME_PATH
)


print()
print("=" * 70)
print("EDITOR REGION DETECTION")
print("=" * 70)

print()
print("FRAME:")
print(FRAME_PATH)

print()
print("ORIGINAL SIZE:")
print(
    region["original_width"],
    "x",
    region["original_height"],
)

print()
print("EDITOR REGION:")
print(
    f"x={region['x']}, "
    f"y={region['y']}, "
    f"width={region['width']}, "
    f"height={region['height']}"
)


output = crop_editor_region(
    filepath=FRAME_PATH,
    region=region,
    output_filepath=OUTPUT_PATH,
)

print()
print("CROPPED FILE:")
print(output)

print()
print("=" * 70)