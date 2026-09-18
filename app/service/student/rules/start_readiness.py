"""Chain of Responsibility implementation for evaluating contest session start readiness."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.models.contest import Contest, ContestTeam
from app.utils.enums import (
    ContestRunStatus,
    ContestStatus,
    ContestTeamParticipationType,
    TeamApprovalStatus,
    TeamStatus,
)


@dataclass(frozen=True)
class StartReadinessContext:
    """Context data required to evaluate whether a student or team can start a contest session."""

    contest: Contest
    contest_team: ContestTeam
    run_status: ContestRunStatus
    session_ended: bool
    already_started: bool
    is_leader: bool


@dataclass(frozen=True)
class StartReadinessResult:
    """Result of start readiness evaluation indicating permission and optional reason."""

    can_start: bool
    reason: Optional[str] = None


class StartReadinessHandler(ABC):
    """Abstract base handler in the Chain of Responsibility for start readiness.

    Each handler checks a specific condition. If the condition prevents starting,
    it halts the chain and returns can_start=False along with its specific failure reason.
    Otherwise, it passes the context to the next handler in the chain.
    """

    reason: Optional[str] = None

    def __init__(self, next_handler: Optional["StartReadinessHandler"] = None) -> None:
        """Initialize handler with optional next successor.

        Args:
            next_handler: The successor handler in the chain.
        """
        self._next_handler: Optional["StartReadinessHandler"] = next_handler

    def set_next(self, handler: "StartReadinessHandler") -> "StartReadinessHandler":
        """Set the next handler in the chain and return it for fluent linking.

        Args:
            handler: The successor handler to add.

        Returns:
            StartReadinessHandler: The passed handler for chaining.
        """
        self._next_handler = handler
        return handler

    @abstractmethod
    def check(self, context: StartReadinessContext) -> StartReadinessResult:
        """Evaluate the readiness condition for the given context.

        Args:
            context: Context containing contest, team, runtime status, and leader flag.

        Returns:
            StartReadinessResult: Outcome with can_start and failure reason if blocked.
        """
        pass

    def check_next(self, context: StartReadinessContext) -> StartReadinessResult:
        """Forward evaluation to the next handler in the chain or default to can_start=True.

        Args:
            context: The context being evaluated.

        Returns:
            StartReadinessResult: Result from next handler or successful default.
        """
        if self._next_handler is not None:
            return self._next_handler.check(context)
        return StartReadinessResult(can_start=True, reason=None)


class DraftTeamReadinessHandler(StartReadinessHandler):
    """Checks if the team is in draft status."""

    reason = "Team is in draft status"

    def check(self, context: StartReadinessContext) -> StartReadinessResult:
        if context.contest_team.team_status == TeamStatus.DRAFT:
            return StartReadinessResult(can_start=False, reason=self.reason)
        return self.check_next(context)


class ApprovedTeamReadinessHandler(StartReadinessHandler):
    """Checks if the team has been approved by organizers."""

    reason = "Team is not approved by contest organizers"

    def check(self, context: StartReadinessContext) -> StartReadinessResult:
        if context.contest_team.approval_status != TeamApprovalStatus.APPROVED:
            return StartReadinessResult(can_start=False, reason=self.reason)
        return self.check_next(context)


class CancelledContestReadinessHandler(StartReadinessHandler):
    """Checks if the contest has been cancelled."""

    reason = "Contest has been cancelled"

    def check(self, context: StartReadinessContext) -> StartReadinessResult:
        if context.contest.status == ContestStatus.CANCELLED:
            return StartReadinessResult(can_start=False, reason=self.reason)
        return self.check_next(context)


class UpcomingContestReadinessHandler(StartReadinessHandler):
    """Checks if the contest has not started yet."""

    reason = "Contest has not started yet"

    def check(self, context: StartReadinessContext) -> StartReadinessResult:
        if context.run_status == ContestRunStatus.UPCOMING:
            return StartReadinessResult(can_start=False, reason=self.reason)
        return self.check_next(context)


class EndedContestReadinessHandler(StartReadinessHandler):
    """Checks if the contest has already ended."""

    reason = "Contest has already ended"

    def check(self, context: StartReadinessContext) -> StartReadinessResult:
        if context.run_status == ContestRunStatus.ENDED:
            return StartReadinessResult(can_start=False, reason=self.reason)
        return self.check_next(context)


class EndedSessionReadinessHandler(StartReadinessHandler):
    """Checks if the contest session has already ended."""

    reason = "Contest session has already ended"

    def check(self, context: StartReadinessContext) -> StartReadinessResult:
        if context.session_ended:
            return StartReadinessResult(can_start=False, reason=self.reason)
        return self.check_next(context)


class LeaderRestrictionReadinessHandler(StartReadinessHandler):
    """Checks if only the leader is allowed to start the session."""

    reason = "Only the team leader can start the contest session"

    def check(self, context: StartReadinessContext) -> StartReadinessResult:
        if (
            not context.already_started
            and context.contest.participation_type
            == ContestTeamParticipationType.LEADER_ONLY
            and not context.is_leader
        ):
            return StartReadinessResult(can_start=False, reason=self.reason)
        return self.check_next(context)


class CanStartReadinessHandler(StartReadinessHandler):
    """Terminal handler confirming all checks passed and the session can start."""

    def check(self, context: StartReadinessContext) -> StartReadinessResult:
        return StartReadinessResult(can_start=True, reason=None)


def build_start_readiness_chain() -> StartReadinessHandler:
    """Build and link the start readiness Chain of Responsibility in the defined order:

    Draft? -> Approved? -> Cancelled? -> Upcoming? -> Ended? -> Session ended? -> Leader restriction? -> CAN START

    Returns:
        StartReadinessHandler: Head of the configured chain.
    """
    draft_handler = DraftTeamReadinessHandler()
    approved_handler = ApprovedTeamReadinessHandler()
    cancelled_handler = CancelledContestReadinessHandler()
    upcoming_handler = UpcomingContestReadinessHandler()
    ended_handler = EndedContestReadinessHandler()
    session_ended_handler = EndedSessionReadinessHandler()
    leader_handler = LeaderRestrictionReadinessHandler()
    can_start_handler = CanStartReadinessHandler()

    (
        draft_handler.set_next(approved_handler)
        .set_next(cancelled_handler)
        .set_next(upcoming_handler)
        .set_next(ended_handler)
        .set_next(session_ended_handler)
        .set_next(leader_handler)
        .set_next(can_start_handler)
    )

    return draft_handler
