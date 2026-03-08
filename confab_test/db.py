"""SQLite logging for all test runs and results."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from confab_test.tests.base import TestResult


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    """Create tables if they don't exist."""
    conn = _connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            model       TEXT NOT NULL,
            started_at  TEXT NOT NULL,
            finished_at TEXT,
            config_json TEXT
        );

        CREATE TABLE IF NOT EXISTS results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES runs(id),
            test_id     TEXT NOT NULL,
            category    TEXT NOT NULL,
            test_name   TEXT NOT NULL,
            prompts     TEXT NOT NULL,
            responses   TEXT NOT NULL,
            verdict     TEXT NOT NULL,
            score       REAL NOT NULL,
            reason      TEXT NOT NULL,
            duration    REAL,
            metadata    TEXT,
            timestamp   TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def create_run(db_path: str, model: str, config: dict) -> int:
    conn = _connect(db_path)
    cur = conn.execute(
        "INSERT INTO runs (model, started_at, config_json) VALUES (?,?,?)",
        (model, datetime.utcnow().isoformat(), json.dumps(config)),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def finish_run(db_path: str, run_id: int) -> None:
    conn = _connect(db_path)
    conn.execute(
        "UPDATE runs SET finished_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), run_id),
    )
    conn.commit()
    conn.close()


def save_result(db_path: str, run_id: int, result: TestResult) -> None:
    conn = _connect(db_path)
    conn.execute(
        """INSERT INTO results
           (run_id, test_id, category, test_name, prompts, responses,
            verdict, score, reason, duration, metadata, timestamp)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,
            result.test_id,
            result.category,
            result.test_name,
            json.dumps(result.prompts),
            json.dumps(result.responses),
            result.verdict,
            result.score,
            result.reason,
            result.duration,
            json.dumps(result.metadata),
            result.timestamp.isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def load_run_results(db_path: str, run_id: int) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM results WHERE run_id=? ORDER BY id", (run_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_all_runs(db_path: str) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    rows = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
