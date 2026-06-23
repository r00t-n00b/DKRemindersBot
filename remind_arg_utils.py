"""Helpers for normalizing /remind raw arguments."""


def strip_first_token_from_first_line(raw_args: str, first_token: str) -> str:
    first_line = (raw_args or "").splitlines()[0].lstrip()
    rest_first_line = first_line[len(first_token):].lstrip()
    rest_lines = "\n".join((raw_args or "").splitlines()[1:])

    parts = []
    if rest_first_line:
        parts.append(rest_first_line)
    if rest_lines.strip():
        parts.append(rest_lines)

    return "\n".join(parts).strip()
