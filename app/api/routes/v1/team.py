from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_teams():
    return [{"id": 1, "name": "Team 1"}]

@router.post("/")
def create_team():
    return {"message": "Team created"}
