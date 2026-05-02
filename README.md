# call-archive

Local, privacy-first pipeline for processing phone call recordings:
- transcription (faster-whisper),
- semantic summarization (local LLM),
- categorization,
- retention decision support.

No data leaves your machine.

## Context

This project is designed to work with **BCR (Basic Call Recorder)**.

Recordings are produced on the phone and synchronized to the computer (e.g. via Syncthing, rsync, etc.).  
That synchronization step is **out of scope** for this project.

The only assumption:
- new recordings (audio + JSON metadata) appear in configured `ingest_dir`.

## Goals

* Reduce storage usage of call recordings over time
* Keep **structured knowledge** (transcripts + notes)
* Retain only recordings that have **real value** (legal, business, commitments, disputes, etc.)
* Maintain full **local control and privacy**

## Directory layout

```text
/data/calls/
  new/          # incoming recordings (from phone sync)
  2026/         # organized by year (after scan)
  rm/           # "deleted" recordings (manual cleanup)
  transcripts/
  notes/
  calls.sqlite
```

### Lifecycle

1. Files appear in `new/`
2. `scan` moves them to `{year}/`
3. `process`:

   * transcribes audio
   * analyzes content using local LLM
   * assigns category + retention proposal
4. `review`:

   * you confirm or override decision
5. `delete-approved`:

   * audio is moved to `rm/` (never hard-deleted)

## Features

* Directory-based ingestion model (`ingest_dir/ → storage_dir/{year}/ → storage_dir/rm/`)
* Full local processing (no cloud dependency)
* Structured outputs (JSON + SQLite)
* Extensible **categories** (configured in YAML)
* Per-number retention heuristics
* Safe deletion (only after manual review)

## Categories

Categories are defined in `config.yaml`:

```yaml
categories:
  - work
  - family
  - spam
  - friends
  - unknown
```

The local LLM:

* always receives the current list
* must choose exactly one category

You can freely extend this list.

## Requirements

* Python 3.11+
* faster-whisper
* Local LLM (recommended: Ollama)

## Installation

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Usage

```bash
call-archive init --config config.yaml
call-archive scan --config config.yaml
call-archive process --config config.yaml
call-archive list --config config.yaml
call-archive show --config config.yaml 1
call-archive review --config config.yaml 1 --decision delete_audio_keep_transcript
call-archive delete-approved --config config.yaml
```

## Safety model

* No automatic deletion
* All decisions require explicit review
* Audio is moved to `rm/`, not deleted
* Full audit trail in SQLite

## Intended use

This is useful if:

* you record calls for **memory / accountability**
* you want **automatic summarization**
* you want to **control storage growth**
* you need to keep everything **local**

## Non-goals

* Call recording itself (handled by BCR)
* File synchronization (external tools)
* Cloud integrations

## License
GPL-3.0 license 
