"""Account lifecycle: soft-delete a user and disconnect their integrations."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.services.user_lifecycle_service import UserLifecycleService

router = APIRouter(prefix="/api/users", tags=["users"])


async def require_platform_admin_any_org(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """platform_admin in any active org — env-independent, unlike the
    slug="platform"-bound check used for organization provisioning."""
    result = await db.execute(
        select(Membership.id).where(
            Membership.user_id == current_user.id,
            Membership.role == Role.platform_admin,
            Membership.lifecycle_status == "active",
        )
    )
    if result.first() is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only platform_admin can deactivate accounts")
    return current_user


@router.post(
    "/{user_id}/deactivate",
)
async def deactivate_user_account(
    user_id: str,
    current_user: User = Depends(require_platform_admin_any_org),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete the account (active -> inactive), revoke sessions and
    disconnect every integration the account created. The user row is kept
    for audit; only the ZITADEL-side identity deletion is a hard delete."""
    ok = await UserLifecycleService(db).deactivate_everywhere(
        user_id=user_id,
        actor_user_id=current_user.id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True, "status": "inactive"}
