"""
Student validators - check if data follows business rules.

Examples of business rules:
- Team must have 1-3 members
- Team name must not be empty
- Student can only be in one team per contest
"""

class StudentValidator:
    """Validates student operations."""

    @staticmethod
    def validate_team_name(team_name: str) -> None:
        """
        Business Rule: Team name cannot be empty or too long.
        
        This gets called in SERVICE layer before creating team.
        
        Args:
            team_name: The team name to validate
            
        Raises:
            StudentRegistrationException: If invalid
        """
        if not team_name or len(team_name.strip()) == 0:
            raise StudentRegistrationException("Team name cannot be empty")
        
        if len(team_name) > 100:
            raise StudentRegistrationException("Team name must be 100 characters or less")

    @staticmethod
    def validate_member_emails(emails: list[str] | None) -> None:
        """
        Business Rule: Member emails must be valid format.
        
        Args:
            emails: List of email addresses
            
        Raises:
            StudentRegistrationException: If invalid
        """
        if emails is None:
            return

        if len(emails) == 0:
            raise StudentRegistrationException("At least one member email required")

        for email in emails:
            if "@" not in email:
                raise StudentRegistrationException(f"Invalid email format: {email}")

    @staticmethod
    def validate_team_size(team_size: int, max_size: int = 3) -> None:
        """
        Business Rule: Team cannot have more than max_size members.
        
        Args:
            team_size: Number of members
            max_size: Maximum allowed (default 3)
            
        Raises:
            StudentRegistrationException: If invalid
        """
        if team_size > max_size:
            raise StudentRegistrationException(
                f"Team cannot have more than {max_size} member(s)"
            )


class StudentRegistrationException(Exception):
    """Raised when student registration violates business rules."""
    
    def __init__(self, message: str):
        self.error_code = "STUDENT_REGISTRATION_ERROR"
        self.status_code = 400
        super().__init__(message)