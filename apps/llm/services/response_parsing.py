"""
Shared helpers for parsing LLM text responses.

Different providers/models format "structured" text differently even when
given the same prompt: vLLM's Llama/Qwen models tend to comply literally
with "respond ONLY with JSON" instructions, while Claude and GPT models more
often add a preamble sentence, wrap JSON in a code fence regardless of
instructions, or bold plain-text headers (**DECISION:** instead of
DECISION:). Every LLM response-parsing site in this app funnels through
these helpers so that behavior doesn't depend on which provider answered.
"""

import json
import re
from typing import Any, Tuple

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_BOLD_HEADER_RE = re.compile(r'^\*\*(.+?)\*\*')
_BULLET_RE = re.compile(r'^(?:[-*•]|\d+[.)])\s+(.*)')


def extract_json(text: str) -> Any:
    """Parse a JSON object/array out of raw LLM output.

    Tries, in order: a fenced code block (```json or plain ```) found
    anywhere in the text, the whole stripped string, then the substring
    from the first '{'/'[' to the last matching '}'/']' - so a preamble
    sentence or trailing commentary around the JSON doesn't break parsing.
    Raises json.JSONDecodeError if nothing parseable is found, matching the
    exception callers already catch from a plain json.loads() call.
    """
    text = text.strip()

    fence_match = _FENCE_RE.search(text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass  # fenced content wasn't valid JSON on its own - fall through

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for open_ch, close_ch in (('{', '}'), ('[', ']')):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue

    raise json.JSONDecodeError("Could not extract JSON from response", text, 0)


def normalize_line(line: str) -> str:
    """Strip markdown bold from a line's leading header if present, so
    "**DECISION:** APPROVED" and "DECISION: APPROVED" parse the same way."""
    line = line.strip()
    return _BOLD_HEADER_RE.sub(r'\1', line).strip()


def match_bullet(line: str) -> Tuple[bool, str]:
    """Return (True, content) if line is a bullet in any common style
    (-, *, •, "1.", "1)"), else (False, '')."""
    m = _BULLET_RE.match(line.strip())
    if m:
        return True, m.group(1).strip()
    return False, ''
