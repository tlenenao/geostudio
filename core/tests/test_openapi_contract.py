# SPDX-License-Identifier: Apache-2.0
"""AUD-046 : le document OpenAPI est un contrat lisible (version réelle, auth, tags)."""

import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_openapi_contract():
    schema = TestClient(create_app()).get("/openapi.json").json()
    assert schema["info"]["version"] == tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    assert "Authentification" in schema["info"]["description"]
    bearer = schema["components"]["securitySchemes"]["bearerAuth"]
    assert (bearer["type"], bearer["scheme"]) == ("http", "bearer")
    assert {"bearerAuth": []} in schema["security"]
    untagged = [
        f"{method.upper()} {path}"
        for path, ops in schema["paths"].items()
        for method, op in ops.items()
        if isinstance(op, dict) and not op.get("tags")
    ]
    assert untagged == []
