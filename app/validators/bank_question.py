from app.exceptions.bank import (
    BankQuestionAlreadyExistsError,
    BankQuestionNotFoundError,
)


class BankQuestionValidator:
    """Validator for bank-question association constraints.

    Encapsulates business rule validation for operations that link or manage
    questions within a bank context. Ensures data integrity by checking
    prerequisites before state changes occur.

    Methods:
        validate_question_already_exist: Ensure no duplicate question associations
        validate_questions_linked_to_bank: Ensure all required questions are associated
    """

    @staticmethod
    def validate_question_already_exist(existing, bank_id, question_ids):
        """Validate that no provided questions are already linked to the bank.

        Args:
            existing: List of BankQuestion objects already linked to the bank.
            bank_id: UUID of the bank being queried.
            question_ids: List of question UUIDs being validated (for context).

        Raises:
            BankQuestionAlreadyExistsError: If any question in existing is already linked.
        """
        if existing:
            raise BankQuestionAlreadyExistsError(
                str(bank_id), str(existing[0].question_id)
            )

    @staticmethod
    def validate_questions_linked_to_bank(existing, bank_id, question_ids):
        """Validate that all provided questions are linked to the bank.

        Args:
            existing: List of BankQuestion objects currently linked to the bank.
            bank_id: UUID of the bank being checked.
            question_ids: List of question UUIDs that must all be linked.

        Raises:
            BankQuestionNotFoundError: If any question in question_ids is not in existing.
        """
        existing_ids = {bq.question_id for bq in existing}

        missing = [q_id for q_id in question_ids if q_id not in existing_ids]
        if missing:
            raise BankQuestionNotFoundError(str(bank_id), str(missing[0]))
