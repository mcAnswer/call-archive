from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig, load_config, normalize_phone_number
from .db import connect, init_db, row_to_dict
from .files import (
    AUDIO_SUFFIXES,
    ensure_layout,
    first_call,
    load_metadata,
    metadata_phone_number,
    metadata_year,
    move_audio_to_rm,
    move_pair_to_year,
    sha256_file,
    sibling_metadata_path,
)
from .llm import analyze_with_ollama, build_prompt
from .models import ProcessingStatus, RetentionDecision, ReviewStatus
from .transcriber import run_transcription


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="call-archive")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init")
    subparsers.add_parser("scan")

    process_parser = subparsers.add_parser("process")
    process_parser.add_argument("--limit", type=int, default=0)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status", choices=["pending", "reviewed"], default=None)
    list_parser.add_argument("--category", default=None)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("call_id", type=int)

    review_parser = subparsers.add_parser("review")
    review_parser.add_argument("call_id", type=int)
    review_parser.add_argument(
        "--decision",
        choices=[decision.value for decision in RetentionDecision],
        required=True,
    )

    subparsers.add_parser("delete-approved")

    return parser


def command_init(config: AppConfig) -> int:
    ensure_layout(config.ingest_dir, config.storage_dir, config.transcripts_dir, config.notes_dir)
    init_db(config.database_path)
    return 0


def command_scan(config: AppConfig) -> int:
    ensure_layout(config.ingest_dir, config.storage_dir, config.transcripts_dir, config.notes_dir)
    init_db(config.database_path)

    audio_files = sorted(path for path in config.ingest_dir.iterdir() if path.suffix.lower() in AUDIO_SUFFIXES)

    with connect(config.database_path) as connection:
        for audio_path in audio_files:
            metadata_path = sibling_metadata_path(audio_path)
            if not metadata_path.exists():
                print(f"SKIP missing metadata: {audio_path}")
                continue

            try:
                metadata = load_metadata(metadata_path)
            except (json.JSONDecodeError, OSError, ValueError) as error:
                print(f"WARNING invalid metadata JSON: {metadata_path} ({error})")
                continue

            target_audio, target_metadata = move_pair_to_year(audio_path, config.storage_dir, metadata)
            if not target_audio.exists() or not target_metadata.exists():
                print(f"SKIP incomplete move: {audio_path}")
                continue

            try:
                metadata = load_metadata(target_metadata)
            except (json.JSONDecodeError, OSError, ValueError) as error:
                print(f"WARNING invalid metadata JSON after move: {target_metadata} ({error})")
                continue

            call = first_call(metadata)
            output = metadata.get("output", {})
            recording = output.get("recording", {}) if isinstance(output, dict) else {}
            duration = recording.get("duration_secs_total") if isinstance(recording, dict) else None
            phone_number = metadata_phone_number(metadata)
            phone_number_formatted = call.get("phone_number_formatted")
            contact_name = call.get("contact_name") or call.get("caller_name")
            timestamp = str(metadata.get("timestamp", ""))
            year = metadata_year(metadata)
            now = utc_now()

            connection.execute(
                """
                INSERT OR IGNORE INTO calls (
                    audio_path, metadata_path, storage_stem,
                    phone_number, phone_number_formatted, contact_name,
                    direction, timestamp, year, duration_secs,
                    audio_sha256, metadata_sha256,
                    transcription_status, analysis_status,
                    review_status, category,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(target_audio),
                    str(target_metadata),
                    target_audio.stem,
                    phone_number,
                    str(phone_number_formatted) if phone_number_formatted is not None else None,
                    str(contact_name) if contact_name is not None else None,
                    str(metadata.get("direction", "")),
                    timestamp,
                    year,
                    float(duration) if isinstance(duration, int | float) else None,
                    sha256_file(target_audio),
                    sha256_file(target_metadata),
                    ProcessingStatus.NEW.value,
                    ProcessingStatus.NEW.value,
                    ReviewStatus.PENDING.value,
                    "unknown",
                    now,
                    now,
                ),
            )

            connection.execute(
                """
                UPDATE calls
                SET audio_path = ?, metadata_path = ?, updated_at = ?
                WHERE audio_path IN (?, ?) OR metadata_path IN (?, ?)
                """,
                (
                    str(target_audio),
                    str(target_metadata),
                    now,
                    str(audio_path),
                    str(target_audio),
                    str(sibling_metadata_path(audio_path)),
                    str(target_metadata),
                ),
            )
            print(f"SCANNED {target_audio}")

    return 0


def command_process(config: AppConfig, limit: int) -> int:
    ensure_layout(config.ingest_dir, config.storage_dir, config.transcripts_dir, config.notes_dir)
    init_db(config.database_path)

    with connect(config.database_path) as connection:
        query = """
            SELECT * FROM calls
            WHERE transcription_status != ? OR analysis_status != ?
            ORDER BY timestamp ASC
        """
        parameters: list[Any] = [ProcessingStatus.DONE.value, ProcessingStatus.DONE.value]
        if limit > 0:
            query += " LIMIT ?"
            parameters.append(limit)

        rows = connection.execute(query, parameters).fetchall()

        for row in rows:
            call = row_to_dict(row)
            call_id = int(call["id"])
            audio_path = Path(str(call["audio_path"]))
            metadata_path = Path(str(call["metadata_path"]))
            now = utc_now()

            try:
                storage_stem = str(call["storage_stem"] or audio_path.stem)
                transcript_path = config.transcripts_dir / f"{storage_stem}.txt"
                if call["transcription_status"] != ProcessingStatus.DONE.value:
                    generated_transcript_path = run_transcription(audio_path, config.transcription)
                    transcript_path.write_text(
                        generated_transcript_path.read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                    connection.execute(
                        """
                        UPDATE calls
                        SET storage_stem = ?, transcription_status = ?, updated_at = ?, error = NULL
                        WHERE id = ?
                        """,
                        (storage_stem, ProcessingStatus.DONE.value, now, call_id),
                    )

                if transcript_path is None:
                    raise ValueError("Missing transcript path.")

                metadata = load_metadata(metadata_path)
                transcript = transcript_path.read_text(encoding="utf-8")
                phone_number = normalize_phone_number(str(call["phone_number"]))
                normally_delete = phone_number in config.normalized_delete_numbers()

                prompt = build_prompt(
                    metadata=metadata,
                    transcript=transcript,
                    categories=config.categories,
                    normally_delete_by_number=normally_delete,
                )
                note = analyze_with_ollama(
                    config=config.llm,
                    prompt=prompt,
                    categories=config.categories,
                )

                note_path = config.notes_dir / f"{storage_stem}.txt"
                note_path.write_text(
                    note.model_dump_json(indent=2),
                    encoding="utf-8",
                )

                connection.execute(
                    """
                    UPDATE calls
                    SET storage_stem = ?,
                        analysis_status = ?,
                        proposed_retention = ?,
                        category = ?,
                        reason = ?,
                        updated_at = ?,
                        error = NULL
                    WHERE id = ?
                    """,
                    (
                        storage_stem,
                        ProcessingStatus.DONE.value,
                        note.recommended_retention.value,
                        note.category,
                        note.reason,
                        now,
                        call_id,
                    ),
                )
                print(f"PROCESSED #{call_id} {audio_path.name}")

            except Exception as exception:
                connection.execute(
                    """
                    UPDATE calls
                    SET error = ?, updated_at = ?,
                        transcription_status = CASE
                            WHEN transcription_status = ? THEN transcription_status
                            ELSE ?
                        END,
                        analysis_status = ?
                    WHERE id = ?
                    """,
                    (
                        repr(exception),
                        now,
                        ProcessingStatus.DONE.value,
                        ProcessingStatus.FAILED.value,
                        ProcessingStatus.FAILED.value,
                        call_id,
                    ),
                )
                print(f"FAILED #{call_id}: {exception}")

    return 0


def command_list(config: AppConfig, status: str | None, category: str | None) -> int:
    init_db(config.database_path)
    clauses: list[str] = []
    parameters: list[Any] = []

    if status is not None:
        clauses.append("review_status = ?")
        parameters.append(status)
    if category is not None:
        clauses.append("category = ?")
        parameters.append(category)

    query = "SELECT * FROM calls"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY timestamp DESC"

    with connect(config.database_path) as connection:
        rows = connection.execute(query, parameters).fetchall()
        for row in rows:
            call = row_to_dict(row)
            print(
                f"#{call['id']} {call['timestamp']} "
                f"{call['phone_number_formatted'] or call['phone_number']} "
                f"cat={call['category']} proposed={call['proposed_retention']} "
                f"review={call['review_status']} audio={call['audio_path']}"
            )
    return 0


def command_show(config: AppConfig, call_id: int) -> int:
    init_db(config.database_path)
    with connect(config.database_path) as connection:
        row = connection.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
        if row is None:
            raise ValueError(f"Call not found: {call_id}")

        call = row_to_dict(row)
        print(json.dumps(call, ensure_ascii=False, indent=2))

        note_path_raw = call.get("note_path")
        storage_stem = call.get("storage_stem")
        if isinstance(storage_stem, str) and storage_stem:
            note_path = config.notes_dir / f"{storage_stem}.txt"
            if note_path.exists():
                print("\nNOTE:")
                print(note_path.read_text(encoding="utf-8"))

    return 0


def command_review(config: AppConfig, call_id: int, decision: str) -> int:
    init_db(config.database_path)
    with connect(config.database_path) as connection:
        row = connection.execute("SELECT id FROM calls WHERE id = ?", (call_id,)).fetchone()
        if row is None:
            raise ValueError(f"Call not found: {call_id}")

        connection.execute(
            """
            UPDATE calls
            SET reviewed_retention = ?, review_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (decision, ReviewStatus.REVIEWED.value, utc_now(), call_id),
        )
        print(f"REVIEWED #{call_id}: {decision}")
    return 0


def command_delete_approved(config: AppConfig) -> int:
    init_db(config.database_path)
    with connect(config.database_path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM calls
            WHERE review_status = ?
              AND reviewed_retention = ?
            ORDER BY timestamp ASC
            """,
            (
                ReviewStatus.REVIEWED.value,
                RetentionDecision.DELETE_AUDIO_KEEP_TRANSCRIPT.value,
            ),
        ).fetchall()

        for row in rows:
            call = row_to_dict(row)
            audio_path = Path(str(call["audio_path"]))
            if not audio_path.exists():
                print(f"SKIP missing audio #{call['id']}: {audio_path}")
                continue

            target = move_audio_to_rm(audio_path, config.storage_dir)
            connection.execute(
                """
                UPDATE calls
                SET audio_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(target), utc_now(), int(call["id"])),
            )
            print(f"MOVED_TO_RM #{call['id']}: {target}")

    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(args.config)

    if args.command == "init":
        return command_init(config)
    if args.command == "scan":
        return command_scan(config)
    if args.command == "process":
        return command_process(config, int(args.limit))
    if args.command == "list":
        return command_list(config, args.status, args.category)
    if args.command == "show":
        return command_show(config, int(args.call_id))
    if args.command == "review":
        return command_review(config, int(args.call_id), str(args.decision))
    if args.command == "delete-approved":
        return command_delete_approved(config)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
