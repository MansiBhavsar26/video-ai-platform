from app.services.developer_action_pipeline import (
    build_developer_action_timeline,
)


segments = [
    {
        "start_time": 109.77,
        "end_time": 114.69,
        "text": "to use create react app let's just",
    },
    {
        "start_time": 150.03,
        "end_time": 158.25,
        "text": "right here so we're gonna do CDU react tutorial and then we're going to do yarn",
    },
    {
        "start_time": 152.19,
        "end_time": 160.53,
        "text": "tutorial and then we're going to do yarn start and that's going to automatically",
    },
    {
        "start_time": 1864.93,
        "end_time": 1869.76,
        "text": "and it says you're adding a router we",
    },
    {
        "start_time": 1867.09,
        "end_time": 1872.57,
        "text": "can do NPM install that save reactor out",
    },
    {
        "start_time": 1869.76,
        "end_time": 1877.86,
        "text": "or Dom so let's go ahead and do that",
    },
    {
        "start_time": 1893.88,
        "end_time": 1903.03,
        "text": "replace our main component with this code right here let's replace app dot",
    },
    {
        "start_time": 1903.03,
        "end_time": 1908.07,
        "text": "J's here save it",
    },
    {
        "start_time": 2288.21,
        "end_time": 2295.00,
        "text": "create a new file called product item Jas",
    },
    {
        "start_time": 2657.25,
        "end_time": 2665.00,
        "text": "let's name this file add item J s",
    },
]


actions = build_developer_action_timeline(
    segments
)


print("=" * 80)
print("DEVELOPER ACTION TIMELINE")
print("=" * 80)

print(f"ACTIONS FOUND: {len(actions)}")
print()

for index, action in enumerate(
    actions,
    start=1,
):

    print(
        f"ACTION {index}"
    )

    print(
        f"TYPE: {action['action']}"
    )

    print(
        f"VALUE: {action['value']}"
    )

    if "operation" in action:
        print(
            f"OPERATION: {action['operation']}"
        )

    print(
        f"TIME: "
        f"{action['start_time']:.2f}s - "
        f"{action['end_time']:.2f}s"
    )

    print(
        f"CONFIDENCE: "
        f"{action['confidence']}"
    )

    print(
        f"EVIDENCE: "
        f"{action['evidence']}"
    )

    print("-" * 80)