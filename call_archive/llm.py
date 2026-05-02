from __future__ import annotations

import json
from typing import Any

import requests

from .config import LlmConfig
from .models import CallNote


def build_prompt(
    *,
    metadata: dict[str, Any],
    transcript: str,
    categories: list[str],
) -> str:
    return f"""
Jesteś lokalnym asystentem do analizy prywatnych transkrypcji rozmów telefonicznych.
Nie wolno Ci zakładać informacji, których nie ma w metadanych lub transkrypcji.
Masz zwrócić wyłącznie poprawny JSON zgodny ze schematem.

Dostępne kategorie:
{json.dumps(categories, ensure_ascii=False)}

Wybierz dokładnie jedną kategorię z powyższej listy.

Zasady retencji:
- Jeżeli rozmowa zawiera istotne ustalenia, spór, zobowiązania, kwestie prawne, finansowe, techniczne, reklamacyjne albo dowodowe i ma być na pewno zachowana niezależnie od innych reguł, rekomenduj keep.
- Jeżeli rozmowa jest nieistotna, spamowa, pomyłkowa, pusta albo czysto organizacyjna bez wartości dowodowej i ma być usunięta niezależnie od innych reguł, rekomenduj delete.
- Jeżeli decyzja ma zostać podjęta wg domyślnej polityki systemu, rekomenduj default.
- Jeżeli transkrypcja jest zbyt słaba albo nie da się ocenić treści, rekomenduj review.

Dozwolone wartości recommended_retention:
- default
- keep
- delete
- review

Dozwolone wartości importance:
- low
- medium
- high
- unknown

Wymagany JSON:
{{
  "participants": ["..."],
  "caller_or_contact": "...",
  "category": "...",
  "topic": "...",
  "summary": "...",
  "agreements": ["..."],
  "action_items": ["..."],
  "importance": "low|medium|high|unknown",
  "contains_sensitive_or_legal_content": false,
  "recommended_retention": "default|keep|delete|review",
  "reason": "..."
}}

Metadane:
{json.dumps(metadata, ensure_ascii=False, indent=2)}

Transkrypcja:
{transcript}
""".strip()


def analyze_with_ollama(
    *,
    config: LlmConfig,
    prompt: str,
    categories: list[str],
) -> CallNote:
    if config.provider != "ollama":
        raise ValueError(f"Unsupported LLM provider: {config.provider}")

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "participants": {"type": "array", "items": {"type": "string"}},
            "caller_or_contact": {"type": "string"},
            "category": {"type": "string", "enum": categories},
            "topic": {"type": "string"},
            "summary": {"type": "string"},
            "agreements": {"type": "array", "items": {"type": "string"}},
            "action_items": {"type": "array", "items": {"type": "string"}},
            "importance": {"type": "string", "enum": ["low", "medium", "high", "unknown"]},
            "contains_sensitive_or_legal_content": {"type": "boolean"},
            "recommended_retention": {
                "type": "string",
                "enum": [
                    "default",
                    "keep",
                    "delete",
                    "review",
                ],
            },
            "reason": {"type": "string"},
        },
        "required": [
            "participants",
            "caller_or_contact",
            "category",
            "topic",
            "summary",
            "agreements",
            "action_items",
            "importance",
            "contains_sensitive_or_legal_content",
            "recommended_retention",
            "reason",
        ],
        "additionalProperties": False,
    }

    response = requests.post(
        f"{config.base_url.rstrip('/')}/api/generate",
        json={
            "model": config.model,
            "prompt": prompt,
            "stream": False,
            "format": schema,
            "think": False,
        },
        timeout=config.timeout_secs,
    )
    response.raise_for_status()

    response_data: Any = response.json()
    raw = response_data.get("response")
    if not isinstance(raw, str):
        raise ValueError("Ollama response does not contain string field 'response'.")

    try:
        parsed: Any = json.loads(raw)
    except json.decoder.JSONDecodeError:
        print("Call JSON:", repr(response_data))
        raise
    note = CallNote.model_validate(parsed)
    if note.category not in categories:
        note.category = "unknown"
    return note
