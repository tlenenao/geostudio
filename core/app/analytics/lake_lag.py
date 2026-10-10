# SPDX-License-Identifier: Apache-2.0
"""REV-280f : retard du lac en octets de WAL, mesuré côté lecture par LSN
(`pg_current_wal_lsn` - `confirmed_flush_lsn` du slot CDC). Complète `asOf`
(fraîcheur en temps), qui reste la mesure de référence."""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CDC_SLOT = (
    "geostudio_cdc_slot"  # dupliqué à dessein comme app/instance/routes.py (= consumer.SLOT_NAME)
)


def lake_lag_bytes(session: Session) -> int | None:
    """Octets de WAL pas encore confirmés par le worker CDC ; None sans slot
    ou si la mesure est impossible (droits, base sans WAL logique)."""
    try:
        row = session.execute(
            text(
                "SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)::bigint "
                "FROM pg_replication_slots WHERE slot_name = :n"
            ),
            {"n": _CDC_SLOT},
        ).first()
    except Exception as exc:
        logger.warning("lag du lac: mesure LSN impossible (%s)", type(exc).__name__)
        session.rollback()
        return None
    return None if row is None or row[0] is None else max(0, int(row[0]))
