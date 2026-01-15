import enum

class UserRole(enum.Enum):
    student = "student"
    instructor = "instructor"
    admin = "admin"

class QuestionDifficulty(enum.Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
