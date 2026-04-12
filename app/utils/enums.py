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


class ExecutionStatus(str, enum.Enum):
    """
    Enumeration of code execution status outcomes from Judge0.

    Represents the final state of code execution against a test case,
    indicating whether execution succeeded and how output compared to expected.

    Attributes:
        ACCEPTED: Code executed successfully and output matches expected (test passed).
        WRONG_ANSWER: Code executed successfully but output does not match expected.
        TIME_LIMIT_EXCEEDED: Code did not complete within the time limit.
        RUNTIME_ERROR: Code crashed or raised an exception during execution.
        MEMORY_LIMIT_EXCEEDED: Code exceeded the memory usage limit.
        CPU_TIME_LIMIT_EXCEEDED: Code exceeded CPU time limit.
        SYSTEM_ERROR: Judge0 system encountered an error during execution.
        INTERNAL_ERROR: Judge0 encountered an internal error during execution.
    """

    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG_ANSWER"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    CPU_TIME_LIMIT_EXCEEDED = "CPU_TIME_LIMIT_EXCEEDED"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class TeamApprovalMode(str, enum.Enum):
    """
    Enumeration of contest-level team approval modes.

    Attributes:
        AUTO_APPROVE: Teams are approved automatically when created.
        INSTRUCTOR_REVIEW: Teams are kept waiting until an instructor approves.
    """

    AUTO_APPROVE = "AUTO_APPROVE"
    INSTRUCTOR_REVIEW = "INSTRUCTOR_REVIEW"


class TeamStatus(str, enum.Enum):
    """
    Enumeration of team statuses within a contest.

    Attributes:
        DRAFT: Team is being formed and can still be modified.
        CONFIRMED: Team is finalized and ready for contest participation.
    """

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class TeamApprovalStatus(str, enum.Enum):
    """
    Enumeration of approval states for a team's contest enrollment.

    Attributes:
        WAITING: Team is awaiting instructor review.
        APPROVED: Team enrollment is approved.
    """

    WAITING = "WAITING"
    APPROVED = "APPROVED"


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


class SubmissionStatus(str, enum.Enum):
    """
    Enumeration of submission evaluation statuses.

    Represents the lifecycle and final verdict of a code submission
    during online judging.

    Attributes:
        QUEUED: Submission is accepted by the system and waiting to be judged.
        RUNNING: Submission is currently being compiled or executed.
        AC: Accepted; all test cases passed.
        WA: Wrong Answer; one or more test cases failed.
        TLE: Time Limit Exceeded during execution.
        RE: Runtime Error occurred while running the submission.
        CE: Compilation Error prevented execution.
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    AC = "AC"
    WA = "WA"
    TLE = "TLE"
    RE = "RE"
    CE = "CE"
