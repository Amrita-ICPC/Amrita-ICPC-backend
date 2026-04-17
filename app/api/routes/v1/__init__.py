from fastapi import APIRouter

from app.api.routes.v1 import (
    bank,
    bank_questions,
    contest,
    execution,
    image,
    question,
    team,
    user,
)
from app.api.routes.v1.students import router as students_router

api_v1_router = APIRouter()

api_v1_router.include_router(user.router, prefix="/users", tags=["Users"])
api_v1_router.include_router(question.router, prefix="/questions", tags=["Questions"])
api_v1_router.include_router(contest.router, prefix="/contests", tags=["Contests"])
api_v1_router.include_router(bank.router, prefix="/banks", tags=["Banks"])
api_v1_router.include_router(
    bank_questions.router, prefix="/banks", tags=["Bank Questions"]
)
api_v1_router.include_router(team.router, tags=["Teams"])
api_v1_router.include_router(students_router, tags=["Students"])
api_v1_router.include_router(execution.router)
api_v1_router.include_router(image.router, tags=["Images"])
