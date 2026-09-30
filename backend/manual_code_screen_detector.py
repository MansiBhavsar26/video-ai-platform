from app.services.code_screen_detector import (
    detect_code_screen_windows,
)


actions = [
    {
        "action": "run_command",
        "value": "npm install react-router-dom",
        "start_time": 1864.93,
        "end_time": 1877.86,
    },
    {
        "action": "edit_file",
        "value": "App.js",
        "operation": "replace",
        "start_time": 1893.88,
        "end_time": 1908.07,
    },
    {
        "action": "create_file",
        "value": "ProductItem.js",
        "operation": "create",
        "start_time": 2288.21,
        "end_time": 2295.00,
    },
]


windows = detect_code_screen_windows(
    actions,
    padding_seconds=5.0,
)


print("CODE WINDOWS:", len(windows))

for index, window in enumerate(windows, start=1):

    print()
    print(f"WINDOW {index}")
    print(
        f"TIME: "
        f"{window['start_time']:.2f}s - "
        f"{window['end_time']:.2f}s"
    )
    print(
        f"ACTION: {window['action']}"
    )
    print(
        f"VALUE: {window['value']}"
    )