"""Offline city aliases and IANA timezone lookup; never guess ambiguous input."""

from zoneinfo import available_timezones

CITY_ZONES = {
    "мадрид": "Europe/Madrid", "барселона": "Europe/Madrid", "москва": "Europe/Moscow",
    "токио": "Asia/Tokyo", "берлин": "Europe/Berlin", "париж": "Europe/Paris",
    "лондон": "Europe/London", "лиссабон": "Europe/Lisbon", "рим": "Europe/Rome",
    "амстердам": "Europe/Amsterdam", "прага": "Europe/Prague", "варшава": "Europe/Warsaw",
    "киев": "Europe/Kyiv", "стамбул": "Europe/Istanbul", "дубай": "Asia/Dubai",
    "тбилиси": "Asia/Tbilisi", "ереван": "Asia/Yerevan", "бангкок": "Asia/Bangkok",
    "сингапур": "Asia/Singapore", "шанхай": "Asia/Shanghai", "сеул": "Asia/Seoul",
    "сидней": "Australia/Sydney", "нью-йорк": "America/New_York",
    "лос-анджелес": "America/Los_Angeles", "чикаго": "America/Chicago",
    "торонто": "America/Toronto", "буэнос-айрес": "America/Argentina/Buenos_Aires",
}


def search_timezones(raw):
    value = (raw or "").strip().casefold()
    if len(value) < 2 or len(value) > 100:
        return []
    zones = available_timezones()
    canonical = {z.casefold(): z for z in zones}
    if value in canonical:
        return [canonical[value]]
    if value in CITY_ZONES:
        zone = CITY_ZONES[value]
        return [zone] if zone in zones else []
    term = value.replace(" ", "_")
    result = {zone for city, zone in CITY_ZONES.items() if value in city and zone in zones}
    result.update(z for z in zones if term in z.casefold() and not z.startswith(("posix/", "right/")))
    return sorted(result)[:8]
