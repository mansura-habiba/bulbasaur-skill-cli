"""Offline OAC read-only client protocol and security assertions."""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "examples/open_agentic_catalog/read_only_client.py"
spec = importlib.util.spec_from_file_location("bulbasaur_oac_example", SOURCE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
CatalogReader = module.CatalogReader


class Response:
    status = 200

    def __init__(self, request):
        self.request = request

    def geturl(self):
        return self.request.full_url

    def read(self, _size):
        if self.request.full_url.endswith("/capabilities"):
            return b'{"resourceKinds":["agent","mcp_server","skill","plugin"]}'
        return b'{"items":[],"nextCursor":null}'

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_requests_are_get_only() -> None:
    requests = []

    def mocked_urlopen(request, timeout):
        requests.append(request)
        return Response(request)

    client = CatalogReader("http://127.0.0.1:8080", "fake-token")
    with patch.object(module.urllib.request, "urlopen", side_effect=mocked_urlopen):
        assert client.capabilities()
        assert client.list_skills()["items"] == []
    assert len(requests) == 2
    assert all(req.get_method() == "GET" for req in requests)
    assert requests[1].full_url.endswith("/api/v1/resources?kind=skill&limit=5")
    assert all(req.get_header("Authorization") == "Bearer fake-token" for req in requests)


def test_origin_restrictions() -> None:
    with pytest.raises(ValueError):
        CatalogReader("http://catalog.example.org", "token")
    with pytest.raises(ValueError):
        CatalogReader("https://u:p@catalog.example.org", "token")
    with pytest.raises(ValueError):
        CatalogReader("https://catalog.example.org/some/path", "token")
    with pytest.raises(ValueError):
        CatalogReader("https://catalog.example.org", "")
    with pytest.raises(ValueError):
        CatalogReader("https://catalog.example.org", "token").list_skills(101)
