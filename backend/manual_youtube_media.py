from app.services.youtube_media import (
    get_youtube_video_info,
)


URL = (
    "https://www.youtube.com/watch?v="
    "S66rHpyU-Eg"
)


info = get_youtube_video_info(URL)

print("VIDEO ID:", info["id"])
print("TITLE:", info["title"])
print("DURATION:", info["duration"])
print("WIDTH:", info["width"])
print("HEIGHT:", info["height"])
print("FPS:", info["fps"])
print("EXT:", info["ext"])