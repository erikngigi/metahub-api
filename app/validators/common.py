import re
from datetime import date

from app.exceptions.errors import ValidationFailed

MIN_YEAR = 1888  # earliest surviving film
MAX_QUERY_LENGTH = 200
MAX_SEASON = 100
MAX_EPISODE = 9999

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
_PROVIDER_ID = re.compile(r"^[A-Za-z0-9:_\-]{1,64}$")


def sanitize_query(value: str) -> str:
    """Strips control characters, collapses whitespace, and enforces length."""
    cleaned = _WHITESPACE.sub(" ", _CONTROL_CHARS.sub(" ", value)).strip()
    if not cleaned:
        raise ValidationFailed("query must not be empty")
    if len(cleaned) > MAX_QUERY_LENGTH:
        raise ValidationFailed(f"query must be at most {MAX_QUERY_LENGTH} characters")
    return cleaned


def validate_year(year: int | None) -> int | None:
    if year is None:
        return None
    max_year = date.today().year + 5  # allow announced upcoming releases
    if not MIN_YEAR <= year <= max_year:
        raise ValidationFailed(f"year must be between {MIN_YEAR} and {max_year}")
    return year


def validate_season_episode(season: int | None, episode: int | None) -> tuple[int | None, int | None]:
    if episode is not None and season is None:
        raise ValidationFailed("episode requires season")
    if season is not None and not 0 <= season <= MAX_SEASON:  # season 0 = specials
        raise ValidationFailed(f"season must be between 0 and {MAX_SEASON}")
    if episode is not None and not 1 <= episode <= MAX_EPISODE:
        raise ValidationFailed(f"episode must be between 1 and {MAX_EPISODE}")
    return season, episode


def validate_provider_id(value: str) -> str:
    """Generic shape check for path parameters. The provider does format-specific parsing."""
    cleaned = value.strip()
    if not _PROVIDER_ID.fullmatch(cleaned):
        raise ValidationFailed("id contains invalid characters or is too long")
    return cleaned
