from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import normalize_phone_number


AUDIO_SUFFIXES: set[str] = {".oga", ".ogg", ".opus", ".m4a", ".mp3", ".wav", ".flac"}


def ensure_layout(recordings_dir: Path, transcripts_dir: Path, notes_dir: Path) -> None:
    for directory in [
        recordings_dir,
        recordings_dir / "new",
        recordings_dir / "rm",
        transcripts_dir,
        notes_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def load_metadata(path: Path) -> dict[str, Any]:
    with path.open("rt", encoding="utf-8") as handle:
        data: Any = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Metadata is not an object: {path}")
    return data


def metadata_year(metadata: dict[str, Any]) -> str:
    timestamp = str(metadata.get("timestamp", ""))
    if len(timestamp) >= 4 and timestamp[:4].isdigit():
        return timestamp[:4]
    unix_ms = metadata.get("timestamp_unix_ms")
    if isinstance(unix_ms, int):
        return datetime.fromtimestamp(unix_ms / 1000).strftime("%Y")
    return datetime.now().strftime("%Y")


def first_call(metadata: dict[str, Any]) -> dict[str, Any]:
    calls = metadata.get("calls")
    if isinstance(calls, list) and calls and isinstance(calls[0], dict):
        return calls[0]
    return {}


def metadata_phone_number(metadata: dict[str, Any]) -> str:
    call = first_call(metadata)
    raw = call.get("phone_number")
    return normalize_phone_number(str(raw)) if raw is not None else ""


def sibling_metadata_path(audio_path: Path) -> Path:
    return audio_path.with_suffix(".json")


def transcript_path_for_audio(audio_path: Path) -> Path:
    return audio_path.with_suffix(".txt")


def move_pair_to_year(audio_path: Path, recordings_dir: Path, metadata: dict[str, Any]) -> tuple[Path, Path]:
    year = metadata_year(metadata)
    target_dir = recordings_dir / year
    target_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = sibling_metadata_path(audio_path)
    target_audio = unique_target(target_dir / audio_path.name)
    target_metadata = target_audio.with_suffix(".json")

    shutil.move(str(audio_path), str(target_audio))
    shutil.move(str(metadata_path), str(target_metadata))

    return target_audio, target_metadata


def unique_target(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    counter = 1
    while True:
        candidate = parent / f"{stem}.{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def move_audio_to_rm(audio_path: Path, recordings_dir: Path) -> Path:
    rm_dir = recordings_dir / "rm"
    rm_dir.mkdir(parents=True, exist_ok=True)
    target = unique_target(rm_dir / audio_path.name)
    shutil.move(str(audio_path), str(target))
    return target
