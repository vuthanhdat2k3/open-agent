import json
from typing import Any


def format_sse(ev: dict[str, Any]) -> str:
    name = ev.get("event", "message")
    data = json.dumps(ev.get("data", {}), ensure_ascii=False)
    return f"event: {name}\ndata: {data}\n\n"
