"""
Admin sub-router -- every route is protected by JWT via ``require_admin``.
"""

from fastapi import APIRouter, Depends

from backend.security.auth import require_admin

from . import (
    analytics,
    backups,
    bots,
    bug_reports,
    cooldowns,
    content_factory,
    content_transfer,
    content_packs,
    credits,
    dlq,
    logs,
    memberships,
    membership_plans,
    notifications,
    pack_items,
    payment_management,
    platform_settings,
    referrals,
    streaks,
    test_panel,
    tokens,
    tutorials,
    upi_config,
    users,
    credit_packages,
)

router = APIRouter(dependencies=[Depends(require_admin)])

router.include_router(users.router, prefix="/users", tags=["admin-users"])
router.include_router(bots.router, prefix="/bots", tags=["admin-bots"])
router.include_router(content_packs.router, prefix="/content-packs", tags=["admin-content-packs"])
router.include_router(pack_items.router, prefix="/pack-items", tags=["admin-pack-items"])
router.include_router(tokens.router, prefix="/tokens", tags=["admin-tokens"])
router.include_router(credits.router, prefix="/credits", tags=["admin-credits"])
router.include_router(memberships.router, prefix="/memberships", tags=["admin-memberships"])
router.include_router(membership_plans.router, prefix="/membership-plans", tags=["admin-membership-plans"])
router.include_router(referrals.router, prefix="/referrals", tags=["admin-referrals"])
router.include_router(upi_config.router, prefix="/upi-config", tags=["admin-upi-config"])
router.include_router(payment_management.router, prefix="/payment-mgmt", tags=["admin-payment-mgmt"])
router.include_router(analytics.router, prefix="/analytics", tags=["admin-analytics"])
router.include_router(platform_settings.router, prefix="/settings", tags=["admin-settings"])
router.include_router(cooldowns.router, prefix="/cooldowns", tags=["admin-cooldowns"])
router.include_router(test_panel.router, prefix="/test", tags=["admin-test"])
router.include_router(logs.router, prefix="/logs", tags=["admin-logs"])
router.include_router(credit_packages.router, prefix="/credit-packages", tags=["admin-credit-packages"])
router.include_router(streaks.router, prefix="/streaks", tags=["admin-streaks"])
router.include_router(dlq.router, prefix="/dlq", tags=["admin-dlq"])
router.include_router(notifications.router, prefix="/notifications", tags=["admin-notifications"])
router.include_router(content_factory.router, prefix="/content-factory", tags=["admin-content-factory"])
router.include_router(content_transfer.router, prefix="/content-transfer", tags=["admin-content-transfer"])
router.include_router(bug_reports.router, prefix="/bug-reports", tags=["admin-bug-reports"])
router.include_router(tutorials.router, prefix="/tutorials", tags=["admin-tutorials"])
router.include_router(backups.router, prefix="/backups", tags=["admin-backups"])
