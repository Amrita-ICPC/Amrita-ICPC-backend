"""Chain of Responsibility implementation for determining contest team registration status."""

from abc import ABC, abstractmethod
from typing import Optional

from app.models.contest import ContestTeam
from app.utils.enums import RegistrationState, TeamApprovalStatus, TeamStatus


class RegistrationStatusHandler(ABC):
    """Abstract base handler for the registration status Chain of Responsibility.

    Each handler encapsulates a single check condition and either returns
    a resolved RegistrationState or delegates to the next handler in the chain.
    """

    def __init__(
        self, next_handler: Optional["RegistrationStatusHandler"] = None
    ) -> None:
        """Initialize the handler with an optional successor.

        Args:
            next_handler: The next handler to evaluate if this handler cannot resolve the status.
        """
        self._next_handler: Optional["RegistrationStatusHandler"] = next_handler

    def set_next(
        self, handler: "RegistrationStatusHandler"
    ) -> "RegistrationStatusHandler":
        """Set the next handler in the chain and return the added handler for fluent chaining.

        Args:
            handler: The successor handler.

        Returns:
            The passed handler to support chaining.
        """
        self._next_handler = handler
        return handler

    @abstractmethod
    def check(self, contest_team: ContestTeam) -> RegistrationState:
        """Evaluate the contest team to determine its RegistrationState.

        Args:
            contest_team: The contest team entity to inspect.

        Returns:
            RegistrationState: The determined registration state.
        """
        pass

    def check_next(self, contest_team: ContestTeam) -> RegistrationState:
        """Delegate evaluation to the next handler in the chain, or return default.

        Args:
            contest_team: The contest team entity to inspect.

        Returns:
            RegistrationState: The result from the next handler, or NOT_REGISTERED if at chain end.
        """
        if self._next_handler is not None:
            return self._next_handler.check(contest_team)
        return RegistrationState.NOT_REGISTERED


class DraftTeamHandler(RegistrationStatusHandler):
    """Handler for teams that are currently in DRAFT status."""

    def check(self, contest_team: ContestTeam) -> RegistrationState:
        """Check if the team is in draft status.

        Args:
            contest_team: The contest team to check.

        Returns:
            RegistrationState.NOT_REGISTERED if team is draft, otherwise delegates to next handler.
        """
        if contest_team.team_status == TeamStatus.DRAFT:
            return RegistrationState.NOT_REGISTERED
        return self.check_next(contest_team)


class WaitingApprovalHandler(RegistrationStatusHandler):
    """Handler for teams with approval status WAITING."""

    def check(self, contest_team: ContestTeam) -> RegistrationState:
        """Check if the team is waiting for approval.

        Args:
            contest_team: The contest team to check.

        Returns:
            RegistrationState.PENDING_APPROVAL if waiting, otherwise delegates to next handler.
        """
        if contest_team.approval_status == TeamApprovalStatus.WAITING:
            return RegistrationState.PENDING_APPROVAL
        return self.check_next(contest_team)


class ApprovedTeamHandler(RegistrationStatusHandler):
    """Handler for teams with approval status APPROVED."""

    def check(self, contest_team: ContestTeam) -> RegistrationState:
        """Check if the team is approved.

        Args:
            contest_team: The contest team to check.

        Returns:
            RegistrationState.APPROVED if approved, otherwise delegates to next handler.
        """
        if contest_team.approval_status == TeamApprovalStatus.APPROVED:
            return RegistrationState.APPROVED
        return self.check_next(contest_team)


class DefaultRegistrationStatusHandler(RegistrationStatusHandler):
    """Fallback handler returning NOT_REGISTERED when no prior condition matched."""

    def check(self, contest_team: ContestTeam) -> RegistrationState:
        """Return the default fallback registration state.

        Args:
            contest_team: The contest team to check.

        Returns:
            RegistrationState.NOT_REGISTERED.
        """
        return RegistrationState.NOT_REGISTERED


def build_registration_status_chain() -> RegistrationStatusHandler:
    """Factory function to build and configure the default registration status chain.

    Returns:
        RegistrationStatusHandler: The head of the configured handler chain.
    """
    draft_handler = DraftTeamHandler()
    waiting_handler = WaitingApprovalHandler()
    approved_handler = ApprovedTeamHandler()
    default_handler = DefaultRegistrationStatusHandler()

    draft_handler.set_next(waiting_handler).set_next(approved_handler).set_next(
        default_handler
    )
    return draft_handler
