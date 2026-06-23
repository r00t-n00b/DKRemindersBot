"""Compatibility helper for parsers with optional default_time support."""


def parse_with_optional_default_time(
    parser,
    raw: str,
    current_now,
    *,
    default_time,
):
    try:
        return parser(raw, current_now, default_time=default_time)
    except TypeError as e:
        if "default_time" not in str(e) and "unexpected keyword" not in str(e):
            raise
        return parser(raw, current_now)
