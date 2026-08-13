"""Atomic daily budget reservations for trusted-rule automation.

Budget counters are admission control, not analytics.  Callers must reserve
both the user and organization scope in the same transaction before creating
an auto-execution proposal.  The conditional UPDATE is deliberately done in
SQL so concurrent workers cannot pass a read-then-write check together.
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_intelligence.contracts import AutomationBudgetReservation
from app.db.base import gen_id, utc_now
from app.models.customer_intelligence import CiAutomationBudget


def _insert_for_dialect(db: AsyncSession):
    dialect = db.bind.dialect.name if db.bind is not None else "postgresql"
    if dialect == "sqlite":
        return sqlite_insert(CiAutomationBudget)
    return postgres_insert(CiAutomationBudget)


async def reserve_daily_budget(
    db: AsyncSession,
    *,
    budget_date: str,
    user_id: str,
    org_id: str,
    user_limit: int,
    org_limit: int,
    amount: int = 1,
) -> AutomationBudgetReservation:
    """Reserve one or more daily budget units atomically in the transaction.

    If either scope has no capacity, no counter is committed by this helper;
    the caller should roll back the surrounding transaction and route the
    email to explicit approval.  A successful reservation is only durable
    when the caller commits the same transaction that creates the proposal.
    """

    if amount < 1:
        raise ValueError("amount must be positive")

    scopes = (("USER", user_id, user_limit), ("ORG", org_id, org_limit))
    reserved: list[tuple[str, str]] = []
    for scope_type, scope_id, budget_limit in scopes:
        statement = _insert_for_dialect(db).values(
            id=gen_id(),
            scope_type=scope_type,
            scope_id=scope_id,
            budget_date=budget_date,
            used=0,
            budget_limit=budget_limit,
            updated_at=utc_now(),
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=["scope_type", "scope_id", "budget_date"]
        )
        await db.execute(statement)

        result = await db.execute(
            update(CiAutomationBudget)
            .where(
                CiAutomationBudget.scope_type == scope_type,
                CiAutomationBudget.scope_id == scope_id,
                CiAutomationBudget.budget_date == budget_date,
                CiAutomationBudget.used + amount <= CiAutomationBudget.budget_limit,
            )
            .values(used=CiAutomationBudget.used + amount, updated_at=utc_now())
            .returning(CiAutomationBudget.id)
        )
        if result.scalar_one_or_none() is None:
            return AutomationBudgetReservation(reserved=False, scopes=reserved, reason="AUTOMATION_BUDGET_EXCEEDED")
        reserved.append((scope_type, scope_id))

    return AutomationBudgetReservation(reserved=True, scopes=reserved, reason=None)


async def reserve_scope_budget(
    db: AsyncSession,
    *,
    scope_type: str,
    scope_id: str,
    budget_date: str,
    budget_limit: int,
    amount: int = 1,
) -> bool:
    """Atomically reserve a single generic daily budget scope."""
    statement = _insert_for_dialect(db).values(
        id=gen_id(),
        scope_type=scope_type,
        scope_id=scope_id,
        budget_date=budget_date,
        used=0,
        budget_limit=budget_limit,
        updated_at=utc_now(),
    )
    await db.execute(
        statement.on_conflict_do_nothing(
            index_elements=["scope_type", "scope_id", "budget_date"]
        )
    )
    result = await db.execute(
        update(CiAutomationBudget)
        .where(
            CiAutomationBudget.scope_type == scope_type,
            CiAutomationBudget.scope_id == scope_id,
            CiAutomationBudget.budget_date == budget_date,
            CiAutomationBudget.used + amount <= CiAutomationBudget.budget_limit,
        )
        .values(used=CiAutomationBudget.used + amount, updated_at=utc_now())
        .returning(CiAutomationBudget.id)
    )
    return result.scalar_one_or_none() is not None
