from fastapi import APIRouter
from sqlalchemy import text
from fastapi import Depends
from sqlalchemy.orm import Session
from app.core.clients.database import get_db

router = APIRouter()

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        # Check database connection
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
