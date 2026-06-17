"""Data transfer objects for contest question operations.

This module defines DTOs that encapsulate data transferred between the API
schema layer and the repository layer for contest question operations. Using
DTOs maintains a clear separation of concerns and prevents API schemas from
leaking into persistence logic.

DTOs in this module:
    - AddContestQuestionData: DTO for adding a question to a contest
    - RemoveContestQuestionData: DTO for removing a question from a contest
    - AddContestQuestionsData: DTO for batch adding multiple questions
    - RemoveContestQuestionsData: DTO for batch removing multiple questions
"""

from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID


@dataclass
class AddContestQuestionData:
    """
    Data transfer object for adding a question to a contest.

    This DTO encapsulates the data needed to add a question to a contest at the
    repository level, maintaining independence from the API schema layer.

    Attributes:
        contest_id: UUID of the contest.
        question_id: UUID of the question to add.
        order: Position of the question in the contest (1-indexed).
        duration: Time allocated for this question in seconds.
        score: Points awarded for solving this question.
        created_by: UUID of the user adding the question.
    """

    contest_id: UUID
    question_id: UUID
    order: int
    duration: Optional[int]
    score: Optional[int]
    created_by: UUID
    max_submission: Optional[int] = None
    bank_question_id: Optional[UUID] = None


@dataclass
class RemoveContestQuestionData:
    """
    Data transfer object for removing a question from a contest.

    This DTO encapsulates the data needed to remove a question from a contest
    at the repository level.

    Attributes:
        contest_id: UUID of the contest.
        question_id: UUID of the question to remove.
    """

    contest_id: UUID
    question_id: UUID


@dataclass
class AddContestQuestionsData:
    """
    Data transfer object for batch adding multiple questions to a contest.

    This DTO encapsulates the list of questions to add in a single batch operation.

    Attributes:
        questions: List of AddContestQuestionData for each question to add.
    """

    questions: List[AddContestQuestionData]


@dataclass
class RemoveContestQuestionsData:
    """
    Data transfer object for batch removing multiple questions from a contest.

    This DTO encapsulates the question IDs to remove in a single batch operation.

    Attributes:
        contest_id: UUID of the contest.
        question_ids: List of question IDs to remove.
    """

    contest_id: UUID
    question_ids: List[UUID]
