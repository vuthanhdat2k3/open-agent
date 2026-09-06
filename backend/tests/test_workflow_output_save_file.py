"""The `output` node's `save_as_file` config must actually write to the
Sandbox workspace.

Regression for a bug found via live testing: the output node's schema/UI let
authors set `delivery_channel`/`store_format`/`store_name`, but the engine
never read any of them — the "save the brief as a file" part of a generated
workflow silently did nothing. `save_as_file`/`file_name` are the real,
engine-backed replacement fields.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.core.workflow.engine import _save_output_file


async def test_save_output_file_writes_markdown_under_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.core.workflow.engine.get_settings",
        lambda: SimpleNamespace(workspace_dir=str(tmp_path)),
    )
    workflow = SimpleNamespace(id="wf-1", org_id="org-1")
    await _save_output_file(workflow, {"file_name": "briefs/today"}, "hello world", db=None, user_id=None)
    assert (tmp_path / "briefs" / "today.md").read_text(encoding="utf-8") == "hello world"


async def test_save_output_file_defaults_name_from_workflow_id(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.core.workflow.engine.get_settings",
        lambda: SimpleNamespace(workspace_dir=str(tmp_path)),
    )
    workflow = SimpleNamespace(id="wf-42", org_id="org-1")
    await _save_output_file(workflow, {}, "content", db=None, user_id=None)
    assert (tmp_path / "workflow-outputs" / "wf-42.md").exists()


async def test_save_output_file_rejects_path_escape(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.core.workflow.engine.get_settings",
        lambda: SimpleNamespace(workspace_dir=str(tmp_path)),
    )
    workflow = SimpleNamespace(id="wf-1", org_id="org-1")
    await _save_output_file(
        workflow, {"file_name": "../../etc/passwd"}, "pwned", db=None, user_id=None
    )
    assert not any(tmp_path.parent.rglob("passwd*"))
