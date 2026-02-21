from uuid import UUID

from app.exceptions.bank import BankAccessDeniedError, BankPermissionError
from app.models.bank import Bank
from app.utils.enums import BankPermission


class BankOperationGuard:
    """Guard for bank operation permission validation.

    This class evaluates business-level and data-level permissions
    prior to executing repository or service modifications. It throws
    appropriate exceptions if rules are violated.
    """

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
