from app.services.action_reconstructor import (
    reconstruct_react_setup,
)

from app.services.file_action_extractor import (
    extract_file_edit_actions,
)

from app.services.transcript_action_extractor import (
    extract_transcript_actions,
)


def _action_key(action: dict) -> tuple:
    return (
        action.get("action"),
        str(action.get("value", "")).strip().lower(),
        round(float(action.get("start_time", 0)) / 5),
    )


def _action_to_step(action: dict, step_number: int) -> dict:
    action_type = action["action"]
    value = action.get("value", "")

    if action_type == "run_command":
        instruction = value
        name = None
        path = value
    elif action_type == "edit_file":
        operation = action.get("operation", "edit")
        instruction = f"{operation.capitalize()} {value}"
        name = value
        path = value
    elif action.get("instruction"):
        instruction = action["instruction"]
        name = value
        path = value
    elif action_type == "install_dependency":
        instruction = f"Install the {value} dependency."
        name = value
        path = None
    else:
        instruction = f"Create {value}."
        name = value
        path = value

    return {
        "step": step_number,
        "action": action_type,
        "name": name,
        "path": path,
        "instruction": instruction,
        "start_time": float(action["start_time"]),
        "end_time": float(action["end_time"]),
        "confidence": float(action.get("confidence", 0.0)),
        "verified": False,
        "evidence": {
            "source": "transcript",
            "text": action.get("evidence", ""),
        },
    }


def build_developer_action_timeline(
    segments: list[dict],
) -> list[dict]:
    """
    Combine command actions and file actions
    into one chronological developer-action timeline.
    """

    if not segments:
        return []

    command_actions = reconstruct_react_setup(
        segments=segments
    )

    file_actions = extract_file_edit_actions(
        segments
    )

    transcript_actions = extract_transcript_actions(
        segments
    )

    actions = (
        command_actions
        + file_actions
        + transcript_actions
    )

    unique_actions = []
    seen_actions = set()

    for action in actions:
        key = _action_key(action)
        if key in seen_actions:
            continue
        seen_actions.add(key)
        unique_actions.append(action)

    unique_actions.sort(
        key=lambda action: action["start_time"]
    )

    return unique_actions


def build_tutorial_steps(
    segments: list[dict],
) -> list[dict]:
    actions = build_developer_action_timeline(segments)
    return [
        _action_to_step(action, index)
        for index, action in enumerate(actions, start=1)
    ]