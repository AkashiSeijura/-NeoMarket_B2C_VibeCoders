from fastapi import APIRouter

from src.api.routes import cart, catalog

api_router = APIRouter()
api_router.include_router(cart.router)
api_router.include_router(catalog.router)
