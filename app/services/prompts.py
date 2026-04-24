from __future__ import annotations

import json
from typing import Any

from app.schemas.base import EventType
from app.schemas.registry import SchemaRegistry

# When extraction is impossible without guessing, the model must return this flag (bool true)
# and nothing else shaped like a successful record. The worker treats it as a hard failure.
EXTRACTION_FAILED_MARKER = "_extraction_failed"


def classify_system_prompt() -> str:
    keys = sorted(e.value for e in SchemaRegistry.all_keys()) + [EventType.UNCLASSIFIED.value]
    label_list = ", ".join(keys)
    body_lines = [
        "You are a supply-chain webhook router. Classify the JSON payload into exactly one label.",
        f"Reply with JSON only, no markdown: {{\"type\": one of {label_list}}}.",
    ]
    for et in sorted(SchemaRegistry.all_keys(), key=lambda e: e.value):
        b = SchemaRegistry.get(et).classify_blurb
        body_lines.append(f"{et.value}: {b}.")
    body_lines.append(
        "UNCLASSIFIED: not clearly one of the above, or not enough to normalize."
    )
    return "\n".join(body_lines)


def classify_user_payload(payload: dict[str, Any]) -> str:
    return "Payload (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def extract_system_prompt() -> str:
    err_shape = (
        f'{{"{EXTRACTION_FAILED_MARKER}": true, "reason": "<brief why>", '
        '"missing_fields": ["<camelCase names absent or ambiguous in the source>"]}}'
    )
    return (
        "You are a strict data extraction tool. Output exactly one JSON object, no markdown.\n"
        "Source property names may differ from the target schema (snake_case, abbreviations, "
        "vendor-specific keys). Infer which source key corresponds to each required output field, "
        "then emit only the canonical field names from the task with values taken from the "
        "payload — do not treat a value as missing only because the source key is spelled "
        "differently.\n"
        "When a value is present but encoded differently from the target schema, normalize it "
        "to the required form whenever that conversion is deterministic from the source alone "
        "(same instant, amount, or category — not a guess), e.g. times toward ISO 8601, numeric "
        "strings to numbers, currency toward valid 3-letter codes.\n"
        "For schema enum fields: vendor strings often differ from the allowed literals. Map to "
        "the exact enum value the schema requires when exactly one option clearly matches the "
        "source. Any brief hints on the Task line are illustrative only, not an exhaustive "
        "synonym list — infer from meaning. Use the error object only when the source could fit "
        "more than one enum or none.\n"
        "If the source time is ambiguous (e.g. no timezone and multiple interpretations), use "
        "the error object instead of picking one.\n"
        "Use only values that are explicitly present or unambiguous in the source. "
        "Do not invent values or fill gaps when no source property plausibly supplies a field.\n"
        "Never use placeholders or defaults to satisfy required fields (no empty strings, 0, "
        "false, \"N/A\", \"unknown\", fabricated instants or amounts, or an enum literal with "
        "no clear semantic match in the source).\n"
        "If any required field has no plausible source property after considering naming variants, "
        "do not output a partial or fabricated record. Respond with ONLY this error object "
        "(boolean must be JSON true):\n"
        f"  {err_shape}\n"
        "When every required field is clearly present in the source, output the normal record "
        "with the exact schema field names; no extra keys."
    )


def extract_user_message(
    event_type: EventType, payload: dict[str, Any], previous_errors: str | None
) -> str:
    entry = SchemaRegistry.get(event_type)
    schema_doc = entry.extract_instruction
    model_schema = entry.pydantic_model.model_json_schema()
    err = f"\n\nValidation errors to fix (if any): {previous_errors}\n" if previous_errors else ""
    fail_hint = (
        f"If the source still does not clearly supply every required field (after matching "
        f"differently named keys to schema fields), respond with "
        f'{{"{EXTRACTION_FAILED_MARKER}": true, ...}} as in the system instructions — '
        "do not fabricate data to clear validation errors (converting encoding or format of "
        "an explicit source value is not fabrication).\n"
    )
    return (
        f"Task: {schema_doc}\n"
        f"{fail_hint}"
        f"JSON Schema hint for fields: {json.dumps(model_schema, ensure_ascii=False)[:8000]}\n"
        f"Source payload to interpret:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        f"{err}"
    )
