# SPDX-License-Identifier: Apache-2.0
"""SP-42/F-coeur-contenu-04 : DELETE /items/{id} (ou /configs/by-item/{id})
sur un Dataset encore référencé par une AlertRule (alert.datasetItemId)
laissait cette AlertRule orpheline silencieusement (204, aucun signal).
Patron de fixture copié de test_alert_routes.py::_setup (mêmes contraintes :
CORE_AUTH_MODE=mock résout toujours oidc_sub="mock-sub", donc l'utilisateur
propriétaire des items créés directement via le repository doit avoir cet
oidc_sub exact pour que app.sharing.authorization.can autorise les requêtes
HTTP réelles)."""

from fastapi.testclient import TestClient

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _setup(monkeypatch, tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'configs_delete_reverse_refs.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        dataset_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="dataset",
            title="Dataset",
        )
        dataset_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "col1"},
            }
        )
        configs_repo.create_config(s, dataset_config, item_id=dataset_item.id, tenant_id=tenant.id)
        rule_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="alert",
            title="High counts",
        )
        alert_config = BuilderConfig.model_validate(
            {
                "kind": "alert",
                "alert": {
                    "datasetItemId": dataset_item.id,
                    "query": {"agg": "count"},
                    "condition": {"expr": "value > 100"},
                    "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                    "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                },
            }
        )
        configs_repo.create_config(s, alert_config, item_id=rule_item.id, tenant_id=tenant.id)
        s.commit()
        dataset_item_id, rule_item_id = dataset_item.id, rule_item.id
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client, dataset_item_id, rule_item_id


def test_delete_item_refuses_when_an_alert_rule_still_references_it(monkeypatch, tmp_path):
    client, dataset_item_id, rule_item_id = _setup(monkeypatch, tmp_path)

    response = client.delete(f"/items/{dataset_item_id}")

    assert response.status_code == 409
    assert "alert" in response.json()["detail"]
    # ni le Dataset ni sa config n'ont été supprimés (refus, pas suppression
    # partielle) :
    assert client.get(f"/items/{dataset_item_id}").status_code == 200
    assert client.get(f"/configs/by-item/{dataset_item_id}").status_code == 200
    # l'AlertRule référençant toujours ce Dataset n'a pas été altérée :
    still_referenced = client.get(f"/configs/by-item/{rule_item_id}").json()
    assert still_referenced["config"]["alert"]["datasetItemId"] == dataset_item_id


def test_delete_config_by_item_refuses_when_an_alert_rule_still_references_it(
    monkeypatch, tmp_path
):
    client, dataset_item_id, _rule_item_id = _setup(monkeypatch, tmp_path)

    response = client.delete(f"/configs/by-item/{dataset_item_id}")

    assert response.status_code == 409
    assert client.get(f"/items/{dataset_item_id}").status_code == 200


def test_delete_item_succeeds_once_the_referencing_alert_rule_is_gone(monkeypatch, tmp_path):
    # Contre-épreuve : une fois la seule référence levée, la suppression du
    # Dataset redevient possible (pas un verrou permanent).
    client, dataset_item_id, rule_item_id = _setup(monkeypatch, tmp_path)
    assert client.delete(f"/items/{rule_item_id}").status_code == 204

    response = client.delete(f"/items/{dataset_item_id}")
    assert response.status_code == 204
