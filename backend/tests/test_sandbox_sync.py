from __future__ import annotations

import io
import tarfile
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.tools.registry import get_tool
from app.core.tools.sandbox import (
    build_docker_args,
    sync_sandbox_artifacts,
)
from app.core.tools.types import ToolContext
from app.db.base import Base
from app.models.workspace import WorkspaceArtifact


def test_build_docker_args_rm_flags() -> None:
    args_rm = build_docker_args("python", "script.py", rm=True)
    assert "--rm" in args_rm
    assert "--read-only" in args_rm
    assert any("tmpfs" in a for a in args_rm)

    args_no_rm = build_docker_args("python", "script.py", rm=False)
    assert "--rm" not in args_no_rm
    assert "--read-only" not in args_no_rm
    assert not any("tmpfs" in a for a in args_no_rm)


async def test_sync_sandbox_artifacts_extracts_and_upserts(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Prepare fake tar containing reports/Bao_Cao_ProtonX_VietNam.pdf
    pdf_content = b"%PDF-1.4 simulated pdf binary content"
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        info = tarfile.TarInfo("reports/Bao_Cao_ProtonX_VietNam.pdf")
        info.size = len(pdf_content)
        tar.addfile(info, io.BytesIO(pdf_content))
    tar_bytes = tar_buf.getvalue()

    diff_output = b"A /work/reports\nA /work/reports/Bao_Cao_ProtonX_VietNam.pdf\nA /work/script.py\n"

    class FakeDiffProc:
        returncode = 0

        async def communicate(self):
            return diff_output, b""

    class FakeCpProc:
        returncode = 0

        async def communicate(self):
            return tar_bytes, b""

    async def fake_create_subprocess_exec(*args, **_kwargs):
        if args[1] == "diff":
            return FakeDiffProc()
        if args[1] == "cp":
            return FakeCpProc()
        raise ValueError(f"unexpected command {args}")

    async with session_factory() as session:
        ctx = ToolContext(
            db=session,
            org_id="org-test-123",
            user_id="user-test-456",
            session_id="session-789",
            workspace_dir=str(tmp_path),
        )

        with patch("app.core.tools.sandbox._docker_available", return_value=True), patch(
            "app.core.tools.sandbox.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec
        ):
            synced = await sync_sandbox_artifacts(
                "cname-test",
                str(tmp_path),
                script_filename="script.py",
                ctx=ctx,
                source_tool="run_code",
            )

        assert "reports/Bao_Cao_ProtonX_VietNam.pdf" in synced
        assert "script.py" not in synced

        # Verify file is extracted on disk
        dest_file = tmp_path / "reports" / "Bao_Cao_ProtonX_VietNam.pdf"
        assert dest_file.exists()
        assert dest_file.read_bytes() == pdf_content

        # Verify DB artifact record was created
        res = await session.execute(select(WorkspaceArtifact).where(WorkspaceArtifact.org_id == "org-test-123"))
        artifacts = res.scalars().all()
        assert len(artifacts) == 1
        assert artifacts[0].path == "reports/Bao_Cao_ProtonX_VietNam.pdf"
        assert artifacts[0].size == len(pdf_content)
        assert artifacts[0].source_tool == "run_code"
        assert artifacts[0].created_by_user_id == "user-test-456"

    await engine.dispose()


async def test_run_code_end_to_end_mock_syncs_artifacts(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    csv_content = b"col1,col2\nval1,val2\n"
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        info = tarfile.TarInfo("output.csv")
        info.size = len(csv_content)
        tar.addfile(info, io.BytesIO(csv_content))
    tar_bytes = tar_buf.getvalue()

    diff_output = b"A /work/output.csv\nA /work/script.py\n"

    class FakeReader:
        def __init__(self) -> None:
            self._lines = iter([b"Generated CSV output\n"])

        async def readline(self) -> bytes:
            return next(self._lines, b"")

    class FakeWriter:
        def write(self, _b: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

    class FakeProcess:
        returncode = 0
        stdin = FakeWriter()
        stdout = FakeReader()

        async def wait(self) -> None:
            return None

    class FakeDiffProc:
        returncode = 0

        async def communicate(self):
            return diff_output, b""

    class FakeCpProc:
        returncode = 0

        async def communicate(self):
            return tar_bytes, b""

    class FakeKillProc:
        returncode = 0

        async def wait(self):
            return None

    async def fake_create_subprocess_exec(*args, **_kwargs):
        if args[0] == "docker" and args[1] == "run":
            return FakeProcess()
        if args[0] == "docker" and args[1] == "diff":
            return FakeDiffProc()
        if args[0] == "docker" and args[1] == "cp":
            return FakeCpProc()
        if args[0] == "docker" and args[1] in ("rm", "kill"):
            return FakeKillProc()
        raise ValueError(f"unexpected command {args}")

    async with session_factory() as session:
        ctx = ToolContext(
            db=session,
            org_id="org-test-csv",
            user_id="user-csv",
            workspace_dir=str(tmp_path),
        )

        with patch("app.core.tools.sandbox._docker_available", return_value=True), patch(
            "app.core.tools.sandbox.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec
        ):
            run_code_tool = get_tool("run_code")
            res = await run_code_tool.run(
                {"language": "python", "code": "print('hello')", "filename": "script.py"},
                ctx,
            )

        assert "Generated CSV output" in res
        assert "exit code: 0" in res
        assert "artifacts synced to workspace: output.csv" in res

        # Check extracted file
        assert (tmp_path / "output.csv").exists()
        assert (tmp_path / "output.csv").read_bytes() == csv_content

        # Check DB record
        res_db = await session.execute(select(WorkspaceArtifact).where(WorkspaceArtifact.org_id == "org-test-csv"))
        records = res_db.scalars().all()
        assert len(records) == 1
        assert records[0].path == "output.csv"
        assert records[0].size == len(csv_content)

    await engine.dispose()
