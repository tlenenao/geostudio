# SPDX-License-Identifier: Apache-2.0
"""Compteurs du limiteur de débit partagé (ARC-32). Table d'infrastructure,
volontairement SANS tenant_id/audit_log (clé d'appelant hachée, jamais
d'entité métier ; écriture à chaque requête limitée — un audit_log y serait
absurde) : exception à la règle « tenant_id partout », assumée en ADR 0019."""

import sqlalchemy as sa

from app.db import Base

rate_limit_counters = sa.Table(
    "rate_limit_counters",
    Base.metadata,
    sa.Column("key_hash", sa.String(64), primary_key=True),
    sa.Column("grp", sa.String(), primary_key=True),
    sa.Column("window_start", sa.BigInteger(), primary_key=True),
    sa.Column("hits", sa.Integer(), nullable=False),
)
