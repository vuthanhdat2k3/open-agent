from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command


def test_multitenancy_migration_backfill(tmp_path: Path) -> None:
    db_file = tmp_path / "test_migration.db"
    sync_url = f"sqlite:///{db_file.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", async_url)

    engine = create_engine(sync_url)

    # 1. Create pre-M1 schema tables ONLY (without org_id / created_by_user_id)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE providers ("
                "id VARCHAR(36) PRIMARY KEY, "
                "key VARCHAR(64) UNIQUE NOT NULL, "
                "name VARCHAR(128) UNIQUE NOT NULL, "
                "base_url VARCHAR(512) NOT NULL, "
                "api_key VARCHAR(512) NOT NULL, "
                "env_var VARCHAR(128) NOT NULL, "
                "is_default BOOLEAN, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE models ("
                "id VARCHAR(36) PRIMARY KEY, "
                "provider_id VARCHAR(36) NOT NULL, "
                "name VARCHAR(128) NOT NULL, "
                "display_name VARCHAR(128) NOT NULL, "
                "tier VARCHAR(32), "
                "context_window INTEGER, "
                "input_cost_per_1k FLOAT, "
                "output_cost_per_1k FLOAT, "
                "active BOOLEAN, "
                "created_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE agents ("
                "id VARCHAR(36) PRIMARY KEY, "
                "name VARCHAR(128) UNIQUE NOT NULL, "
                "description VARCHAR(512), "
                "system_prompt TEXT NOT NULL, "
                "model_id VARCHAR(36) NOT NULL, "
                "tools JSON, "
                "max_iterations INTEGER, "
                "temperature FLOAT, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE mcp_servers ("
                "id VARCHAR(36) PRIMARY KEY, "
                "name VARCHAR(128) UNIQUE NOT NULL, "
                "transport_type VARCHAR(32) NOT NULL, "
                "config JSON NOT NULL, "
                "status VARCHAR(32), "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE workflows ("
                "id VARCHAR(36) PRIMARY KEY, "
                "name VARCHAR(128) UNIQUE NOT NULL, "
                "description VARCHAR(512), "
                "definition JSON NOT NULL, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE sessions ("
                "id VARCHAR(36) PRIMARY KEY, "
                "title VARCHAR(256), "
                "agent_id VARCHAR(36), "
                "workflow_id VARCHAR(36), "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE messages ("
                "id VARCHAR(36) PRIMARY KEY, "
                "session_id VARCHAR(36) NOT NULL, "
                "role VARCHAR(32) NOT NULL, "
                "content TEXT NOT NULL, "
                "tokens INTEGER, "
                "created_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE usage_events ("
                "id VARCHAR(36) PRIMARY KEY, "
                "session_id VARCHAR(36), "
                "agent_id VARCHAR(36), "
                "model_id VARCHAR(36), "
                "prompt_tokens INTEGER, "
                "completion_tokens INTEGER, "
                "cost FLOAT, "
                "created_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE uploaded_files ("
                "id VARCHAR(36) PRIMARY KEY, "
                "filename VARCHAR(256) NOT NULL, "
                "filepath VARCHAR(512) NOT NULL, "
                "file_size INTEGER NOT NULL, "
                "mime_type VARCHAR(128), "
                "session_id VARCHAR(36), "
                "created_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE agent_memories ("
                "id VARCHAR(36) PRIMARY KEY, "
                "agent_id VARCHAR(36) NOT NULL, "
                "owner_type VARCHAR(32) NOT NULL, "
                "memory_type VARCHAR(64) NOT NULL, "
                "attribute VARCHAR(128) NOT NULL, "
                "value TEXT NOT NULL, "
                "importance INTEGER, "
                "confidence FLOAT, "
                "source VARCHAR(32), "
                "metadata JSON, "
                "last_accessed_at DATETIME, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE session_memories ("
                "id VARCHAR(36) PRIMARY KEY, "
                "session_id VARCHAR(36) NOT NULL, "
                "key VARCHAR(256) NOT NULL, "
                "value TEXT NOT NULL, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )

        # Insert pre-M1 sample data into models, providers, agents
        conn.execute(
            text(
                "INSERT INTO providers (id, key, name, base_url, api_key, env_var, is_default, created_at, updated_at) "
                "VALUES ('p1', 'openai', 'OpenAI', 'http://api', '', '', 1, '2026-01-01', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO models (id, provider_id, name, display_name, created_at) "
                "VALUES ('m1', 'p1', 'gpt-4o', 'GPT-4o', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO agents (id, name, description, system_prompt, model_id, tools, max_iterations, temperature, created_at, updated_at) "
                "VALUES ('a1', 'Legacy Agent', 'Pre-M1 Agent', 'Prompt', 'm1', '[]', 10, 0.7, '2026-01-01', '2026-01-01')"
            )
        )

    engine.dispose()

    # 2. Stamp Alembic at 0001_structured_memory
    command.stamp(alembic_cfg, "0001_structured_memory")

    # 3. Upgrade to head (runs 0002 and 0003)
    command.upgrade(alembic_cfg, "head")

    # 4. Assert migrations and backfill
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        orgs = conn.execute(text("SELECT id, name, slug FROM organizations")).fetchall()
        assert len(orgs) == 1
        assert orgs[0][0] == "default-org-id"
        assert orgs[0][1] == "Default Organization"
        assert orgs[0][2] == "default"

        users = conn.execute(text("SELECT id, email, display_name FROM users")).fetchall()
        assert len(users) == 1
        assert users[0][0] == "default-user-id"
        assert users[0][1] == "admin@openagent.local"

        memberships = conn.execute(text("SELECT org_id, user_id, role FROM memberships")).fetchall()
        assert len(memberships) == 1
        assert memberships[0][0] == "default-org-id"
        assert memberships[0][1] == "default-user-id"
        # 0059_profile_role_hardening normalizes the legacy ``admin`` spelling
        assert memberships[0][2] == "org_admin"

        releases = conn.execute(
            text(
                "SELECT agent_id, version, status, system_prompt "
                "FROM agent_releases WHERE agent_id = 'a1'"
            )
        ).fetchall()
        assert releases == [("a1", 1, "published", "Prompt")]
        active_release = conn.execute(
            text(
                "SELECT active_release_id, latest_release_number "
                "FROM agents WHERE id = 'a1'"
            )
        ).one()
        assert active_release[0]
        assert active_release[1] == 1

        agents = conn.execute(text("SELECT id, name, org_id, allowed_risk_tiers FROM agents")).fetchall()
        assert len(agents) == 1
        assert agents[0][0] == "a1"
        assert agents[0][2] == "default-org-id"
        assert agents[0][3] == '["safe", "read"]'

        # 5. Assert composite unique constraint per-tenant on migrated DB:
        # Create a second organization and insert an agent & provider with identical name/key
        conn.execute(
            text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES ('org-2', 'Org 2', 'org-2', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO providers (id, org_id, key, name, base_url, api_key, env_var, is_default, created_at, updated_at) "
                "VALUES ('p2', 'org-2', 'openai', 'OpenAI', 'http://api2', '', '', 0, '2026-01-01', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO agents (id, org_id, name, description, system_prompt, model_id, tools, max_iterations, temperature, created_at, updated_at) "
                "VALUES ('a2', 'org-2', 'Legacy Agent', 'Agent in Org 2', 'Prompt', 'm1', '[]', 10, 0.7, '2026-01-01', '2026-01-01')"
            )
        )

        agents_org2 = conn.execute(text("SELECT id, name, org_id FROM agents WHERE org_id = 'org-2'")).fetchall()
        assert len(agents_org2) == 1
        assert agents_org2[0][0] == "a2"
        assert agents_org2[0][1] == "Legacy Agent"

    engine.dispose()
