import enum


class UserRole(str, enum.Enum):
    """
    Enumeration of user roles within the ICPC backend system.

    Defines the hierarchical roles that control access permissions
    and determine what actions users can perform.

    Attributes:
        student: Regular students who can participate in contests and join teams.
        instructor: Instructors who can create and manage contests for their courses.
        admin: System administrators with full access to all system features.
        manager: Organizational managers with elevated permissions across contests.
    """

    student = "student"
    instructor = "instructor"
    admin = "admin"
    manager = "manager"


class QuestionDifficulty(str, enum.Enum):
    """
    Enumeration of question difficulty levels for contest problems.

    Used to categorize problems by their complexity and expected
    solving time to help with contest balancing and participant preparation.

    Attributes:
        EASY: Basic problems suitable for beginners, typically solvable in 15-30 minutes.
        MEDIUM: Intermediate problems requiring algorithmic thinking, 30-60 minutes.
        HARD: Advanced problems demanding complex algorithms, 60+ minutes.
    """

    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class BankPermission(str, enum.Enum):
    """
    Enumeration of permissions for question banks.

    Controls access levels for question banks, allowing fine-grained
    permission management for collaborative question management.

    Attributes:
        read: Permission to view questions and bank metadata only.
        edit: Permission to modify questions and bank content.
        owner: Full control including permission management and deletion.
    """

    read = "read"
    edit = "edit"
    owner = "owner"


class ContestStatus(str, enum.Enum):
    """
    Enumeration of contest lifecycle statuses.

    Tracks the current state of a contest from creation through completion,
    controlling participant access and available operations.

    Attributes:
        DRAFT: Contest is being configured and not visible to participants.
        SCHEDULED: Contest is published and scheduled for future start.
        RUNNING: Contest is currently active and accepting submissions.
        PAUSED: Contest is temporarily halted, submissions disabled.
        FINISHED: Contest has concluded, final results available.
        CANCELLED: Contest has been cancelled and will not proceed.
    """

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class ScoringType(str, enum.Enum):
    """
    Enumeration of scoring methods for contest evaluation.

    Determines how submissions are evaluated and scored during contests,
    affecting the judging workflow and result calculation.

    Attributes:
        AUTO: Fully automatic scoring using predefined test cases and judges.
        MANUAL: Human-reviewed scoring for subjective or complex evaluation.
        HYBRID: Combined automatic and manual scoring for comprehensive assessment.
    """

    AUTO = "AUTO"
    MANUAL = "MANUAL"
    HYBRID = "HYBRID"


class TeamStatus(str, enum.Enum):
    """
    Enumeration of team statuses within a contest.

    Attributes:
        DRAFT: Team is being formed and can still be modified.
        CONFIRMED: Team is finalized and ready for contest participation.
    """

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class ViolationType(str, enum.Enum):
    """
    Enumeration of violation types that can occur during contests.

    Attributes:
        CHEATING: Unauthorized collaboration or assistance during contest.
        MULTIPLE_ACCOUNTS: Using multiple accounts to gain unfair advantage.
        LATE_SUBMISSION: Submitting solutions after the deadline.
        RULE_VIOLATION: General violation of contest rules and regulations.
    """

    CHEATING = "cheating"
    MULTIPLE_ACCOUNTS = "multiple_accounts"
    LATE_SUBMISSION = "late_submission"
    RULE_VIOLATION = "rule_violation"


class ViolationSeverity(str, enum.Enum):
    """
    Enumeration of violation severity levels.

    Attributes:
        LOW: Minor infractions with minimal impact.
        MEDIUM: Moderate violations requiring attention.
        HIGH: Serious violations affecting contest integrity.
        CRITICAL: Severe violations requiring immediate action.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
