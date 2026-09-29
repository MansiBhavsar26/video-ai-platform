from app.services.developer_action_pipeline import build_tutorial_steps


def _segment(start, text):
    return {"start_time": start, "end_time": start + 3, "text": text}


def test_transcript_actions_cover_implementation_language_and_preserve_evidence():
    steps = build_tutorial_steps([
        _segment(10, "Now let's create our Product Item component"),
        _segment(20, "Add a route for products"),
        _segment(30, "Define the Product model"),
        _segment(40, "Add a function called loadProducts"),
        _segment(50, "Connect the frontend to the products API"),
        _segment(60, "Add state"),
    ])

    assert [step["action"] for step in steps] == [
        "create_component",
        "create_route",
        "create_model",
        "create_function",
        "implement",
        "implement",
    ]
    assert steps[0]["name"] == "ProductItem"
    assert steps[0]["path"] == "ProductItem"
    assert steps[0]["start_time"] == 10
    assert steps[0]["end_time"] == 13
    assert steps[0]["evidence"] == {
        "source": "transcript",
        "text": "Now let's create our Product Item component",
    }
    assert steps[0]["confidence"] > steps[-1]["confidence"]


def test_transcript_actions_reject_explanations_and_hypotheticals():
    steps = build_tutorial_steps([
        _segment(10, "We already installed the package"),
        _segment(20, "You can create a component if you want to"),
        _segment(30, "This component displays products"),
        _segment(40, "Later we'll create the API route"),
    ])

    assert steps == []


def test_repeated_component_action_is_deduplicated():
    steps = build_tutorial_steps([
        _segment(10, "Let's create a ProductItem component"),
        _segment(12, "We're creating the ProductItem component"),
    ])

    assert len(steps) == 1
    assert steps[0]["action"] == "create_component"