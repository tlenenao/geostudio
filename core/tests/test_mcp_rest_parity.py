# SPDX-License-Identifier: Apache-2.0
"""Parité outil MCP <-> route REST équivalente — SP-43 Étape 8, oracle de
régression pour tout le découpage de mcp/tools.py en tools/<domaine>.py +
couches de service partagées (items/service.py, configs/service.py,
pipelines/service.py). Sert aussi à documenter les écarts de comportement
déjà existants avant refactor (cf. spec §6 : un écart trouvé ne doit jamais
être "corrigé" silencieusement pendant ce découpage — seulement documenté).

Écrit et exécuté AVANT tout déplacement de code (Step 1/2 du plan) : les
fixtures/helpers réutilisés ici (`app_client`, `call_tool`,
`call_tool_expecting_error`) sont ceux déjà en usage dans les 24
`test_mcp_*.py` existants (tests/test_mcp_tools_create.py,
tests/test_mcp_tools_pipeline.py) — il n'existe pas de fixture nommée
`mcp_client`/`http_client`/`seeded_item`/`seeded_pipeline` dans ce dépôt (la
spec source en inventait les noms) ; un seul TestClient FastAPI sait déjà
parler les deux protocoles (REST directement, MCP via le handshake
JSON-RPC encapsulé par `call_tool`)."""

from tests.test_mcp_tools_create import app_client, call_tool  # noqa: F401,F811
from tests.test_mcp_tools_pipeline import _linear_pipeline_args, _register_collections
from tests.test_mcp_tools_pipeline import app_client as pipeline_app_client  # noqa: F401,F811


def test_get_item_tool_matches_get_item_route(app_client):  # noqa: F811
    from app.items import repository as items_repo

    with app_client.session_factory() as session:
        item = items_repo.create_item(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            resource_type="app",
            title="Parity item",
        )
        session.commit()
        item_id = item.id

    rest_result = app_client.get(
        f"/items/{item_id}", headers={"Authorization": "Bearer anything"}
    ).json()
    with app_client:
        tool_result = call_tool(app_client, "get_item", {"itemId": item_id})

    assert tool_result["pk"] == rest_result["pk"]
    assert tool_result["title"] == rest_result["title"]
    assert tool_result["permissions"] == rest_result["permissions"]
    # Écart pré-existant, non corrigé par SP-43 (déjà documenté par le
    # docstring de _without_thumbnail_url dans app/mcp/tools.py avant ce
    # refactor, cf. SP-42 F-coeur-federation-08) : thumbnailUrl diffère
    # volontairement entre les deux surfaces — un jeton MCP (CORE_MCP_AUDIENCE)
    # ne peut jamais authentifier GET /items/{id}/thumbnail (CORE_OIDC_AUDIENCE),
    # donc le tool MCP omet ce champ (None) même quand la route REST le
    # renseigne. Volontairement non comparé ici.


def test_get_sharing_tool_matches_get_sharing_route(app_client):  # noqa: F811
    from app.items import repository as items_repo

    with app_client.session_factory() as session:
        item = items_repo.create_item(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            resource_type="app",
            title="Parity item sharing",
        )
        session.commit()
        item_id = item.id

    rest_result = app_client.get(
        f"/items/{item_id}/sharing", headers={"Authorization": "Bearer anything"}
    ).json()
    with app_client:
        tool_result = call_tool(app_client, "get_sharing", {"itemId": item_id})

    assert tool_result == rest_result


def test_run_pipeline_tool_matches_run_pipeline_route_except_actor_kind(
    pipeline_app_client,  # noqa: F811
    monkeypatch,
):
    """Écart connu et attendu, présent dans app/mcp/tools.py bien avant
    SP-43 : actor_kind="agent" (tool MCP run_pipeline) vs actor_kind="user"
    (route REST POST /pipelines/{id}/run) sur la ligne d'audit
    "pipeline.run" — documenté ici explicitement, ne jamais l'unifier sans
    décision produit explicite (design volontaire : distinguer un run
    déclenché par un agent MCP d'un run déclenché par un humain dans le
    builder)."""
    from sqlalchemy import select

    from app.audit.models import AuditLog
    from app.collections import repository as collections_repo
    from app.pipelines.jobs import run_pipeline_task

    # run_pipeline_task.defer() needs a procrastinate app opened against a
    # real Postgres connection — out of scope here (this test only cares
    # about the audit row written before the job is deferred, on both
    # surfaces). No-op it exactly like tests/test_pipeline_routes.py does
    # via its get_task_deferrer override, but from the task side since the
    # MCP tool calls run_pipeline_task.defer directly (no DI to override).
    monkeypatch.setattr(run_pipeline_task, "defer", lambda **kwargs: None)

    # Un seul client (une seule base sqlite sous-jacente, cf. app_client
    # ci-dessus) : appeler pipeline_app_client(...) deux fois pointerait les
    # deux "clients" vers le même fichier sqlite (même tmp_path), et
    # _register_collections sème toujours les mêmes noms de table
    # ("villes"/"villes_propres") -> collision UNIQUE si réutilisé tel quel.
    client = pipeline_app_client(etl_enabled=True)

    with client:
        source_id, target_id = _register_collections(client)
        created = call_tool(client, "create_pipeline", _linear_pipeline_args(source_id, target_id))
        tool_run = call_tool(client, "run_pipeline", {"pipelineId": created["pk"]})
    assert "runId" in tool_run

    with client.session_factory() as session:
        source2 = collections_repo.create_collection(
            session,
            tenant_id=client.tenant.id,
            owner_id=client.mock_user.id,
            table_name="villes_rest",
            title="Villes REST",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        target2 = collections_repo.create_collection(
            session,
            tenant_id=client.tenant.id,
            owner_id=client.mock_user.id,
            table_name="villes_propres_rest",
            title="Villes propres REST",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        session.commit()
        source2_id, target2_id = source2.id, target2.id

    pipeline_args = _linear_pipeline_args(source2_id, target2_id)
    rest_created = client.post(
        "/configs",
        json={
            "title": "Pipeline REST",
            "config": {
                "version": 1,
                "kind": "pipeline",
                "pipeline": {
                    "nodes": pipeline_args["nodes"],
                    "edges": pipeline_args["edges"],
                },
            },
        },
        headers={"Authorization": "Bearer anything"},
    )
    assert rest_created.status_code == 201
    pipeline_item_id = rest_created.json()["itemId"]
    rest_run = client.post(
        f"/pipelines/{pipeline_item_id}/run",
        headers={"Authorization": "Bearer anything"},
    )
    assert rest_run.status_code == 202
    assert "runId" in rest_run.json()

    with client.session_factory() as session:
        entries = session.scalars(
            select(AuditLog).where(
                AuditLog.tenant_id == client.tenant.id, AuditLog.action == "pipeline.run"
            )
        ).all()

    assert any(e.actor_kind == "agent" for e in entries)
    assert any(e.actor_kind == "user" for e in entries)


def test_run_alert_rule_tool_matches_sweep_alert_rules_task_effect_for_one_rule(
    app_client,  # noqa: F811
    monkeypatch,
):
    """run_alert_rule (GAP-48, SP-53) n'a aucune route REST "exécuter
    maintenant" jumelle (une alerte s'évalue normalement par balayage
    périodique, app/alerts/jobs.py::sweep_alert_rules_task) — la parité
    comparée ici est donc l'effet observable du tool MCP sur une seule
    règle contre l'effet du balayage restreint à cette même règle
    (list_due_rules mocké pour ne renvoyer qu'elle), pas deux surfaces
    REST/MCP d'une même route."""
    from sqlalchemy import select

    from app.alerts import jobs as alerts_jobs
    from app.alerts import repository as alerts_repo
    from app.alerts.models import AlertEvaluation
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig
    from app.items import repository as items_repo

    with app_client.session_factory() as session:
        dataset_item = items_repo.create_item(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            resource_type="dataset",
            title="Dataset",
        )
        dataset_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "incidents", "columns": {}},
            }
        )
        configs_repo.create_config(
            session, dataset_config, item_id=dataset_item.id, tenant_id=app_client.tenant.id
        )
        session.commit()
        dataset_item_id = dataset_item.id

    # Un seul "with app_client:" pour les deux appels MCP : le
    # StreamableHTTPSessionManager sous-jacent ne supporte qu'un cycle
    # démarrage/arrêt par instance (RuntimeError sur un 2e "with" séparé,
    # constaté en écrivant ce test — piège CLAUDE.md n°3, jamais mentionné
    # par la spec).
    deferred_via_tool: list[dict] = []
    monkeypatch.setattr(
        alerts_jobs.evaluate_alert_task, "defer", lambda **kw: deferred_via_tool.append(kw)
    )
    with app_client:
        created = call_tool(
            app_client,
            "create_alert_rule",
            {
                "title": "Parity rule",
                "datasetItemId": dataset_item_id,
                "query": {"agg": "count"},
                "condition": {"expr": "value > 10"},
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        )
        alert_item_id = created["pk"]

        tool_result = call_tool(app_client, "run_alert_rule", {"alertRuleId": alert_item_id})
    assert "evaluationId" in tool_result

    # --- Effet du balayage cron pour cette seule règle ---
    deferred_via_sweep = []
    monkeypatch.setattr(
        alerts_jobs.evaluate_alert_task, "defer", lambda **kw: deferred_via_sweep.append(kw)
    )
    monkeypatch.setattr(
        alerts_repo, "list_due_rules", lambda session: [(alert_item_id, app_client.tenant.id)]
    )
    alerts_jobs.sweep_alert_rules_task(timestamp=0)

    assert len(deferred_via_tool) == 1
    assert len(deferred_via_sweep) == 1
    assert deferred_via_tool[0]["tenant_id"] == deferred_via_sweep[0]["tenant_id"]

    with app_client.session_factory() as session:
        pending = session.scalars(
            select(AlertEvaluation).where(
                AlertEvaluation.tenant_id == app_client.tenant.id,
                AlertEvaluation.alert_rule_item_id == alert_item_id,
                AlertEvaluation.state == "pending",
            )
        ).all()
    # Une ligne pending par déclenchement (tool + balayage) : le même effet
    # observable des deux côtés, aucun raccourci parallèle.
    assert len(pending) == 2
