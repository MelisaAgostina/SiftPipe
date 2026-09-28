"""
blocks/llm.py

Shared Anthropic call shape used by every block that asks the LLM for a JSON
verdict. Previously copied independently in main.py's ask_llm() and
generate_payloads.py's ask_llm() (same client.messages.create(...) shape,
same ```json fence stripping, same temperature=0.0), with analyze_results.py
repeating the fence-stripping a third time as a defensive fallback. A
model-version bump meant remembering to update more than one place - this
module is the single place now.

Each caller keeps its own error-recovery behavior (main.py's flat error
dict, generate_payloads.py's partial-JSON salvage) since those differ by
what each block does with a failure - only the call + parse shape is shared.
"""

import json
import os

from anthropic import Anthropic

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Labels pipeline.ask_llm() puts in the "vulnerability" field of the
# placeholder dict it returns when a call fails. Defined once here, not
# retyped as string literals in each block that needs to recognise a failed
# call: B8 once compared against a literal that ask_llm had since stopped
# emitting (a translated string), and nothing noticed because the test used the
# same stale literal. Import these instead of writing the text out again.
API_ERROR_LABEL = "API Error"
PARSE_ERROR_LABEL = "JSON Parse Error"
# Older spelling of PARSE_ERROR_LABEL. No longer emitted, but B8_dynamic.json
# files written by earlier runs can still contain it.
LEGACY_PARSE_ERROR_LABEL = "Error de Parseo JSON"
LLM_ERROR_LABELS = (API_ERROR_LABEL, PARSE_ERROR_LABEL, LEGACY_PARSE_ERROR_LABEL)


def is_llm_error(response):
    """True if `response` is the placeholder ask_llm() returns for a failed
    call rather than a real model answer."""
    return isinstance(response, dict) and response.get("vulnerability") in LLM_ERROR_LABELS


def get_default_client():
    return Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def strip_json_fence(text):
    """Strips a ```json / ``` markdown code fence some LLM responses wrap
    their JSON in, despite being told not to."""
    return text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def call_llm_json(prompt, client=None, *, system, max_tokens=4096, temperature=0.0, model=CLAUDE_MODEL):
    """Calls the model and returns the parsed JSON payload.

    Raises json.JSONDecodeError (with the raw response text attached as
    `.raw_text`) on unparsable output, so callers with different recovery
    needs can each decide how to handle it rather than this helper picking
    one behavior for all of them.
    """
    if client is None:
        client = get_default_client()

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    text = strip_json_fence(response.content[0].text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        e.raw_text = text
        raise
