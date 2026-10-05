from collections import Counter

import cv2


def generate_video_description(
    frames,
    detections,
    video_duration,
    ocr_results=None,
):
    """
    Generate a natural-language description
    using local Python analysis.

    No external AI API is used.
    """

    if not frames:
        return "No frames were available for analysis."

    # --------------------------------------------------
    # Collect detected objects
    # --------------------------------------------------

    if isinstance(detections, Counter):
        object_counts = detections
    else:
        labels = [
            detection["label"]
            for detection in detections
        ]
        object_counts = Counter(labels)

    # --------------------------------------------------
    # Build object description
    # --------------------------------------------------

    if object_counts:

        object_parts = []

        for label, count in object_counts.items():

            if count == 1:

                object_parts.append(
                    f"one {label}"
                )

            else:

                object_parts.append(
                    f"{count} detections of {label}"
                )

        if len(object_parts) == 1:

            objects_text = object_parts[0]

        else:

            objects_text = (
                ", ".join(object_parts[:-1])
                + " and "
                + object_parts[-1]
            )

    else:

        objects_text = (
            "no recognizable objects"
        )

    # --------------------------------------------------
    # Video duration
    # --------------------------------------------------

    duration = video_duration

    # --------------------------------------------------
    # Detect scene changes
    # --------------------------------------------------

    scene_changes = 0
    previous_image = None

    for frame in frames:

        filepath = frame.get("filepath")

        if not filepath:
            continue

        current_image = cv2.imread(filepath)

        if current_image is None:
            continue

        if previous_image is not None:

            try:

                previous_gray = cv2.cvtColor(
                    previous_image,
                    cv2.COLOR_BGR2GRAY,
                )

                current_gray = cv2.cvtColor(
                    current_image,
                    cv2.COLOR_BGR2GRAY,
                )

                difference = cv2.absdiff(
                    previous_gray,
                    current_gray,
                )

                change_score = difference.mean()

                if change_score > 15:

                    scene_changes += 1

            except Exception:

                pass

        previous_image = current_image

    # --------------------------------------------------
    # Start description
    # --------------------------------------------------

    description_parts = []

    description_parts.append(
        "This video is approximately "
        f"{duration:.1f} seconds long."
    )

    description_parts.append(
        f"The video contains "
        f"{objects_text}."
    )

    # --------------------------------------------------
    # Scene information
    # --------------------------------------------------

    if scene_changes > 0:

        description_parts.append(
            "The visual content changes "
            "during the video."
        )

    else:

        description_parts.append(
            "The visual scene remains "
            "relatively consistent throughout "
            "the video."
        )

    # --------------------------------------------------
    # Computer/electronic device detection
    # --------------------------------------------------

    screen_objects = {
        "laptop",
        "tv",
        "cell phone",
        "keyboard",
        "mouse",
    }

    detected_screen_objects = (
        set(object_counts.keys())
        & screen_objects
    )

    if detected_screen_objects:

        description_parts.append(
            "The scene appears to involve "
            "a computer or electronic device."
        )

    # --------------------------------------------------
    # OCR information
    # --------------------------------------------------

    if ocr_results:

        unique_texts = []

        for result in ocr_results:

            text = result.get(
                "text",
                "",
            ).strip()

            if (
                text
                and text not in unique_texts
            ):

                unique_texts.append(
                    text
                )

        if unique_texts:

            combined_text = " ".join(
                unique_texts
            )

            if len(combined_text) > 500:

                combined_text = (
                    combined_text[:500]
                    + "..."
                )

            description_parts.append(
                "Text visible in the video "
                "includes: "
                f"{combined_text}"
            )

    return " ".join(
        description_parts
    )