from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_questions():
    return [{"id": 1, "text": "Question 1"}]

@router.post("/")
def create_question():
    return {"message": "Question created"}
