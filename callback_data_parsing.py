"""Small helpers for parsing callback_data payloads."""


def parse_optional_int_callback_id(data: str, *, prefix: str):
    if not data.startswith(prefix):
        raise ValueError(f"callback data must start with {prefix!r}")

    raw_id = data[len(prefix):]
    try:
        return int(raw_id)
    except ValueError:
        return None
