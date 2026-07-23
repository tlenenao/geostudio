# SPDX-License-Identifier: Apache-2.0
"""Le moteur de moissonnage (SP-12c) : fetch via le connecteur du type de la
source, puis upsert idempotent des HarvestedRecord contre harvest_records
(§2.3 spec — contrainte unique (tenant_id, source_id, external_id) garantit
l'absence de doublon même sur exécutions concurrentes). Ne lève jamais : toute
erreur de fetch termine la source en last_status="error", jamais un job
zombie (même philosophie que app.ingestion.tasks)."""
import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.harvest import repository as harvest_repo
from app.harvest.connectors import get_connector
from app.harvest.connectors.base import HarvestedRecord
from app.harvest.egress import guarded_get
from app.harvest.models import HarvestSource
from app.ingestion.importer import run_import
from app.items import repository as items_repo

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _content_hash(rec: HarvestedRecord) -> str:
    raw = "|".join([
        rec.title, rec.abstract, ",".join(sorted(rec.keywords)),
        ",".join(f"{v:.6f}" for v in rec.bbox),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _layer_kind(rec: HarvestedRecord) -> str | None:
    if rec.raster_tiles_url is not None:
        return "raster"
    if rec.items_url is not None:
        return "feature"
    return None


def harvest_source(
    session: Session, source: HarvestSource, *, http_get=guarded_get,
) -> None:
    # Capturés avant tout accès DB : une IntegrityError de flush expire
    # immédiatement TOUS les attributs des objets de la session (pas
    # seulement au moment où on appelle nous-même session.rollback()) —
    # relire `source.tenant_id`/`source.id` après un tel échec redéclenche
    # une requête sur une transaction déjà invalidée (PendingRollbackError).
    # Ces deux chaînes ne dépendent d'aucune transaction, donc restent
    # utilisables même après un rollback.
    tenant_id = source.tenant_id
    source_id = source.id
    try:
        connector = get_connector(source.type)
        records = list(connector.fetch(source.url))
    except Exception as exc:
        logger.exception("harvest source %s: échec de récupération", source.id)
        source.last_status = "error"
        source.last_error = str(exc)[:500]
        session.flush()
        return

    # Le traitement par enregistrement (upsert, y compris fetch_copy_geojson/
    # run_import en mode copy — fail-fast, réseau) est capturé au même titre
    # que le fetch ci-dessus : le contrat de harvest_source est de ne JAMAIS
    # lever, pour que le job procrastinate (Task 5) ne retente jamais un
    # zombie. Décision : en cas d'échec en cours de boucle, on rollback (cf.
    # bloc except plus bas) — les enregistrements déjà upsertés plus tôt dans
    # la même boucle sont donc ANNULÉS, pas conservés ; c'est sans dommage car
    # l'upsert est idempotent et le moissonnage suivant réconcilie tout. On ne
    # lance PAS mark_missing_as_stale et on ne marque PAS "ok" : la source
    # passe "error" pour que sa santé soit visible.
    try:
        seen_external_ids: set[str] = set()
        for rec in records:
            seen_external_ids.add(rec.external_id)
            digest = _content_hash(rec)
            existing = harvest_repo.get_record(
                session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
            )
            if source.mode == "copy":
                _upsert_copy(session, source, rec, existing, digest, connector, http_get)
            else:
                _upsert_reference(session, source, rec, existing, digest)

        harvest_repo.mark_missing_as_stale(
            session, tenant_id=source.tenant_id, source_id=source.id, seen_external_ids=seen_external_ids,
        )
    except Exception as exc:
        logger.exception("harvest source %s: échec de traitement des enregistrements", source_id)
        # La boucle peut avoir empoisonné la transaction SQLAlchemy elle-même
        # (ex. IntegrityError réelle heurtée par un flush interne — pas une
        # simple exception Python — dans run_import en mode copy, ou une
        # contrainte unique heurtée par une exécution concurrente) : écrire
        # directement `source.last_status = "error"` puis flush() lèverait
        # alors à son tour (le flush ne fait *aucune* vérification de l'état
        # de la transaction tant qu'aucun objet n'est modifié : un flush "à
        # blanc" ne suffit pas à sonder l'empoisonnement, il faut réellement
        # rollback), laissant la source bloquée en "running" (committé par
        # mark_running) — le zombie exact que ce fix vise à éliminer. On
        # rollback donc TOUJOURS avant d'écrire le statut d'erreur, pour
        # repartir d'une transaction saine dans tous les cas (poisoned ou
        # non) ; cela expire l'objet `source`, on le recharge donc avant de
        # le modifier.
        session.rollback()
        source = harvest_repo.get_source(session, tenant_id=tenant_id, source_id=source_id)
        if source is None:
            return
        source.last_status = "error"
        source.last_error = str(exc)[:500]
        session.flush()
        return

    source.last_run_at = _now()
    source.last_status = "ok"
    source.last_error = None
    session.flush()


def _upsert_reference(session, source, rec: HarvestedRecord, existing, digest: str) -> None:
    if existing is None:
        item = items_repo.create_item(
            session, tenant_id=source.tenant_id, owner_id=source.owner_id,
            resource_type="external", title=rec.title,
        )
        items_repo.update_item(
            session, tenant_id=source.tenant_id, item_id=item.id,
            title=None, abstract=rec.abstract, keywords=rec.keywords, is_published=None,
        )
        write_audit(
            session, tenant_id=source.tenant_id, actor_id=source.owner_id, actor_kind="user",
            action="harvest_record.create", object_type="item", object_id=item.id,
            payload={"sourceId": source.id, "externalId": rec.external_id},
        )
        harvest_repo.create_record(
            session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
            item_id=item.id, collection_id=None, content_hash=digest,
            external_url=rec.external_url, tiles_url=rec.raster_tiles_url, layer_kind=_layer_kind(rec),
        )
        return

    if existing.content_hash != digest:
        items_repo.update_item(
            session, tenant_id=source.tenant_id, item_id=existing.item_id,
            title=rec.title, abstract=rec.abstract, keywords=rec.keywords, is_published=None,
        )
    harvest_repo.update_record(
        session, existing, content_hash=digest, harvested_at=_now(), is_stale=False,
        external_url=rec.external_url, tiles_url=rec.raster_tiles_url, layer_kind=_layer_kind(rec),
    )


def _upsert_copy(session, source, rec: HarvestedRecord, existing, digest: str, connector, http_get) -> None:
    if existing is not None:
        # v0 : un contenu déjà copié n'est jamais ré-importé — le pipeline
        # SP-6 (run_import) ne sait que CRÉER une nouvelle collection, jamais
        # mettre à jour le contenu d'une collection existante. Seule la
        # fraîcheur du mapping avance, pour respecter "jamais de doublon"
        # sans reconstruire une synchronisation de contenu hors périmètre
        # SP-12c (cf. plan §Global Constraints).
        harvest_repo.update_record(session, existing, content_hash=digest, harvested_at=_now(), is_stale=False)
        return

    if rec.items_url is None:
        logger.warning(
            "harvest source %s: collection distante %s sans lien items, copie ignorée",
            source.id, rec.external_id,
        )
        return

    content = connector.fetch_copy_geojson(rec, http_get=http_get)
    if content is None:
        logger.warning(
            "harvest source %s: connecteur sans contenu copiable pour %s, ignoré",
            source.id, rec.external_id,
        )
        return
    result = run_import(
        session, tenant_id=source.tenant_id, created_by=source.owner_id,
        filename="harvest.geojson", content=content, collection_title=rec.title,
        lat_field=None, lon_field=None,
    )
    write_audit(
        session, tenant_id=source.tenant_id, actor_id=source.owner_id, actor_kind="user",
        action="harvest_record.create", object_type="collection", object_id=result.collection_id,
        payload={"sourceId": source.id, "externalId": rec.external_id},
    )
    harvest_repo.create_record(
        session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
        item_id=result.item_id, collection_id=result.collection_id, content_hash=digest,
        external_url=rec.external_url, tiles_url=None, layer_kind=_layer_kind(rec),
    )
