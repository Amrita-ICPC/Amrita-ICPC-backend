from datetime import datetime, timedelta, timezone

from app.utils.enums import ContestRunStatus


def compute_run_status(
    start_time: datetime, end_time: datetime | None
) -> ContestRunStatus:
    """Derive the temporal run-state of a contest from its start/end times.

    Args:
        start_time: Contest start time (may be timezone-aware or naive UTC).
        end_time: Contest end time (may be timezone-aware or naive UTC, optional).

    Returns:
        ContestRunStatus.UPCOMING if now < start_time.
        ContestRunStatus.LIVE     if start_time <= now <= end_time (or end_time is None).
        ContestRunStatus.ENDED    if now > end_time.
    """
    now = datetime.now(tz=timezone.utc)

    def _aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    if now < _aware(start_time):
        return ContestRunStatus.UPCOMING
    if end_time is None or now <= _aware(end_time):
        return ContestRunStatus.LIVE
    return ContestRunStatus.ENDED


def calculate_effective_times(
    base_end_time: datetime | None,
    total_paused_duration: int,
    extra_time_seconds: int | None,
    is_paused: bool = False,
    paused_at: datetime | None = None,
) -> tuple[datetime | None, int]:
    """Calculate the effective end time and remaining seconds.

    Args:
        base_end_time: The base end time of the contest (optional).
        total_paused_duration: Total seconds the contest has been paused.
        extra_time_seconds: Extra seconds granted to the team/user.
        is_paused: True if the contest is currently paused.
        paused_at: The timestamp when the contest was paused.

    Returns:
        tuple[datetime | None, int]: A tuple containing the effective end time
            and the remaining seconds (not negative).
    """
    from datetime import timedelta

    if base_end_time is None:
        return None, 99999999

    def _aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    extra_time = extra_time_seconds if extra_time_seconds is not None else 0

    effective_end_time = (
        _aware(base_end_time)
        + timedelta(seconds=total_paused_duration)
        + timedelta(seconds=extra_time)
    )

    if is_paused and paused_at is not None:
        reference_time = _aware(paused_at)
    else:
        reference_time = datetime.now(timezone.utc)

    remaining_seconds = max(
        int((effective_end_time - reference_time).total_seconds()),
        0,
    )
    return effective_end_time, remaining_seconds


def calculate_base_end_time(
    start_time: datetime,
    end_time: datetime | None,
    duration: int | None,
) -> datetime | None:
    """Calculate the base end time for a contest session starting at a given start time.

    Args:
        start_time: The starting timestamp (typically now_utc).
        end_time: The absolute end time of the contest.
        duration: The allowed duration of the contest in seconds.

    Returns:
        datetime | None: The computed base end time for the session.
    """
    if duration is not None:
        duration_end = start_time + timedelta(seconds=duration)
        if end_time is not None:
            return min(duration_end, end_time)
        return duration_end
    return end_time
