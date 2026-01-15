from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_users():
    return [{"id": 1, "name": "User 1"}]

@router.post("/")
def create_user():
    return {"message": "User created"}
