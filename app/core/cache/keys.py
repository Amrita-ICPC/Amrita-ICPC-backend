# app/core/cache/keys.py
"""
Canonical cache key builders.

Every cache namespace used by @cache_get/@cache_set has a matching builder
here, and every @cache_delete call site that must invalidate it should call
the *same* function (or its `_pattern`/`_bust_*` counterpart) rather than
hand-writing an f-string. This is what keeps read keys and invalidation
patterns from drifting apart - see the *_bust_* helpers below, which are
the single source of truth for "what must be cleared when X changes".

Convention:
- `entity:{id}` -> a single object.
- `entities:...` (plural) -> a collection/list view.
- `student:` prefix -> the student-facing mirror of an instructor-facing
  namespace; mutations on the instructor side must bust both.
"""

import json
from typing import Any
from uuid import UUID


def normalize(value: Any) -> str:
    """
    Render a value for embedding in a cache key.

    None -> "none"; dict/list -> canonical JSON (sort_keys) so equivalent
    filters always hash to the same key; everything else -> str(value).
    Do not pass raw free-text (search terms, names) through this without
    considering that ':' or '*' in the text can corrupt key structure or
    unintentionally widen a wildcard match.
    """
    if value is None:
        return "none"
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return str(value)


# ---------------------------------------------------------------------------
# Contest (instructor-facing)
# ---------------------------------------------------------------------------


def contest_detail_key(contest_id: UUID, user_id: UUID) -> str:
    return f"contest:{contest_id}:user:{user_id}"


def contest_bust_pattern(contest_id: UUID) -> str:
    """Busts contest_detail_key, instructor list, and leaderboard for this contest."""
    return f"contest:{contest_id}*"


def contests_list_key(
    user_id: UUID,
    *,
    search_term: str | None = None,
    status: Any = None,
    run_status: Any = None,
    is_public: Any = None,
    skip: int = 0,
    limit: int = 100,
) -> str:
    return (
        f"contests:user:{user_id}:search:{search_term}:status:{status}:"
        f"run_status:{run_status}:public:{is_public}:skip:{skip}:limit:{limit}"
    )


def contests_deleted_list_key(
    user_id: UUID,
    *,
    search_term: str | None = None,
    status: Any = None,
    skip: int = 0,
    limit: int = 100,
) -> str:
    return (
        f"contests:deleted:user:{user_id}:search:{search_term}:"
        f"status:{status}:skip:{skip}:limit:{limit}"
    )


CONTESTS_LIST_BUST_PATTERN = "contests:*"


def contest_instructors_list_key(
    contest_id: UUID, user_id: UUID, *, skip: int = 0, limit: int = 100
) -> str:
    return f"contest:{contest_id}:instructors:user:{user_id}:skip:{skip}:limit:{limit}"


def contest_instructors_bust_pattern(contest_id: UUID) -> str:
    return f"contest:{contest_id}:instructors:*"


def contest_leaderboard_key(
    contest_id: UUID,
    *,
    search_term: str | None = None,
    sort_order: str = "desc",
    skip: int = 0,
    limit: int = 50,
) -> str:
    return (
        f"contest:{contest_id}:leaderboard:search:{search_term}:"
        f"sort:{sort_order}:skip:{skip}:limit:{limit}"
    )


def contest_leaderboard_bust_pattern(contest_id: UUID) -> str:
    return f"contest:{contest_id}:leaderboard*"


def contest_full_bust(contest_id: UUID) -> list[str]:
    """Standard bust list for any mutation that changes contest state
    visible to instructors, students, and the contest list.

    Includes the per-student session-validation cache: contest.status
    changes (e.g. cancel_contest sets CANCELLED directly, bypassing
    update_contest's structural-change guard) must not leave an already
    cached "contest is published, session is fine" entry valid for up to
    its TTL after the contest is cancelled/deleted/restored.
    """
    return [
        contest_bust_pattern(contest_id),
        CONTESTS_LIST_BUST_PATTERN,
        *student_contests_bust(),
        student_session_validation_bust_pattern(contest_id),
    ]


# ---------------------------------------------------------------------------
# Student-facing contest mirror
# ---------------------------------------------------------------------------


def student_contests_list_key(
    user_id: UUID,
    request: Any,
    search: str | None,
    pagination: Any,
) -> str:
    status = ",".join(request.status) if request.status else "any"
    return (
        f"student:contests:user:{user_id}:reg:{request.registered}:"
        f"results_published:{request.results_published}:status:{status}:"
        f"search:{search or 'none'}:skip:{pagination.skip}:limit:{pagination.limit}:"
        f"min_team:{request.min_team_size}:max_team:{request.max_team_size}"
    )


def student_contest_detail_key(contest_id: UUID, user_id: UUID) -> str:
    return f"student:contest:user:{user_id}:contest:{contest_id}"


def student_contests_bust() -> list[str]:
    """Both the plural (list) and singular (detail) student contest caches."""
    return ["student:contests:user:*", "student:contest:user:*"]


def student_session_validation_key(contest_id: UUID, user_id: UUID) -> str:
    return f"contests:{contest_id}:users:{user_id}:session-validation"


def student_session_validation_bust_pattern(contest_id: UUID) -> str:
    return f"contests:{contest_id}:users:*:session-validation"


def student_question_eval_key(contest_id: UUID, question_id: UUID) -> str:
    return f"contests:{contest_id}:questions:{question_id}"


def student_question_eval_bust_pattern(contest_id: UUID) -> str:
    """All per-question student eval caches for a contest."""
    return f"contests:{contest_id}:questions:*"


# ---------------------------------------------------------------------------
# Contest questions (instructor-facing)
# ---------------------------------------------------------------------------


def contest_questions_list_key(
    contest_id: UUID,
    user_id: UUID,
    *,
    search_term: str | None = None,
    difficulty: Any = None,
    language_id: Any = None,
    tag_id: Any = None,
    tag_name: Any = None,
    sort_by: Any = None,
    sort_order: str = "asc",
    skip: int = 0,
    limit: int = 20,
    contest_team_member_id: UUID | None = None,
) -> str:
    return (
        f"contest:{contest_id}:questions:user:{user_id}:search:{search_term}:"
        f"difficulty:{difficulty}:language:{language_id}:tag_id:{tag_id}:"
        f"tag_name:{tag_name}:sort_by:{sort_by}:sort_order:{sort_order}:"
        f"skip:{skip}:limit:{limit}:member:{contest_team_member_id}"
    )


def contest_question_item_key(
    contest_id: UUID, question_id: UUID, user_id: UUID
) -> str:
    return f"contest:{contest_id}:questions:item:{question_id}:user:{user_id}"


def contest_questions_bust(contest_id: UUID) -> list[str]:
    """Bust list for any contest-question mutation (add/remove/update/reorder/clone)."""
    return [
        contest_bust_pattern(contest_id),
        CONTESTS_LIST_BUST_PATTERN,
        student_question_eval_bust_pattern(contest_id),
    ]


# ---------------------------------------------------------------------------
# Banks
# ---------------------------------------------------------------------------


def bank_key(bank_id: UUID) -> str:
    return f"bank:{bank_id}"


def banks_list_key(
    user_id: UUID,
    *,
    skip: int = 0,
    limit: int = 100,
    search_term: str | None = None,
    sort_by: Any = None,
) -> str:
    sort_value = sort_by.value if sort_by else ""
    return (
        f"banks:user:{user_id}:skip:{skip}:limit:{limit}:"
        f"search:{search_term or ''}:sort:{sort_value}"
    )


def banks_list_bust_pattern(user_id: UUID) -> str:
    return f"banks:user:{user_id}:*"


def banks_deleted_list_key(user_id: UUID, *, skip: int = 0, limit: int = 100) -> str:
    return f"banks:deleted:user:{user_id}:skip:{skip}:limit:{limit}"


def banks_deleted_list_bust_pattern(user_id: UUID) -> str:
    return f"banks:deleted:user:{user_id}:*"


def bank_bust(bank_id: UUID, *user_ids: UUID) -> list[str]:
    """Bust the bank object plus every affected user's bank list caches."""
    keys = [bank_key(bank_id)]
    for uid in user_ids:
        keys.append(banks_list_bust_pattern(uid))
        keys.append(banks_deleted_list_bust_pattern(uid))
    return keys


# ---------------------------------------------------------------------------
# Bank questions
# ---------------------------------------------------------------------------


def bank_questions_list_key(
    bank_id: UUID,
    user_id: UUID,
    *,
    skip: int = 0,
    limit: int = 100,
    filters: Any = None,
) -> str:
    return (
        f"banks:questions:v2:{bank_id}:user:{user_id}:skip:{skip}:limit:{limit}:"
        f"filters:{normalize(filters)}"
    )


def bank_question_item_key(bank_id: UUID, question_id: UUID, user_id: UUID) -> str:
    return f"bank:question:v2:{bank_id}:{question_id}:user:{user_id}"


def bank_question_bust(bank_id: UUID) -> list[str]:
    """Bust list for any bank<->question association mutation."""
    return [
        bank_key(bank_id),
        f"banks:questions:v2:{bank_id}:*",
        f"bank:question:v2:{bank_id}:*",
    ]


# ---------------------------------------------------------------------------
# Questions (global, cross-bank)
# ---------------------------------------------------------------------------


def question_detail_key(question_id: UUID, user_id: UUID) -> str:
    return f"question:{question_id}:user:{user_id}"


def question_bust(question_id: UUID) -> list[str]:
    """Bust every cache that can hold this question: the question detail
    itself, its bank-question associations, and any contest question view
    (instructor list/item + student eval detail) across all contests.

    Questions added to a contest via add_questions_to_contest are linked
    by reference (no deep copy), so editing the question through the
    generic question or bank-question endpoints must also reach the
    student-facing per-contest eval detail key
    (student_question_eval_key: "contests:{contest_id}:questions:{question_id}"),
    which lives under the plural "contests:" namespace with no
    "student:" prefix - distinct from every other pattern below.
    """
    return [
        f"question:{question_id}",
        f"question:{question_id}:*",
        f"bank:question:*:{question_id}:*",
        "banks:questions:*",
        f"contest:*:questions:item:{question_id}:*",
        "contest:*:questions:user:*",
        f"contests:*:questions:{question_id}",
        "student:contest:*",
        "student:contests:*",
    ]


PLATFORM_LANGUAGES_KEY = "platform:languages"
JUDGE0_LANGUAGES_KEY = "judge0:languages"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def user_by_id_key(user_id: UUID) -> str:
    return f"user:id:{user_id}"


def user_by_keycloak_id_key(keycloak_user_id: str) -> str:
    return f"user:keycloak:{keycloak_user_id}"


USER_BY_KEYCLOAK_BUST_PATTERN = "user:keycloak:*"


def user_list_key(filters: Any, actor_id: UUID) -> str:
    return (
        f"user:list:{actor_id}:{filters.role}:{filters.query}:"
        f"{normalize(filters.audience_ids)}:{filters.skip}:{filters.limit}"
    )


USER_LIST_BUST_PATTERN = "user:list:*"


def user_settings_bust(user_id: UUID) -> list[str]:
    return [user_by_id_key(user_id), USER_BY_KEYCLOAK_BUST_PATTERN]


# ---------------------------------------------------------------------------
# Audiences
# ---------------------------------------------------------------------------


def audience_key(audience_id: UUID) -> str:
    return f"audience:{audience_id}"


def audiences_list_key(
    actor_id: UUID, skip: int, limit: int, query: str | None = None
) -> str:
    return f"audiences:user:{actor_id}:skip:{skip}:limit:{limit}:q:{query or ''}"


def audiences_brief_list_key(
    actor_id: UUID,
    is_admin: bool,
    skip: int,
    limit: int,
    query: str | None = None,
) -> str:
    role = "admin" if is_admin else "user"
    return (
        f"audiences:brief:{role}:{actor_id}:skip:{skip}:limit:{limit}:q:{query or ''}"
    )


AUDIENCES_LIST_BUST_PATTERN = "audiences:user:*"
AUDIENCES_BRIEF_BUST_PATTERN = "audiences:brief:*"


def audience_users_list_key(
    audience_id: UUID,
    actor_id: UUID,
    skip: int,
    limit: int,
    *,
    role: Any = None,
    query: str | None = None,
) -> str:
    return (
        f"audience_users:user:{actor_id}:{audience_id}:skip:{skip}:limit:{limit}:"
        f"role:{role or ''}:q:{query or ''}"
    )


def audience_users_bust_pattern(audience_id: UUID) -> str:
    return f"audience_users:user:*:{audience_id}:*"


def audience_list_bust() -> list[str]:
    """Bust for create/update: only the list caches change."""
    return [AUDIENCES_LIST_BUST_PATTERN, AUDIENCES_BRIEF_BUST_PATTERN]


def audience_bust(audience_id: UUID) -> list[str]:
    """Bust for delete/membership changes: list caches, the audience
    object, and its membership caches."""
    return [
        *audience_list_bust(),
        audience_key(audience_id),
        audience_users_bust_pattern(audience_id),
    ]


# ---------------------------------------------------------------------------
# Contest teams (instructor-facing)
# ---------------------------------------------------------------------------


def contest_team_bust_pattern(contest_id: UUID, contest_team_id: UUID) -> str:
    return f"contest:{contest_id}:team:{contest_team_id}:*"


def contest_teams_list_bust_pattern(contest_id: UUID) -> str:
    return f"contest:{contest_id}:teams:*"


def contest_teams_list_key(
    contest_id: UUID,
    user_id: UUID,
    *,
    search_term: str | None = None,
    status: Any = None,
    approval_status: Any = None,
    skip: int = 0,
    limit: int = 100,
    sort_by: Any = None,
    sort_order: str = "desc",
    flagged: Any = None,
) -> str:
    return (
        f"contest:{contest_id}:teams:user:{user_id}:search:{search_term}:"
        f"status:{status}:approval:{approval_status}:skip:{skip}:limit:{limit}:"
        f"sort_by:{sort_by}:sort_order:{sort_order}:flagged:{flagged}"
    )


def contest_team_detail_key(contest_id: UUID, team_id: UUID, user_id: UUID) -> str:
    return f"contest:{contest_id}:team:{team_id}:user:{user_id}"


def contest_team_members_list_key(
    contest_team_id: UUID,
    user_id: UUID,
    *,
    search_term: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> str:
    return (
        f"team:{contest_team_id}:members:user:{user_id}:"
        f"search:{search_term}:skip:{skip}:limit:{limit}"
    )


def contest_team_members_bust_pattern(contest_team_id: UUID) -> str:
    return f"team:{contest_team_id}:members:*"


def contest_team_status_bust(contest_id: UUID, contest_team_id: UUID) -> list[str]:
    """Bust for approve/reject/disqualify: team detail, team list, and its
    member list all change (approval/status is visible in each)."""
    return [
        contest_team_bust_pattern(contest_id, contest_team_id),
        contest_teams_list_bust_pattern(contest_id),
        contest_team_members_bust_pattern(contest_team_id),
    ]


# ---------------------------------------------------------------------------
# Student teams
# ---------------------------------------------------------------------------


def student_teams_list_key(user_id: UUID, filters: Any, pagination: Any) -> str:
    return (
        f"student:teams:user:{user_id}"
        f":search:{filters.search_term or 'none'}"
        f":created:{filters.created_only}"
        f":leader:{filters.leader_only}"
        f":min:{filters.min_size or 'none'}"
    )


def student_team_detail_key(team_id: UUID, user_id: UUID) -> str:
    return f"student:team:{team_id}:user:{user_id}"


def student_teams_list_bust_pattern(user_id: UUID) -> str:
    return f"student:teams:user:{user_id}:*"


def student_team_bust_pattern(team_id: UUID) -> str:
    return f"student:team:{team_id}:*"


STUDENT_TEAMS_SEARCH_BUST_PATTERN = "student:teams:search:*"
STUDENT_TEAMS_LIST_BUST_PATTERN = "student:teams:user:*"


def student_team_search_key(name: str, pagination: Any, user_id: UUID) -> str:
    return (
        f"student:teams:search:{name}"
        f":skip:{pagination.skip}:limit:{pagination.limit}"
        f":user:{user_id}"
    )


def student_team_bust(*user_ids: UUID, team_id: UUID | None = None) -> list[str]:
    """Bust for any team roster/detail mutation affecting the given users
    (and, if known, a specific team)."""
    keys = [STUDENT_TEAMS_SEARCH_BUST_PATTERN, STUDENT_TEAMS_LIST_BUST_PATTERN]
    for uid in user_ids:
        keys.append(student_teams_list_bust_pattern(uid))
    if team_id is not None:
        keys.append(student_team_bust_pattern(team_id))
    return keys


def student_invitations_list_key(
    user_id: UUID,
    invitation_type: Any,
    invitation_status: Any = None,
    team_id: UUID | None = None,
    sent: bool = False,
) -> str:
    status = invitation_status.value if invitation_status else "all"
    return (
        f"student:invitations:user:{user_id}"
        f":type:{invitation_type.value}:status:{status}"
        f":team:{team_id if team_id else 'all'}:sent:{sent}"
    )


def student_invitations_bust_pattern(user_id: UUID) -> str:
    return f"student:invitations:user:{user_id}:*"
