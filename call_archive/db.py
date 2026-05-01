from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


SCHEMA: str = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY,
    audio_path TEXT UNIQUE NOT NULL,
    metadata_path TEXT NOT NULL,
    transcript_path TEXT,
    note_path TEXT,

    phone_number TEXT,
    phone_number_formatted TEXT,
    contact_name TEXT,
    direction TEXT,
    timestamp TEXT,
    year TEXT,
    duration_secs REAL,

    audio_sha256 TEXT NOT NULL,
    metadata_sha256 TEXT NOT NULL,

    transcription_status TEXT NOT NULL,
    analysis_status TEXT NOT NULL,
    proposed_retention TEXT,
    reviewed_retention TEXT,
    review_status TEXT NOT NULL,

    category TEXT NOT NULL DEFAULT 'unknown',
    reason TEXT,
    error TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_calls_review_status ON calls(review_status);
CREATE INDEX IF NOT EXISTS idx_calls_phone_number ON calls(phone_number);
CREATE INDEX IF NOT EXISTS idx_calls_category ON calls(category);
CREATE INDEX IF NOT EXISTS idx_calls_timestamp ON calls(timestamp);
"""


@contextmanager
def connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(database_path: Path) -> None:
    with connect(database_path) as connection:
        connection.executescript(SCHEMA)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
