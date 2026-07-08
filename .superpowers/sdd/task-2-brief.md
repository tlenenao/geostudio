### Task 2: items repository, schemas, and read/update endpoints

**Files:**
- Create: `core/app/items/schemas.py`, `core/app/items/repository.py`, `core/app/items/routes.py`
- Modify: `core/app/main.py`
- Create: `core/tests/test_items_repository.py`, `core/tests/test_items_routes.py`

**Interfaces:**
- Consumes: `app.items.models.Item`, `app.audit.writer.write_audit`, `app.auth.dependency.get_current_user`, `app.users.models.User`, `app.db.get_session`.
- Produces: `app.items.schemas.{ItemRead, ItemPage, ItemUpdatePatch}`; `app.items.repository.{create_item, get_item, list_items, update_item}`; `GET /items`, `GET /items/{id}`, `PATCH /items/{id}` registered via `app.items.routes.router`. `create_item(session, *, tenant_id, owner_id, resource_type, title) -> Item` — used by Task 3's `configs` rewrite.

- [ ] **Step 1: Write the schemas**

`core/app/items/schemas.py`:
```python
from pydantic import BaseModel, Field


class ItemRead(BaseModel):
    pk: str
    resourceType: str
    title: str
    abstract: str
    owner: str
    thumbnailUrl: str | None
    date: str
    configId: str | None
    isPublished: bool


class ItemPage(BaseModel):
    items: list[ItemRead]
    total: int
    page: int
    pageSize: int


class ItemUpdatePatch(BaseModel):
    title: str | None = None
    abstract: str | None = None
    keywords: list[str] | None = None
    isPublished: bool | None = Field(default=None)
```

- [ ] **Step 2: Write the failing repository tests**

`core/tests/test_items_repository.py`:
```python
import pytest

from app.db import make_engine, make_session_factory, init_db
from app.items import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant_and_user(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-1",
        username="alice", email=None, first_name="", last_name="",
    )
    return tenant, user


def test_create_and_get_item(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="My App",
    )

    read = repo.get_item(session, tenant_id=tenant.id, item_id=item.id)
    assert read is not None
    assert read.title == "My App"
    assert read.owner == "alice"
    assert read.resourceType == "app"
    assert read.configId is None  # no config lookup from app.items — see plan Architecture
    assert read.isPublished is False


def test_get_item_missing_returns_none(session, tenant_and_user):
    tenant, _ = tenant_and_user
    assert repo.get_item(session, tenant_id=tenant.id, item_id="nope") is None


def test_list_items_scope_mine(session, tenant_and_user):
    tenant, user = tenant_and_user
    other = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-2",
        username="bob", email=None, first_name="", last_name="",
    )
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Mine")
    repo.create_item(session, tenant_id=tenant.id, owner_id=other.id, resource_type="app", title="Theirs")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type=None, scope="mine", page=1, page_size=12,
    )
    assert page.total == 1
    assert [i.title for i in page.items] == ["Mine"]


def test_list_items_scope_public(session, tenant_and_user):
    tenant, user = tenant_and_user
    published = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Published")
    repo.update_item(session, tenant_id=tenant.id, item_id=published.id, title=None, abstract=None, keywords=None, is_published=True)
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Draft")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type=None, scope="public", page=1, page_size=12,
    )
    assert page.total == 1
    assert [i.title for i in page.items] == ["Published"]


def test_list_items_scope_shared_is_empty(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Any")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type=None, scope="shared", page=1, page_size=12,
    )
    assert page.total == 0
    assert page.items == []


def test_list_items_search_and_type_filter(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Incidents map")
    repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="dashboard", title="Sales dashboard")

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q="incidents", resource_type=None, scope="all", page=1, page_size=12,
    )
    assert [i.title for i in page.items] == ["Incidents map"]

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q=None, resource_type="dashboard", scope="all", page=1, page_size=12,
    )
    assert [i.title for i in page.items] == ["Sales dashboard"]


def test_update_item_patches_fields(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Old title")

    updated = repo.update_item(
        session, tenant_id=tenant.id, item_id=item.id,
        title="New title", abstract="New abstract", keywords=["a", "b"], is_published=None,
    )
    assert updated is not None
    assert updated.title == "New title"
    assert updated.abstract == "New abstract"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_items_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.items.repository'`.

- [ ] **Step 4: Write the repository**

`core/app/items/repository.py`:
```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.items.models import Item
from app.items.schemas import ItemPage, ItemRead
from app.users.models import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_read(item: Item, owner_username: str) -> ItemRead:
    # configId is always None: app.items must never import app.configs (see
    # plan Architecture — items sits below configs in the layering), and the
    # shell's own Item.configId is already hardcoded to null everywhere today
    # (itemClient.ts's toItem()), so this isn't a behavior regression for any
    # current consumer. Real wiring, if ever needed, belongs in app.configs.
    return ItemRead(
        pk=item.id,
        resourceType=item.resource_type,
        title=item.title,
        abstract=item.abstract,
        owner=owner_username,
        thumbnailUrl=f"/items/{item.id}/thumbnail" if item.thumbnail_key else None,
        date=item.created_at.isoformat(),
        configId=None,
        isPublished=item.is_published,
    )


def create_item(
    session: Session, *, tenant_id: str, owner_id: str, resource_type: str, title: str
) -> Item:
    item = Item(
        id=uuid.uuid4().hex, tenant_id=tenant_id, owner_id=owner_id,
        resource_type=resource_type, title=title,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def get_item(session: Session, *, tenant_id: str, item_id: str) -> ItemRead | None:
    row = session.execute(
        select(Item, User.username)
        .join(User, User.id == Item.owner_id)
        .where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).first()
    if row is None:
        return None
    item, owner_username = row
    return _to_read(item, owner_username)


def list_items(
    session: Session,
    *,
    tenant_id: str,
    current_user_id: str,
    q: str | None,
    resource_type: str | None,
    scope: str,
    page: int,
    page_size: int,
) -> ItemPage:
    if scope == "shared":
        return ItemPage(items=[], total=0, page=page, pageSize=page_size)

    query = select(Item, User.username).join(User, User.id == Item.owner_id).where(Item.tenant_id == tenant_id)
    if resource_type:
        query = query.where(Item.resource_type == resource_type)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Item.title.ilike(like), Item.abstract.ilike(like)))
    if scope == "mine":
        query = query.where(Item.owner_id == current_user_id)
    elif scope == "public":
        query = query.where(Item.is_published.is_(True))
    # scope == "all": no extra filter (real visibility filtering arrives in SP-1c)

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(Item.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [_to_read(item, owner_username) for item, owner_username in rows]
    return ItemPage(items=items, total=total, page=page, pageSize=page_size)


def update_item(
    session: Session,
    *,
    tenant_id: str,
    item_id: str,
    title: str | None,
    abstract: str | None,
    keywords: list[str] | None,
    is_published: bool | None,
) -> ItemRead | None:
    item = session.execute(
        select(Item).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        return None
    if title is not None:
        item.title = title
    if abstract is not None:
        item.abstract = abstract
    if keywords is not None:
        item.keywords = keywords
    if is_published is not None:
        item.is_published = is_published
    session.commit()
    session.refresh(item)
    owner_username = session.scalar(select(User.username).where(User.id == item.owner_id)) or ""
    return _to_read(item, owner_username)
```

- [ ] **Step 5: Run repository tests to verify they pass**

Run: `cd core && uv run pytest tests/test_items_repository.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Write the failing route tests**

`core/tests/test_items_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )

    app = create_app()

    def override_session():
        with Session() as s:
            yield s

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _seed_item(client, title="My App") -> str:
    # No linked Config/ConfigRevision needed here: these routes never look up
    # configId (see plan Architecture — app.items must not import app.configs).
    with client.session_factory() as session:
        item = items_repo.create_item(
            session, tenant_id=client.tenant.id, owner_id=client.user.id,
            resource_type="app", title=title,
        )
        return item.id


def test_get_item_returns_it(client):
    item_id = _seed_item(client)
    response = client.get(f"/items/{item_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "My App"
    assert body["owner"] == "alice"


def test_get_item_missing_returns_404(client):
    assert client.get("/items/nope").status_code == 404


def test_list_items_default_scope_all(client):
    _seed_item(client, title="One")
    _seed_item(client, title="Two")
    response = client.get("/items")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["pageSize"] == 12


def test_patch_item_updates_title(client):
    item_id = _seed_item(client)
    response = client.patch(f"/items/{item_id}", json={"title": "Renamed"})
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"


def test_patch_item_missing_returns_404(client):
    assert client.patch("/items/nope", json={"title": "x"}).status_code == 404
```

- [ ] **Step 7: Run route tests to verify they fail**

Run: `cd core && uv run pytest tests/test_items_routes.py -v`
Expected: FAIL — `/items` routes don't exist yet (404s where 200s are expected).

- [ ] **Step 8: Write the routes**

`core/app/items/routes.py`:
```python
from fastapi import APIRouter, Depends, HTTPException

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.items import repository as repo
from app.items.schemas import ItemPage, ItemRead, ItemUpdatePatch
from app.users.models import User
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/items", response_model=ItemPage)
def list_items(
    q: str | None = None,
    type: str | None = None,
    scope: str = "all",
    page: int = 1,
    pageSize: int = 12,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemPage:
    return repo.list_items(
        session, tenant_id=user.tenant_id, current_user_id=user.id,
        q=q, resource_type=type, scope=scope, page=page, page_size=pageSize,
    )


@router.get("/items/{item_id}", response_model=ItemRead)
def get_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemRead:
    result = repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result


@router.patch("/items/{item_id}", response_model=ItemRead)
def update_item(
    item_id: str,
    patch: ItemUpdatePatch,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemRead:
    result = repo.update_item(
        session, tenant_id=user.tenant_id, item_id=item_id,
        title=patch.title, abstract=patch.abstract, keywords=patch.keywords,
        is_published=patch.isPublished,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")

    if patch.isPublished is True:
        action = "item.publish"
    elif patch.isPublished is False:
        action = "item.unpublish"
    else:
        action = "item.update"
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action=action, object_type="item", object_id=item_id, payload={},
    )
    return result
```

- [ ] **Step 9: Register the router in `app/main.py`**

Add the import `from app.items import routes as items_routes` and, next to the other `app.include_router(...)` calls, add `app.include_router(items_routes.router)`.

- [ ] **Step 10: Run route tests to verify they pass**

Run: `cd core && uv run pytest tests/test_items_routes.py -v`
Expected: PASS (5 tests).

- [ ] **Step 11: Run the full suite and `lint-imports`**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS; `Contracts: 1 kept, 0 broken.`

- [ ] **Step 12: Commit**

```bash
git add core/app/items core/app/main.py core/tests/test_items_repository.py core/tests/test_items_routes.py
git commit -m "feat(core): items repository, schemas, and GET/PATCH endpoints"
```

---

