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


class TeamNotFoundError(AppBaseException):
    """Raised when a team is not found."""

    def __init__(self, team_id: str, contest_id: str):
        super().__init__(
            message=f"Team {team_id} not found in contest {contest_id}",
            status_code=404,
            detail=f"Team {team_id} not found in this contest.",
        )
