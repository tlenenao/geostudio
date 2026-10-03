# SPDX-License-Identifier: Apache-2.0
import os
from html import escape
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs import repository as configs_repo
from app.configs.repository import ConfigRead
from app.db import get_session
from app.items import repository as items_repo
from app.items.routes import get_thumbnail_store
from app.items.schemas import ItemPage, ItemRead
from app.items.storage import ThumbnailStore
from app.tenants.repository import DEFAULT_TENANT_SLUG

router = APIRouter(prefix="/public")

# Plafond du protocole sitemaps (50 000 URL par fichier). Appel interne : la
# borne pageSize<=100 ne vaut que pour la route anonyme /items.
# ponytail: un seul fichier ; index de sitemaps au-delà de 50 000 pages publiques.
_SITEMAP_MAX_URLS = 50_000

# Surfaces anonymes : cache partagé court (aucune donnée privée n'y figure).
_CACHE = {"Cache-Control": "public, max-age=300"}


def _lastmod(iso: str | None) -> str:
    return f"<lastmod>{xml_escape(iso)}</lastmod>" if iso else ""


def _render_sitemap_xml(
    base_url: str, items: list[ItemRead], dataset_ids: list[str] | None = None
) -> str:
    entries: list[tuple[str, str | None]] = []
    for item in items:
        if item.resourceType == "site":
            if item.slug:
                entries.append((f"/sites/{item.slug}", item.updatedAt))
        else:
            entries.append((f"/public/items/{item.pk}", item.updatedAt))
    entries += [(f"/public/datasets/{cid}", None) for cid in dataset_ids or []]
    urls = "".join(
        f"<url><loc>{xml_escape(base_url + quote(path, safe='/'))}</loc>{_lastmod(mod)}</url>"
        for path, mod in entries
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def _render_social_preview_html(
    base_url: str,
    *,
    title: str,
    description: str,
    path: str,
    og_type: str = "website",
    image_url: str | None = None,
) -> str:
    # Tout texte issu d'un item/collection est échappé (attributs ET corps) :
    # un titre ne doit jamais injecter de balise.
    t = escape(title)
    d = escape(description)
    canonical = escape(base_url + quote(path, safe="/"))
    image = f'<meta property="og:image" content="{escape(image_url)}">' if image_url else ""
    card = "summary_large_image" if image_url else "summary"
    return (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        f"<title>{t}</title>"
        f'<meta name="description" content="{d}">'
        f'<meta property="og:title" content="{t}">'
        f'<meta property="og:description" content="{d}">'
        f'<meta property="og:type" content="{escape(og_type)}">'
        f'<meta property="og:url" content="{canonical}">'
        f"{image}"
        f'<meta name="twitter:card" content="{card}">'
        f'<link rel="canonical" href="{canonical}">'
        f"</head><body><h1>{t}</h1><p>{d}</p></body></html>"
    )


def _thumb_url(base_url: str, item: ItemRead) -> str | None:
    return f"{base_url}/api/v1{item.thumbnailUrl}" if item.thumbnailUrl else None


@router.get("/items", response_model=ItemPage)
def list_public_items(
    type: str | None = None,
    tag: str | None = None,
    page: int = Query(1, ge=1),
    # Borne haute : route anonyme (P24.05).
    pageSize: int = Query(12, ge=1, le=100),
    session: Session = Depends(get_session, scope="function"),
) -> ItemPage:
    return items_repo.list_published_items(
        session,
        resource_type=type,
        tag=tag,
        page=page,
        page_size=pageSize,
    )


@router.get("/items/{item_id}", response_model=ItemRead)
def get_public_item(
    item_id: str, session: Session = Depends(get_session, scope="function")
) -> ItemRead:
    result = items_repo.get_published_item(session, item_id=item_id, tenant_id=DEFAULT_TENANT_SLUG)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result


@router.get("/sites/{slug}", response_model=ItemRead)
def get_public_site(
    slug: str, session: Session = Depends(get_session, scope="function")
) -> ItemRead:
    result = items_repo.get_published_site_by_slug(session, slug=slug)
    if result is None:
        raise HTTPException(status_code=404, detail="site not found")
    return result


@router.get("/sitemap.xml", response_class=Response)
@router.head("/sitemap.xml", include_in_schema=False)
def public_sitemap(session: Session = Depends(get_session, scope="function")) -> Response:
    page = items_repo.list_published_items(session, page=1, page_size=_SITEMAP_MAX_URLS)
    datasets = collections_repo.list_visible_collections(
        session, tenant_id=DEFAULT_TENANT_SLUG, user_id=None, can_see_all=False
    )
    base_url = os.environ["PUBLIC_BASE_URL"]
    body = _render_sitemap_xml(
        base_url,
        page.items,
        [c.id for c in datasets][: max(0, _SITEMAP_MAX_URLS - len(page.items))],
    )
    return Response(content=body, media_type="application/xml", headers=_CACHE)


@router.get("/robots.txt", response_class=Response)
@router.head("/robots.txt", include_in_schema=False)
def public_robots() -> Response:
    base_url = os.environ["PUBLIC_BASE_URL"]
    return Response(
        content=f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n",
        media_type="text/plain",
        headers=_CACHE,
    )


def _preview(**kw: str | None) -> Response:
    html = _render_social_preview_html(os.environ["PUBLIC_BASE_URL"], **kw)  # type: ignore[arg-type]
    return Response(content=html, media_type="text/html", headers=_CACHE)


@router.get("/sites/{slug}/social-preview", response_class=Response)
def public_site_social_preview(
    slug: str, session: Session = Depends(get_session, scope="function")
) -> Response:
    item = items_repo.get_published_site_by_slug(session, slug=slug)
    if item is None:
        raise HTTPException(status_code=404, detail="site not found")
    base_url = os.environ["PUBLIC_BASE_URL"]
    return _preview(
        title=item.title,
        description=item.abstract or "",
        path=f"/sites/{item.slug}",
        image_url=_thumb_url(base_url, item),
    )


@router.get("/items/{item_id}/social-preview", response_class=Response)
def public_item_social_preview(
    item_id: str, session: Session = Depends(get_session, scope="function")
) -> Response:
    item = items_repo.get_published_item(session, item_id=item_id, tenant_id=DEFAULT_TENANT_SLUG)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    base_url = os.environ["PUBLIC_BASE_URL"]
    return _preview(
        title=item.title,
        description=item.abstract or "",
        path=f"/public/items/{item.pk}",
        og_type="article",
        image_url=_thumb_url(base_url, item),
    )


@router.get("/datasets/{collection_id}/social-preview", response_class=Response)
def public_dataset_social_preview(
    collection_id: str, session: Session = Depends(get_session, scope="function")
) -> Response:
    col = collections_repo.get_collection(
        session, tenant_id=DEFAULT_TENANT_SLUG, collection_id=collection_id
    )
    if col is None or not col.is_public:
        raise HTTPException(status_code=404, detail="dataset not found")
    return _preview(
        title=col.title, description=col.description or "", path=f"/public/datasets/{col.id}"
    )


@router.get("/items/{item_id}/thumbnail")
def public_item_thumbnail(
    item_id: str,
    session: Session = Depends(get_session, scope="function"),
    store: ThumbnailStore = Depends(get_thumbnail_store),
) -> Response:
    key = items_repo.get_published_thumbnail_key(session, item_id=item_id)
    if key is None:
        raise HTTPException(status_code=404, detail="no thumbnail")
    content, content_type = store.read(key)
    # nosniff : un contenu uploadé servi sans authentification ne doit jamais
    # être interprété comme HTML.
    return Response(
        content=content,
        media_type=content_type,
        headers={**_CACHE, "X-Content-Type-Options": "nosniff"},
    )


@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_public_config_by_item(
    item_id: str, session: Session = Depends(get_session, scope="function")
) -> ConfigRead:
    item = items_repo.get_published_item(session, item_id=item_id, tenant_id=DEFAULT_TENANT_SLUG)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    result = configs_repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result
