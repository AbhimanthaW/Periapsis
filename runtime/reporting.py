"""Durable, versioned records of planning executions and their calculation trace."""

from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from hashlib import sha256
import json
import sqlite3
from threading import Lock
from time import perf_counter
from uuid import uuid4


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json(value):
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _error(exc):
    code = getattr(exc, "code", None)
    if code is None:
        return {"code": "INTERNAL_ERROR", "message": "Execution did not complete"}
    return {"code": code, "message": str(exc)}


class ReportStore:
    """SQLite transactions publish each trace step and the final result independently."""

    def __init__(self, path=None):
        self._lock = Lock()
        self._db = sqlite3.connect(":memory:" if path is None else path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS report_runs_v1 (
                report_id TEXT PRIMARY KEY, kind TEXT NOT NULL, request_id TEXT NOT NULL,
                started_utc TEXT NOT NULL, finished_utc TEXT, duration_ms REAL,
                status TEXT NOT NULL, revision INTEGER, request TEXT NOT NULL,
                provenance TEXT NOT NULL, result TEXT, error TEXT
            );
            CREATE TABLE IF NOT EXISTS report_steps_v1 (
                report_id TEXT NOT NULL REFERENCES report_runs_v1(report_id), sequence INTEGER NOT NULL,
                name TEXT NOT NULL, kind TEXT NOT NULL, method TEXT NOT NULL,
                started_utc TEXT NOT NULL, duration_ms REAL, status TEXT NOT NULL,
                inputs TEXT NOT NULL, outputs TEXT, error TEXT,
                PRIMARY KEY (report_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS report_artifacts_v1 (
                sha256 TEXT PRIMARY KEY, payload TEXT NOT NULL
            );
        """)

    def close(self):
        with self._lock:
            self._db.close()

    def _write(self, sql, parameters):
        with self._lock, self._db:
            self._db.execute(sql, parameters)

    def artifact(self, payload):
        raw = _json(payload)
        digest = sha256(raw.encode("utf-8")).hexdigest()
        self._write("INSERT OR IGNORE INTO report_artifacts_v1 VALUES (?, ?)", (digest, raw))
        return {"sha256": digest, "href": f"/api/v1/report-artifacts/{digest}"}

    def read_artifact(self, digest):
        with self._lock:
            row = self._db.execute("SELECT payload FROM report_artifacts_v1 WHERE sha256 = ?", (digest,)).fetchone()
        return None if row is None else row["payload"].encode("utf-8")

    @contextmanager
    def run(self, kind, request, provenance):
        report = RunReport(self, kind, request, provenance)
        try:
            yield report
        except Exception as exc:
            report.finish(error=_error(exc))
            raise

    def list(self, limit, offset):
        with self._lock:
            rows = self._db.execute("""
                SELECT report_id, kind, request_id, started_utc, finished_utc, duration_ms, status, revision
                FROM report_runs_v1 ORDER BY rowid DESC LIMIT ? OFFSET ?
            """, (limit + 1, offset)).fetchall()
        return {"schema_version": 1, "reports": [dict(row) for row in rows[:limit]],
                "next_offset": offset + limit if len(rows) > limit else None}

    def read(self, report_id):
        with self._lock:
            # Both reads share a snapshot, including when another process uses the database.
            self._db.execute("BEGIN")
            with self._db:
                row = self._db.execute("SELECT * FROM report_runs_v1 WHERE report_id = ?", (report_id,)).fetchone()
                if row is None:
                    return None
                steps = self._db.execute("""
                    SELECT sequence, name, kind, method, started_utc, duration_ms, status, inputs, outputs, error
                    FROM report_steps_v1 WHERE report_id = ? ORDER BY sequence
                """, (report_id,)).fetchall()
        return {"schema_version": 1, **_decode(row, "request", "provenance", "result", "error"),
                "calculation_trace": [_decode(step, "inputs", "outputs", "error") for step in steps]}


def _decode(row, *columns):
    return dict(row) | {name: None if row[name] is None else json.loads(row[name]) for name in columns}


class RunReport:
    def __init__(self, store, kind, request, provenance):
        self.store = store
        self.id = uuid4().hex
        self.started = perf_counter()
        self.sequence = 0
        store._write("""
            INSERT INTO report_runs_v1 (report_id, kind, request_id, started_utc, status, request, provenance)
            VALUES (?, ?, ?, ?, 'running', ?, ?)
        """, (self.id, kind, request["request_id"], _utc(), _json(request), _json(provenance)))

    @contextmanager
    def stage(self, name, kind, method, inputs):
        self.sequence += 1
        sequence = self.sequence
        self.store._write("""
            INSERT INTO report_steps_v1 (report_id, sequence, name, kind, method, started_utc, status, inputs)
            VALUES (?, ?, ?, ?, ?, ?, 'running', ?)
        """, (self.id, sequence, name, kind, method, _utc(), _json(inputs)))
        started, outputs = perf_counter(), {}
        try:
            yield outputs
            encoded = _json(outputs)
        except Exception as exc:
            self._end_stage(sequence, started, "failed", None, _json(_error(exc)))
            raise
        else:
            self._end_stage(sequence, started, "completed", encoded, None)

    def _end_stage(self, sequence, started, status, outputs, error):
        self.store._write("""
            UPDATE report_steps_v1 SET status = ?, duration_ms = ?, outputs = ?, error = ?
            WHERE report_id = ? AND sequence = ?
        """, (status, round((perf_counter() - started) * 1000, 3), outputs, error, self.id, sequence))

    def finish(self, result=None, *, error=None):
        self.store._write("""
            UPDATE report_runs_v1 SET status = ?, finished_utc = ?, duration_ms = ?, revision = ?, result = ?, error = ?
            WHERE report_id = ? AND status = 'running'
        """, ("completed" if error is None else "failed", _utc(), round((perf_counter() - self.started) * 1000, 3),
              None if result is None else result.get("revision"), None if result is None else _json(result),
              None if error is None else _json(error), self.id))


def stage(report, name, method, inputs, *, kind="deterministic"):
    return nullcontext({}) if report is None else report.stage(name, kind, method, inputs)
