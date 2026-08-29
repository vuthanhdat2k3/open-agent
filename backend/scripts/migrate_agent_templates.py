"""Live data migration script for System Agent Templates and Org Agent Settings.

Usage:
    python -m scripts.migrate_agent_templates --dry-run
    python -m scripts.migrate_agent_templates --apply
    python -m scripts.migrate_agent_templates --apply --csv-report migration_report.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from typing import Any

from sqlalchemy import select

from app.core.agents.templates import (
    SYSTEM_AGENT_BLUEPRINTS,
    SystemAgentBlueprint,
    _template_match_hash,
)
from app.db.session import async_session_maker
from app.models.agent import Agent
from app.models.agent_release import AgentRelease
from app.models.org_agent_settings import OrgAgentSettings


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace("_", "-")


def _calculate_tool_overlap(agent_tools: list[str], template_tools: list[str]) -> float:
    set_a = set(agent_tools or [])
    set_b = set(template_tools or [])
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def _extract_agent_config(agent: Agent, release: AgentRelease | None) -> dict[str, Any]:
    """Extract configuration dictionary for hash calculation, preferring active release snapshot if available."""
    if release is not None:
        return {
            "description": release.description or "",
            "system_prompt": release.system_prompt or "",
            "tools": release.tools or [],
            "allowed_risk_tiers": release.allowed_risk_tiers or ["safe", "read"],
            "kind": release.kind or "worker",
            "max_iterations": release.max_iterations or 12,
            "temperature": release.temperature or 0.7,
            "enable_thinking": bool(agent.enable_thinking),
            "a2a_exposed": bool(agent.a2a_exposed),
            "auto_rollback_enabled": bool(agent.auto_rollback_enabled),
        }
    return {
        "description": agent.description or "",
        "system_prompt": agent.system_prompt or "",
        "tools": agent.tools or [],
        "allowed_risk_tiers": agent.allowed_risk_tiers or ["safe", "read"],
        "kind": agent.kind or "worker",
        "max_iterations": agent.max_iterations or 12,
        "temperature": agent.temperature or 0.7,
        "enable_thinking": bool(agent.enable_thinking),
        "a2a_exposed": bool(agent.a2a_exposed),
        "auto_rollback_enabled": bool(agent.auto_rollback_enabled),
    }


async def run_migration(apply: bool = False, csv_path: str = "agent_migration_review.csv") -> None:
    print("=" * 80)
    print(f"🚀 SYSTEM AGENT TEMPLATES MIGRATION — MODE: {'[APPLY]' if apply else '[DRY-RUN]'}")
    print("=" * 80)

    async with async_session_maker() as db:
        # Load all agents
        res = await db.execute(select(Agent).order_by(Agent.org_id, Agent.created_at))
        agents = res.scalars().all()

        print(f"📊 Found {len(agents)} total agent records across all organizations.")

        # Preload active releases
        release_ids = [a.active_release_id for a in agents if a.active_release_id]
        releases_by_id: dict[str, AgentRelease] = {}
        if release_ids:
            rel_res = await db.execute(
                select(AgentRelease).where(AgentRelease.id.in_(release_ids))
            )
            releases_by_id = {r.id: r for r in rel_res.scalars().all()}

        tier1_high: list[dict[str, Any]] = []
        tier2_ambiguous: list[dict[str, Any]] = []
        tier3_custom: list[dict[str, Any]] = []

        for agent in agents:
            norm_name = _normalize_name(agent.name)
            release = releases_by_id.get(agent.active_release_id) if agent.active_release_id else None
            config = _extract_agent_config(agent, release)
            agent_hash = _template_match_hash(config)

            matched_blueprint: SystemAgentBlueprint | None = SYSTEM_AGENT_BLUEPRINTS.get(norm_name)

            if matched_blueprint is not None:
                tool_overlap = _calculate_tool_overlap(agent.tools, matched_blueprint.tools)
                kind_match = (agent.kind == matched_blueprint.kind)
                is_pristine = (agent_hash == matched_blueprint.baseline_match_hash)

                record_info = {
                    "agent_id": agent.id,
                    "org_id": agent.org_id,
                    "name": agent.name,
                    "matched_template": matched_blueprint.key,
                    "tool_overlap": round(tool_overlap * 100, 1),
                    "kind_match": kind_match,
                    "is_pristine": is_pristine,
                    "agent_hash": agent_hash,
                    "baseline_hash": matched_blueprint.baseline_match_hash,
                    "agent": agent,
                    "blueprint": matched_blueprint,
                }

                if tool_overlap >= 0.7 and kind_match:
                    tier1_high.append(record_info)
                else:
                    tier2_ambiguous.append(record_info)
            else:
                tier3_custom.append({
                    "agent_id": agent.id,
                    "org_id": agent.org_id,
                    "name": agent.name,
                    "matched_template": None,
                    "tool_overlap": 0.0,
                    "kind_match": False,
                    "is_pristine": False,
                    "agent_hash": agent_hash,
                    "baseline_hash": "",
                    "agent": agent,
                    "blueprint": None,
                })

        # Summary Table
        print("\n📈 CLASSIFICATION SUMMARY:")
        print(f"  • Tier 1 (High Confidence Match):   {len(tier1_high):>4} agents")
        t1_pristine = [r for r in tier1_high if r["is_pristine"]]
        t1_customized = [r for r in tier1_high if not r["is_pristine"]]
        print(f"      - Pristine (Hash Match):        {len(t1_pristine):>4} -> Safe for zero-row pooled candidate")
        print(f"      - Modified (Hash Mismatch):     {len(t1_customized):>4} -> Keep as customized in DB")
        print(f"  • Tier 2 (Ambiguous Match - Review):{len(tier2_ambiguous):>4} agents -> Requires manual review")
        print(f"  • Tier 3 (Custom Agents):           {len(tier3_custom):>4} agents -> Pure custom, untouched\n")

        # Export CSV report
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Tier",
                "Agent ID",
                "Org ID",
                "Agent Name",
                "Matched Template",
                "Tool Overlap %",
                "Kind Match",
                "Pristine Baseline Match",
                "Action in --apply",
            ])
            for r in tier1_high:
                action = "Set template_key, is_customized=False, extract settings" if r["is_pristine"] else "Set template_key, is_customized=True (keep DB row)"
                writer.writerow([
                    "Tier 1 (High)",
                    r["agent_id"],
                    r["org_id"],
                    r["name"],
                    r["matched_template"],
                    r["tool_overlap"],
                    r["kind_match"],
                    r["is_pristine"],
                    action,
                ])
            for r in tier2_ambiguous:
                writer.writerow([
                    "Tier 2 (Ambiguous)",
                    r["agent_id"],
                    r["org_id"],
                    r["name"],
                    r["matched_template"],
                    r["tool_overlap"],
                    r["kind_match"],
                    r["is_pristine"],
                    "NO ACTION (Needs Human Review)",
                ])
            for r in tier3_custom:
                writer.writerow([
                    "Tier 3 (Custom)",
                    r["agent_id"],
                    r["org_id"],
                    r["name"],
                    "None",
                    0.0,
                    False,
                    False,
                    "NO ACTION (Pure Custom Agent)",
                ])

        print(f"📄 Detailed CSV review report written to: {csv_path}")

        # Execute Apply if requested
        if apply:
            print("\n⚙️  Applying Tier-1 updates to database...")
            applied_count = 0
            settings_created = 0

            for r in tier1_high:
                agent = r["agent"]
                tpl_key = r["matched_template"]
                is_pristine = r["is_pristine"]

                agent.template_key = tpl_key
                if is_pristine:
                    agent.is_customized = False
                    # Extract cheap settings to org_agent_settings if model_id exists
                    if agent.model_id:
                        # Check existing settings
                        existing_settings = await db.scalar(
                            select(OrgAgentSettings).where(
                                OrgAgentSettings.org_id == agent.org_id,
                                OrgAgentSettings.template_key == tpl_key,
                            )
                        )
                        if not existing_settings:
                            settings = OrgAgentSettings(
                                org_id=agent.org_id,
                                template_key=tpl_key,
                                is_pinned=r["blueprint"].is_pinned_by_default,
                                is_enabled=True,
                                model_override_id=agent.model_id,
                                temperature_override=agent.temperature if agent.temperature != 0.7 else None,
                            )
                            db.add(settings)
                            settings_created += 1
                else:
                    agent.is_customized = True

                applied_count += 1

            await db.commit()
            print(f"✅ Successfully updated {applied_count} Tier-1 agents and created {settings_created} org_agent_settings records!")
        else:
            print("\n💡 Run with '--apply' to persist Tier-1 classification to database.")


def main():
    parser = argparse.ArgumentParser(description="Migrate Agent Templates and classify pristine vs customized agents.")
    parser.add_argument("--apply", action="store_true", help="Apply updates to database (default is dry-run)")
    parser.add_argument("--csv-report", default="agent_migration_review.csv", help="Path to write CSV review report")
    args = parser.parse_args()

    asyncio.run(run_migration(apply=args.apply, csv_path=args.csv_report))


if __name__ == "__main__":
    main()
