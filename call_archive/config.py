from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class TranscriptionConfig(BaseModel):
    module: str = "transcribe"
    model: str = "medium"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    vad_filter: bool = True
    timestamps: bool = False


class LlmConfig(BaseModel):
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str
    timeout_secs: int = 180


class RetentionConfig(BaseModel):
    normally_delete_numbers: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    recordings_dir: Path
    database_path: Path
    transcripts_dir: Path
    notes_dir: Path
    transcription: TranscriptionConfig
    llm: LlmConfig
    categories: list[str]
    retention: RetentionConfig

    def normalized_delete_numbers(self) -> set[str]:
        return {normalize_phone_number(number) for number in self.retention.normally_delete_numbers}


def normalize_phone_number(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(character for character in value if character.isdigit())


def load_config(path: Path) -> AppConfig:
    data: Any
    with path.open("rt", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    config = AppConfig.model_validate(data)
    if not config.categories:
        raise ValueError("Config must define at least one category.")
    if "unknown" not in config.categories:
        raise ValueError("Config categories must include 'unknown'.")
    return config
