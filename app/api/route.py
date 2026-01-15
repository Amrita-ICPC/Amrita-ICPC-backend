from fastapi import APIRouter
from app.api.routes import health
from app.api.routes.v1 import api_v1_router

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(api_v1_router, prefix="/v1")
