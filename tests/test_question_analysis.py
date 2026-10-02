from backend.question_analysis import answer_aspects, question_aspects


def test_question_aspects_preserve_qualified_names_and_direct_question_parts():
    parts = question_aspects(
        "Trace BaseModel.model_dump() into its serializer. Which method returns the dictionary, "
        "and how is exclude_none passed to it?"
    )
    assert len(parts) == 3
    assert "BaseModel.model_dump()" in parts[0]
    assert "dictionary" in parts[1]
    assert "exclude_none" in parts[2]


def test_question_aspects_split_a_multistage_trace_into_requested_steps():
    parts = question_aspects(
        "A BaseModel field refers to a type that is undefined when the class is created. "
        "Trace what happens during class creation and on the first validation attempt after "
        "that type is defined: how is the validator mocked, how is rebuilding triggered, "
        "and where is the real validator installed? What happens if the type is still undefined?"
    )
    assert len(parts) == 6
    assert "class creation" in parts[0]
    assert "first validation attempt" in parts[1]
    assert "validator mocked" in parts[2]
    assert "rebuilding triggered" in parts[3]
    assert "validator installed" in parts[4]
    assert "still undefined" in parts[5]
    grouped = answer_aspects(
        "A BaseModel field refers to a type that is undefined when the class is created. "
        "Trace what happens during class creation and on the first validation attempt after "
        "that type is defined: how is the validator mocked, how is rebuilding triggered, "
        "and where is the real validator installed? What happens if the type is still undefined?"
    )
    assert len(grouped) == 6
    assert all(
        any(
            term in group
            for term in ("creation", "validation", "mocked", "triggered", "installed", "undefined")
        )
        for group in grouped
    )
