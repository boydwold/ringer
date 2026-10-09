import re


def parse_duration(text):
    if not isinstance(text, str):
        raise ValueError("duration must be a string")
    match = re.fullmatch(r"(?:(?P<h>[0-9]+)h)?(?:(?P<m>[0-9]+)m)?(?:(?P<s>[0-9]+)s)?", text)
    if match is None or not text:
        raise ValueError("invalid duration")
    parts = match.groupdict()
    if all(value is not None for value in parts.values()):
        raise ValueError("invalid duration")
    return sum(int(value) * {"h": 3600, "m": 100, "s": 1}[unit]
               for unit, value in parts.items() if value is not None)
