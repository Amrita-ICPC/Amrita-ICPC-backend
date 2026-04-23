from app.exceptions.base import AppBaseException


class TeamAlreadyExistsError(AppBaseException):
    """Raised when a team with the same name already exists in the contest."""

    def __init__(self, name: str, contest_id: str):
        super().__init__(
            message=f"Team '{name}' already exists in contest {contest_id}",
            status_code=409,
            detail=f"Team with name '{name}' already exists in contest {contest_id}",
        )


class InvalidTeamSizeError(AppBaseException):
    """Raised when the team size violates contest rules."""

    def __init__(self, size: int, min_size: int, max_size: int):
        super().__init__(
            message=f"Invalid team size: {size}. Must be between {min_size} and {max_size}.",
            status_code=400,
            detail=f"Team size {size} is invalid. Allowed range: {min_size}-{max_size}.",
        )


class InvalidTeamSizeByModeError(AppBaseException):
    """Raised when the team size is greater than 1 when the contest mode is individual"""

    def __init__(self, detail=None):
        super().__init__(
            "Team size must be 1 when the contest mode is individual", 400, detail
        )


class TeamNotFoundError(AppBaseException):
    """Raised when a team is not found."""

    def __init__(self, team_id: str, contest_id: str):
        super().__init__(
            message=f"Team {team_id} not found in contest {contest_id}",
            status_code=404,
            detail=f"Team {team_id} not found in this contest.",
        )


class MemberAlreadyInTeamError(AppBaseException):
    """Raised when trying to add a member who is already in the team."""

    def __init__(self, user_id: str, team_name: str):
        super().__init__(
            message=f"User {user_id} is already a member of team '{team_name}'",
            status_code=409,
            detail=f"User {user_id} is already in this team.",
        )


class MemberNotInTeamError(AppBaseException):
    """Raised when trying to remove a member who is not in the team."""

    def __init__(self, user_id: str, team_name: str):
        super().__init__(
            message=f"User {user_id} is not a member of team '{team_name}'",
            status_code=404,
            detail=f"User {user_id} is not in this team.",
        )


class CannotRemoveTeamLeaderError(AppBaseException):
    """Raised when trying to remove the team leader without specifying a new leader."""

    def __init__(self, team_name: str):
        super().__init__(
            message=f"Cannot remove team leader from '{team_name}' without assigning a new leader",
            status_code=400,
            detail="A new leader must be specified when removing the current team leader.",
        )


class InvalidLeaderAssignmentError(AppBaseException):
    """Raised when trying to assign a leader who is being removed from the team."""

    def __init__(self, leader_id: str, team_name: str):
        super().__init__(
            message=f"Cannot assign user {leader_id} as leader of team '{team_name}' - user is being removed",
            status_code=400,
            detail="New leader cannot be one of the members being removed from the team.",
        )


class ApprovalNotAllowedError(AppBaseException):
    """Raised when a team approval operation is not allowed in current state."""

    def __init__(self, team_id: str, contest_id: str):
        super().__init__(
            message=(
                f"Team {team_id} cannot be approved in contest {contest_id} for the current approval mode/state"
            ),
            status_code=400,
            detail="Approval is not allowed for this team in the current contest approval mode.",
        )
