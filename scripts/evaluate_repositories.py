"""Run a reproducible API-level retrieval evaluation on local checkouts.

Usage: python -m scripts.evaluate_repositories flask=/path/to/flask ...
"""

import json
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

CASES = {
    "flask": [
        {
            "question": "How does Flask.wsgi_app handle a WSGI request and app context?",
            "expected_symbols": ["flask.app.Flask.wsgi_app"],
        },
        {
            "question": "Where does Flask dispatch a matched request to its view?",
            "expected_symbols": ["flask.app.Flask.dispatch_request"],
        },
        {
            "question": "Which method performs request preprocessing before dispatch?",
            "expected_symbols": ["flask.app.Flask.preprocess_request"],
        },
    ],
    "requests": [
        {
            "question": "How does the top-level request function dispatch HTTP requests?",
            "expected_symbols": ["requests.api.request"],
        },
        {
            "question": "Where does Session prepare a request before sending?",
            "expected_symbols": ["requests.sessions.Session.prepare_request"],
        },
        {
            "question": "Which Session method chooses a transport adapter?",
            "expected_symbols": ["requests.sessions.Session.get_adapter"],
        },
    ],
    "httpx": [
        {
            "question": "How does the synchronous Client send a request?",
            "expected_symbols": ["httpx._client.Client.send"],
        },
        {
            "question": "Where does Client handle authentication during send?",
            "expected_symbols": ["httpx._client.Client._send_handling_auth"],
        },
        {
            "question": "Which method chooses the transport for one request?",
            "expected_symbols": ["httpx._client.Client._send_single_request"],
        },
    ],
    "pytest": [
        {
            "question": "Where is the pytest session wrapped for execution and cleanup?",
            "expected_symbols": ["_pytest.main.wrap_session"],
        },
        {
            "question": "What loops through collected tests during a pytest run?",
            "expected_symbols": ["_pytest.main.pytest_runtestloop"],
        },
        {
            "question": "Which runner method records a test call report?",
            "expected_symbols": ["_pytest.runner.call_and_report"],
        },
    ],
    "rich": [
        {
            "question": "How does Console.print render output?",
            "expected_symbols": ["rich.console.Console.print"],
        },
        {
            "question": "Which Console method measures renderable width?",
            "expected_symbols": ["rich.console.Console.measure"],
        },
        {
            "question": "Where are Console segments converted to terminal output?",
            "expected_symbols": ["rich.console.Console._render_buffer"],
        },
    ],
    "petclinic": [
        {
            "question": "How does OwnerController process the owner find form?",
            "expected_symbols": [
                "org.springframework.samples.petclinic.owner.OwnerController.processFindForm"
            ],
        },
        {
            "question": "Where is a new owner creation form initialized?",
            "expected_symbols": [
                "org.springframework.samples.petclinic.owner.OwnerController.initCreationForm"
            ],
        },
        {
            "question": "Which controller method displays one owner?",
            "expected_symbols": [
                "org.springframework.samples.petclinic.owner.OwnerController.showOwner"
            ],
        },
    ],
    "commons-lang": [
        {
            "question": "What does StringUtils.isEmpty return for a null or empty sequence?",
            "expected_symbols": ["org.apache.commons.lang3.StringUtils.isEmpty"],
        },
        {
            "question": "How does StringUtils identify whitespace-only text?",
            "expected_symbols": ["org.apache.commons.lang3.StringUtils.isBlank"],
        },
        {
            "question": "Which method checks that a CharSequence is not blank?",
            "expected_symbols": ["org.apache.commons.lang3.StringUtils.isNotBlank"],
        },
    ],
    "mockito": [
        {
            "question": "How does MockitoCore create a mock using settings?",
            "expected_symbols": ["org.mockito.internal.MockitoCore.mock"],
        },
        {
            "question": "Where does MockitoCore verify a mock with VerificationMode?",
            "expected_symbols": ["org.mockito.internal.MockitoCore.verify"],
        },
        {
            "question": "Which handler processes a mock invocation?",
            "expected_symbols": ["org.mockito.internal.handler.MockHandlerImpl.handle"],
        },
    ],
}


def main():
    import os

    with tempfile.TemporaryDirectory(prefix="devpilot-evaluation-") as data:
        os.environ["DEVPILOT_DATA"] = data
        from backend import db
        from backend.main import app

        report = {}
        with TestClient(app) as client:
            for item in sys.argv[1:]:
                label, source = item.split("=", 1)
                if label not in CASES or not Path(source).is_dir():
                    raise SystemExit(
                        f"Expected {label}=an existing directory; labels: {list(CASES)}"
                    )
                response = client.post("/api/repositories", json={"source": source, "name": label})
                repo_id = response.json()["id"]
                for _ in range(300):
                    repo = client.get(f"/api/repositories/{repo_id}").json()
                    if repo["status"] in ("ready", "failed"):
                        break
                    time.sleep(0.1)
                if repo["status"] != "ready":
                    raise SystemExit(f"{label}: {repo['status']}: {repo['error']}")
                result = client.post(
                    f"/api/repositories/{repo_id}/evaluate", json={"cases": CASES[label]}
                )
                result.raise_for_status()
                indexed = {symbol["qualified"] for symbol in db.symbols(repo_id)}
                missing = sorted(
                    symbol
                    for case in CASES[label]
                    for symbol in case["expected_symbols"]
                    if symbol not in indexed
                )
                report[label] = {
                    "commit": repo["commit_id"],
                    "fingerprint": repo["fingerprint"],
                    "stats": repo["stats"],
                    "evaluation": result.json(),
                    "missing_expected_symbols": missing,
                }
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
