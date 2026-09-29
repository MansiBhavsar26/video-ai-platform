import re

from app.services.action_context import build_action_context, combine_context_text


_NEGATIVE_PREFIXES = re.compile(
    r"\b(?:already\s+installed|you\s+can|you\s+could|if\s+you\s+want\s+to|"
    r"we\s+will\s+discuss|later\s+we(?:'ll|\s+will)|this\s+(?:file|component)\s+(?:contains|displays|is\s+responsible))\b",
    re.IGNORECASE,
)


def _clean_name(value: str) -> str:
    value = re.split(r"\b(?:and|then|here|with|for|because|which|that)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.sub(r"\b(?:called|named)\b", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip(" .,:;\"'")


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in re.findall(r"[A-Za-z0-9]+", _clean_name(value)))


def _context_for(segments: list[dict], segment: dict) -> str:
    context = build_action_context(segments, float(segment["start_time"]), float(segment["end_time"]), padding_seconds=20.0)
    return combine_context_text(context)


def _make_action(action: str, value: str, segment: dict, confidence: float, instruction: str | None = None) -> dict:
    result = {
        "action": action,
        "value": value,
        "start_time": float(segment["start_time"]),
        "end_time": float(segment["end_time"]),
        "evidence": segment["text"].strip(),
        "confidence": confidence,
    }
    if instruction:
        result["instruction"] = instruction
    return result


def extract_transcript_actions(segments: list[dict]) -> list[dict]:
    """Extract explicit implementation actions while retaining transcript evidence."""
    actions = []

    for segment in sorted(segments, key=lambda item: item["start_time"]):
        text = segment.get("text", "").strip()
        if not text or _NEGATIVE_PREFIXES.search(text):
            continue

        context_text = _context_for(segments, segment)
        lowered = text.lower()
        action = None

        component = re.search(
            r"\b(?:create|make|build)\s+(?:a|an|our|new)?\s*"
            r"(?:component\s+called\s+)?([A-Za-z][A-Za-z0-9 _-]*?)\s+component\b"
            r"|\b(?:create|make|build)\s+(?:a|an|our|new)?\s+component\s+"
            r"(?:called|named)\s+([A-Za-z][A-Za-z0-9 _-]*)",
            text,
            re.IGNORECASE,
        )
        if component:
            name = _pascal_case(component.group(1) or component.group(2))
            if name:
                action = _make_action("create_component", name, segment, 0.94)

        if action is None and re.search(
            r"\b(?:create|add|define)\s+(?:a|an|the|new)?\s*(?:api\s+)?"
            r"(?:route|endpoint)\b|\badd\s+(?:an?\s+)?api\s+endpoint\b|"
            r"\bcreate\s+(?:an?\s+)?api\b|\badd\s+(?:an?\s+)?controller\b",
            text,
            re.IGNORECASE,
        ):
            subject = re.search(r"\b(?:for|to)\s+([A-Za-z][A-Za-z0-9 _-]*)", text, re.IGNORECASE)
            subject_name = _clean_name(subject.group(1)) if subject else ""
            value = f"{subject_name} API route" if subject_name else "API route"
            action_type = "create_api" if "api" in lowered or "endpoint" in lowered else "create_route"
            action = _make_action(action_type, value, segment, 0.92)

        if action is None and re.search(
            r"\b(?:create|add|define)\s+(?:a|an|the|new)?\s*"
            r"(?:[A-Za-z][A-Za-z0-9_-]*\s+)?(?:model|schema|table)\b|"
            r"\bconfigure\s+(?:the\s+)?database\b|\bcreate\s+(?:the\s+)?database\b",
            text,
            re.IGNORECASE,
        ):
            model = re.search(r"\b(?:model|schema|table)\s+(?:for\s+)?([A-Za-z][A-Za-z0-9 _-]*)", text, re.IGNORECASE)
            if re.search(r"\b(?:model|schema|table)\b", lowered):
                value = f"{_pascal_case(model.group(1))} model" if model else "database model"
                action = _make_action("create_model", value, segment, 0.92)
            else:
                action = _make_action("configure", "database", segment, 0.88)

        if action is None:
            function = re.search(
                r"\b(?:add|create|define)\s+(?:a|an|the|new)?\s*"
                r"(?:function|method)\s*(?:called|named)?\s*"
                r"([A-Za-z][A-Za-z0-9_-]*)?",
                text,
                re.IGNORECASE,
            )
            if function:
                action = _make_action("create_function", function.group(1) or "function", segment, 0.90)

        if action is None:
            implementation = re.search(
                r"\b(?:implement|add|create)\s+(?:the\s+)?"
                r"(state|an?\s+event\s+handler|an?\s+form|validation|functionality)\b"
                r"|\b(?:connect|link)\s+(?:the\s+)?(.+?)\s+to\s+(?:the\s+)?(.+)$"
                r"|\b(?:fetch|call)\s+(?:data|the\s+api|an?\s+api)\b"
                r"|\brender\s+(?:the\s+)?(?:component|.+)\b",
                text,
                re.IGNORECASE,
            )
            if implementation:
                if implementation.group(2) and implementation.group(3):
                    value = f"{_clean_name(implementation.group(2))} to {_clean_name(implementation.group(3))}"
                    instruction = f"Connect {value}."
                else:
                    value = _clean_name(implementation.group(1) or "frontend functionality")
                    instruction = f"Implement {value}."
                action = _make_action("implement", value, segment, 0.84, instruction)

        if action is None and re.search(
            r"\b(?:install|add)\s+(?!it\b)([A-Za-z][A-Za-z0-9_.-]*)\s+(?:package|library|dependency)\b|"
            r"\bimport\s+([A-Za-z][A-Za-z0-9_.-]*)\b",
            text,
            re.IGNORECASE,
        ):
            dependency = re.search(r"\b(?:install|add|import)\s+([A-Za-z][A-Za-z0-9_.-]*)", text, re.IGNORECASE)
            if dependency and not re.search(r"\b(?:already|could|can|want)\b", context_text, re.IGNORECASE):
                action = _make_action("install_dependency", dependency.group(1), segment, 0.86)

        if action:
            actions.append(action)

    return actions