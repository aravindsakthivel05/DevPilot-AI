import json
from pathlib import Path

from backend.retrieval import asks_external_state


def test_external_runtime_questions_are_identified():
    cases = [
        json.loads(line)
        for line in Path("evaluation/cases-v2.jsonl").read_text().splitlines()
        if line.strip()
    ]
    for case in cases:
        if not case["answerable"]:
            assert asks_external_state(case["question"]), case["id"]


def test_normal_repository_questions_are_not_abstained():
    for question in (
        "How does Flask.wsgi_app handle a WSGI request and app context?",
        "How does the current implementation parse options?",
        "Which method reads the database configuration from source?",
    ):
        assert not asks_external_state(question)
