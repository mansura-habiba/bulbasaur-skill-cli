"""Read-only Open Agentic Catalog API example; no CLI or invented write routes."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CatalogReader:
    base_url: str
    bearer_token: str
    timeout_seconds: float = 8.0

    def __post_init__(self) -> None:
        origin = urllib.parse.urlsplit(self.base_url)
        if origin.scheme != "https" and not (
            origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
        ):
            raise ValueError("Catalog origin must be HTTPS or loopback HTTP")
        if origin.username or origin.password or origin.query or origin.fragment or origin.path not in {"", "/"}:
            raise ValueError("Catalog origin must be an origin without credentials or extra path")
        if not self.bearer_token:
            raise ValueError("A scoped bearer token is required")

    def _get(self, path: str) -> dict[str, Any]:
        target = self.base_url.rstrip("/") + path
        request = urllib.request.Request(target, method="GET", headers={
            "Authorization": "Bearer " + self.bearer_token,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            if response.geturl() != target:
                raise ValueError("Unexpected API redirect")
            if response.status != 200:
                raise ValueError("Unexpected API status")
            content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise ValueError("Catalog response exceeds 2 MB")
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ValueError("Catalog response must be a JSON object")
            return payload

    def capabilities(self) -> dict[str, Any]:
        return self._get("/api/v1/capabilities")

    def list_skills(self, limit: int = 5) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1-100")
        query = urllib.parse.urlencode({"kind": "skill", "limit": limit})
        return self._get("/api/v1/resources?" + query)


def main() -> None:
    reader = CatalogReader(os.environ["OAC_API_ORIGIN"], os.environ["OAC_BEARER_TOKEN"])
    capabilities = reader.capabilities()
    inventory = reader.list_skills()
    print(json.dumps({
        "capabilities_response_received": bool(capabilities),
        "local_skill_resources": len(inventory.get("items", [])),
        "has_more": bool(inventory.get("nextCursor")),
        "note": "Authorized local Resource inventory; not public ARD Search",
    }, indent=2))


if __name__ == "__main__":
    main()
