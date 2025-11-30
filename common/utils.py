"""
Shared utility functions for all services.
"""

from datetime import datetime, date
from typing import Optional


def parse_date(date_str: Optional[str]) -> date:
    """
    Parse a date string in ISO format or YYYY-MM-DD.
    Returns today's date if parsing fails or input is None.
    """
    if not date_str:
        return date.today()

    try:
        return datetime.fromisoformat(date_str).date()
    except (ValueError, TypeError):
        pass

    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        pass

    return date.today()


def day_name_from_date(date_str: Optional[str] = None) -> str:
    """
    Get the day name (Monday, Tuesday, etc.) from a date string.
    Returns today's day name if no date provided or parsing fails.
    """
    d = parse_date(date_str)
    return d.strftime("%A")
