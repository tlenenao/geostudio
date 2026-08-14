### Task 6: Core read/proxy route

**Files:**
- Modify: `core/app/tileset3d/routes.py` (add the read endpoint)
- Test: `core/tests/test_tileset3d_routes.py` (extend)

**Interfaces:**
- Consumes: `app.items.repository.get_access_facts`; `app.sharing.authorization.can`; `app.configs.repository.get_config_by_item`; `S3RangeFile` (Task 3).
- Produces: `GET /tileset3d/{item_id}/{path:path}` → entry bytes with a guessed `Content-Type`, `404` if the item doesn't exist/isn't readable by the caller or the entry doesn't exist in the zip.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_tileset3d_routes.py` (reuses the `env` fixture and `_FakeS3Client` already defined in that file):

```python
import io
import json
import zipfile

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Tileset3DPayload
from app.items import repository as items_repo


def _valid_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tileset.json", json.dumps({"asset": {"version": "1.0"}, "root": {}}))
        zf.writestr("tiles/0.b3dm", b"\x00" * 16)
    return buf.getvalue()


def _seed_hosted_tileset_item(session, *, tenant_id, owner_id, fake_s3, key="tenant/x/city.zip"):
    fake_s3.objects[key] = _valid_zip_bytes()
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="tileset3d", title="Ville",
    )
    config = BuilderConfig(
        kind="tileset3d",
        tileset3d=Tileset3DPayload(sourceKey=key, tilesetJsonPath="tileset.json", totalBytes=100, entryCount=2),
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_read_tileset3d_entry_returns_tileset_json(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/tileset.json")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert json.loads(r.content)["asset"]["version"] == "1.0"


def test_read_tileset3d_entry_returns_tile_binary(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/tiles/0.b3dm")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.content == b"\x00" * 16


def test_read_tileset3d_entry_404_for_missing_entry(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/does-not-exist.b3dm")
    assert r.status_code == 404


def test_read_tileset3d_entry_404_for_unknown_item(env):
    client, *_ = env
    r = client.get("/tileset3d/does-not-exist/tileset.json")
    assert r.status_code == 404


def test_read_tileset3d_entry_404_for_a_private_item_owned_by_another_user(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        bob = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=bob.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/tileset.json")
    assert r.status_code == 404
```

No new import is needed for this test — `core/tests/test_tileset3d_routes.py` already imports `get_or_create_user` (Task 4, used by its `env` fixture to create `alice`); this test's `bob = get_or_create_user(...)` reuses that same import.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_tileset3d_routes.py -k read_tileset3d_entry -v`
Expected: FAIL — 404 on every request (no `/tileset3d/{item_id}/{path}` route registered yet).

- [ ] **Step 3: Implement the read route**

Add to `core/app/tileset3d/routes.py` — new imports at the top:

```python
from fastapi import Response

from app.configs import repository as configs_repo
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.tileset3d.storage import S3RangeFile
```

New module-level constant and helper, placed above the route functions:

```python
_CONTENT_TYPES = {
    ".json": "application/json",
    ".gltf": "application/json",
    ".b3dm": "application/octet-stream",
    ".i3dm": "application/octet-stream",
    ".pnts": "application/octet-stream",
    ".cmpt": "application/octet-stream",
    ".glb": "application/octet-stream",
}


def _content_type_for(path: str) -> str:
    for ext, content_type in _CONTENT_TYPES.items():
        if path.endswith(ext):
            return content_type
    return "application/octet-stream"
```

New route, appended at the end of the file:

```python
@router.get("/tileset3d/{item_id}/{path:path}")
def read_tileset3d_entry(
    item_id: str, path: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
) -> Response:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.tileset3d is None:
        raise HTTPException(status_code=404, detail="tileset not found")
    payload = config.config.tileset3d

    import zipfile

    range_file = S3RangeFile(s3, bucket=bucket, key=payload.sourceKey)
    try:
        with zipfile.ZipFile(range_file) as zf:
            data = zf.read(path)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="entry not found") from exc

    return Response(
        content=data, media_type=_content_type_for(path),
        headers={"Cache-Control": "private, max-age=3600"},
    )
```

(The `import zipfile` is placed inline in the function rather than at module top only to keep the diff local to this step — move it to the top-level imports alongside the others added in this step; either placement is fine, top-level is the repo's usual convention, so put it there in the final file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_tileset3d_routes.py -v`
Expected: PASS (all tests, including the ones from Task 4).

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd core && git add app/tileset3d/routes.py tests/test_tileset3d_routes.py
git commit -m "feat(core): tileset3d read/proxy route"
```

---

