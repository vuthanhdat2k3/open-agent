import pytest

from app.core.runtime_context import (
    build_runtime_context,
    normalize_timezone,
    now_in_timezone,
)
from app.core.tools.builtins import _get_current_time
from app.core.tools.types import ToolContext


def test_runtime_context_uses_iana_timezone() -> None:
    context = build_runtime_context("Asia/Bangkok")

    assert "User timezone: Asia/Bangkok" in context
    assert "Local date:" in context
    assert "Current UTC:" in context


def test_invalid_timezone_falls_back_to_vietnam() -> None:
    assert normalize_timezone("not/a-zone") == "Asia/Ho_Chi_Minh"
    assert now_in_timezone("not/a-zone").tzinfo.key == "Asia/Ho_Chi_Minh"


@pytest.mark.asyncio
async def test_current_time_tool_returns_fresh_authoritative_time() -> None:
    result = await _get_current_time({}, ToolContext(db=None, timezone_name="Asia/Bangkok"))  # type: ignore[arg-type]

    assert "Timezone: Asia/Bangkok" in result
    assert "UTC:" in result
    assert "Local date:" in result
