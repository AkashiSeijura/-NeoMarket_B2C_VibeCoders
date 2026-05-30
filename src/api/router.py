from fastapi import APIRouter

from src.api.routes import cart, catalog, favorites, home, orders

api_router = APIRouter()
api_router.include_router(cart.router)
api_router.include_router(catalog.router)
api_router.include_router(favorites.router)
api_router.include_router(home.router)
api_router.include_router(orders.router)
