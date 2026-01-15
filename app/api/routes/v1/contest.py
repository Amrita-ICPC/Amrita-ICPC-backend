from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def get_contests():
    return [{"id": 1, "name": "Contest 1"}]


@router.post("/")
def create_contest():
    return {"message": "Contest created"}
