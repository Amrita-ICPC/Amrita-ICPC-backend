"""Execution strategies translating a question's testcases into Judge0 submissions.

Standard (imperative) questions send the student's program as-is with the
testcase input as stdin, and let Judge0 diff stdout against the expected
output. SQL questions assemble a different program per testcase (a database
fixture plus the student's query) and judge the result set on the platform
side, since Judge0's trimmed exact-match can't express "same rows, any
order" or SQL-specific formatting.

Every call site that talks to Judge0 (practice run, draft run, and the
official submit/evaluation pipeline) resolves a strategy via
:func:`get_execution_strategy` and routes submission-building and
pass/fail judging through it, so question-type-specific behavior lives in
exactly one place.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod

from app.core.config import config
from app.repositories.dto.judge0 import Judge0ExecutionRequestDTO
from app.utils.enums import QuestionType

# SQLite dot-commands prepended to every SQL submission so the result set is
# rendered in a stable, comparable format regardless of the student's query.
# `.separator` is pinned explicitly rather than relying on `.mode list`'s
# built-in default, so the format doesn't depend on the sqlite3 build Judge0
# happens to run.
_SQLITE_OUTPUT_PRAGMA = '.headers on\n.mode list\n.separator "|"\n.nullvalue NULL\n'


@dataclasses.dataclass(frozen=True)
class TestCaseView:
    """Minimal per-testcase shape an execution strategy needs.

    Decouples strategies from the several differently-shaped testcase
    objects used across call sites (ORM ``TestCase``, the evaluation
    pipeline's ``QuestionTestCaseResponse``, and the ephemeral draft-run
    ``DraftTestCase``, which even names its expected-output field
    differently). Callers adapt their native testcase object to this view
    once, at the call site.
    """

    input: str
    """Stdin for STANDARD questions; fixture SQL (DDL + seed data) for SQL."""

    output: str
    """Expected stdout for STANDARD questions; expected result set for SQL."""

    is_ordered: bool = True
    """SQL-only: whether row order in `output` must match exactly."""


class ExecutionStrategy(ABC):
    """Builds Judge0 submissions for a question and judges their results."""

    @abstractmethod
    def build_submission(
        self, request: Judge0ExecutionRequestDTO, testcase: TestCaseView
    ) -> tuple[Judge0ExecutionRequestDTO, str, str | None]:
        """Build the (request, stdin, expected_output) to submit to Judge0.

        Args:
            request: Base execution request (source code, language, limits).
            testcase: The testcase driving this submission.

        Returns:
            A tuple of the (possibly testcase-specific) request, the stdin to
            send, and the expected_output to send Judge0 for its own
            comparison (``None`` when the strategy judges the result itself).
        """

    @abstractmethod
    def passed(
        self, *, judge0_accepted: bool, stdout: str | None, testcase: TestCaseView
    ) -> bool:
        """Decide pass/fail for a Judge0 result that did not error out.

        Args:
            judge0_accepted: Whether Judge0 itself reported ACCEPTED. For
                strategies that send ``expected_output``, this already
                reflects Judge0's own diff. For strategies that don't, it
                only means "ran without crashing".
            stdout: Decoded stdout from the execution.
            testcase: The testcase this result belongs to.

        Returns:
            True if the submission should be judged as passing this testcase.
        """

    def redact(self, text: str | None, testcase: TestCaseView) -> str | None:
        """Strip any hidden judge setup out of text before it reaches a client.

        Default: no-op. STANDARD questions have nothing analogous to redact
        -- hidden testcases are already excluded server-side before a
        response is built, so stdin is never a client-visible secret in the
        first place. SQL overrides this because its fixture is invisibly
        prepended to every submission (Judge0 has no separate "seed the
        database" step), so it can otherwise leak into stderr/compile_output
        for a student-triggered query error.

        Args:
            text: Raw stderr/compile_output/message from a Judge0 result.
            testcase: The testcase the result belongs to.

        Returns:
            ``text``, with anything that must stay hidden removed.
        """
        return text

    def visible_input(self, testcase: TestCaseView) -> str | None:
        """Return the testcase input safe to echo back to a client, or None.

        Default: return it as-is. STANDARD's stdin is only ever shown for
        non-hidden testcases, and it's the student's own input, not a
        secret. SQL overrides this to always return ``None``, since
        ``testcase.input`` there is the instructor's hidden database fixture
        (schema + seed) rather than anything the student provided.
        """
        return testcase.input


class StandardExecutionStrategy(ExecutionStrategy):
    """Today's behavior: run the program as-is and let Judge0 diff the output."""

    def build_submission(self, request, testcase):
        return request, testcase.input, testcase.output

    def passed(self, *, judge0_accepted, stdout, testcase):
        return judge0_accepted


class SqlExecutionStrategy(ExecutionStrategy):
    """Runs a student query against a per-testcase SQLite fixture.

    No stdin and no ``expected_output`` are sent to Judge0: the fixture is
    baked into the submitted source (Judge0 has no separate "seed the
    database" step), and the result-set comparison runs on the platform via
    :meth:`passed` rather than Judge0's trimmed exact-match, so unordered
    result sets can be judged correctly.

    Two authoring constraints fall out of the comparison scheme:

    - The fixture (``testcase.input``) must be pure DDL/DML (``CREATE``,
      ``INSERT``, ...) that produces no query output of its own -- any stray
      ``SELECT`` in the fixture would print its own header line and shift
      everything :func:`_result_sets_match` assumes about line 0.
    - The judged query is expected to be a single ``SELECT``. sqlite3 prints
      a fresh header line per statement with ``.headers on``, so a
      multi-statement query with more than one result-producing ``SELECT``
      is not handled correctly by the unordered (``is_ordered=False``)
      comparison, which sorts everything after line 0 as one data-row set.
    """

    def build_submission(self, request, testcase):
        fixture_sql = testcase.input
        source = f"{_SQLITE_OUTPUT_PRAGMA}{fixture_sql}\n{request.source_code}"
        return dataclasses.replace(request, source_code=source), "", None

    def passed(self, *, judge0_accepted, stdout, testcase):
        if not judge0_accepted:
            return False
        return _result_sets_match(
            stdout or "", testcase.output, ordered=testcase.is_ordered
        )

    def redact(self, text, testcase):
        if not text:
            return text
        fixture_sql = testcase.input
        redacted = text.replace(fixture_sql, "[hidden setup omitted]")
        redacted = redacted.replace(_SQLITE_OUTPUT_PRAGMA, "")
        return redacted

    def visible_input(self, testcase):
        return None


def _result_sets_match(actual: str, expected: str, *, ordered: bool) -> bool:
    """Compare SQLite ``.mode list`` output, trimming trailing whitespace per line.

    Args:
        actual: Raw stdout captured from the SQLite submission.
        expected: Expected result set, in the same ``.mode list`` format.
        ordered: When False, data rows (everything after the header row) are
            compared as a multiset instead of positionally, since SQLite does
            not guarantee row order without an explicit ``ORDER BY``.

    Returns:
        True if the two result sets are equivalent under the given ordering
        rule.
    """
    actual_lines = [line.rstrip() for line in actual.strip("\n").splitlines()]
    expected_lines = [line.rstrip() for line in expected.strip("\n").splitlines()]
    if ordered or not actual_lines or not expected_lines:
        return actual_lines == expected_lines
    return actual_lines[0] == expected_lines[0] and sorted(actual_lines[1:]) == sorted(
        expected_lines[1:]
    )


def get_execution_strategy(
    *,
    question_type: QuestionType | None = None,
    language_id: int | None = None,
) -> ExecutionStrategy:
    """Resolve the execution strategy for a question or a draft run.

    Question-bound runs and submits know ``question_type`` directly. Draft
    runs have no persisted Question, so SQL is instead inferred from
    ``language_id`` matching the configured Judge0 SQLite language.

    Args:
        question_type: The question's persisted type, if known.
        language_id: The Judge0 language ID being executed, if known.

    Returns:
        A ``SqlExecutionStrategy`` when either signal indicates SQL,
        otherwise the ``StandardExecutionStrategy``.
    """
    is_sql = question_type == QuestionType.SQL or (
        language_id is not None and language_id == config.JUDGE0_SQLITE_LANGUAGE_ID
    )
    return SqlExecutionStrategy() if is_sql else StandardExecutionStrategy()
