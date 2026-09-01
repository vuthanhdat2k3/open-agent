import asyncio
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import get_settings
from app.models.application_session import ApplicationSession
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

API_BASE = "http://127.0.0.1.sslip.io:8000"

ROLES_USERS = {
    "user": "user@protonx.com",
    "operator": "operator@protonx.com",
    "org_admin": "admin@protonx.com",
    "platform_admin": "zitadel-admin@zitadel.127.0.0.1.sslip.io",
}

def _hash(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()

async def create_direct_test_session(db, email: str) -> tuple[str, str, str]:
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()
    if not user:
        raise ValueError(f"User {email} not found")
    
    m_res = await db.execute(select(Membership).where(Membership.user_id == user.id))
    membership = m_res.scalars().first()
    if not membership:
        raise ValueError(f"Membership for {email} not found")

    settings = get_settings()
    raw_session = secrets.token_urlsafe(48)
    raw_csrf = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    session = ApplicationSession(
        session_token_hash=_hash(raw_session),
        csrf_token_hash=_hash(raw_csrf),
        user_id=user.id,
        organization_id=membership.org_id,
        membership_id=membership.id,
        auth_time=now,
        last_seen_at=now,
        idle_expires_at=now + timedelta(minutes=settings.application_session_idle_minutes or 120),
        absolute_expires_at=now + timedelta(hours=settings.application_session_absolute_hours or 24),
        created_ip_hash=None,
        created_user_agent_hash=None,
    )
    db.add(session)
    await db.commit()
    return raw_session, raw_csrf, membership.org_id

async def run_api_suite():
    settings = get_settings()
    engine = create_async_engine(settings.db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    tokens = {}
    csrf_tokens = {}
    org_ids = {}

    print("--- 1. Generating direct Application Sessions for all 4 roles ---")
    async with async_session() as db:
        for role, email in ROLES_USERS.items():
            try:
                raw_session, raw_csrf, org_id = await create_direct_test_session(db, email)
                tokens[role] = raw_session
                csrf_tokens[role] = raw_csrf
                org_ids[role] = org_id
                print(f"[{role.upper()}] Session generated for {email} (org: {org_id})")
            except Exception as e:
                print(f"[{role.upper()}] Error: {e}")

    results = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        protonx_org_id = org_ids.get("user") or org_ids.get("org_admin")

        # First fetch a valid model_id for testing agent creation
        op_cookie = f"{settings.application_session_cookie_name or 'oa_session'}={tokens.get('operator')}"
        models_resp = await client.get(f"{API_BASE}/api/models", headers={"Cookie": op_cookie})
        model_list = models_resp.json() if models_resp.status_code == 200 else []
        test_model_id = model_list[0]["id"] if model_list else "dummy-model-id"

        endpoints = [
            # 1. Health & Status
            {"name": "GET /health", "method": "GET", "url": "/health", "role": "user", "expected": [200]},
            {"name": "GET /api/health", "method": "GET", "url": "/api/health", "role": "user", "expected": [200]},
            
            # 2. Auth Identity
            {"name": "GET /api/auth/me (User)", "method": "GET", "url": "/api/auth/me", "role": "user", "expected": [200]},
            {"name": "GET /api/auth/me (Operator)", "method": "GET", "url": "/api/auth/me", "role": "operator", "expected": [200]},
            {"name": "GET /api/auth/me (Org Admin)", "method": "GET", "url": "/api/auth/me", "role": "org_admin", "expected": [200]},
            {"name": "GET /api/auth/me (Platform Admin)", "method": "GET", "url": "/api/auth/me", "role": "platform_admin", "expected": [200]},

            # 3. Agents Management
            {"name": "GET /api/agents (User - Read Allowed)", "method": "GET", "url": "/api/agents", "role": "user", "expected": [200]},
            {"name": "GET /api/agents/tools (Operator)", "method": "GET", "url": "/api/agents/tools", "role": "operator", "expected": [200]},
            {"name": "POST /api/agents (User - Forbidden 403)", "method": "POST", "url": "/api/agents", "role": "user", "json": {"name": "Test", "kind": "worker", "model_id": test_model_id}, "expected": [403]},
            {"name": "POST /api/agents (Operator - Allowed 201)", "method": "POST", "url": "/api/agents", "role": "operator", "json": {"name": "Test Worker E2E Sweep", "kind": "worker", "model_id": test_model_id, "system_prompt": "You are a test agent."}, "expected": [200, 201]},

            # 4. Providers & Models
            {"name": "GET /api/providers (User - Forbidden 403)", "method": "GET", "url": "/api/providers", "role": "user", "expected": [403]},
            {"name": "GET /api/providers (Operator - Allowed 200)", "method": "GET", "url": "/api/providers", "role": "operator", "expected": [200]},
            {"name": "GET /api/providers/templates (Operator 200)", "method": "GET", "url": "/api/providers/templates", "role": "operator", "expected": [200]},
            {"name": "GET /api/models/tier-matrix (User - Allowed Read 200)", "method": "GET", "url": "/api/models/tier-matrix", "role": "user", "expected": [200]},
            {"name": "GET /api/models/tier-matrix (Operator - Allowed 200)", "method": "GET", "url": "/api/models/tier-matrix", "role": "operator", "expected": [200]},
            {"name": "PUT /api/models/tier-matrix (User - Forbidden 403)", "method": "PUT", "url": "/api/models/tier-matrix", "role": "user", "json": {"economy_model_id": test_model_id}, "expected": [403]},
            {"name": "GET /api/models (Operator - Allowed 200)", "method": "GET", "url": "/api/models", "role": "operator", "expected": [200]},

            # 5. Sessions & Chat
            {"name": "GET /api/sessions (User - Allowed 200)", "method": "GET", "url": "/api/sessions", "role": "user", "expected": [200]},

            # 6. Workflows
            {"name": "GET /api/workflows (User - Allowed 200)", "method": "GET", "url": "/api/workflows", "role": "user", "expected": [200]},
            {"name": "GET /api/workflows/node-definitions (User 200)", "method": "GET", "url": "/api/workflows/node-definitions", "role": "user", "expected": [200]},
            {"name": "GET /api/workflows/node-options (User 200)", "method": "GET", "url": "/api/workflows/node-options", "role": "user", "expected": [200]},
            {"name": "GET /api/workflows/tool-options (User 200)", "method": "GET", "url": "/api/workflows/tool-options", "role": "user", "expected": [200]},

            # 7. MCP Servers
            {"name": "GET /api/mcp/servers (User - Forbidden 403)", "method": "GET", "url": "/api/mcp/servers", "role": "user", "expected": [403]},
            {"name": "GET /api/mcp/servers (Operator - Allowed 200)", "method": "GET", "url": "/api/mcp/servers", "role": "operator", "expected": [200]},

            # 8. Files / Knowledge Base
            {"name": "GET /api/files (User - Allowed Read 200)", "method": "GET", "url": "/api/files", "role": "user", "expected": [200]},
            {"name": "GET /api/files (Operator - Allowed 200)", "method": "GET", "url": "/api/files", "role": "operator", "expected": [200]},

            # 9. Workspace / Sandbox
            {"name": "GET /api/workspace/artifacts (User - Allowed Read 200)", "method": "GET", "url": "/api/workspace/artifacts", "role": "user", "expected": [200]},
            {"name": "GET /api/workspace/artifacts (Operator - Allowed 200)", "method": "GET", "url": "/api/workspace/artifacts", "role": "operator", "expected": [200]},

            # 10. Evaluations
            {"name": "GET /api/evaluations/suites (User - Forbidden 403)", "method": "GET", "url": "/api/evaluations/suites", "role": "user", "expected": [403]},
            {"name": "GET /api/evaluations/suites (Operator - Allowed 200)", "method": "GET", "url": "/api/evaluations/suites", "role": "operator", "expected": [200]},

            # 11. Customer & Email Intelligence
            {"name": "GET /api/customer-intelligence/cases (User 200)", "method": "GET", "url": "/api/customer-intelligence/cases", "role": "user", "expected": [200]},
            {"name": "GET /api/customer-intelligence/calendar-connections (User 200)", "method": "GET", "url": "/api/customer-intelligence/calendar-connections", "role": "user", "expected": [200]},
            {"name": "GET /api/email-intelligence/trusted-rules (User 200)", "method": "GET", "url": "/api/email-intelligence/trusted-rules", "role": "user", "expected": [200]},

            # 12. Approvals
            {"name": "GET /api/approvals (User 200)", "method": "GET", "url": "/api/approvals", "role": "user", "expected": [200]},

            # 13. Audit & Observability
            {"name": "GET /api/debug/sessions (User - Allowed Read 200)", "method": "GET", "url": "/api/debug/sessions", "role": "user", "expected": [200]},
            {"name": "GET /api/debug/sessions (Operator - Allowed 200)", "method": "GET", "url": "/api/debug/sessions", "role": "operator", "expected": [200]},
            {"name": "GET /api/debug/usage (Org Admin - Allowed 200)", "method": "GET", "url": "/api/debug/usage", "role": "org_admin", "expected": [200]},

            # 14. Org Administration (Members, Quotas, Email Gateway)
            {"name": f"GET /api/orgs/{protonx_org_id}/members (Operator - Forbidden 403)", "method": "GET", "url": f"/api/orgs/{protonx_org_id}/members", "role": "operator", "expected": [403]},
            {"name": f"GET /api/orgs/{protonx_org_id}/members (Org Admin - Allowed 200)", "method": "GET", "url": f"/api/orgs/{protonx_org_id}/members", "role": "org_admin", "expected": [200]},
            {"name": f"GET /api/orgs/{protonx_org_id}/quota (Operator - Forbidden 403)", "method": "GET", "url": f"/api/orgs/{protonx_org_id}/quota", "role": "operator", "expected": [403]},
            {"name": f"GET /api/orgs/{protonx_org_id}/quota (Org Admin - Allowed 200)", "method": "GET", "url": f"/api/orgs/{protonx_org_id}/quota", "role": "org_admin", "expected": [200]},
            {"name": "GET /api/admin/email-intelligence/overview (Org Admin - Allowed 200)", "method": "GET", "url": "/api/admin/email-intelligence/overview", "role": "org_admin", "expected": [200]},

            # 15. Platform Administration (Multi-Tenancy)
            {"name": "GET /api/orgs (Org Admin - Read own/scoped 200)", "method": "GET", "url": "/api/orgs", "role": "org_admin", "expected": [200]},
            {"name": "POST /api/orgs (Org Admin - Forbidden 403)", "method": "POST", "url": "/api/orgs", "role": "org_admin", "json": {"name": "Unauthorized Org"}, "expected": [403]},
            {"name": "GET /api/orgs (Platform Admin - Full List 200)", "method": "GET", "url": "/api/orgs", "role": "platform_admin", "expected": [200]},
        ]

        print("\n--- 2. Executing API Test Matrix ---")
        cookie_name = settings.application_session_cookie_name or "oa_session"
        for ep in endpoints:
            role = ep["role"]
            tok = tokens.get(role)
            csrf = csrf_tokens.get(role)
            headers = {}
            if tok:
                headers["Cookie"] = f"{cookie_name}={tok}"
            if csrf and ep["method"] in {"POST", "PUT", "DELETE", "PATCH"}:
                headers["X-CSRF-Token"] = csrf
            
            url = f"{API_BASE}{ep['url']}"
            method = ep["method"]
            json_body = ep.get("json")

            try:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, json=json_body)
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, json=json_body)
                elif method == "DELETE":
                    resp = await client.delete(url, headers=headers)
                
                status = resp.status_code
                passed = status in ep["expected"]
                res_item = {
                    "name": ep["name"],
                    "method": method,
                    "url": ep["url"],
                    "role": role,
                    "status": status,
                    "expected": ep["expected"],
                    "passed": passed,
                    "response": resp.text[:120]
                }
                results.append(res_item)
                flag = "✅ PASS" if passed else "❌ FAIL"
                print(f"{flag} [{status}] ({role.upper()}) {ep['name']}")
            except Exception as e:
                print(f"❌ ERR ({role.upper()}) {ep['name']} -> {e}")
                results.append({
                    "name": ep["name"],
                    "method": method,
                    "url": ep["url"],
                    "role": role,
                    "status": "ERROR",
                    "expected": ep["expected"],
                    "passed": False,
                    "response": str(e)
                })

    with open("/app/scripts/api_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n--- Summary ---")
    pass_cnt = sum(1 for r in results if r["passed"])
    fail_cnt = len(results) - pass_cnt
    print(f"Total: {len(results)} | Passed: {pass_cnt} | Failed: {fail_cnt}")

if __name__ == "__main__":
    asyncio.run(run_api_suite())
