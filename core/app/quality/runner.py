# SPDX-License-Identifier: Apache-2.0
"""Évaluation d'un lot de règles CEL (`constraint` + `batch`) sur toutes les entités d'une
collection (ARC-14). Lecture par pages keyset sous `rls_scope` : mémoire O(page), masquage GAP-22 du
demandeur jamais contourné."""

import dataclasses
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.collections.introspection import TableInfo
from app.features import repository as features_repo
from app.features.cel_rules import RuleNotApplicable, evaluate
from app.features.rls import rls_scope

PAGE_SIZE = 1000
SAMPLE_MAX = 1000
CHECKED_KINDS = ("constraint", "batch")


class Cancelled(Exception):
    pass


def run_batch(
    session: Session,
    info: TableInfo,
    *,
    tenant_id: str,
    masked: bool,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[int, dict, list]:
    """(entités contrôlées, résumé par règle, échantillon de violations). `info` porte les
    règles (`with_attribute_rules`) ; les entités ne sont jamais modifiées."""
    rules = [r for r in info.rules if r["kind"] in CHECKED_KINDS]
    summary = {
        r["id"]: {"message": r["message"], "kind": r["kind"], "violations": 0, "errors": 0}
        for r in rules
    }
    sample: list[dict] = []
    checked = 0
    if not rules:
        return 0, summary, sample
    # Les règles ne lisent que les attributs : pas de géométrie à décoder (la route refuse
    # d'ailleurs les lecteurs sous limite géographique, GAP-27).
    read_info = dataclasses.replace(info, geometry_column=None, geometry_type=None)
    cursor = None
    while True:
        with rls_scope(session, tenant_id, masked=masked, geo_limits={}):
            page = features_repo.select_features(
                session, read_info, limit=PAGE_SIZE, offset=0, after=cursor, count_mode="none"
            )
        for feature in page.features:
            props = feature["properties"]
            for rule in rules:
                try:
                    ok = evaluate(info, rule["expression"], props)
                except RuleNotApplicable:
                    summary[rule["id"]]["errors"] += 1
                    continue
                if ok is False:
                    summary[rule["id"]]["violations"] += 1
                    if len(sample) < SAMPLE_MAX:
                        sample.append(
                            {
                                "fid": feature["id"],
                                "ruleId": rule["id"],
                                "field": rule.get("field") or "",
                                "message": rule["message"],
                            }
                        )
        checked += len(page.features)
        cursor = page.next_cursor
        if cursor is None:
            return checked, summary, sample
        if should_cancel is not None and should_cancel():
            raise Cancelled
