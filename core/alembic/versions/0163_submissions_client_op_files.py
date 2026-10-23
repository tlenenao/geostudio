# SPDX-License-Identifier: Apache-2.0
"""submissions.client_op_id + submission_files : soumission publique idempotente et multi-fichiers
(L8, AUD-071)

`client_op_id` : un rejeu de la même saisie (file hors-ligne) ne consomme pas de second slot.
`submission_files` : jusqu'à 5 fichiers par soumission ; l'ancienne colonne `attachment` est
conservée et lue (soumissions en attente avant la migration).

Revision ID: 0163
Revises: 0162
Create Date: 2026-10-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0163"
down_revision = "0162"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("client_op_id", sa.String(), nullable=True))
    op.create_index(
        "uq_submissions_token_client_op",
        "submissions",
        ["token_id", "client_op_id"],
        unique=True,
        postgresql_where=sa.text("client_op_id IS NOT NULL"),
        sqlite_where=sa.text("client_op_id IS NOT NULL"),
    )
    op.create_table(
        "submission_files",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "submission_id",
            sa.String(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_key", sa.String(), nullable=False),
        sa.Column("attachment", sa.JSON(), nullable=True),
        sa.Column("attachment_key", sa.String(), nullable=True),
    )
    op.create_index("ix_submission_files_submission", "submission_files", ["submission_id"])
    op.create_index("ix_submission_files_attachment_key", "submission_files", ["attachment_key"])


def downgrade() -> None:
    op.drop_index("ix_submission_files_attachment_key", table_name="submission_files")
    op.drop_index("ix_submission_files_submission", table_name="submission_files")
    op.drop_table("submission_files")
    op.drop_index("uq_submissions_token_client_op", table_name="submissions")
    op.drop_column("submissions", "client_op_id")
