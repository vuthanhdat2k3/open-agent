import asyncio
import tempfile
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.tools.filesystem import _list_dir, _search_files, _write_file
from app.core.tools.sandbox import _run_code
from app.core.tools.shell import _run_shell
from app.core.tools.types import ToolContext


async def main():
    settings = get_settings()
    engine = create_async_engine(settings.db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_path = Path(temp_dir)
        print(f"Temporary workspace initialized at: {workspace_path}")

        async with async_session() as db:
            ctx = ToolContext(
                db=db,
                org_id="test-org-coder",
                user_id="test-user-coder",
                agent_id="test-agent-coder",
                session_id="test-session-coder",
                workspace_dir=str(workspace_path),
            )

            # 1. Test write_file
            print("\n1. [WRITE_FILE] Writing 'matrix_ops.py'...")
            py_code = (
                "def matrix_mult(A, B):\n"
                "    rows_A = len(A)\n"
                "    cols_A = len(A[0])\n"
                "    rows_B = len(B)\n"
                "    cols_B = len(B[0])\n"
                "    if cols_A != rows_B:\n"
                "        raise ValueError('Incompatible dimensions')\n"
                "    C = [[0 for _ in range(cols_B)] for _ in range(rows_A)]\n"
                "    for i in range(rows_A):\n"
                "        for j in range(cols_B):\n"
                "            for k in range(cols_A):\n"
                "                C[i][j] += A[i][k] * B[k][j]\n"
                "    return C\n\n"
                "if __name__ == '__main__':\n"
                "    A = [[1, 2], [3, 4]]\n"
                "    B = [[5, 6], [7, 8]]\n"
                "    res = matrix_mult(A, B)\n"
                "    print(f'RESULT={res}')\n"
            )
            res_write = await _write_file({"path": "src/matrix_ops.py", "content": py_code}, ctx)
            print("Output:", res_write)

            # 2. Test list_directory
            print("\n2. [LIST_DIRECTORY] Listing workspace root & src/...")
            res_list = await _list_dir({"path": "src"}, ctx)
            print("Output:\n", res_list)

            # 3. Test search_files (grep)
            print("\n3. [SEARCH_FILES] Searching for 'matrix_mult' in workspace...")
            res_search = await _search_files({"pattern": "matrix_mult"}, ctx)
            print("Output:\n", res_search)

            # 4. Test run_code in Docker Sandbox
            print("\n4. [RUN_CODE] Executing Python runner inside Docker Sandbox...")
            runner_code = (
                "from src.matrix_ops import matrix_mult\n"
                "A = [[2, 0], [1, 3]]\n"
                "B = [[1, 4], [2, 5]]\n"
                "print('SANDBOX_CALCULATED:', matrix_mult(A, B))\n"
            )
            res_run_code = await _run_code({"language": "python", "code": runner_code}, ctx)
            print("Output:\n", res_run_code)

            # 5. Test run_shell in Docker Sandbox
            print("\n5. [RUN_SHELL] Executing Bash shell inside Docker Sandbox...")
            shell_cmd = "ls -la src && cat src/matrix_ops.py | grep def && echo 'SHELL_RUNNER_SUCCESS'"
            res_shell = await _run_shell({"cmd": shell_cmd}, ctx)
            print("Output:\n", res_shell)

            # 6. Test File Modification & Delete simulation
            print("\n6. [FILE_MODIFICATION & DELETE] Modifying and cleaning up...")
            target_file = workspace_path / "src" / "matrix_ops.py"
            assert target_file.exists(), "File should exist"
            print(f"File size: {target_file.stat().st_size} bytes")
            target_file.unlink()
            print(f"File deleted. Exists: {target_file.exists()}")

            res_list_after = await _list_dir({"path": "src"}, ctx)
            print("Directory after deletion:\n", res_list_after)

    print("\n=== ALL CODING & SANDBOX TESTS COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(main())
