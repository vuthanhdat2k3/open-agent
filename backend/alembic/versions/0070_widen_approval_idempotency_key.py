"""Widen approval_requests.idempotency_key to match the ORM model.

c1973696 (2026-09-02, "fix(approval): widen idempotency_key column to 256
chars") widened the column only in app/models/approval_request.py, without a
migration. The live column stayed VARCHAR(128) while the app builds keys as
f"{root_run_id}:{task_id}:{tool_name}:{sha256_hex}" - routinely 130-150+
chars for any nested delegation - so every such INSERT raised
StringDataRightTruncationError, poisoning the session (PendingRollbackError)
and silently killing the whole request. This is why a manual-approval-gated
tool call (e.g. write_file under a delegated sub-agent) never produced an
ApprovalRequest row and the run appeared to hang forever with no error.

Revision ID: 0070_widen_approval_idempotency_key
Revises: 0069_membership_multi_role
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0070_widen_approval_idempotency_key"
down_revision: str | None = "0069_membership_multi_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.alter_column(
            "idempotency_key",
            existing_type=sa.String(length=128),
            type_=sa.String(length=256),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.alter_column(
            "idempotency_key",
            existing_type=sa.String(length=256),
            type_=sa.String(length=128),
            existing_nullable=True,
        )
