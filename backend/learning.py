"""Persistent, human-reviewed examples for cross-repository retrieval evaluation."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from . import db


def _now():
    return datetime.now(timezone.utc).isoformat()


def _decode(row):
    result = dict(row)
    result["initial_result"] = json.loads(result["initial_result"] or "null")
    result["review"] = json.loads(result["review"] or "null")
    result["review_history"] = json.loads(result["review_history"])
    return result


def get_case(repo_id, case_id):
    with db.connection() as connection:
        row = connection.execute(
            """SELECT learning_cases.*,
                      learning_repository_splits.split AS repository_split
               FROM learning_cases
               LEFT JOIN learning_repository_splits
                 ON learning_repository_splits.repo_id=learning_cases.repo_id
               WHERE learning_cases.repo_id=? AND learning_cases.id=?""",
            (repo_id, case_id),
        ).fetchone()
    return _decode(row) if row else None


def list_cases(repo_id, status="all", limit=100, offset=0):
    where = "learning_cases.repo_id=?"
    values = [repo_id]
    if status != "all":
        where += " AND learning_cases.review_status=?"
        values.append(status)
    values.extend((limit, offset))
    with db.connection() as connection:
        rows = connection.execute(
            f"""SELECT learning_cases.*,
                       learning_repository_splits.split AS repository_split
                FROM learning_cases
                LEFT JOIN learning_repository_splits
                  ON learning_repository_splits.repo_id=learning_cases.repo_id
                WHERE {where}
                ORDER BY learning_cases.created_at DESC
                LIMIT ? OFFSET ?""",
            values,
        ).fetchall()
    return [_decode(row) for row in rows]


def create_case(repo_id, question, investigation_id=None):
    repo = db.repository(repo_id)
    if not repo or repo["status"] != "ready":
        raise ValueError("Repository snapshot is not ready.")

    initial_result = None
    if investigation_id:
        with db.connection() as connection:
            run = connection.execute(
                "SELECT repo_id,created_at,question,result FROM investigations WHERE id=?",
                (investigation_id,),
            ).fetchone()
        if not run or run["repo_id"] != repo_id:
            raise ValueError("Investigation does not belong to this repository.")
        if run["question"] != question:
            raise ValueError("Question must match the saved investigation.")
        result = json.loads(run["result"])
        if result.get("snapshot") != repo["fingerprint"]:
            raise ValueError("Investigation belongs to a different repository snapshot.")
        initial_result = {
            "answer": result.get("answer", ""),
            "generated": bool(result.get("generated")),
            "abstained": bool(result.get("abstained")),
            "warning": result.get("warning"),
            "citation_check": result.get("citation_check"),
            "model": result.get("model"),
            "answer_prompt_version": result.get("answer_prompt_version"),
            "retrieval_version": result.get("retrieval_version"),
            "evidence": [
                {
                    key: item.get(key)
                    for key in ("qualified", "path", "start_line", "end_line", "reason")
                }
                for item in result.get("evidence", [])
            ],
        }
        with db.connection() as connection:
            existing = connection.execute(
                "SELECT id FROM learning_cases WHERE repo_id=? AND investigation_id=?",
                (repo_id, investigation_id),
            ).fetchone()
        if existing:
            return get_case(repo_id, existing["id"])

    case_id = uuid.uuid4().hex
    try:
        with db.connection() as connection:
            connection.execute(
                """INSERT INTO learning_cases
                   (id,repo_id,snapshot,investigation_id,created_at,question,initial_result)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    case_id,
                    repo_id,
                    repo["fingerprint"],
                    investigation_id,
                    _now(),
                    question,
                    json.dumps(initial_result) if initial_result else None,
                ),
            )
    except sqlite3.IntegrityError:
        if investigation_id:
            with db.connection() as connection:
                existing = connection.execute(
                    "SELECT id FROM learning_cases WHERE repo_id=? AND investigation_id=?",
                    (repo_id, investigation_id),
                ).fetchone()
            if existing:
                return get_case(repo_id, existing["id"])
        raise
    return get_case(repo_id, case_id)


def review_case(repo_id, case_id, review):
    repo = db.repository(repo_id)
    if not repo or repo["status"] != "ready":
        raise ValueError("Repository snapshot is not ready.")
    case = get_case(repo_id, case_id)
    if not case:
        raise KeyError("Learning case not found for this repository.")
    if case["snapshot"] != repo["fingerprint"]:
        raise ValueError("Repository snapshot changed; create a new review case.")
    if not review["notes"].strip():
        raise ValueError("Review notes are required.")

    expected = review["expected_symbols"]
    if len(expected) != len(set(expected)):
        raise ValueError("Expected symbols must be unique.")
    if review["answerable"]:
        if not expected:
            raise ValueError("Answerable cases require at least one expected symbol.")
        if not (review.get("expected_answer") or "").strip():
            raise ValueError("Answerable cases require a reviewed expected answer.")
        if not review["source_refs"]:
            raise ValueError("Answerable cases require reviewed source references.")
    elif expected or review["source_refs"]:
        raise ValueError("Unanswerable cases cannot label supporting symbols or source ranges.")

    if case["initial_result"] and case["initial_result"].get("generated"):
        if not isinstance(review.get("answer_correct"), bool):
            raise ValueError("Review the generated answer's correctness.")
        if not isinstance(review.get("all_claims_supported"), bool):
            raise ValueError("Review whether every generated claim is source-supported.")
    if case["initial_result"] and not isinstance(review.get("appropriate_abstention"), bool):
        raise ValueError("Review whether the response answered or abstained appropriately.")

    with db.connection() as connection:
        symbols = connection.execute(
            "SELECT qualified,path,start_line,end_line FROM symbols WHERE repo_id=?",
            (repo_id,),
        ).fetchall()
        by_name = {}
        for symbol in symbols:
            by_name.setdefault(symbol["qualified"], []).append(dict(symbol))
        missing = sorted(set(expected) - by_name.keys())
        if missing:
            raise ValueError("Expected symbols are not in this snapshot: " + ", ".join(missing))
        for source_ref in review["source_refs"]:
            matches = [
                symbol
                for symbol in by_name.get(source_ref["qualified"], [])
                if symbol["path"] == source_ref["path"]
                and symbol["start_line"] <= source_ref["start_line"]
                and source_ref["end_line"] <= symbol["end_line"]
            ]
            if source_ref["qualified"] not in expected or not matches:
                raise ValueError(
                    "Each source range must fall inside an expected symbol in this snapshot."
                )
        referenced = {item["qualified"] for item in review["source_refs"]}
        if review["answerable"] and referenced != set(expected):
            raise ValueError("Add a reviewed source range for every expected symbol.")

        split = connection.execute(
            "SELECT split FROM learning_repository_splits WHERE repo_id=?", (repo_id,)
        ).fetchone()
        if split and split["split"] != review["split"]:
            raise ValueError(
                f"All cases from this repository must stay in its {split['split']} split."
            )
        if not split:
            connection.execute(
                "INSERT INTO learning_repository_splits(repo_id,split,assigned_at) VALUES (?,?,?)",
                (repo_id, review["split"], _now()),
            )

        current = connection.execute(
            "SELECT review,review_history FROM learning_cases WHERE id=? AND repo_id=?",
            (case_id, repo_id),
        ).fetchone()
        history = json.loads(current["review_history"])
        if current["review"]:
            history.append(json.loads(current["review"]))
        connection.execute(
            """UPDATE learning_cases
               SET review_status='reviewed',review=?,review_history=?
               WHERE id=? AND repo_id=?""",
            (
                json.dumps({**review, "reviewed_at": _now()}),
                json.dumps(history),
                case_id,
                repo_id,
            ),
        )
    return get_case(repo_id, case_id)
