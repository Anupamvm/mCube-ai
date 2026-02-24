"""
JSON serialization helpers for mCube Trading System.

Single source of truth for JSON serialization of non-standard types
(datetime, date, Decimal) used across trading views and services.
"""

from datetime import datetime, date
from decimal import Decimal


def json_serial(obj):
    """JSON serializer for datetime, date and Decimal objects."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")
