from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return naive UTC for MySQL DATETIME columns without deprecated utcnow()."""
    return datetime.now(UTC).replace(tzinfo=None)
