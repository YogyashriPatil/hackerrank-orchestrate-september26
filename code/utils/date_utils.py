from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


def to_timestamp(value: Any) -> pd.Timestamp | None:
    """
    Convert any supported date/datetime value into
    pandas.Timestamp.

    Returns None for missing/invalid values.
    """

    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        return value

    if isinstance(value, datetime):
        return pd.Timestamp(value)

    if isinstance(value, date):
        return pd.Timestamp(value)

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    try:
        converted = pd.to_datetime(value, errors="coerce")

        if pd.isna(converted):
            return None

        return pd.Timestamp(converted)

    except Exception:
        return None


def same_date(left: Any, right: Any) -> bool:
    """
    Safely compare two values by calendar date.
    """

    left_ts = to_timestamp(left)
    right_ts = to_timestamp(right)

    if left_ts is None or right_ts is None:
        return False

    return left_ts.normalize() == right_ts.normalize()


def date_before(left: Any, right: Any) -> bool:
    """
    Safely evaluate left < right.
    """

    left_ts = to_timestamp(left)
    right_ts = to_timestamp(right)

    if left_ts is None or right_ts is None:
        return False

    return left_ts < right_ts


def date_before_or_equal(left: Any, right: Any) -> bool:
    """
    Safely evaluate left <= right.
    """

    left_ts = to_timestamp(left)
    right_ts = to_timestamp(right)

    if left_ts is None or right_ts is None:
        return False

    return left_ts <= right_ts


def date_after(left: Any, right: Any) -> bool:
    """
    Safely evaluate left > right.
    """

    left_ts = to_timestamp(left)
    right_ts = to_timestamp(right)

    if left_ts is None or right_ts is None:
        return False

    return left_ts > right_ts


def date_after_or_equal(left: Any, right: Any) -> bool:
    """
    Safely evaluate left >= right.
    """

    left_ts = to_timestamp(left)
    right_ts = to_timestamp(right)

    if left_ts is None or right_ts is None:
        return False

    return left_ts >= right_ts