"""
Central API router -- mounts public endpoints and admin sub-router.
"""

from fastapi import APIRouter

from .endpoints import access, auth, health, internal, payments, webhook, payment_flow, sms_webhook, public_settings, ad_watch, credit_packages
from .admin.router import router as admin_router

api_router = APIRouter()

# -- public endpoints -------------------------------------------------
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(webhook.router, prefix="/webhook", tags=["webhook"])
api_router.include_router(access.router, prefix="/access", tags=["access"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(payment_flow.router, prefix="/payments", tags=["payment-flow"])
api_router.include_router(sms_webhook.router, prefix="/sms", tags=["sms"])
api_router.include_router(public_settings.router, prefix="/settings", tags=["public-settings"])
api_router.include_router(internal.router, prefix="/internal", tags=["internal"])
api_router.include_router(ad_watch.router, prefix="/ad-watch", tags=["ad-watch"])
api_router.include_router(credit_packages.router, prefix="/credit-packages", tags=["credit-packages"])

# -- admin endpoints (JWT-protected) ---------------------------------
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])