## Task 2: Core — `symbology` field on `MapLayer`

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_configs_map_symbology.py` (create)

**Interfaces:**
- Produces: `MapLayer.symbology: dict | None = None` (untyped, mirrors
  `paint: dict | None` and `props: dict | None` on the same model — this
  model validates coarse shape only, exactly like its two neighbors).

- [ ] **Step 1: Find the existing round-trip test pattern for `MapLayer`**

Run: `grep -rn "popup" core/tests/test_configs*.py`

Read whichever file that finds (it exercises `MapLayer.popup` round-trip
through `POST /configs` or `PUT /configs/{id}` — SP-24 added it) to copy its
exact request/assertion shape for the new test below.

- [ ] **Step 2: Write the failing test**

Create `core/tests/test_configs_map_symbology.py`, mirroring the file found
in Step 1 (same fixtures, same route, same auth setup — copy them, don't
invent new ones):

```python
# SPDX-License-Identifier: Apache-2.0
"""symbology (SP-25) round-trips through MapConfig exactly like paint/popup
(SP-24) — an untyped dict on MapLayer, same precedent."""

# (imports and fixtures: copy verbatim from the file found in Task 2 Step 1)


def test_map_layer_symbology_round_trips(client):
    payload = {
        "kind": "map",
        "title": "Carte test",
        "owner": "u1",
    }
    item = client.post("/configs", json=payload).json()

    map_config = {
        "basemap": {"style": "https://example.test/style.json"},
        "view": {"center": [0, 0], "zoom": 5},
        "layers": [
            {
                "id": "l1",
                "title": "Communes",
                "visible": True,
                "kind": "vector",
                "tilesUrl": "https://example.test/tiles/{z}/{x}/{y}.mvt",
                "sourceLayer": "communes",
                "collectionId": "communes",
                "symbology": {
                    "color": {
                        "field": "population",
                        "mode": "numeric",
                        "classification": {"method": "quantile", "classes": 5},
                        "palette": "sequential-blue",
                        "domain": {"kind": "numeric-classed", "breaks": [0, 10, 20, 30, 40, 50]},
                        "computedAt": "2026-08-23T00:00:00Z",
                    }
                },
            }
        ],
    }
    response = client.put(f"/configs/{item['id']}", json={"config": map_config})
    assert response.status_code == 200

    got = client.get(f"/configs/{item['id']}").json()
    assert got["config"]["layers"][0]["symbology"] == map_config["layers"][0]["symbology"]
```

Adjust the exact route paths/payload envelope (`POST /configs` vs a
different creation route, `PUT` vs `PATCH`, whether `config` is nested or
top-level) to match precisely what the file found in Step 1 actually uses —
this sketch shows the shape of the assertion, not a guaranteed-correct route
contract.

- [ ] **Step 3: Run it to verify it fails**

Run: `cd core && uv run pytest tests/test_configs_map_symbology.py -v`
Expected: FAIL — `symbology` stripped from the round-tripped config (Pydantic
drops unknown fields silently by default) or a 422 if `MapLayer` is
constructed with `extra="forbid"` (check `class Config` / `model_config` on
`MapLayer` first — if it forbids extra fields, this test fails loudly
instead of silently, which is the RED state either way).

- [ ] **Step 4: Add the field**

In `core/app/configs/schemas.py`, in `MapLayer` (right after `popup:
PopupConfig | None = None`):

```python
    popup: PopupConfig | None = None
    symbology: dict | None = None
```

- [ ] **Step 5: Run it to verify it passes**

Run: `cd core && uv run pytest tests/test_configs_map_symbology.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full core suite + gates**

Run: `cd core && uv run pytest -v && ruff check . && ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && lint-imports`
Expected: all green, count ≥ previous + 1.

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_configs_map_symbology.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute symbology à MapLayer

Champ non typé, même précédent que paint/props — le shell (SP-25) y
écrit la symbologie déclarative d'une couche.
EOF
)"
```

---

