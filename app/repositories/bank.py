from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.exceptions.bank import BankNotFoundError
from app.models.bank import Bank, BankShare
from app.repositories.dto import BankFilters, PaginatedResult, PaginationParams
from app.schema.bank import BankCreate
from app.utils.enums import BankPermission


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

    def __init__(self, db: Session):
        """Initialize the repository with a database session.

        Args:
            db (Session): The active SQLAlchemy database session.
        """
        self.db = db

    def get_bank_or_raise(self, bank_id: UUID, load_relations: bool = False) -> Bank:
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
        query = self.db.query(Bank)

        if load_relations:
            query = query.options(joinedload(Bank.questions), joinedload(Bank.shares))

        bank = query.filter(Bank.id == bank_id, Bank.is_deleted.is_(False)).first()
        if not bank:
            raise BankNotFoundError(str(bank_id))

        return bank

    def get_deleted_bank_or_raise(self, bank_id: UUID) -> Bank:
        """Retrieve a softly deleted bank by its ID or raise a custom exception if missing.

        Args:
            bank_id (UUID): The unique ID of the bank to fetch.

        Returns:
            Bank: The corresponding bank model object.

        Raises:
            BankNotFoundError: If the bank cannot be found or is not deleted.
        """
        bank = (
            self.db.query(Bank)
            .filter(Bank.id == bank_id, Bank.is_deleted.is_(True))
            .first()
        )
        if not bank:
            raise BankNotFoundError(str(bank_id))

        return bank

    def get_banks_with_filters(
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
            self.db.query(Bank)
            .outerjoin(BankShare)
            .filter(
                Bank.is_deleted.is_(False),
                or_(Bank.created_by == user_id, BankShare.user_id == user_id),
            )
        )

        if filters.search_term:
            base_query = base_query.filter(Bank.name.ilike(f"%{filters.search_term}%"))

        base_query = base_query.distinct()
        total = base_query.count()
        banks = base_query.offset(pagination.skip).limit(pagination.limit).all()

        return PaginatedResult(total=total, items=banks)

    def get_bank_by_name_and_creator(self, name: str, user_id: UUID) -> Bank | None:
        """Check if a specific user already created a bank with a given name.

        Args:
            name (str): The requested bank name.
            user_id (UUID): The user attempting to create the bank.

        Returns:
            Bank | None: The existing bank if found, None otherwise.
        """
        return (
            self.db.query(Bank)
            .filter(Bank.name == name, Bank.created_by == user_id)
            .first()
        )

    def create_bank(self, bank_data: BankCreate, user_id: UUID) -> Bank:
        """Create a new bank in the database.

        Args:
            bank_data (BankCreate): The data needed to create the bank.
            user_id (UUID): The ID of the user creating the bank.

        Returns:
            Bank: The newly created bank instance populated with default values.
        """
        db_bank = Bank(
            name=bank_data.name,
            description=bank_data.description,
            created_by=user_id,
            is_deleted=False,
        )
        self.db.add(db_bank)
        self.db.flush()
        self.db.refresh(db_bank)
        return db_bank

    def update_bank(self, bank: Bank) -> Bank:
        """Commit an updated bank model to the database.

        Args:
            bank (Bank): The modified bank model object.

        Returns:
            Bank: The refreshed bank object.
        """
        self.db.flush()
        self.db.refresh(bank)
        return bank

    def delete_bank(self, bank: Bank) -> None:
        """Hard delete a bank from the database.

        Args:
            bank (Bank): The bank object to delete.
        """
        self.db.delete(bank)
        self.db.flush()

    def get_soft_deleted_banks(
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
            self.db.query(Bank)
            .outerjoin(BankShare)
            .filter(
                Bank.is_deleted.is_(True),
                or_(Bank.created_by == user_id, BankShare.user_id == user_id),
            )
        )

        if filters.search_term:
            base_query = base_query.filter(Bank.name.ilike(f"%{filters.search_term}%"))

        base_query = base_query.distinct()
        total = base_query.count()
        banks = base_query.offset(pagination.skip).limit(pagination.limit).all()

        return PaginatedResult(total=total, items=banks)

    def soft_delete_bank(self, bank: Bank, user_id: UUID) -> None:
        """Soft delete a bank by setting deletion flags.

        Args:
            bank (Bank): The bank object to soft delete.
            user_id (UUID): The user ID performing the soft delete.
        """
        bank.is_deleted = True
        bank.deleted_at = datetime.now(timezone.utc)
        bank.deleted_by = user_id
        self.db.flush()

    def restore_bank(self, bank: Bank) -> Bank:
        """Restore a softly deleted bank.

        Args:
            bank (Bank): The bank object to restore.

        Returns:
            Bank: The restored bank object.
        """
        bank.is_deleted = False
        bank.deleted_at = None
        bank.deleted_by = None
        self.db.flush()
        self.db.refresh(bank)
        return bank

    def get_share_for_user(self, bank_id: UUID, user_id: UUID) -> BankShare | None:
        """Retrieve the specific share permission a user has on a bank.

        Args:
            bank_id (UUID): The bank ID.
            user_id (UUID): The user ID.

        Returns:
            BankShare | None: The share configuration if it exists, otherwise None.
        """
        return (
            self.db.query(BankShare)
            .filter(BankShare.bank_id == bank_id, BankShare.user_id == user_id)
            .first()
        )

    def add_share(
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
        self.db.flush()
        return share

    def remove_share(self, share: BankShare) -> None:
        """Remove a user's access to a bank.

        Args:
            share (BankShare): The share association to delete.
        """
        self.db.delete(share)
        self.db.flush()

    def batch_flush(self) -> None:
        """Flush the current session to commit bulk schema changes instantly."""
        self.db.flush()
