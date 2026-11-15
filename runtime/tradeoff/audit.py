"""T7 · Audit log: append-only JSON lines with a hash chain.

Each line is one canonical JSON record holding the previous record's hash and
its own. Editing, reordering or removing any line except the tail breaks
``verify``. Removing lines from the END cannot be detected by the chain alone;
keep the latest hash somewhere else if that matters.
"""
import json
from pathlib import Path

from ._common import canonical, digest, refuse, utc

CODE = "INVALID_AUDIT"
SCHEMA = "tradeoff-audit-v1"
GENESIS = "0" * 64
KINDS = ("assessment", "acceptance", "refusal", "withdrawal")


def _records(path):
    path = Path(path)
    if not path.exists():
        return []
    return path.read_bytes().split(b"\n")[:-1] if path.read_bytes() else []


def verify(path):
    """{"ok", "records", "first_bad_line", "reason", "head_sha256"}; lines are 1-based."""
    previous, count = GENESIS, 0
    raw = Path(path).read_bytes() if Path(path).exists() else b""
    if raw and not raw.endswith(b"\n"):
        return {"ok": False, "records": 0, "first_bad_line": raw.count(b"\n") + 1,
                "reason": "last line is incomplete", "head_sha256": None}
    for number, line in enumerate(_records(path), start=1):
        bad = lambda reason: {"ok": False, "records": count, "first_bad_line": number,   # noqa: E731
                              "reason": reason, "head_sha256": None}
        try:
            record = json.loads(line)
        except ValueError:
            return bad("line is not JSON")
        if not isinstance(record, dict) or record.get("schema") != SCHEMA:
            return bad("unexpected record schema")
        claimed = record.get("sha256")
        body = {k: v for k, v in record.items() if k != "sha256"}
        if canonical(record) != line:
            return bad("line is not in canonical form")
        if record.get("seq") != number:
            return bad("sequence number does not match the line")
        if record.get("prev_sha256") != previous:
            return bad("previous-record hash does not match")
        if digest(body) != claimed:
            return bad("record hash does not match its content")
        previous, count = claimed, count + 1
    return {"ok": True, "records": count, "first_bad_line": None, "reason": None,
            "head_sha256": previous if count else None}


def append(path, kind, body, *, time_utc):
    """Append one record. Refuses to extend a log that does not verify."""
    if kind not in KINDS:
        refuse(CODE, f"kind must be one of {list(KINDS)}")
    utc(time_utc, "time_utc", CODE)
    state = verify(path)
    if not state["ok"]:
        refuse(CODE, f"audit log does not verify at line {state['first_bad_line']}: {state['reason']}")
    record = {"schema": SCHEMA, "seq": state["records"] + 1, "time_utc": time_utc, "kind": kind,
              "prev_sha256": state["head_sha256"] or GENESIS, "body": json.loads(canonical(body))}
    record["sha256"] = digest(record)
    with open(path, "ab") as handle:
        handle.write(canonical(record) + b"\n")
    return record


def assessment_body(result):
    """Audit body for one assessment set: input hashes, model version, options and classes."""
    first = result["assessments"][0]
    return {"inputs": first["inputs"], "model": result["model"],
            "amber_gates": result["amber_gates"], "authority": result["authority"],
            "return_now": result["return_now"],
            "options": [{"option_id": a["option_id"], "class": a["class"],
                         "first_failing_rule": a["first_failing_rule"]} for a in result["assessments"]]}


def record_assessment(path, result):
    return append(path, "assessment", assessment_body(result), time_utc=result["assessed_utc"])


def record_decision(path, record):
    """Append an acceptance, refusal or withdrawal record (signatures and reasons included)."""
    kind = {"accepted": "acceptance", "refused": "refusal", "withdrawn": "withdrawal"}.get(record.get("status"))
    if kind is None:
        refuse(CODE, "record status must be accepted, refused or withdrawn")
    when = record["withdrawn"]["utc"] if kind == "withdrawal" else record["decided_utc"]
    return append(path, kind, record, time_utc=when)


def accepted_count(path, envelope_id):
    """AMBER acceptances recorded for this envelope. A log that does not verify is refused."""
    state = verify(path)
    if not state["ok"]:
        refuse(CODE, f"audit log does not verify at line {state['first_bad_line']}: {state['reason']}")
    total = 0
    for line in _records(path):
        record = json.loads(line)
        if record["kind"] == "acceptance" and record["body"].get("envelope_id") == envelope_id:
            total += 1
    return total
