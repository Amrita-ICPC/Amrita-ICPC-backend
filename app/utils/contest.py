from datetime import datetime, timezone

from app.utils.enums import ContestRunStatus


def compute_run_status(start_time: datetime, end_time: datetime) -> ContestRunStatus:
    """Derive the temporal run-state of a contest from its start/end times.

    Args:
        start_time: Contest start time (may be timezone-aware or naive UTC).
        end_time: Contest end time (may be timezone-aware or naive UTC).

    Returns:
        ContestRunStatus.UPCOMING if now < start_time.
        ContestRunStatus.LIVE     if start_time <= now <= end_time.
        ContestRunStatus.ENDED    if now > end_time.
    """
    now = datetime.now(tz=timezone.utc)

    def _aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    if now < _aware(start_time):
        return ContestRunStatus.UPCOMING
    if now <= _aware(end_time):
        return ContestRunStatus.LIVE
    return ContestRunStatus.ENDED
