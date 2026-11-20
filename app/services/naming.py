"""Filename-safe naming helpers shared by all providers."""

import re

_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename_part(value: str) -> str:
    """Remove characters that are illegal in filenames on Windows, macOS or Linux."""
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("", value)
    return re.sub(r"\s+", " ", cleaned).strip().rstrip(".")


def format_episode_label(show: str, season: int, number: int, episode: str) -> str:
    """Return ``Show S01E01 - Episode`` with filename-unsafe characters removed."""
    return f"{sanitize_filename_part(show)} S{season:02d}E{number:02d} - {sanitize_filename_part(episode)}"
