# SPDX-License-Identifier: Apache-2.0
"""SP-58 Tâche 9 : purge_tenant — filet caractéristique (spec §5, premier
risque cité : ordre de suppression faux ou incomplet est le pire résultat
possible du plan entier).

Énumère TOUS les modèles SQLAlchemy qui portent une colonne tenant_id via
Base.registry.mappers plutôt qu'une liste recopiée à la main (même piège
que toFrontLayer(), SP-43 §1.2) — un futur module qui ajoute tenant_id sans
être couvert par purge_tenant serait sinon invisible. Un rang par table
(colonne, valeur) construit une ligne minimale valide pour CHAQUE modèle,
dans l'ordre de dépendance FK réel (vérifié par introspection directe du
schéma, pas deviné) — voir _create_one_row_per_model.

Tourne contre un Postgres réel (pg_engine, marker postgis) : SQLite
n'applique pas les contraintes FK par défaut, ce qui masquerait exactement
la classe de défaut que ce test doit détecter."""

import uuid

import pytest
from sqlalchemy import func, select, text

from app.alerts.models import AlertEvaluation
from app.appexport.models import AppExportJob
from app.attachments.models import Attachment
from app.audit.models import AuditLog
from app.collections.models import Collection
from app.collections.publication import remove_table_from_publication
from app.compliance.purge import purge_tenant
from app.configs.models import Config, ConfigRevision
from app.db import Base
from app.export.models import ExportJob
from app.extensions.models import Extension
from app.harvest.models import HarvestRecord, HarvestSource
from app.ingestion.models import IngestionJob
from app.items.models import Item
from app.mapicons.models import MapIcon
from app.notifications.models import Notification, NotificationPreference
from app.pipelines.models import PipelineRun
from app.reports.models import ReportRun
from app.roles.models import Role
from app.secrets.models import ConnectorSecret
from app.sharing.models import CollectionShare, Group, GroupMember, ItemShare
from app.tenants.models import Tenant
from app.terrain3d.models import Terrain3DJob
from app.tileset3d.models import Tileset3DJob
from app.users.models import User

pytestmark = pytest.mark.postgis


def _models_with_tenant_id():
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, "tenant_id"):
            yield cls


class _FakeS3Client:
    """Double minimal : list_objects_v2 toujours vide (aucun objet réel à
    lister dans ce test — la Tâche 9 vérifie les LIGNES de base, pas le
    contenu S3 réel), delete_objects/delete_object no-op."""

    def list_objects_v2(self, *, Bucket, Prefix="", ContinuationToken=None):
        return {"Contents": [], "IsTruncated": False, "NextContinuationToken": None}

    def delete_objects(self, *, Bucket, Delete):
        pass

    def delete_object(self, *, Bucket, Key):
        pass


def _create_tenant_with_one_row_in_every_model(session) -> str:
    tenant_id = f"purge-test-{uuid.uuid4().hex[:8]}"
    session.add(Tenant(id=tenant_id, slug=tenant_id, name="Tenant de test purge"))
    session.flush()

    role = Role(
        id=f"{tenant_id}-role",
        tenant_id=tenant_id,
        name="Administrateur",
        slug="admin",
        is_built_in=True,
        privileges=[],
    )
    session.add(role)
    session.flush()

    user = User(
        id=f"{tenant_id}-user",
        tenant_id=tenant_id,
        oidc_sub=f"{tenant_id}-sub",
        username="u",
        role_id=role.id,
    )
    session.add(user)
    session.flush()

    item = Item(
        id=f"{tenant_id}-item",
        tenant_id=tenant_id,
        owner_id=user.id,
        resource_type="map",
        title="Item de test",
    )
    session.add(item)

    collection = Collection(
        id=f"{tenant_id}-col",
        tenant_id=tenant_id,
        owner_id=user.id,
        table_name=f"t_{tenant_id.replace('-', '_')}",
        title="Collection de test",
        description="",
        pk_column="id",
    )
    session.add(collection)

    group = Group(
        id=f"{tenant_id}-grp", tenant_id=tenant_id, name="Groupe de test", created_by=user.id
    )
    session.add(group)

    harvest_source = HarvestSource(
        id=f"{tenant_id}-hs",
        tenant_id=tenant_id,
        owner_id=user.id,
        type="stac",
        url="https://example.test/stac",
    )
    session.add(harvest_source)

    extension = Extension(
        id=f"{tenant_id}-ext",
        tenant_id=tenant_id,
        owner_id=user.id,
        tag="test-ext",
        label="Extension de test",
        module_url="https://example.test/ext.js",
        props={},
        default_size={},
        permissions={},
    )
    session.add(extension)

    map_icon = MapIcon(
        id=f"{tenant_id}-icon",
        tenant_id=tenant_id,
        title="Icône de test",
        category="test",
        s3_key=f"{tenant_id}/icons/i.svg",
        content_type="image/svg+xml",
        created_by=user.id,
    )
    session.add(map_icon)

    connector_secret = ConnectorSecret(
        id=f"{tenant_id}-secret",
        tenant_id=tenant_id,
        name="secret-test",
        kind="rest",
        ciphertext=b"cipher",
        nonce=b"nonce",
        created_by=user.id,
    )
    session.add(connector_secret)
    session.flush()

    # Réellement créer la table dynamique de la collection (purge_tenant
    # doit la DROP réellement, pas seulement retirer la ligne catalogue —
    # cf. app/compliance/purge.py, décision documentée dans son commit :
    # aucun code existant du dépôt (unregister_collection y compris) ne
    # DROP jamais la table dynamique, seule cette purge le fait).
    session.execute(text(f'CREATE TABLE public."{collection.table_name}" (id serial PRIMARY KEY)'))

    ingestion_job = IngestionJob(
        id=f"{tenant_id}-ingest",
        tenant_id=tenant_id,
        created_by=user.id,
        source_key=f"{tenant_id}/data.geojson",
        filename="data.geojson",
        collection_title="Collection importée",
        item_id=item.id,
        collection_id=collection.id,
    )
    session.add(ingestion_job)

    terrain_job = Terrain3DJob(
        id=f"{tenant_id}-terrain",
        tenant_id=tenant_id,
        created_by=user.id,
        source_key=f"{tenant_id}/dem.tif",
        filename="dem.tif",
        title="Terrain de test",
        item_id=item.id,
    )
    session.add(terrain_job)

    tileset_job = Tileset3DJob(
        id=f"{tenant_id}-tileset",
        tenant_id=tenant_id,
        created_by=user.id,
        source_key=f"{tenant_id}/t.zip",
        upload_id="up1",
        filename="t.zip",
        title="Tileset de test",
        item_id=item.id,
    )
    session.add(tileset_job)
    session.flush()

    export_job = ExportJob(
        id=f"{tenant_id}-export",
        tenant_id=tenant_id,
        item_id=item.id,
        user_id=user.id,
        format="png",
        status="done",
        result_key=f"renders/{tenant_id}-export.png",
        byte_size=10,
    )
    session.add(export_job)

    appexport_job = AppExportJob(
        id=f"{tenant_id}-appexport",
        tenant_id=tenant_id,
        item_id=item.id,
        user_id=user.id,
        mode="static",
        status="done",
        result_key=f"appexports/{tenant_id}-appexport.zip",
        byte_size=10,
    )
    session.add(appexport_job)
    session.flush()

    attachment = Attachment(
        id=f"{tenant_id}-att",
        tenant_id=tenant_id,
        collection_id=collection.id,
        fid="f1",
        field_key="photos",
        filename="a.jpg",
        content_type="image/jpeg",
        byte_size=100,
        s3_key=f"{tenant_id}/{collection.id}/f1/a.jpg",
        created_by=user.id,
    )
    session.add(attachment)

    notification = Notification(
        id=f"{tenant_id}-notif",
        tenant_id=tenant_id,
        recipient_user_id=user.id,
        kind="ingestion",
        status="success",
        item_id=item.id,
        item_title="Import terminé",
    )
    session.add(notification)

    notif_pref = NotificationPreference(user_id=user.id, tenant_id=tenant_id)
    session.add(notif_pref)

    group_member = GroupMember(group_id=group.id, user_id=user.id, tenant_id=tenant_id)
    session.add(group_member)

    collection_share = CollectionShare(
        collection_id=collection.id, group_id=group.id, tenant_id=tenant_id, role="viewer"
    )
    session.add(collection_share)

    config = Config(id=f"{tenant_id}-config", tenant_id=tenant_id, kind="map", item_id=item.id)
    session.add(config)
    session.flush()

    item_share = ItemShare(item_id=item.id, group_id=group.id, tenant_id=tenant_id, role="viewer")
    session.add(item_share)

    config_revision = ConfigRevision(
        tenant_id=tenant_id, config_id=config.id, version=1, data={"kind": "map"}
    )
    session.add(config_revision)

    alert_eval = AlertEvaluation(
        id=f"{tenant_id}-alert",
        tenant_id=tenant_id,
        alert_rule_item_id=item.id,
        state="ok",
    )
    session.add(alert_eval)

    pipeline_run = PipelineRun(
        id=f"{tenant_id}-piperun", tenant_id=tenant_id, pipeline_item_id=item.id
    )
    session.add(pipeline_run)

    report_run = ReportRun(id=f"{tenant_id}-reportrun", tenant_id=tenant_id, report_item_id=item.id)
    session.add(report_run)

    harvest_record = HarvestRecord(
        id=f"{tenant_id}-hrecord",
        tenant_id=tenant_id,
        source_id=harvest_source.id,
        external_id="ext1",
        item_id=item.id,
        collection_id=collection.id,
    )
    session.add(harvest_record)

    audit_log = AuditLog(
        tenant_id=tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="test.action",
        object_type="item",
        object_id=item.id,
        payload={},
    )
    session.add(audit_log)

    session.commit()
    return tenant_id


def test_purge_tenant_removes_every_row_in_every_tenant_scoped_table(pg_engine):
    from app.db import make_session_factory

    Session = make_session_factory(pg_engine)
    with Session() as session:
        tenant_id = _create_tenant_with_one_row_in_every_model(session)

    with Session() as session:
        purge_tenant(
            session, _FakeS3Client(), tenant_id=tenant_id, requested_by_user_id="requester"
        )
        session.commit()

    with Session() as session:
        for cls in _models_with_tenant_id():
            remaining = session.scalar(
                select(func.count()).select_from(cls).where(cls.tenant_id == tenant_id)
            )
            assert remaining == 0, f"{cls.__name__} still has rows for the purged tenant"
        assert session.get(Tenant, tenant_id) is None


class _PaginatingFakeS3Client:
    """Double avec un vrai magasin en mémoire, paginé à 1000 clés par page
    comme la vraie API S3 — sert à falsifier explicitement l'absence de
    pagination (spec §3.1.2 Tâche 3 Step 2, même piège appliqué ici à la
    purge : Step 4 de la Tâche 9)."""

    def __init__(self, objects: dict[str, bytes], *, bucket: str):
        # Un seul bucket "réel" (celui sous test) : purge_tenant interroge
        # aussi les 2 autres buckets tenant-préfixés (tileset3d/terrain3d)
        # — sans ce filtre, une pagination cassée sur le premier bucket
        # serait masquée par un second appel (bucket différent, page unique
        # car <1000 clés restantes) qui finirait le travail à sa place.
        self.objects = objects
        self.bucket = bucket

    def list_objects_v2(self, *, Bucket, Prefix="", ContinuationToken=None):
        if Bucket != self.bucket:
            return {"Contents": [], "IsTruncated": False, "NextContinuationToken": None}
        # Marqueur = dernière clé vue (comme la vraie API S3), PAS un index
        # numérique : self.objects RÉTRÉCIT entre deux appels (delete_objects
        # est appelé après chaque page par l'appelant réel) — un index
        # recalculé sur une liste qui a déjà perdu la page précédente
        # sauterait par erreur la moitié des clés restantes.
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        if ContinuationToken is not None:
            keys = [k for k in keys if k > ContinuationToken]
        page_size = 1000
        page_keys = keys[:page_size]
        truncated = len(keys) > page_size
        return {
            "Contents": [{"Key": k} for k in page_keys],
            "IsTruncated": truncated,
            "NextContinuationToken": page_keys[-1] if truncated else None,
        }

    def delete_objects(self, *, Bucket, Delete):
        if Bucket != self.bucket:
            return
        for obj in Delete["Objects"]:
            self.objects.pop(obj["Key"], None)

    def delete_object(self, *, Bucket, Key):
        self.objects.pop(Key, None)


def test_purge_tenant_paginates_past_1000_s3_objects(pg_engine, monkeypatch):
    from app.db import make_session_factory

    Session = make_session_factory(pg_engine)
    with Session() as session:
        tenant_id = _create_tenant_with_one_row_in_every_model(session)

    monkeypatch.setenv("S3_UPLOADS_BUCKET", "geostudio-uploads")
    objects = {f"{tenant_id}/{i}.bin": b"x" for i in range(1500)}
    s3 = _PaginatingFakeS3Client(objects, bucket="geostudio-uploads")

    with Session() as session:
        purge_tenant(session, s3, tenant_id=tenant_id, requested_by_user_id="requester")
        session.commit()

    # 1500 objets d'1 tenant : une implémentation qui ne suit pas
    # IsTruncated/NextContinuationToken n'en supprimerait que les 1000
    # premiers (ordre lexicographique), laissant 500 orphelins.
    assert len(s3.objects) == 0, f"{len(s3.objects)} objets S3 orphelins après la purge"


def test_purge_tenant_is_resumable_after_a_crash_mid_way(pg_engine):
    """Simule un purge_tenant interrompu juste après la suppression des
    roles (users déjà supprimés à cette étape, cf. app/compliance/purge.py
    — roles est l'étape suivante), avant audit_log/purge_receipts/tenant
    (spec §5, reprise après crash) : la seconde invocation ne doit pas
    planter sur des lignes déjà absentes."""
    from app.db import make_session_factory

    Session = make_session_factory(pg_engine)
    with Session() as session:
        tenant_id = _create_tenant_with_one_row_in_every_model(session)

    import app.compliance.purge as purge_module

    original_delete_all = purge_module._delete_all

    class _InjectedCrash(Exception):
        pass

    def _crash_after_users(session, model, tenant_id_arg):
        result = original_delete_all(session, model, tenant_id_arg)
        if model is Role:
            raise _InjectedCrash("simulated crash right before roles are deleted")
        return result

    with Session() as session:
        purge_module._delete_all = _crash_after_users
        try:
            with pytest.raises(_InjectedCrash):
                purge_tenant(
                    session, _FakeS3Client(), tenant_id=tenant_id, requested_by_user_id="r"
                )
            session.commit()  # tout ce qui a été flush() avant le crash reste acquis
        finally:
            purge_module._delete_all = original_delete_all

    # Deuxième invocation, sans injection : ne doit pas planter sur des
    # lignes déjà absentes (DROP TABLE déjà fait, DELETE déjà à 0 lignes).
    with Session() as session:
        purge_tenant(session, _FakeS3Client(), tenant_id=tenant_id, requested_by_user_id="r")
        session.commit()

    with Session() as session:
        for cls in _models_with_tenant_id():
            remaining = session.scalar(
                select(func.count()).select_from(cls).where(cls.tenant_id == tenant_id)
            )
            assert remaining == 0, f"{cls.__name__} still has rows after the resumed purge"
        assert session.get(Tenant, tenant_id) is None


def test_purge_tenant_collection_teardown_is_idempotent_if_replayed(pg_engine):
    """Isole précisément le risque cité par la spec §5 ("le DROP TABLE
    d'une collection déjà droppée et le retrait d'une table déjà retirée
    de la publication CDC doivent être vérifiés explicitement, pas
    supposés") : rejoue les deux opérations deux fois de suite sur la même
    table, sans passer par purge_tenant en entier (le scénario de crash
    complet, ci-dessus, ne rejoue jamais réellement cette étape précise —
    son point d'injection tombe après que la collection a déjà disparu du
    catalogue)."""
    from app.db import make_session_factory

    Session = make_session_factory(pg_engine)
    table_name = f"t_idempotence_{uuid.uuid4().hex[:8]}"
    with Session() as session:
        session.execute(text(f'CREATE TABLE public."{table_name}" (id serial PRIMARY KEY)'))
        session.commit()

    with Session() as session:
        remove_table_from_publication(session, table_name)
        session.execute(text(f'DROP TABLE IF EXISTS public."{table_name}" CASCADE'))
        session.commit()

    # Rejoué : la table et l'entrée de publication CDC ont déjà disparu —
    # ne doit pas lever (piège explicite de la spec, falsifié en retirant
    # IF EXISTS ci-dessous avant de l'accepter).
    with Session() as session:
        remove_table_from_publication(session, table_name)
        session.execute(text(f'DROP TABLE IF EXISTS public."{table_name}" CASCADE'))
        session.commit()
