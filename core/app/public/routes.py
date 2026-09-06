# SPDX-License-Identifier: Apache-2.0
import os
from html import escape
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.configs.repository import ConfigRead
from app.db import get_session
from app.items import repository as items_repo
from app.items.schemas import ItemPage, ItemRead
from app.tenants.repository import DEFAULT_TENANT_SLUG

router = APIRouter(prefix="/public")

# Volontairement large (pas de nouvelle fonction dédiée) : list_published_items
# charge déjà TOUTES les lignes visibles avant de trancher en Python (spec
# SP-55 §3.2) — un sitemap veut l'intégralité du catalogue, pas une page.
# Cohérent avec l'hypothèse d'échelle documentée à cet endroit (petite
# échelle, catalogue d'un tenant).
_SITEMAP_PAGE_SIZE = 100_000


def _render_sitemap_xml(base_url: str, sites: list[ItemRead]) -> str:
    urls = "".join(
        f"<url><loc>{xml_escape(base_url)}/sites/{xml_escape(site.slug)}</loc></url>"
        for site in sites
        if site.slug
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def _render_social_preview_html(base_url: str, item: ItemRead) -> str:
    title = escape(item.title)
    description = escape(item.abstract or "")
    canonical = escape(f"{base_url}/sites/{item.slug}")
    return (
        "<!doctype html><html><head>"
        f"<title>{title}</title>"
        f'<meta name="description" content="{description}">'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{description}">'
        f'<link rel="canonical" href="{canonical}">'
        "</head><body></body></html>"
    )


@router.get("/items", response_model=ItemPage)
def list_public_items(
    type: str | None = None,
    tag: str | None = None,
    page: int = Query(1, ge=1),
    # Pas de borne haute, même choix que GET /items (cf. commentaire sur
    # cette route dans app/items/routes.py) : le défaut démontré est
    # l'absence de borne BASSE, pas l'absence de borne haute — ne pas en
    # ajouter une non demandée par la trouvaille.
    pageSize: int = Query(12, ge=1),
    session: Session = Depends(get_session),
) -> ItemPage:
    return items_repo.list_published_items(
        session,
        resource_type=type,
        tag=tag,
        page=page,
        page_size=pageSize,
    )


@router.get("/items/{item_id}", response_model=ItemRead)
def get_public_item(item_id: str, session: Session = Depends(get_session)) -> ItemRead:
    result = items_repo.get_published_item(session, item_id=item_id, tenant_id=DEFAULT_TENANT_SLUG)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result


@router.get("/sites/{slug}", response_model=ItemRead)
def get_public_site(slug: str, session: Session = Depends(get_session)) -> ItemRead:
    result = items_repo.get_published_site_by_slug(session, slug=slug)
    if result is None:
        raise HTTPException(status_code=404, detail="site not found")
    return result


@router.get("/sitemap.xml", response_class=Response)
def public_sitemap(session: Session = Depends(get_session)) -> Response:
    page = items_repo.list_published_items(
        session, resource_type="site", page=1, page_size=_SITEMAP_PAGE_SIZE
    )
    base_url = os.environ["PUBLIC_BASE_URL"]
    body = _render_sitemap_xml(base_url, page.items)
    return Response(content=body, media_type="application/xml")


@router.get("/robots.txt", response_class=Response)
def public_robots() -> Response:
    base_url = os.environ["PUBLIC_BASE_URL"]
    return Response(
        content=f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n",
        media_type="text/plain",
    )


@router.get("/sites/{slug}/social-preview", response_class=Response)
def public_site_social_preview(slug: str, session: Session = Depends(get_session)) -> Response:
    item = items_repo.get_published_site_by_slug(session, slug=slug)
    if item is None:
        raise HTTPException(status_code=404, detail="site not found")
    base_url = os.environ["PUBLIC_BASE_URL"]
    html = _render_social_preview_html(base_url, item)
    return Response(content=html, media_type="text/html")


@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_public_config_by_item(item_id: str, session: Session = Depends(get_session)) -> ConfigRead:
    item = items_repo.get_published_item(session, item_id=item_id, tenant_id=DEFAULT_TENANT_SLUG)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    result = configs_repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result
