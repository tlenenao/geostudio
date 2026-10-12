# SPDX-License-Identifier: Apache-2.0
"""Routes du widget « Analyse » (ARC-25) — montées sans flag (ni CORE_ETL_ENABLED : aucune op n'est
planifiée, tout est synchrone et borné), derrière l'authentification. Lecture = mêmes portes que
`POST /collections/{id}/aggregate` (`get_collection_for_read`, refus des limites géographiques,
champs masqués)."""

import os
from collections.abc import Callable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.collections.introspection import Introspector
from app.collections.routes import get_collection_for_read, get_ddl_applier, get_introspector
from app.collections.sensitive import masked_fields_for
from app.configs.geo_limits_dep import get_request_geo_limits
from app.db import get_session
from app.errors import ValidationHTTPException
from app.features.routes import get_analytics_base_uri
from app.pipelines.analysis import (
    AnalysisError,
    AnalysisRequest,
    run_analysis,
    tool_catalog,
)
from app.pipelines.runtime import PipelineRuntimeError
from app.sharing.geo_limits import refuse_if_geo_limited
from app.users.models import User

router = APIRouter()


def _error(field: str, code: str, message: str) -> ValidationHTTPException:
    return ValidationHTTPException(
        errors=[{"field": field, "code": code, "message": message}], status_code=422
    )


@router.get("/analysis/tools")
def list_analysis_tools(user: User = Depends(get_current_user)) -> dict:
    return {"tools": tool_catalog()}


@router.post("/collections/{collection_id}/analysis")
def run_collection_analysis(
    collection_id: str,
    body: AnalysisRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect: Introspector = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
    base_uri: str = Depends(get_analytics_base_uri),
    geo_limits=Depends(get_request_geo_limits),
) -> dict:
    source = get_collection_for_read(session, user, collection_id)
    other = (
        get_collection_for_read(session, user, body.otherCollectionId)
        if body.otherCollectionId
        else None
    )
    # GAP-27 : le lac DuckDB n'est pas soumis à la RLS — refus fail-closed, comme /aggregate.
    for col in (source, other):
        if col is not None:
            refuse_if_geo_limited(geo_limits, col.table_name, path="analysis")
    try:
        return run_analysis(
            session,
            user=user,
            source=source,
            other=other,
            req=body,
            introspect=introspect,
            masked_source=masked_fields_for(session, user, source),
            masked_other=masked_fields_for(session, user, other) if other else frozenset(),
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            access_key=os.environ["S3_ACCESS_KEY"],
            secret_key=os.environ["S3_SECRET_KEY"],
            base_uri=base_uri,
            apply_ddl=apply_ddl,
        )
    except AnalysisError as exc:
        raise _error("analysis", "invalid_analysis", str(exc)) from exc
    except PipelineRuntimeError as exc:
        raise _error("analysis", "analysis_failed", str(exc)) from exc
