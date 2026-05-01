from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .config import TranscriptionConfig


class TranscribeFile(Protocol):
    def __call__(
        self,
        input_file: Path,
        *,
        model_name: str,
        device: str,
        compute_type: str,
        beam_size: int,
        vad_filter: bool,
        timestamps: bool,
    ) -> Any: ...


def run_transcription(input_file: Path, config: TranscriptionConfig) -> Path:
    module = importlib.import_module(config.module)
    transcribe_file_any = getattr(module, "transcribe_file")
    transcribe_file: TranscribeFile = transcribe_file_any

    transcribe_file(
        input_file,
        model_name=config.model,
        device=config.device,
        compute_type=config.compute_type,
        beam_size=config.beam_size,
        vad_filter=config.vad_filter,
        timestamps=config.timestamps,
    )

    transcript_path = input_file.with_suffix(".txt")
    if not transcript_path.exists():
        raise FileNotFoundError(
            f"Transcription finished, but expected transcript was not created: {transcript_path}"
        )
    return transcript_path
