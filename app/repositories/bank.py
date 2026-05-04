from datetime import datetime, timezone
from typing import List
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.exceptions.bank import BankNotFoundError
from app.models.bank import Bank, BankQuestion, BankShare
from app.models.question import Question, QuestionLanguage, QuestionTemplate, TestCase
from app.models.tag import QuestionTag, Tag
from app.models.user import User
from app.repositories.dto import (
    BankFilters,
    BankQuestionFilters,
    PaginatedResult,
    PaginationParams,
)
from app.utils.enums import BankPermission, BankQuestionSortBy, SortOrder


class BankRepository:
    """Repository for bank-related database operations.

    This class encapsulates all direct SQLAlchemy calls and query logic
    for the bank domain.

    Responsibilities:
        - Handle CRUD for banks.
        - Manage bank sharing and permissions relationships.
        - Fetch banks with proper filters for pagination.
        - Hide ORM details from the service layer.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the repository with a database session.

        Args:
            db (AsyncSession): The active SQLAlchemy database session.
        """
        self.db = db

    async def get_bank_or_raise(
        self, bank_id: UUID, load_relations: bool = False
    ) -> Bank:
        """Retrieve a bank by its ID or raise a custom exception if missing.

        Args:
            bank_id (UUID): The unique ID of the bank to fetch.
            load_relations (bool): Whether to eagerly load associated questions and shares.
                Defaults to False for lightweight queries.

        Returns:
            Bank: The corresponding bank model object.

        Raises:
            BankNotFoundError: If the bank cannot be found.
        """
        query = select(Bank)

        if load_relations:
            query = query.options(
                joinedload(Bank.questions)
                .joinedload(BankQuestion.question)
                .selectinload(Question.languages)
                .selectinload(QuestionLanguage.language),
                joinedload(Bank.questions)
                .joinedload(BankQuestion.question)
                .selectinload(Question.testcases),
                joinedload(Bank.questions)
                .joinedload(BankQuestion.question)
                .selectinload(Question.templates)
                .selectinload(QuestionTemplate.language),
                joinedload(Bank.questions)
                .joinedload(BankQuestion.question)
                .selectinload(Question.tags),
                joinedload(Bank.shares),
            )

        result = await self.db.execute(
            query.filter(Bank.id == bank_id, Bank.is_deleted.is_(False))
        )
        bank = result.unique().scalars().first()
        if not bank:
            raise BankNotFoundError(str(bank_id))

        return bank

    async def get_deleted_bank_or_raise(self, bank_id: UUID) -> Bank:
        """Retrieve a softly deleted bank by its ID or raise a custom exception if missing.

        Args:
            bank_id (UUID): The unique ID of the bank to fetch.

        Returns:
            Bank: The corresponding bank model object.

        Raises:
            BankNotFoundError: If the bank cannot be found or is not deleted.
        """
        result = await self.db.execute(
            select(Bank).filter(Bank.id == bank_id, Bank.is_deleted.is_(True))
        )
        bank = result.unique().scalars().first()
        if not bank:
            raise BankNotFoundError(str(bank_id))

        return bank

    async def get_banks_with_filters(
        self,
        user_id: UUID,
        filters: BankFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """Retrieve a paginated list of banks accessible to a specific user.

        A user has access to banks they created or banks shared with them.

        Args:
            user_id (UUID): The user ID requesting the list.
            filters (BankFilters): Filter criteria (e.g., search term).
            pagination (PaginationParams): Pagination definition (skip and limit).

        Returns:
            PaginatedResult: Object containing the total element count and the data slice.
        """
        base_query = (
            select(Bank)
            .outerjoin(BankShare)
            .filter(
                Bank.is_deleted.is_(False),
                or_(Bank.created_by == user_id, BankShare.user_id == user_id),
            )
        )

        if filters.search_term:
            base_query = base_query.filter(Bank.name.ilike(f"%{filters.search_term}%"))

        base_query = base_query.distinct()

        count_query = select(func.count()).select_from(
            base_query.with_only_columns(Bank.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar()

        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        banks = list(result.unique().scalars().all())

        return PaginatedResult(total=total or 0, items=banks)

    async def get_bank_by_name_and_creator(
        self, name: str, user_id: UUID
    ) -> Bank | None:
        """Check if a specific user already created a bank with a given name.

        Args:
            name (str): The requested bank name.
            user_id (UUID): The user attempting to create the bank.

        Returns:
            Bank | None: The existing bank if found, None otherwise.
        """
        result = await self.db.execute(
            select(Bank).filter(Bank.name == name, Bank.created_by == user_id)
        )

        return result.scalars().first()

    async def create_bank(self, bank: Bank) -> Bank:
        """Create a new bank in the database.

        Args:
            bank_data (BankCreate): The data needed to create the bank.
            user_id (UUID): The ID of the user creating the bank.

        Returns:
            Bank: The newly created bank instance populated with default values.
        """
        self.db.add(bank)
        await self.db.flush()
        await self.db.refresh(bank)
        return bank

    async def update_bank(self, bank: Bank) -> Bank:
        """Commit an updated bank model to the database.

        Args:
            bank (Bank): The modified bank model object.

        Returns:
            Bank: The refreshed bank object.
        """
        await self.db.flush()
        await self.db.refresh(bank)
        return bank

    async def delete_bank(self, bank: Bank) -> None:
        """Hard delete a bank from the database.

        Args:
            bank (Bank): The bank object to delete.
        """
        await self.db.delete(bank)
        await self.db.flush()

    async def get_soft_deleted_banks(
        self,
        user_id: UUID,
        filters: BankFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """Retrieve a paginated list of softly deleted banks created by or shared with a user.

        Args:
            user_id (UUID): The user ID requesting the list.
            filters (BankFilters): Filter criteria (e.g., search term).
            pagination (PaginationParams): Pagination definition.

        Returns:
            PaginatedResult: Object containing the data slice.
        """
        base_query = (
            select(Bank)
            .outerjoin(BankShare)
            .filter(
                Bank.is_deleted.is_(True),
                or_(Bank.created_by == user_id, BankShare.user_id == user_id),
            )
        )

        if filters.search_term:
            base_query = base_query.filter(Bank.name.ilike(f"%{filters.search_term}%"))

        base_query = base_query.distinct()

        count_query = select(func.count()).select_from(
            base_query.with_only_columns(Bank.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        banks = list(result.unique().scalars().all())

        return PaginatedResult(total=total, items=banks)

    async def soft_delete_bank(self, bank: Bank, user_id: UUID) -> None:
        """Soft delete a bank by setting deletion flags.

        Args:
            bank (Bank): The bank object to soft delete.
            user_id (UUID): The user ID performing the soft delete.
        """
        bank.is_deleted = True
        bank.deleted_at = datetime.now(timezone.utc)
        bank.deleted_by = user_id
        await self.db.flush()

    async def restore_bank(self, bank: Bank) -> Bank:
        """Restore a softly deleted bank.

        Args:
            bank (Bank): The bank object to restore.

        Returns:
            Bank: The restored bank object.
        """
        bank.is_deleted = False
        bank.deleted_at = None
        bank.deleted_by = None
        await self.db.flush()
        await self.db.refresh(bank)
        return bank

    async def get_share_for_user(
        self, bank_id: UUID, user_id: UUID
    ) -> BankShare | None:
        """Retrieve the specific share permission a user has on a bank.

        Args:
            bank_id (UUID): The bank ID.
            user_id (UUID): The user ID.

        Returns:
            BankShare | None: The share configuration if it exists, otherwise None.
        """
        result = await self.db.execute(
            select(BankShare).filter(
                BankShare.bank_id == bank_id, BankShare.user_id == user_id
            )
        )
        return result.scalars().first()

    async def add_share(
        self, bank_id: UUID, user_id: UUID, permission: BankPermission
    ) -> BankShare:
        """Create a new share entry granting a user access to a bank.

        Args:
            bank_id (UUID): The bank being shared.
            user_id (UUID): The user receiving access.
            permission (BankPermission): The type of access granted.

        Returns:
            BankShare: The created share object.
        """
        share = BankShare(bank_id=bank_id, user_id=user_id, permission=permission)
        self.db.add(share)
        await self.db.flush()
        return share

    async def remove_share(self, bank_id: UUID, user_id: UUID) -> None:
        """Remove a specific user's access to a bank.

        Args:
            bank_id (UUID): The bank ID.
            user_id (UUID): The user ID.
        """
        await self.db.execute(
            delete(BankShare).where(
                BankShare.bank_id == bank_id, BankShare.user_id == user_id
            )
        )
        await self.db.flush()

    async def remove_shares_batch(self, bank_id: UUID, user_ids: List[UUID]) -> None:
        """Remove multiple shares in a single query.

        Args:
            bank_id (UUID): The bank ID.
            user_ids (List[UUID]): The user IDs to unshare.
        """
        if not user_ids:
            return
        await self.db.execute(
            delete(BankShare).where(
                BankShare.bank_id == bank_id, BankShare.user_id.in_(user_ids)
            )
        )
        await self.db.flush()

    async def update_bank_owner(self, bank: Bank, new_owner_id: UUID) -> None:
        """Atomically update the explicit owner field of a bank.

        Args:
            bank (Bank): The database bank model.
            new_owner_id (UUID): The target user ID acquiring ownership.
        """
        bank.created_by = new_owner_id
        await self.db.flush()

    async def update_share_permission(
        self, share: BankShare, permission: BankPermission
    ) -> None:
        """Atomically update an existing share permissions explicitly.

        Args:
            share (BankShare): The database share model.
            permission (BankPermission): The new role being assigned.
        """
        share.permission = permission
        await self.db.flush()

    async def batch_flush(self) -> None:
        """Flush the current session to commit bulk schema changes instantly."""
        await self.db.flush()

    async def get_questions_in_bank_by_ids(
        self, bank_id: UUID, question_ids: List[UUID]
    ) -> List[BankQuestion]:
        """Fetch associative objects matching an array of specific question inputs sequentially.

        Efficiently verifies association linkage utilizing robust SQL targeting vectors exclusively.

        Args:
            bank_id (UUID): Originating structure context bounds checking actively.
            question_ids (List[UUID]): Vector subsets checked across association sets cleanly explicitly.

        Returns:
            List[BankQuestion]: Found associative objects cleanly extracted efficiently directly correctly.
        """
        result = await self.db.execute(
            select(BankQuestion).filter(
                BankQuestion.bank_id == bank_id,
                BankQuestion.question_id.in_(question_ids),
            )
        )
        return list(result.scalars().all())

    async def get_question_entities_in_bank_by_ids(
        self, bank_id: UUID, question_ids: List[UUID]
    ) -> List[Question]:
        """Fetch full Question entities linked to a bank for the given IDs.

        Args:
            bank_id: Source bank identifier.
            question_ids: Specific question IDs to fetch from the source bank.

        Returns:
            List of Question entities that are linked to the provided bank.
        """
        if not question_ids:
            return []

        result = await self.db.execute(
            select(Question)
            .join(BankQuestion, BankQuestion.question_id == Question.id)
            .options(
                selectinload(Question.languages).selectinload(
                    QuestionLanguage.language
                ),
                selectinload(Question.tags),
                selectinload(Question.testcases),
                selectinload(Question.templates).selectinload(
                    QuestionTemplate.language
                ),
            )
            .filter(
                BankQuestion.bank_id == bank_id,
                Question.id.in_(question_ids),
            )
        )
        return list(result.scalars().all())

    async def get_all_question_entities_in_bank(self, bank_id: UUID) -> List[Question]:
        """Fetch all Question entities linked to a bank.

        Args:
            bank_id: Source bank identifier.

        Returns:
            List of all Question entities linked to the provided bank.
        """
        result = await self.db.execute(
            select(Question)
            .join(BankQuestion, BankQuestion.question_id == Question.id)
            .options(
                selectinload(Question.languages).selectinload(
                    QuestionLanguage.language
                ),
                selectinload(Question.tags),
                selectinload(Question.testcases),
                selectinload(Question.templates).selectinload(
                    QuestionTemplate.language
                ),
            )
            .filter(BankQuestion.bank_id == bank_id)
        )
        return list(result.scalars().all())

    async def add_questions_to_bank(
        self, bank_id: UUID, question_ids: List[UUID], user_id: UUID
    ) -> None:
        """Bind bulk collections mapping independent questions locally referencing specific structures seamlessly natively structurally explicitly securely.

        Leverages flush queues injecting batched structures implicitly enforcing schema bindings consistently synchronously properly cleanly.

        Args:
            bank_id (UUID): Central structural context bindings capturing queries uniquely dynamically.
            question_ids (List[UUID]): Unique target constraints globally appending collections natively.
            user_id (UUID): Originator tracking metric explicit log attributes dynamically.
        """
        bqs = [
            BankQuestion(bank_id=bank_id, question_id=q_id, created_by=user_id)
            for q_id in question_ids
        ]
        self.db.add_all(bqs)
        await self.db.flush()

    async def remove_questions_from_bank(self, bqs: List[BankQuestion]) -> None:
        """Sunder explicit tracked associations dynamically natively mapped targeting lists sequentially evaluating strictly.

        Deploys vectorized SQL filtering implicitly evaluating criteria globally destroying relational nodes securely.

        Args:
            bqs (List[BankQuestion]): List of verified associative DB elements to detach completely.
        """
        if not bqs:
            return
        bq_ids = [bq.id for bq in bqs]
        await self.db.execute(delete(BankQuestion).filter(BankQuestion.id.in_(bq_ids)))
        await self.db.flush()

    async def get_questions_in_bank(
        self,
        bank_id: UUID,
        pagination: PaginationParams,
        filters: BankQuestionFilters | None = None,
    ) -> PaginatedResult:
        """Retrieve core subsets evaluated cleanly matching query metrics structurally paginated explicitly properly.

        Extract dynamically linked Question records matching the parent origin Bank ID utilizing optimized SQL Join filtering.
        Supports filtering by title, difficulty, and tags. Supports ordering by title (name) and difficulty.

        Args:
            bank_id (UUID): Source bounds restriction targets.
            pagination (PaginationParams): Offset bounds safely passed to underlying slices explicitly cleanly.
            filters (BankQuestionFilters): Optional filtering and sorting criteria.

        Returns:
            PaginatedResult: Dynamic chunk data collection mapped structurally cleanly successfully.
        """
        base_query = (
            select(Question)
            .join(BankQuestion, BankQuestion.question_id == Question.id)
            .filter(BankQuestion.bank_id == bank_id)
        )

        # Apply filters
        if filters:
            if filters.title:
                base_query = base_query.filter(Question.title.ilike(f"%{filters.title}%"))
            
            if filters.difficulty:
                base_query = base_query.filter(Question.difficulty == filters.difficulty)
            
            if filters.tag:
                tag_subquery = (
                    select(QuestionTag.question_id)
                    .join(Tag, Tag.id == QuestionTag.tag_id)
                    .filter(Tag.name.ilike(f"%{filters.tag}%"))
                )
                base_query = base_query.filter(Question.id.in_(tag_subquery))

        # Apply sorting
        if filters and filters.sort_by:
            sort_attr = None
            if filters.sort_by == BankQuestionSortBy.NAME:
                sort_attr = Question.title
            elif filters.sort_by == BankQuestionSortBy.DIFFICULTY:
                sort_attr = Question.difficulty
            
            if sort_attr is not None:
                if filters.sort_order == SortOrder.DESC:
                   base_query = base_query.order_by(sort_attr.desc(), Question.id.asc())
                else:
                    base_query = base_query.order_by(sort_attr.asc(), Question.id.asc())
        else:
            base_query = base_query.order_by(BankQuestion.created_at, Question.id)

        base_query = base_query.options(
            selectinload(Question.languages).selectinload(
                QuestionLanguage.language
            ),
            selectinload(Question.tags).selectinload(QuestionTag.tag),
            selectinload(Question.templates).selectinload(
                QuestionTemplate.language
            ),
        )

        # Count query doesn't need ORDER BY or DISTINCT now
        count_query = select(func.count()).select_from(base_query.order_by(None).subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        questions = list(result.unique().scalars().all())

        if questions:
            question_ids = [question.id for question in questions]
            count_result = await self.db.execute(
                select(TestCase.question_id, func.count(TestCase.id))
                .where(TestCase.question_id.in_(question_ids))
                .group_by(TestCase.question_id)
            )
            testcase_counts = {qid: count for qid, count in count_result.all()}
            for question in questions:
                setattr(question, "testcase_count", testcase_counts.get(question.id, 0))

        return PaginatedResult(total=total, items=questions)

    async def get_bank_shares_with_filters(
        self,
        bank_id: UUID,
        email: str | None = None,
        username: str | None = None,
    ) -> tuple[User, List[BankShare]]:
        """Retrieve bank owner and filtered share list.

        Args:
            bank_id (UUID): Target bank.
            email (str | None): Optional email filter for shares.
            username (str | None): Optional username (user_id) filter for shares.

        Returns:
            Tuple[User, List[BankShare]]: The bank owner and the list of shares.
        """
        # Fetch bank to get owner
        bank_query = (
            select(Bank)
            .options(joinedload(Bank.creator))
            .filter(Bank.id == bank_id, Bank.is_deleted.is_(False))
        )
        bank_result = await self.db.execute(bank_query)
        bank = bank_result.unique().scalars().first()
        if not bank:
            raise BankNotFoundError(str(bank_id))

        # Fetch shares with filters
        shares_query = (
            select(BankShare)
            .join(User, User.id == BankShare.user_id)
            .options(joinedload(BankShare.user))
            .filter(BankShare.bank_id == bank_id)
        )

        if email:
            shares_query = shares_query.filter(User.email.ilike(f"%{email}%"))
        if username:
            shares_query = shares_query.filter(User.user_id.ilike(f"%{username}%"))

        shares_result = await self.db.execute(shares_query)
        shares = list(shares_result.scalars().all())

        return bank.creator, shares

    async def update_shares_permission(
        self, bank_id: UUID, user_ids: List[UUID], permission: BankPermission
    ) -> None:
        """Update multiple share permissions at once.

        Args:
            bank_id (UUID): The bank ID.
            user_ids (List[UUID]): The users to update.
            permission (BankPermission): The new permission level.
        """
        await self.db.execute(
            update(BankShare)
            .where(BankShare.bank_id == bank_id, BankShare.user_id.in_(user_ids))
            .values(permission=permission)
        )
        await self.db.flush()
