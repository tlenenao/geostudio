# SPDX-License-Identifier: Apache-2.0
"""Routes REST de la bibliothèque d'icônes personnalisées (SP-27 §3.4, D7).

Tenant-scoped, auditée, ouverte à tout utilisateur authentifié du tenant —
délibérément PAS admin-only, contrairement à app.secrets
(`require_privilege(admin.secrets.manage)` sur toutes ses routes) : une
icône est du matériel de présentation attaché à une carte que l'utilisateur
a déjà le droit d'éditer, sans contenu secret.
Ne passe pas par can() : can() autorise l'accès à un ITEM, et une icône n'en
est pas un.

D7 : PAS de présignation. Le précédent d'upload est
POST /items/{item_id}/thumbnail (app/items/routes.py:118-141, le seul
UploadFile du cœur), durci ici par une lecture PAR MORCEAUX avec abandon au
dépassement du plafond. La présignation de app.tileset3d/app.terrain3d existe
parce qu'un tileset pèse des centaines de mégaoctets ; une icône pèse quelques
kilo-octets, et le cœur doit de toute façon lire l'intégralité du fichier pour
l'assainir. Le précédent de proxy de LECTURE, lui, reste
app.tileset3d/app.terrain3d.
"""

import logging
import os
import re
import uuid

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.errors import ValidationHTTPException
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket
from app.mapicons import repository as repo
from app.mapicons.models import MapIcon
from app.mapicons.schemas import (
    ALLOWED_CONTENT_TYPES,
    MAX_ICON_BYTES,
    MAX_TEXT_FIELD_CHARS,
    UPLOAD_CHUNK_BYTES,
    MapIconOut,
)
from app.mapicons.svg import SvgRejected, sanitize_svg, sniff_content_type
from app.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def get_mapicons_bucket() -> str:
    return os.environ.get("S3_MAPICONS_BUCKET", "geostudio-mapicons")


def _to_response(icon: MapIcon) -> MapIconOut:
    return MapIconOut(
        id=icon.id,
        title=icon.title,
        category=icon.category,
        contentType=icon.content_type,
        createdAt=icon.created_at.isoformat(),
    )


async def _read_bounded(file: UploadFile) -> bytes:
    """Lit le corps PAR MORCEAUX et abandonne dès le dépassement du plafond.

    Jamais `await file.read()` sans argument : le plafond doit être appliqué
    AVANT de tenir le fichier entier en mémoire. Mesuré sur un TestClient réel
    (plafond 64, morceaux de 32, charge de 500 octets) : la boucle s'arrête à
    96 octets lus, le reste n'est jamais lu.

    Ce que cela borne : les octets que CETTE route tient en mémoire, et le
    travail d'assainissement. Ce que cela ne borne pas : ce que Starlette a
    déjà accepté — MultiPartParser déverse la partie dans un
    SpooledTemporaryFile (mémoire jusqu'à ~1 Mio, disque ensuite) avant que ce
    handler ne s'exécute. Un plafond de corps de requête global relève du
    reverse-proxy, hors périmètre de ce plan.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_ICON_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"icon too large (limite {MAX_ICON_BYTES} octets)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/map-icons", status_code=201)
async def create_map_icon(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3_client=Depends(get_s3_client),
) -> MapIconOut:
    # Bornes de longueur, précédent app/tileset3d/schemas.py:5-7. Les champs
    # arrivent en multipart, donc validés ici et non par un modèle pydantic.
    for name, value in (("title", title), ("category", category)):
        if not value.strip() or len(value) > MAX_TEXT_FIELD_CHARS:
            raise HTTPException(
                status_code=422,
                detail=f"{name} must be between 1 and {MAX_TEXT_FIELD_CHARS} characters",
            )

    declared = file.content_type or ""
    if declared not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="unsupported content type")

    raw = await _read_bounded(file)

    # Le contentType DÉCLARÉ dans l'en-tête de partie ne prouve rien sur les
    # octets : on tranche sur leur contenu réel.
    sniffed = sniff_content_type(raw)
    if sniffed is None or sniffed != declared:
        raise ValidationHTTPException(
            errors=[
                {
                    "field": "file",
                    "code": "content_type_mismatch",
                    "message": (
                        f"Les octets téléversés ne correspondent pas au type déclaré ({declared})."
                    ),
                }
            ],
            status_code=400,
        )

    body = raw
    if sniffed == "image/svg+xml":
        # ASSAINISSEMENT AVANT ÉCRITURE (D4+D7) : ce sont les octets assainis
        # qui partent sur S3, et rien n'est écrit si l'assainissement échoue.
        # La lecture ne réassainit pas — un seul endroit où la garde peut
        # manquer, et aucun client n'a jamais eu de droit d'écriture sur la clé.
        try:
            body = sanitize_svg(raw)
        except SvgRejected as exc:
            raise ValidationHTTPException(
                errors=[{"field": "file", "code": exc.code, "message": exc.message}],
                status_code=400,
            ) from exc

    # La clé est CHOISIE PAR LE CŒUR, préfixée du tenant. Le client ne la
    # fournit jamais, donc il n'y a plus rien à vérifier à son sujet.
    safe = _SAFE_FILENAME.sub("_", file.filename or "")[:80] or "icon"
    key = f"{user.tenant_id}/{uuid.uuid4().hex}-{safe}"
    bucket = get_mapicons_bucket()
    ensure_uploads_bucket(s3_client, bucket)
    s3_client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=sniffed)

    icon = repo.create_icon(
        session,
        tenant_id=user.tenant_id,
        created_by=user.id,
        title=title,
        category=category,
        s3_key=key,
        content_type=sniffed,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="mapicon.create",
        object_type="mapicon",
        object_id=icon.id,
        payload={"title": icon.title, "category": icon.category},
    )
    return _to_response(icon)


@router.get("/map-icons")
def list_map_icons(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MapIconOut]:
    return [_to_response(i) for i in repo.list_icons(session, tenant_id=user.tenant_id)]


@router.delete("/map-icons/{icon_id}", status_code=204)
def delete_map_icon(
    icon_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3_client=Depends(get_s3_client),
) -> None:
    icon = repo.get_icon(session, tenant_id=user.tenant_id, icon_id=icon_id)
    if icon is None:
        raise HTTPException(status_code=404, detail="icon not found")
    # SP-42/F-securite-autorisation-13 : la lecture reste partagée à
    # l'échelle du tenant (docstring de module), mais la suppression — qui
    # supprime aussi l'objet S3, sans possibilité de restauration — est
    # restreinte au créateur. maps.manage n'est PAS retenu comme bypass ici :
    # le rôle prédéfini « Créateur » (le rôle par défaut de tout nouvel
    # utilisateur non-admin) le porte déjà, ce qui aurait laissé le scénario
    # exact de la trouvaille ouvert (Bob, Créateur par défaut, supprimant
    # l'icône d'Alice). Voir le rapport SP-42 pour l'alternative envisagée
    # et pourquoi elle a été écartée.
    if icon.created_by != user.id:
        raise HTTPException(status_code=403, detail="not allowed")
    title, category, s3_key = icon.title, icon.category, icon.s3_key
    # Base d'abord, S3 ensuite en best-effort : la transaction reste ouverte
    # jusqu'à la fin de la requête (request_scoped_session), donc supprimer
    # l'objet S3 en premier perdrait les octets tout en gardant la ligne si
    # le commit échouait. Un objet orphelin est rattrapable, l'inverse non.
    repo.delete_icon(session, icon)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="mapicon.delete",
        object_type="mapicon",
        object_id=icon_id,
        payload={"title": title, "category": category},
    )
    try:
        s3_client.delete_object(Bucket=get_mapicons_bucket(), Key=s3_key)
    except ClientError:
        logger.warning("mapicon %s: objet S3 %s non supprimé", icon_id, s3_key, exc_info=True)


@router.get("/map-icons/{icon_id}/file")
def read_map_icon_file(
    icon_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3_client=Depends(get_s3_client),
) -> Response:
    icon = repo.get_icon(session, tenant_id=user.tenant_id, icon_id=icon_id)
    if icon is None:
        raise HTTPException(status_code=404, detail="icon not found")
    try:
        obj = s3_client.get_object(Bucket=get_mapicons_bucket(), Key=icon.s3_key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="icon file not found") from exc
    # Nom de fichier servi au navigateur : le dernier segment de la clé, moins
    # le préfixe uuid. La clé est déjà passée par _SAFE_FILENAME à l'écriture,
    # donc elle ne peut contenir ni guillemet ni retour à la ligne.
    filename = icon.s3_key.rsplit("/", 1)[-1].split("-", 1)[-1] or "icon"
    return Response(
        content=obj["Body"].read(),
        media_type=icon.content_type,
        headers={
            # Cache-Control : convention établie des réponses d'octets
            # authentifiées (app.tileset3d:302, app.terrain3d:175).
            "Cache-Control": "private, max-age=3600",
            # nosniff : PREMIÈRE occurrence dans core/app/ (vérifié :
            # grep -rn 'X-Content-Type-Options' core/app/ → vide). Pratique
            # nouvelle, décidée explicitement (D4), parce que c'est la première
            # route du cœur à servir un fichier téléversé par un utilisateur
            # non-admin.
            "X-Content-Type-Options": "nosniff",
            # Content-Disposition, en revanche, a QUATRE précédents dans
            # core/app/ (features/routes.py:331 et :417, harvest/routes.py:444
            # et :542), tous en `attachment; filename="…"` : on suit la
            # convention du dépôt, filename compris. Sans filename, le
            # navigateur dérive le nom du dernier segment d'URL, soit « file ».
            "Content-Disposition": f'attachment; filename="{filename}"',
            # On NE réassainit PAS ici : les octets stockés sont déjà la
            # version assainie, et aucun client n'a jamais eu de droit
            # d'écriture sur cette clé (D7). Réassainir à chaque lecture
            # ajouterait un second endroit où la garde peut manquer, et ferait
            # payer un parse XML à chaque affichage de carte.
        },
    )
