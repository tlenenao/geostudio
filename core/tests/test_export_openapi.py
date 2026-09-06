# SPDX-License-Identifier: Apache-2.0
import json

from scripts.export_openapi import main


def test_main_writes_valid_openapi_json(tmp_path):
    output = tmp_path / "openapi.json"
    main(str(output))

    with open(output) as f:
        schema = json.load(f)

    assert schema["openapi"].startswith("3.")
    assert "/v1/configs" in schema["paths"]
    assert "/v1/me" in schema["paths"]
    assert "/health" in schema["paths"]
