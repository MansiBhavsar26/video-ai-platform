from app.services.file_action_extractor import (
    extract_file_edit_actions,
)


TEST_CASES = [
    {
        "name": "ProductItem creation",
        "segments": [
            {
                "start_time": 2288.21,
                "end_time": 2295.00,
                "text": "create a new file called product item Jas",
            },
        ],
    },
    {
        "name": "AddItem creation",
        "segments": [
            {
                "start_time": 2657.25,
                "end_time": 2665.00,
                "text": "let's name this file add item J s",
            },
        ],
    },
    {
        "name": "App.js replacement",
        "segments": [
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
        ],
    },
]


for test_case in TEST_CASES:

    print("=" * 80)
    print(test_case["name"])
    print("=" * 80)

    actions = extract_file_edit_actions(
        test_case["segments"]
    )

    print(f"ACTIONS FOUND: {len(actions)}")

    for action in actions:
        print(f"ACTION: {action['action']}")
        print(f"FILE: {action['value']}")
        print(f"OPERATION: {action['operation']}")
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

    print()