import json
import re


_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def normalize_llm_json_text(raw: str) -> str:
    """Strip fences and isolate the outermost JSON object from model output."""
    text = (raw or "").strip()
    if not text:
        return text

    fence = _FENCE_PATTERN.search(text)
    if fence:
        text = fence.group(1).strip()

    start = text.find("{")
    if start < 0:
        return text

    extracted = _extract_balanced_object(text[start:])
    return extracted if extracted is not None else text[start:]


def parse_llm_json(raw: str) -> dict:
    """Parse JSON from LLM text with normalization and light repair."""
    text = normalize_llm_json_text(raw)
    if not text:
        raise json.JSONDecodeError("empty LLM JSON response", raw or "", 0)

    candidates = [text]
    escaped = _escape_control_chars_in_strings(text)
    if escaped != text:
        candidates.append(escaped)
    repaired = _repair_truncated_json(text)
    if repaired and repaired not in candidates:
        candidates.append(repaired)
    repaired_escaped = _repair_truncated_json(escaped) if escaped != text else None
    if repaired_escaped and repaired_escaped not in candidates:
        candidates.append(repaired_escaped)

    last_exc: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as exc:
            last_exc = exc

    raise last_exc or json.JSONDecodeError("invalid JSON object", text, 0)


def _extract_balanced_object(text: str) -> str | None:
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[: i + 1]

    return None


def _repair_truncated_json(text: str) -> str | None:
    """Best-effort close for truncated JSON (unterminated string / missing braces)."""
    if not text.startswith("{"):
        return None

    in_string = False
    escape = False
    stack: list[str] = []

    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            if stack[-1] == ch:
                stack.pop()

    suffix = ""
    if in_string:
        suffix += '"'
    suffix += "".join(reversed(stack))
    if not suffix:
        return None
    return text + suffix


def _escape_control_chars_in_strings(text: str) -> str:
    """Escape raw newlines/tabs inside JSON string literals (common LLM mistake)."""
    out: list[str] = []
    in_string = False
    escape = False

    for ch in text:
        if in_string:
            if escape:
                escape = False
                out.append(ch)
            elif ch == "\\":
                escape = True
                out.append(ch)
            elif ch == '"':
                in_string = False
                out.append(ch)
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)

    return "".join(out)
