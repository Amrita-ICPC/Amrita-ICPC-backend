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
        PUBLISHED: Contest is published and visible to participants.
        CANCELLED: Contest has been cancelled.
        DELETED: Contest has been soft-deleted.
    """

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"


class ContestRunStatus(str, enum.Enum):
    """
    Enumeration of the temporal run-state of a contest.

    Derived at read-time from start_time and end_time relative to the
    current UTC timestamp. Not persisted to the database.

    Attributes:
        UPCOMING: Current time is before start_time.
        LIVE: Current time is between start_time and end_time (inclusive).
        ENDED: Current time is after end_time.
    """

    UPCOMING = "UPCOMING"
    LIVE = "LIVE"
    ENDED = "ENDED"


class SortOrder(str, enum.Enum):
    """
    Enumeration for sorting order.

    Attributes:
        ASC: Ascending order.
        DESC: Descending order.
    """

    ASC = "asc"
    DESC = "desc"


class ContestQuestionSortBy(str, enum.Enum):
    """
    Enumeration for contest question sorting options.

    Attributes:
        TITLE: Sort by question title.
        DIFFICULTY: Sort by question difficulty.
        CREATED_AT: Sort by creation timestamp.
        UPDATED_AT: Sort by last update timestamp.
        ORDER: Sort by contest-specific order.
    """

    TITLE = "title"
    DIFFICULTY = "difficulty"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    ORDER = "order"


class BankQuestionSortBy(str, enum.Enum):
    """
    Enumeration for bank question sorting options.

    Attributes:
        NAME = "name"
        DIFFICULTY = "difficulty"
    """

    NAME = "name"
    DIFFICULTY = "difficulty"


class BankSortBy(str, enum.Enum):
    """
    Enumeration for bank sorting options.

    Attributes:
        NAME: Sort alphabetically by bank name.
        UPDATED_NEW: Sort by updated_at descending (most recently updated first).
        UPDATED_OLD: Sort by updated_at ascending (oldest updated first).
        CREATED_AT: Sort by created_at descending (most recently created first).
    """

    NAME = "name"
    UPDATED_NEW = "updated_new"
    UPDATED_OLD = "updated_old"
    CREATED_AT = "created_at"


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
        DISQUALIFIED: Team has been disqualified from the contest.
        CANCELLED: Team has been cancelled from the contest.
    """

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    DISQUALIFIED = "DISQUALIFIED"


class TeamApprovalStatus(str, enum.Enum):
    """
    Enumeration of approval states for a team's contest enrollment.

    Attributes:
        WAITING: Team is awaiting instructor review.
        APPROVED: Team enrollment is approved.
        REJECTED: Team enrollment is rejected.
        CANCELLED: Team enrollment is cancelled.
    """

    WAITING = "WAITING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ContestMode(str, enum.Enum):
    """
    Enumeration of team mode for a contest

    Attributes:
        INDIVIDUAL: Each participant competes independently.
        TEAM: Teams compete collaboratively.
    """

    INDIVIDUAL = "individual"
    TEAM = "team"


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
    SYSTEM_ERROR = "SYSTEM_ERROR"
    AC = "AC"
    WA = "WA"
    TLE = "TLE"
    RE = "RE"
    CE = "CE"
    MLE = "MLE"


class AudienceType(str, enum.Enum):
    """
    Enumeration of audience scopes for content visibility.

    Defines the organizational level used to target content or access rules
    within the system.

    Attributes:
        CLASS: Audience is limited to a specific class.
        DEPARTMENT: Audience is limited to a specific department.
        BATCH: Audience is limited to a specific batch.
        CAMPUS: Audience is limited to the campus level.
    """

    CLASS = "class"
    DEPARTMENT = "department"
    BATCH = "batch"
    CAMPUS = "campus"


class ContestTeamMemberStatus(str, enum.Enum):
    """
    Enumeration of contest team registration statuses.

    Attributes:
        INVITED: User has been invited to join a team but has not yet accepted.
        ACCEPTED: User has accepted the team invitation and is a member of the team.
        CANCELLED: User or team has cancelled the registration.
        REJECTED: User has rejected the team invitation.
        LEFT: User was a member but has left the team.
    """

    INVITED = "INVITED"
    ACCEPTED = "ACCEPTED"
    REMOVED = "REMOVED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    LEFT = "LEFT"


class TeamMemberRole(str, enum.Enum):
    """
    Enumeration of team member roles in a contest.

    Attributes:
        LEADER: The leader of the team.
        MEMBER: A regular member of the team.
    """

    LEADER = "LEADER"
    MEMBER = "MEMBER"


class TeamInvitationStatus(str, enum.Enum):
    """
    Enumeration of team invitation statuses.

    Attributes:
        PENDING: Invitation is pending.
        CANCELLED: Invitation is cancelled.
        ACCEPTED: Invitation is accepted.
        REJECTED: Invitation is rejected.
    """

    PENDING = "PENDING"
    CANCELLED = "CANCELLED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class VisibilityStatus(str, enum.Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


class WorkspaceRole(str, enum.Enum):
    """
    Enumeration of workspace roles for contest sessions.

    Attributes:
        EDITOR: Participant has edit rights in the workspace.
        VIEWER: Participant can only view the workspace.
    """

    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class InvitationType(str, enum.Enum):
    REQUEST = "REQUEST"
    INVITE = "INVITE"


class RegistrationState(str, enum.Enum):
    """
    Enumeration of student registration states in a contest.
    """

    NOT_REGISTERED = "NOT_REGISTERED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"


class ContestTeamParticipationType(str, enum.Enum):
    """
    Enumeration of contest team participation types.

    Attributes:
        LEADER_ONLY: Only leader can code
        INDIVIDUAL_WORKSPACE: Each team member has their own workspace
    """

    LEADER_ONLY = "LEADER_ONLY"
    INDIVIDUAL_WORKSPACE = "INDIVIDUAL_WORKSPACE"
