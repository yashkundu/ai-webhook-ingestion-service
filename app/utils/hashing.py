from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_dumps(data: Any) -> str:
    """Stable string for hashing (sort keys, compact separators)."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def idempotency_key(vendor_id: str, body: Any) -> str:
    body_str = canonical_json_dumps(body)
    h = hashlib.sha256()
    h.update(vendor_id.encode("utf-8"))
    h.update(b"|")
    h.update(body_str.encode("utf-8"))
    return h.hexdigest()
