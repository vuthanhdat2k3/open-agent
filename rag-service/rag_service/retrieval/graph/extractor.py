"""LLM-based entity / relation extraction (LightRAG-style JSON extraction).

Heavy dependency (``openai``) is imported lazily so this module loads cleanly
with no API key or SDK installed.  When the LLM is unavailable the extractor
returns an empty :class:`GraphData` rather than raising.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from rag_service.config import settings
from rag_service.core.logging import logger


@dataclass
class GraphData:
    """Extracted knowledge-graph fragment."""

    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.entities and not self.relations


_EXTRACTION_PROMPT = """You are a knowledge graph extraction engine.
Extract entities and relationships from the text below.

Return ONLY a JSON object with exactly this structure:
{
  "entities": [
    {"id": "<unique_entity_id>", "name": "<entity name>", "type": "<person|organization|technology|concept|location|event|other>", "description": "<short description>"}
  ],
  "relations": [
    {"source": "<source entity id>", "target": "<target entity id>", "relation": "<relationship type>", "weight": <float 0-1>}
  ]
}

Rules:
- Use stable, lowercased ids derived from the entity name (e.g. "openai").
- Only include relations between entities that appear in the entity list.
- Keep entity descriptions concise (<= 20 words).
- If the text contains no extractable entities, return empty lists.

TEXT:
{text}
"""


class EntityRelationExtractor:
    """Extract entities and relations from text using an OpenAI-compatible LLM."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.graph_llm_model

    async def extract(self, text: str, chunk_id: str) -> GraphData:
        """Extract a :class:`GraphData` from ``text``.

        Returns an empty graph (never raises) when the LLM/SDK is unavailable.
        """
        try:
            import openai  # type: ignore
        except Exception as exc:  # noqa: BLE001
            logger.debug("graph_openai_unavailable", error=str(exc))
            return GraphData()

        if not settings.openai_key_effective:
            return GraphData()

        try:
            client = openai.AsyncOpenAI(
                api_key=settings.openai_key_effective,
                base_url=settings.openai_base_url or None,
            )
            resp = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract knowledge graphs as JSON.",
                    },
                    {
                        "role": "user",
                        "content": _EXTRACTION_PROMPT.format(text=(text or "")[:8000]),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            content = resp.choices[0].message.content or "{}"
            data = json.loads(content)
            entities = data.get("entities", []) or []
            relations = data.get("relations", []) or []
            # Tag every entity/edge with the originating chunk for later lookup.
            for ent in entities:
                chunk_ids = set(ent.get("chunk_ids") or [])
                chunk_ids.add(chunk_id)
                ent["chunk_ids"] = sorted(chunk_ids)
            for rel in relations:
                chunk_ids = set(rel.get("chunk_ids") or [])
                chunk_ids.add(chunk_id)
                rel["chunk_ids"] = sorted(chunk_ids)
            return GraphData(entities=entities, relations=relations)
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph_extraction_failed", chunk=chunk_id, error=str(exc))
            return GraphData()
