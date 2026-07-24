"""In-memory NetworkX graph store with node-link JSON persistence."""

from __future__ import annotations

import json
from typing import Any

from rag_service.config import settings
from rag_service.core.logging import logger


def _node_key(entity: dict[str, Any]) -> str:
    return entity.get("id") or entity.get("name") or ""


class NetworkXGraphStore:
    """Per-collection directed graph of extracted entities / relations.

    ``networkx`` is imported lazily (inside methods) so the module — and the
    wider service — boots without it installed.  Graphs are persisted to
    ``settings.graph_persist_dir`` in node-link format.
    """

    def __init__(self, collection_id: str | None = None) -> None:
        self.collection_id = collection_id
        self._nx = None  # imported lazily
        self._graph: Any = None

    # ------------------------------------------------------------------ #
    def _ensure_nx(self) -> Any:
        if self._nx is None:
            import networkx  # type: ignore

            self._nx = networkx
        return self._nx

    def _g(self) -> Any:
        if self._graph is None:
            nx = self._ensure_nx()
            self._graph = nx.DiGraph()
        return self._graph

    # ------------------------------------------------------------------ #
    async def upsert(
        self, collection_id: str, graph_data_list: list[Any]
    ) -> None:
        g = self._g()
        for gd in graph_data_list:
            for ent in gd.entities:
                key = _node_key(ent)
                if not key:
                    continue
                attrs = dict(ent)
                existing = g.nodes.get(key, {})
                chunk_ids = set(existing.get("chunk_ids", []))
                chunk_ids.update(ent.get("chunk_ids", []))
                attrs["chunk_ids"] = sorted(chunk_ids)
                g.add_node(key, **attrs)
            for rel in gd.relations:
                src = rel.get("source")
                tgt = rel.get("target")
                if not src or not tgt:
                    continue
                if not g.has_node(src):
                    g.add_node(src, chunk_ids=[])
                if not g.has_node(tgt):
                    g.add_node(tgt, chunk_ids=[])
                attrs = dict(rel)
                existing = g.get_edge_data(src, tgt, default={})
                chunk_ids = set(existing.get("chunk_ids", []))
                chunk_ids.update(rel.get("chunk_ids", []))
                attrs["chunk_ids"] = sorted(chunk_ids)
                g.add_edge(src, tgt, **attrs)

    # ------------------------------------------------------------------ #
    def _path(self, collection_id: str):
        return settings.graph_persist_dir / f"{collection_id}.json"

    async def save(self, collection_id: str) -> None:
        try:
            nx = self._ensure_nx()
            settings.graph_persist_dir.mkdir(parents=True, exist_ok=True)
            data = nx.node_link_data(self._g())
            with open(self._path(collection_id), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as exc:  # noqa: BLE001 - best effort
            logger.warning("graph_save_failed", collection=collection_id, error=str(exc))

    async def load(self, collection_id: str) -> bool:
        path = self._path(collection_id)
        if not path.exists():
            return False
        try:
            nx = self._ensure_nx()
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._graph = nx.node_link_graph(data, directed=True)
            return True
        except Exception as exc:  # noqa: BLE001 - best effort
            logger.warning("graph_load_failed", collection=collection_id, error=str(exc))
            return False

    async def delete_collection(self, collection_id: str) -> None:
        self._graph = None
        try:
            path = self._path(collection_id)
            if path.exists():
                path.unlink()
        except Exception:  # pragma: no cover
            pass

    @property
    def graph(self) -> Any:
        return self._g()
