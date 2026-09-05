# SPDX-License-Identifier: Apache-2.0
"""Support de job partagé — session, résolution du propriétaire, notification
best-effort. Remplace 5-6 copies quasi identiques (`_session_factory()`/
`_owner_user()`/`_acting_user()`/`_notify()` dans reports/pipelines/ingestion/
appexport/export/alerts jobs.py) qui ont produit 2 UnboundLocalError réels
(SP-39, `app.ingestion.tasks`/`app.pipelines.jobs`) : une variable référencée
par l'appel de notification de la branche d'échec n'était pas garantie liée si
l'échec survenait avant son affectation normale.

`notify_best_effort` isole la SEULE partie strictement commune aux 5-6
sites : ouvrir une session dédiée, écrire la notification, committer, avaler
toute exception. Elle NE résout PAS le destinataire ni le titre/type de
l'item — la recherche préalable à cette extraction (SP-43 Tâche 6) a trouvé
4 formes de résolution différentes selon le domaine (owner résolu par
tenant_id+item_id ; owner explicite sous un autre nom de fonction ;
created_by déjà connu de l'appelant ; user_id déjà résolu par l'appelant) —
cette résolution reste donc dans le `_notify()` propre à chaque domaine, qui
délègue ensuite l'écriture proprement dite à cette fonction. L'isolation
try/except (notification best-effort strictement séparée du commit du statut
du job) est un invariant à préserver dans tout appelant — ne jamais fusionner
les deux blocs (cf. falsifications dédiées, SP-43 Tâche 6 Step 13)."""

import logging
import os
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
from app.notifications import repository as notifications_repo
from app.users.models import User

logger = logging.getLogger(__name__)

SessionFactory = sessionmaker[Session]


def session_factory() -> SessionFactory:
    """Identique aux 5 `_session_factory()` d'origine (reports/pipelines/
    appexport/export/alerts jobs.py) : engine + session factory depuis
    `DATABASE_URL`, repli SQLite mémoire pour ne jamais casser la collecte
    pytest sur un process qui n'a jamais défini cette variable."""
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def resolve_owner_user(session: Session, *, tenant_id: str, item_id: str) -> User:
    """Identique au corps des 3 `_owner_user()`/`_acting_user()` d'origine
    (reports/pipelines/alerts jobs.py). Lève `LookupError` (générique) si
    l'item n'existe pas pour ce tenant — chaque appelant garde son propre
    type d'exception métier (ReportTriggerError/ValueError/
    AlertEvaluationError) via un thin wrapper local qui capture ce
    `LookupError` et le re-lève sous sa forme domaine, pour ne changer aucun
    comportement observable des appelants existants."""
    owner_id = session.execute(
        select(Item.owner_id).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if owner_id is None:
        raise LookupError(f"item '{item_id}' not found")
    user = session.get(User, owner_id)
    assert user is not None
    return user


def notify_best_effort(
    session_factory_fn: Callable[[], Session] | SessionFactory,
    *,
    tenant_id: str,
    recipient_user_id: str,
    kind: str,
    status: str,
    item_id: str | None,
    item_resource_type: str | None,
    item_title: str,
    error: str | None = None,
) -> None:
    """Best-effort : toute exception ici est avalée, jamais propagée — même
    garantie que les 5-6 `_notify()` d'origine. Le destinataire ET le
    titre/type de l'item doivent déjà être résolus par l'appelant (cf.
    docstring de module) ; cette fonction ne fait qu'ouvrir sa PROPRE session
    (isolée de celle de l'appelant, revue finale SP-39 I1 : un DBAPIError
    dans `create_notification` ne doit jamais empoisonner la transaction de
    l'appelant), écrire la notification, committer, et avaler toute
    exception plutôt que de la laisser remonter."""
    try:
        with request_scoped_session(session_factory_fn) as session:
            notifications_repo.create_notification(
                session,
                tenant_id=tenant_id,
                recipient_user_id=recipient_user_id,
                kind=kind,
                status=status,
                item_id=item_id,
                item_resource_type=item_resource_type,
                item_title=item_title,
                error_message=error,
            )
    except Exception:  # noqa: BLE001 — best-effort explicite, jamais remonté
        logger.exception(
            "notification %s (item %s, destinataire %s) : échec de l'écriture",
            kind,
            item_id,
            recipient_user_id,
        )
