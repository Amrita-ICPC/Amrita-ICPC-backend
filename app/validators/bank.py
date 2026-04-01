from uuid import UUID

from app.exceptions.bank import (
    BankAccessDeniedError,
    BankAlreadyExistsError,
    BankPermissionError,
)
from app.models.bank import Bank
from app.utils.enums import BankPermission


class BankValidator:
    """Validator for resolving core bank business rules and structure logic.

    This class handles the logic validating inputs ahead of applying database operations.
    Unlike guards that enforce authorizations, validators ensure the inputs
    to functions fulfill the domain state requirements.
    """

    @staticmethod
    def validate_unique_bank_creation(existing_bank: Bank | None, name: str) -> None:
        """Ensure a user doesn't create duplicate bank names.

        Args:
            existing_bank (Bank | None): The query returned by the repository for this name.
            name (str): The name being tested.

        Raises:
            BankAlreadyExistsError: If the model was populated, a conflict exists.
        """
        if existing_bank:
            raise BankAlreadyExistsError(name)

    @staticmethod
    def construct_valid_update_payload(update_dict: dict) -> dict:
        """Process out invalid fields and return a safe dictionary for updates.

        Skips empty names and unspecified optional fields.

        Args:
            update_dict (dict): The incoming schema dictionary via Pydantic model_dump.

        Returns:
            dict: The validated, sanitized fields to apply.
        """
        validated = {}
        for field, value in update_dict.items():
            if field == "name" and (value is None or value.strip() == ""):
                continue
            if value is None:
                continue
            # Optionally validate description size here or rely on Pydantic's initial validation
            validated[field] = value
        return validated

    @staticmethod
    def check_read_bank(user_id: UUID, bank: Bank) -> None:
        """Confirm a user is authorized to view a bank's contents.

        Requires the user to either own the bank or have a direct share.

        Args:
            user_id (UUID): The attempting user's ID.
            bank (Bank): The bank object being tested.

        Raises:
            BankAccessDeniedError: If the user lacks both ownership and shares.
        """
        if bank.created_by == user_id:
            return  # The owner has full read access

        has_access = any(share.user_id == user_id for share in bank.shares)
        if not has_access:
            raise BankAccessDeniedError()

    @staticmethod
    def check_edit_bank(user_id: UUID, bank: Bank) -> None:
        """Confirm a user is authorized to edit a bank's metadata natively.

        Requires ownership or an explicit `edit` share permission.

        Args:
            user_id (UUID): The attempting user's ID.
            bank (Bank): The bank object being tested.

        Raises:
            BankAccessDeniedError: If the user has absolutely no access.
            BankPermissionError: If the user only has `read` access.
        """
        if bank.created_by == user_id:
            return  # Owner has full edit access

        # Evaluate what type of share they possess
        share_permission = None
        for share in bank.shares:
            if share.user_id == user_id:
                share_permission = share.permission
                break

        if not share_permission:
            raise BankAccessDeniedError()

        if share_permission == BankPermission.read:
            raise BankPermissionError()

    @staticmethod
    def check_manage_bank(user_id: UUID, bank: Bank) -> None:
        """Confirm a user is the owner of the bank.

        This level of control is required for destructive operations like deleting
        or altering access configurations (sharing/unsharing).

        Args:
            user_id (UUID): The attempting user's ID.
            bank (Bank): The target bank.

        Raises:
            BankPermissionError: If the user is not the owner.
        """
        if bank.created_by == user_id:
            return

        owner_share = next(
            (
                s
                for s in bank.shares
                if s.user_id == user_id and s.permission == BankPermission.owner
            ),
            None,
        )
        if owner_share:
            return

        raise BankPermissionError()
