# SPDX-License-Identifier: Apache-2.0
"""Porte unique du routage (ARC-34) : privilège `analytics.view`. REST, outils MCP et ops de
pipeline (worker) appellent TOUS `can_route` — un seul contrôle, pas trois."""

from sqlalchemy.orm import Session

from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.users.models import User


def can_route(session: Session, user: User | None) -> bool:
    return user is not None and has_privilege(session, user, Privilege.ANALYTICS_VIEW.value)
