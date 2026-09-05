from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.execution_policy import ExecutionPolicy
from app.db.base import Base, gen_id, utc_now


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    agent_release_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_releases.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(256), default="New session")
    execution_policy: Mapped[str] = mapped_column(
        String(16), default=ExecutionPolicy.manual.value, nullable=False
    )
    # Set once by the ops_repo.repo_worktree_open tool. When present,
    # ToolContext.workspace_dir uses this real git-worktree path instead of
    # the default ephemeral sandbox for the rest of this session's tool
    # calls (write_file/run_code etc. work unmodified against it).
    workspace_override_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
