from app.exceptions.bank import BankAlreadyExistsError
from app.models.bank import Bank


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
    def construct_valid_update_payload(update_dict: dict, existing_bank: Bank) -> dict:
        """Process out invalid fields and return a safe dictionary for updates.

        Skips empty names and unspecified optional fields.

        Args:
            update_dict (dict): The incoming schema dictionary via Pydantic model_dump.
            existing_bank (Bank): The existing model instance.

        Returns:
            dict: The validated, sanitized fields to apply.
        """
        validated = {}
        for field, value in update_dict.items():
            if field == "name" and (value is None or value.strip() == ""):
                continue
            # Optionally validate description size here or rely on Pydantic's initial validation
            validated[field] = value
        return validated
