# SPDX-License-Identifier: Apache-2.0
"""POST /v1/styles/sld (ARC-28) : exporte une symbologie déclarative en SLD 1.1.
Fonction pure (aucune lecture de données) ; authentifié pour ne pas offrir de CPU
anonyme. Le style MapLibre s'exporte côté shell (`mapLibreStyle.ts`), là où vit
`buildMapPaint`, pour que le rendu rechargé soit identique par construction."""

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.auth.dependency import get_current_user
from app.styles.model import style_from_symbology
from app.styles.sld import style_to_sld
from app.users.models import User

router = APIRouter(prefix="/styles", tags=["styles"])


class SldExportBody(BaseModel):
    symbology: dict | None = None
    geometryKind: Literal["point", "line", "polygon"] = "polygon"
    name: str = Field(default="layer", min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=200)


@router.post(
    "/sld",
    response_class=Response,
    responses={200: {"content": {"application/vnd.ogc.sld+xml": {}}}},
)
def export_sld(body: SldExportBody, _user: User = Depends(get_current_user)) -> Response:
    style = style_from_symbology(body.symbology, body.geometryKind)
    xml = style_to_sld(style, layer_name=body.name, title=body.title)
    return Response(
        content=xml,
        media_type="application/vnd.ogc.sld+xml",
        headers={"Content-Disposition": 'attachment; filename="style.sld"'},
    )
