import enum


class UserRole(enum.Enum):
    student = "student"
    instructor = "instructor"
    admin = "admin"
    manager = "manager"


class QuestionDifficulty(enum.Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
