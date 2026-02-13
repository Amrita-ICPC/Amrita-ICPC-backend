from fastapi import APIRouter

from app.api.routes.v1 import bank, contest, question, team, user

api_v1_router = APIRouter()

api_v1_router.include_router(user.router, prefix="/users", tags=["Users"])
api_v1_router.include_router(question.router, prefix="/questions", tags=["Questions"])
api_v1_router.include_router(contest.router, prefix="/contests", tags=["Contests"])
api_v1_router.include_router(bank.router, prefix="/banks", tags=["Banks"])
api_v1_router.include_router(team.router, tags=["Teams"])
