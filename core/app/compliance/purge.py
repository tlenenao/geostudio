# SPDX-License-Identifier: Apache-2.0
"""purge_tenant — suppression complète et irréversible des données d'un
tenant (RGPD, SP-58 Tâche 9). Le risque le plus élevé de ce plan (spec §5) :
contrairement à _delete_config_and_item/unregister_collection, qui
protègent contre les références orphelines PARCE QU'il reste d'autres
données dans le tenant après leur appel, une purge complète n'a pas ce
problème — tout disparaît dans le même passage, donc l'ordre n'a besoin de
respecter que les contraintes FK réelles (enfant avant parent, vérifiées
par introspection directe du schéma, cf. tests/test_compliance_purge.py),
jamais les gardes métier "encore référencé par" (qui protègent un tenant
partiel, pas un tenant qu'on vide entièrement) — ces gardes ne sont donc
volontairement PAS appelées ici.

Trouvaille de cette tâche (aucun code existant du dépôt ne le fait,
vérifié par grep — même unregister_collection/repo.delete_collection ne
DROP jamais la table dynamique d'une collection, seulement sa ligne
catalogue) : purge_tenant DROP réellement chaque table dynamique de
collection. Un tenant purgé sans cela laisserait ses données géospatiales
brutes intactes en base, orphelines du catalogue mais toujours lisibles
par quiconque connaît le nom de table — inacceptable pour une purge RGPD."""

import logging
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.alerts.models import AlertEvaluation
from app.analytics import lake_purge
from app.apikeys.models import ApiKey
from app.appexport.models import AppExportJob
from app.attachments import repository as attachments_repo
from app.attachments.models import Attachment
from app.attachments.routes import get_attachments_bucket
from app.collections.models import Collection
from app.collections.publication import remove_table_from_publication
from app.compliance.journal import schedule_erasure_journal
from app.compliance.models import PurgeReceipt
from app.configs.models import Config, ConfigRevision
from app.copilot.models import LlmUsage, TenantLlmSettings
from app.dataexport.models import CollectionExportJob
from app.export.models import ExportJob
from app.extensions.models import Extension
from app.geocoding.models import GeocodeJob
from app.harvest.models import HarvestRecord, HarvestSource
from app.history.models import EntityHistory
from app.ingestion.models import IngestionJob
from app.ingestion.routes import get_uploads_bucket
from app.items.models import Item
from app.jobs.after_commit import run_after_commit
from app.mapicons.models import MapIcon, TenantBasemap
from app.notifications.models import Notification, NotificationPreference
from app.outbox.models import FileTrigger, FileTriggerSeen, OutboundWebhook, OutboxEvent
from app.pipelines import checkpoints
from app.pipelines.models import PipelineRun
from app.public_submit.models import Submission, SubmissionToken
from app.quality.models import QualityReport
from app.quotas.models import TenantLimits
from app.raster.models import RasterAsset, RasterJob
from app.raster.routes import get_raster_bucket
from app.relations.models import CollectionRelation
from app.reports.models import ReportRun
from app.roles.models import Role
from app.secrets.models import ConnectorSecret
from app.sharing.models import (
    CollectionGeoLimit,
    CollectionShare,
    Group,
    GroupClaimMapping,
    GroupMember,
    ItemShare,
)
from app.tenants.models import Tenant
from app.terrain3d.models import Terrain3DJob
from app.terrain3d.routes import get_terrain3d_bucket
from app.tileset3d.models import Tileset3DJob
from app.tileset3d.routes import get_tileset3d_bucket
from app.users.models import User

logger = logging.getLogger(__name__)


def _delete_all(session: Session, model, tenant_id: str) -> int:
    count = session.scalar(
        select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
    )
    session.execute(delete(model).where(model.tenant_id == tenant_id))
    return count or 0


def _delete_tenant_prefixed_objects(s3, bucket: str, tenant_id: str) -> int:
    """Supprime tous les objets sous le préfixe `{tenant_id}/` d'un bucket
    tenant-préfixé — pagination explicite (même piège que app.quotas.
    service::tenant_prefixed_storage_bytes, list_objects_v2 tronque à 1000
    clés), delete_objects en lot (max 1000 clés par appel S3)."""
    prefix = f"{tenant_id}/"
    total = 0
    continuation_token: str | None = None
    while True:
        kwargs: dict = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token is not None:
            kwargs["ContinuationToken"] = continuation_token
        page = s3.list_objects_v2(**kwargs)
        keys = [obj["Key"] for obj in page.get("Contents", [])]
        if keys:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in keys]})
            total += len(keys)
        if page.get("IsTruncated"):
            continuation_token = page.get("NextContinuationToken")
        else:
            break
    return total


def _purge_tenant_s3(s3, tenant_id: str, export_result_keys, appexport_result_keys) -> int:
    """Objets S3 des buckets tenant-préfixés (uploads/tileset3d/terrain3d/raster/
    attachments), du lac CDC, et des 2 buckets de sortie de job (result_key connu,
    pas de préfixe commun, cf. spec §1.4/§3.1). Retourne le nombre d'objets supprimés."""
    # ARC-10 : pièces jointes de soumissions en attente (aucune ligne `attachments`).
    total = 0
    for bucket_getter in (
        get_uploads_bucket,
        get_tileset3d_bucket,
        get_terrain3d_bucket,
        get_raster_bucket,
        get_attachments_bucket,
    ):
        total += _delete_tenant_prefixed_objects(s3, bucket_getter(), tenant_id)
    # REV-322 : le lac CDC (bucket geostudio-cdc, préfixe cdc/tenant_id=<t>/ :
    # partitions + snapshots de toutes les collections du tenant).
    total += lake_purge.purge_prefix(
        s3,
        bucket=os.environ.get("S3_CDC_BUCKET", "geostudio-cdc"),
        prefix=lake_purge.lake_prefix(tenant_id),
    )
    exports_bucket = os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")
    appexports_bucket = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
    # REV-283e : exports de données sous `{tenant}/data-exports/` (préfixe tenant).
    total += _delete_tenant_prefixed_objects(s3, exports_bucket, tenant_id)
    for bucket, keys in (
        (exports_bucket, export_result_keys),
        (appexports_bucket, appexport_result_keys),
    ):
        if keys:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in keys]})
            total += len(keys)
    return total


S3_PENDING = "done_with_s3_pending"


def _make_s3_cleanup(
    bind, s3, *, tenant_id: str, receipt_id: str, export_result_keys, appexport_result_keys
):
    def cleanup() -> None:
        deleted, failed = 0, False
        try:
            deleted = _purge_tenant_s3(s3, tenant_id, export_result_keys, appexport_result_keys)
        except Exception:
            failed = True
            logger.exception("purge du tenant %s : nettoyage S3 incomplet", tenant_id)
        # AUD-121 : jamais « done » avec des objets encore présents — le reçu passe en
        # `done_with_s3_pending` (+ clés de sortie de job, introuvables après la purge) et
        # `retry_pending_s3_purges` reprend le nettoyage.
        # Session dédiée : la transaction de la purge est déjà committée. Écrit le
        # comptage réel sur le reçu (best-effort, la purge elle-même est acquise).
        try:
            with Session(bind=bind) as own:
                receipt = own.get(PurgeReceipt, receipt_id)
                if receipt is not None:
                    receipt.counts = {
                        **receipt.counts,
                        "s3_objects_deleted": deleted,
                        **(
                            {
                                "s3_cleanup_failed": 1,
                                "s3_pending_export_keys": list(export_result_keys),
                                "s3_pending_appexport_keys": list(appexport_result_keys),
                            }
                            if failed
                            else {}
                        ),
                    }
                    if failed:
                        receipt.status = S3_PENDING
                    own.commit()
        except Exception:
            logger.exception("purge du tenant %s : comptage S3 non enregistré", tenant_id)

    return cleanup


def purge_tenant(
    session: Session,
    s3,
    *,
    tenant_id: str,
    requested_by_user_id: str,
    receipt_id: str | None = None,
) -> PurgeReceipt:
    """receipt_id : identifiant du reçu de purge à créer, connu par
    l'appelant AVANT que cette fonction ne s'exécute (SP-58 Tâche 10) — la
    route de déclenchement le génère et le renvoie au client comme jobId
    immédiatement, pour que GET /compliance/purges/{purge_id} puisse
    interroger ce même id pendant que le job tourne encore en tâche de
    fond (aucune ligne PurgeReceipt n'existe tant que la purge n'est pas
    terminée : son absence EST le signal "encore en cours"). Défaut
    uuid4() : un appel direct (tests, scripts) sans passer par la route
    reste possible sans en préciser un."""
    tenant = session.get(Tenant, tenant_id)
    tenant_slug = tenant.slug if tenant is not None else tenant_id
    started_at = datetime.now(UTC)
    counts: dict[str, int] = {}

    # 1. Enfants directs d'items SANS cascade DB (doivent être vidés avant
    #    items, sans quoi leur suppression — explicite ou via cascade
    #    depuis configs->items — violerait leur propre FK non-cascade).
    counts["config_revisions"] = _delete_all(session, ConfigRevision, tenant_id)
    counts["entity_history"] = _delete_all(session, EntityHistory, tenant_id)  # ARC-15
    counts["collection_relations"] = _delete_all(session, CollectionRelation, tenant_id)  # ARC-21
    # ARC4-F6 : outbox, déclencheurs fichier (+ clés d'idempotence), destinations (ordre FK)
    counts["outbox"] = _delete_all(session, OutboxEvent, tenant_id)
    counts["file_trigger_seen"] = _delete_all(session, FileTriggerSeen, tenant_id)
    counts["file_triggers"] = _delete_all(session, FileTrigger, tenant_id)
    counts["outbound_webhooks"] = _delete_all(session, OutboundWebhook, tenant_id)
    counts["alert_evaluations"] = _delete_all(session, AlertEvaluation, tenant_id)
    # result_key capturé AVANT suppression des lignes : ExportJob/
    # AppExportJob vivent dans 2 buckets non tenant-préfixés (renders/
    # appexports), leur clé S3 n'est retrouvable que via cette colonne
    # (spec §1.4) — perdue dès que la ligne est supprimée.
    export_result_keys = [
        k
        for k in session.scalars(
            select(ExportJob.result_key).where(ExportJob.tenant_id == tenant_id)
        ).all()
        if k is not None
    ]
    appexport_result_keys = [
        k
        for k in session.scalars(
            select(AppExportJob.result_key).where(AppExportJob.tenant_id == tenant_id)
        ).all()
        if k is not None
    ]
    counts["app_export_jobs"] = _delete_all(session, AppExportJob, tenant_id)
    counts["export_jobs"] = _delete_all(session, ExportJob, tenant_id)
    counts["collection_export_jobs"] = _delete_all(session, CollectionExportJob, tenant_id)
    counts["quality_reports"] = _delete_all(session, QualityReport, tenant_id)
    counts["pipeline_runs"] = _delete_all(session, PipelineRun, tenant_id)
    # F5 : points de reprise Parquet (données tenant) du disque local du processus
    # qui exécute la purge. ponytail: un autre worker/hôte garde ses fichiers jusqu'à
    # la rétention (24 h) ; volume partagé ou purge par worker si multi-hôte.
    checkpoints.purge_tenant(tenant_id)
    counts["report_runs"] = _delete_all(session, ReportRun, tenant_id)
    counts["harvest_records"] = _delete_all(session, HarvestRecord, tenant_id)
    counts["configs"] = _delete_all(session, Config, tenant_id)
    counts["submissions"] = _delete_all(session, Submission, tenant_id)
    counts["submission_tokens"] = _delete_all(session, SubmissionToken, tenant_id)
    session.flush()

    # 2. Collections : dépublication CDC + DROP réel de la table dynamique
    #    + purge des pièces jointes (lignes + S3) AVANT la ligne catalogue
    #    (attachments.collection_id est ON DELETE CASCADE depuis la 0034,
    #    mais delete_all_for_collection nettoie aussi les objets S3 — un
    #    CASCADE Postgres ne le ferait pas).
    attachments_bucket = get_attachments_bucket()
    collections = list(
        session.scalars(select(Collection).where(Collection.tenant_id == tenant_id)).all()
    )
    counts["collections"] = len(collections)
    dropped_tables = 0
    for col in collections:
        remove_table_from_publication(session, col.table_name)
        attachments_repo.delete_all_for_collection(
            session, s3, attachments_bucket, tenant_id=tenant_id, collection_id=col.id
        )
        session.execute(text(f'DROP TABLE IF EXISTS public."{col.table_name}" CASCADE'))
        dropped_tables += 1
    counts["collection_dynamic_tables_dropped"] = dropped_tables
    session.execute(delete(Collection).where(Collection.tenant_id == tenant_id))
    session.flush()

    # 3. Items — désormais safe : tout ce qui le référence sans cascade a
    #    été vidé à l'étape 1 (configs/alert_evaluations/export_jobs/
    #    app_export_jobs/pipeline_runs/report_runs/harvest_records).
    #    item_shares cascade automatiquement (ON DELETE CASCADE).
    counts["raster_assets"] = _delete_all(session, RasterAsset, tenant_id)  # FK items
    counts["items"] = _delete_all(session, Item, tenant_id)
    session.flush()

    # 4. Objets S3 : supprimés APRÈS le commit de la purge (REV-344 c) — un échec
    #    avant le commit laisserait sinon la base intacte et S3 vidé. Les clés
    #    de résultat d'export/appexport sont capturées à l'étape 1 (les lignes
    #    ont disparu). Le comptage réel est écrit sur le reçu par le callback.
    counts["s3_objects_deleted"] = 0
    final_receipt_id = receipt_id if receipt_id is not None else str(uuid.uuid4())
    run_after_commit(
        session,
        _make_s3_cleanup(
            session.get_bind(),
            s3,
            tenant_id=tenant_id,
            receipt_id=final_receipt_id,
            export_result_keys=export_result_keys,
            appexport_result_keys=appexport_result_keys,
        ),
    )

    schedule_erasure_journal(session, kind="tenant", tenant_id=tenant_id, subject_id=tenant_id)

    # 5. Le reste des tables tenant-scoped indépendantes d'items/
    #    collections (ou déjà safe car leurs propres FK non-cascade ont
    #    été traitées plus haut).
    counts["tileset3d_jobs"] = _delete_all(session, Tileset3DJob, tenant_id)
    counts["terrain3d_jobs"] = _delete_all(session, Terrain3DJob, tenant_id)
    counts["raster_jobs"] = _delete_all(session, RasterJob, tenant_id)
    counts["ingestion_jobs"] = _delete_all(session, IngestionJob, tenant_id)
    counts["api_keys"] = _delete_all(session, ApiKey, tenant_id)
    counts["notifications"] = _delete_all(session, Notification, tenant_id)
    counts["notification_preferences"] = _delete_all(session, NotificationPreference, tenant_id)
    counts["connector_secrets"] = _delete_all(session, ConnectorSecret, tenant_id)
    counts["harvest_sources"] = _delete_all(session, HarvestSource, tenant_id)
    counts["map_icons"] = _delete_all(session, MapIcon, tenant_id)
    counts["tenant_basemaps"] = _delete_all(session, TenantBasemap, tenant_id)
    counts["tenant_limits"] = _delete_all(session, TenantLimits, tenant_id)  # AUD-098
    counts["llm_usage"] = _delete_all(session, LlmUsage, tenant_id)  # AUD-106
    counts["tenant_llm_settings"] = _delete_all(session, TenantLlmSettings, tenant_id)  # AUD-149
    counts["geocode_jobs"] = _delete_all(session, GeocodeJob, tenant_id)
    counts["extensions"] = _delete_all(session, Extension, tenant_id)
    counts["group_members"] = _delete_all(session, GroupMember, tenant_id)
    counts["group_claim_mappings"] = _delete_all(session, GroupClaimMapping, tenant_id)
    counts["item_shares"] = _delete_all(session, ItemShare, tenant_id)
    counts["collection_geo_limits"] = _delete_all(session, CollectionGeoLimit, tenant_id)
    counts["collection_shares"] = _delete_all(session, CollectionShare, tenant_id)
    counts["attachments"] = _delete_all(session, Attachment, tenant_id)
    counts["groups"] = _delete_all(session, Group, tenant_id)
    session.flush()

    # 6. Users (désormais safe : les 16 FK de la spec §1.3 ont toutes été
    #    vidées pour ce tenant par les étapes précédentes).
    counts["users"] = _delete_all(session, User, tenant_id)
    session.flush()

    # 7. Roles (après users, qui les référencent par role_id NOT NULL).
    counts["roles"] = _delete_all(session, Role, tenant_id)
    session.flush()

    # 8. audit_log (FK vers tenants.id sans ondelete= — la ligne tenants ne
    #    pourra pas être supprimée tant que des lignes audit_log la
    #    référencent).
    from app.audit import chain as audit_chain
    from app.audit.models import AuditLog

    # AUD-092 : l'audit disparaît avec le tenant, mais son empreinte de tête survit dans
    # le reçu (preuve d'intégrité de ce qui a été purgé, sans conserver de contenu).
    audit_chain.seal_all(session, tenant_id)
    audit_head = audit_chain.head(session, tenant_id)
    if audit_head is not None:
        counts["audit_log_chain_seq"] = audit_head[0]
        counts["audit_log_head_hash"] = audit_head[1]  # type: ignore[assignment]
    with audit_chain.audit_maintenance(session):
        counts["audit_log"] = _delete_all(session, AuditLog, tenant_id)
    session.flush()

    # 9. Preuve de purge — écrite AVANT la suppression du tenant (étape
    #    10) : sinon aucune trace de son tenant_slug ne survivrait.
    #    Volontairement sans FK vers tenants (cf. app/compliance/models.py).
    receipt = session.get(PurgeReceipt, final_receipt_id)
    if receipt is None:  # appel direct (tests, scripts) sans reçu créé par la route
        receipt = PurgeReceipt(
            id=final_receipt_id,
            tenant_slug=tenant_slug,
            requested_by_user_id=requested_by_user_id,
            requested_at=started_at,
            counts={},
        )
        session.add(receipt)
    receipt.status = "done"
    receipt.error = None
    receipt.purged_tenant_id = tenant_id
    receipt.completed_at = datetime.now(UTC)
    receipt.counts = counts
    session.flush()

    # 10. Tenant lui-même.
    session.execute(delete(Tenant).where(Tenant.id == tenant_id))
    session.flush()

    return receipt


def retry_pending_s3_purges(session: Session, s3) -> int:
    """Reprend le nettoyage S3 des purges terminées en base mais pas côté objets (AUD-121).
    Retourne le nombre de reçus soldés."""
    done = 0
    receipts = session.scalars(select(PurgeReceipt).where(PurgeReceipt.status == S3_PENDING)).all()
    for receipt in receipts:
        tenant_id = receipt.purged_tenant_id or receipt.tenant_slug
        counts = dict(receipt.counts)
        try:
            n = _purge_tenant_s3(
                s3,
                tenant_id,
                counts.pop("s3_pending_export_keys", []),
                counts.pop("s3_pending_appexport_keys", []),
            )
        except Exception:
            logger.exception("rattrapage S3 de la purge %s échoué", receipt.id)
            continue
        counts.pop("s3_cleanup_failed", None)
        counts["s3_objects_deleted"] = int(counts.get("s3_objects_deleted", 0)) + n
        receipt.counts = counts
        receipt.status = "done"
        done += 1
    session.flush()
    return done
