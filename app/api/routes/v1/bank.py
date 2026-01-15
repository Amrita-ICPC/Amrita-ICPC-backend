from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def get_banks():
    return [{"id": 1, "name": "Bank 1"}]


@router.post("/")
def create_bank():
    return {"message": "Bank created"}
