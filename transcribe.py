from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcribe audio/video with faster-whisper.")
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to the input audio or video file.",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model name, e.g. tiny, base, small, medium, large-v3. Default: small.",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        choices=["cpu", "cuda", "auto"],
        help="Execution device. Default: cuda.",
    )
    parser.add_argument(
        "--compute-type",
        default="float32",
        help="CTranslate2 compute type. On GTX 1080 Ti, float32 is the safe default.",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=5,
        help="Beam size for decoding. Default: 5.",
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="Print segment start/end timestamps before text.",
    )
    parser.add_argument(
        "--vad-filter",
        action="store_true",
        help="Enable voice activity detection filter.",
    )
    return parser


def format_segment(segment: Segment, include_timestamps: bool) -> str:
    if include_timestamps:
        return f"[{segment.start:.2f} -> {segment.end:.2f}] {segment.text.strip()}"
    return segment.text.strip()


def iter_output_lines(segments: Iterable[Segment], include_timestamps: bool) -> Iterable[str]:
    for segment in segments:
        text: str = format_segment(segment, include_timestamps)
        if text:
            yield text


def transcribe_file(
    input_file: Path,
    *,
    model_name: str,
    device: str,
    compute_type: str,
    beam_size: int,
    vad_filter: bool,
    timestamps: bool,
) -> Path:
    output_file: Path = input_file.with_suffix(".txt")

    model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        download_root="/data/models/faster-whisper",
    )

    transcribe_kwargs: dict[str, object] = {
        "beam_size": beam_size,
        "condition_on_previous_text": False,
    }

    if vad_filter:
        transcribe_kwargs["vad_filter"] = True

    segments, info = model.transcribe(str(input_file), **transcribe_kwargs)

    with output_file.open("wt", encoding="utf-8") as f:
        f.write(
            f"# language={info.language} "
            f"probability={info.language_probability:.3f}\n"
        )

        for line in iter_output_lines(segments, timestamps):
            f.write(f"{line}\n")

    return output_file


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    input_file: Path = args.input_file

    if not input_file.exists():
        parser.error(f"Input file does not exist: {input_file}")

    transcribe_file(
        input_file,
        model_name=args.model,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        vad_filter=args.vad_filter,
        timestamps=args.timestamps,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
