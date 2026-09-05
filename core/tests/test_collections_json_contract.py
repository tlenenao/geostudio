"""Contrat de sérialisation de _collection_json — SP-43 Étape 3. Sert
d'oracle pour shell/e2e/mocks.ts::mockCollection() : si une clé est ajoutée
ou retirée ici sans mise à jour miroir côté fixture E2E, ce test continue de
passer (il ne connaît pas le TS) mais documente la liste exacte à tenir à
jour manuellement des deux côtés — cf. commentaire miroir dans mocks.ts."""

from app.collections.models import Collection
from app.collections.routes import _collection_json
from app.items.schemas import ItemPermissions

EXPECTED_KEYS = {
    "id",
    "title",
    "description",
    "tableName",
    "isPublic",
    "editable",
    "geometryType",
    "srid",
    "pkColumn",
    "permissions",
    "featureCount",
    "owner",
    "attachmentFields",
    "license",
    "licenseUri",
    "producer",
    "contact",
    "updateFrequency",
    "lineage",
    "language",
    "version",
    "temporalStart",
    "temporalEnd",
}


def test_collection_json_serializes_exactly_the_documented_23_keys() -> None:
    col = Collection(
        id="c1",
        title="T",
        description="",
        table_name="t1",
        is_public=False,
        editable=True,
        geometry_type="Point",
        srid=4326,
        pk_column="id",
        feature_count=0,
        attachment_fields=[],
        license="",
        license_uri="",
        producer="",
        contact="",
        update_frequency="",
        lineage="",
        language="",
        version="",
        temporal_start=None,
        temporal_end=None,
    )
    permissions = ItemPermissions(read=True, write=True, delete=False, share=True)

    result = _collection_json(col, permissions, owner="mockuser")

    assert set(result.keys()) == EXPECTED_KEYS
    assert len(EXPECTED_KEYS) == 23
