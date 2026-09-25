# SPDX-License-Identifier: Apache-2.0
"""delete_secret (SP-A6, D05 — MCP) : jumelle MCP de DELETE /secrets/{id}
(app/secrets/routes.py). Garde strictement identique — REV-009, piège
CLAUDE.md n°4 : ne jamais rouvrir côté MCP un trou fermé côté REST."""

from app.roles.repository import ensure_built_in_roles
from app.secrets import repository as secrets_repo
from app.users.repository import set_user_role
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool_expecting_error,
    call_tool_raw,
)


def _demote_to_reader(app_client):  # noqa: F811
    """Rétrograde app_client.mock_user (Créateur par défaut, cf.
    get_or_create_user) vers le rôle prédéfini Lecteur (0 privilège) — même
    idiome que test_mcp_configs_privilege_guard.py::_demote_to_reader."""
    with app_client.session_factory() as session:
        roles = ensure_built_in_roles(session, tenant_id=app_client.tenant.id)
        assert roles["reader"].privileges == []
        set_user_role(
            session,
            tenant_id=app_client.tenant.id,
            user_id=app_client.mock_user.id,
            role_id=roles["reader"].id,
            role_slug="reader",
        )
        session.commit()


def test_delete_secret_removes_it_and_writes_audit(app_client):  # noqa: F811
    with app_client.session_factory() as session:
        secret = secrets_repo.create_secret(
            session,
            tenant_id=app_client.tenant.id,
            created_by=app_client.mock_user.id,
            name="api-key",
            kind="generic",
            ciphertext=b"x",
            nonce=b"y",
        )
        session.commit()
        secret_id = secret.id

    with app_client:
        # call_tool (importée depuis test_mcp_tools_create) suppose un
        # content non vide (json.loads(result["content"][0]["text"])) — ne
        # convient pas à un tool annoté `-> None` (content list vide, comme
        # noté par test_mcp_tools_sharing.py pour set_sharing). call_tool_raw
        # évite ce piège en laissant le test vérifier isError lui-même.
        result = call_tool_raw(app_client, "delete_secret", {"secret_id": secret_id})
    assert not result.get("isError"), result

    with app_client.session_factory() as session:
        assert (
            secrets_repo.get_secret(session, tenant_id=app_client.tenant.id, secret_id=secret_id)
            is None
        )
        from sqlalchemy import select

        from app.audit.models import AuditLog

        rows = session.scalars(select(AuditLog).where(AuditLog.action == "secret.delete")).all()
        assert len(rows) == 1
        assert rows[0].actor_kind == "agent"
        assert rows[0].object_id == secret_id


def test_delete_secret_of_unknown_id_errors(app_client):  # noqa: F811
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "delete_secret", {"secret_id": "does-not-exist"}
        )
    assert "not found" in error_text.lower()


def test_delete_secret_requires_the_same_privilege_as_the_rest_route(app_client):  # noqa: F811
    # REV-009 : jumelle MCP de DELETE /secrets/{id} — la garde
    # ADMIN_SECRETS_MANAGE/AUTOMATION_SECRETS_MANAGE posée sur la route REST
    # doit exister aussi ici, sinon delete_secret (MCP) rouvre exactement le
    # trou fermé côté REST (piège CLAUDE.md n°4).
    with app_client.session_factory() as session:
        secret = secrets_repo.create_secret(
            session,
            tenant_id=app_client.tenant.id,
            created_by=app_client.mock_user.id,
            name="api-key-2",
            kind="generic",
            ciphertext=b"x",
            nonce=b"y",
        )
        session.commit()
        secret_id = secret.id

    _demote_to_reader(app_client)

    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "delete_secret", {"secret_id": secret_id}
        )
    assert "privilege" in error_text.lower()

    with app_client.session_factory() as session:
        assert (
            secrets_repo.get_secret(session, tenant_id=app_client.tenant.id, secret_id=secret_id)
            is not None
        )


def test_delete_secret_refuses_in_read_only_mode(app_client, monkeypatch):  # noqa: F811
    with app_client.session_factory() as session:
        secret = secrets_repo.create_secret(
            session,
            tenant_id=app_client.tenant.id,
            created_by=app_client.mock_user.id,
            name="api-key-3",
            kind="generic",
            ciphertext=b"x",
            nonce=b"y",
        )
        session.commit()
        secret_id = secret.id

    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "delete_secret", {"secret_id": secret_id}
        )
    assert "Mode démo : lecture seule, écritures désactivées." in error_text
