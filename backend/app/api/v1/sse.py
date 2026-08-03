import json
from typing import Any

# SSE comment sent periodically to keep the connection alive through
# proxies/load-balancers that idle-timeout long-lived streams.
SSE_HEARTBEAT_SECONDS = 15.0


def format_sse(ev: dict[str, Any]) -> str:
    name = ev.get("event", "message")
    data = json.dumps(ev.get("data", {}), ensure_ascii=False)
    return f"event: {name}\ndata: {data}\n\n"
