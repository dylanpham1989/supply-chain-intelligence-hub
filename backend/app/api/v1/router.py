from fastapi import APIRouter

from app.api.v1 import alerts, analytics, auth, shipments, suppliers, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(shipments.router)
api_router.include_router(suppliers.router)
api_router.include_router(alerts.router)
api_router.include_router(analytics.router)
