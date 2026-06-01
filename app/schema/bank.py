from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schema.user import UserBasicInfo
from app.utils.enums import (
    BankPermission,
    BankQuestionSortBy,
    QuestionDifficulty,
    SortOrder,
)


class BankBase(BaseModel):
    """Base schema for a Bank containing core editable attributes.

    This model provides the common fields used across various bank schemas
    like creation and response models.
    """

    name: str = Field(..., min_length=1, max_length=255, description="Bank name")
    description: Optional[str] = Field(
        None, max_length=5000, description="Bank description"
    )


class BankCreate(BankBase):
    """Schema for bank creation requests.

    Inherits all core fields from BankBase and requires them for initial creation.
    """

    pass


class BankUpdate(BaseModel):
    """Schema for bank update requests.

    All fields are optional because updates can be partial
    (e.g., updating only the name or only the description).
    """

    name: Optional[str] = Field(None, max_length=255, description="Bank name")
    description: Optional[str] = Field(
        None, max_length=5000, description="Bank description"
    )


class BankResponse(BankBase):
    """Schema for standard bank responses.

    Provides the standard view of a bank including metadata like IDs and timestamps.
    """

    id: UUID = Field(..., description="Bank ID")
    created_by: UUID = Field(..., description="Creator user ID")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Last update time")

    model_config = ConfigDict(from_attributes=True)


class BankShareBase(BaseModel):
    """Base schema for representing a bank share configuration.

    Describes what permission level a specific user has on a bank.
    """

    user_id: UUID = Field(..., description="User ID the bank is shared with")
    permission: BankPermission = Field(..., description="Permission level granted")

    model_config = ConfigDict(from_attributes=True)


class BankDetailResponse(BankResponse):
    """Schema for detailed bank responses.

    Includes the standard bank response and extends it by providing
    aggregated counts of associated questions and share configurations.
    """

    total_questions_count: int = Field(
        default=0, description="Total number of questions in the bank"
    )
    easy_questions_count: int = Field(default=0, description="Number of easy questions")
    medium_questions_count: int = Field(
        default=0, description="Number of medium questions"
    )
    hard_questions_count: int = Field(default=0, description="Number of hard questions")
    shared_users_count: int = Field(
        default=0, description="Number of users the bank is shared with"
    )


class BankShareItem(BaseModel):
    """Schema representing an individual share instruction.

    Used when processing a request to share a bank with specific users.
    """

    user_id: UUID = Field(..., description="User ID to share with")
    permission: BankPermission = Field(
        default=BankPermission.read, description="Permission level"
    )


class BankShareRequest(BaseModel):
    """Schema for processing a bulk bank sharing request.

    Contains a list of shares to add or modify for a bank.
    """

    shares: List[BankShareItem] = Field(..., description="List of users to share with")


class BankQuestionBulk(BaseModel):
    """Schema for processing a bulk bank question manipulation target request.

    Contains a robust list of keys executing against Bank operations explicitly.
    """

    question_ids: List[UUID] = Field(
        ...,
        description="List of target question IDs to assign or strip array",
    )


class BankQuestionCloneRequest(BaseModel):
    """Schema for cloning questions from one bank to another.

    Attributes:
        target_bank_id: Destination bank where cloned questions will be created.
        copy_all: When true, clones all questions from the source bank.
        question_ids: Source-bank IDs to clone; required when copy_all is false
    """

    target_bank_id: UUID = Field(..., description="Destination bank ID")
    copy_all: bool = Field(
        default=False,
        description="Clone all source-bank questions when true",
    )
    question_ids: Optional[List[UUID]] = Field(
        default=None,
        description="Source question IDs to clone; required when copy_all is false",
    )


class BankQuestionFilters(BaseModel):
    """Schema for bank question filtering and sorting parameters."""

    title: Optional[str] = None
    difficulty: Optional[QuestionDifficulty] = None
    tag: Optional[str] = None
    sort_by: Optional[BankQuestionSortBy] = BankQuestionSortBy.NAME
    sort_order: SortOrder = SortOrder.ASC


class BankShareUserResponse(UserBasicInfo):
    """User detail response with associated bank permission."""

    permission: BankPermission


class BankSharesResponse(BaseModel):
    """Comprehensive bank access list including owner and explicit shares."""

    owner: UserBasicInfo
    shares: List[BankShareUserResponse]
