import enum


class UserRole(str, enum.Enum):
    """
    Enumeration of user roles within the system.

    Attributes:
        student: Role for student users.
        instructor: Role for instructor users.
        admin: Role for system administrators.
        manager: Role for managers.
    """

    student = "student"
    instructor = "instructor"
    admin = "admin"
    manager = "manager"


class QuestionDifficulty(str, enum.Enum):
    """
    Enumeration of question difficulty levels.

    Attributes:
        EASY: Represents an easy difficulty level.
        MEDIUM: Represents a medium difficulty level.
        HARD: Represents a hard difficulty level.
    """

    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class BankPermission(str, enum.Enum):
    """
    Enumeration of permissions for question banks.

    Attributes:
        read: Permission to view the bank.
        edit: Permission to modify the bank.
        owner: Full control over the bank.
    """

    read = "read"
    edit = "edit"
    owner = "owner"


class ContestStatus(str, enum.Enum):
    """
    Enumeration of contest statuses.

    Attributes:
        DRAFT: The contest is being created and not yet visible.
        SCHEDULED: The contest is set to start at a future time.
        RUNNING: The contest is currently active.
        PAUSED: The contest has been temporarily halted.
        FINISHED: The contest has concluded.
        CANCELLED: The contest has been cancelled.
    """

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class ScoringType(str, enum.Enum):
    """
    Enumeration of scoring types for contests.

    Attributes:
        AUTO: Automatic scoring.
        MANUAL: Manual scoring.
        HYBRID: Hybrid scoring.
    """

    AUTO = "AUTO"
    MANUAL = "MANUAL"
    HYBRID = "HYBRID"
