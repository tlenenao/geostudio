# SPDX-License-Identifier: Apache-2.0
"""outbound_webhooks + outbox + file_triggers : webhooks sortants, déclencheurs (ARC4-F6, ADR 0027)

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-13

NB : écrite sur 0062 par la voie L, rebasée sur 0065 (voie K2) à l'intégration.
"""

import sqlalchemy as sa

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbound_webhooks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("secret_name", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disabled_reason", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_outbound_webhooks_tenant_id", "outbound_webhooks", ["tenant_id"])
    op.create_table(
        "outbox",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "webhook_id",
            sa.String(),
            sa.ForeignKey("outbound_webhooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_outbox_webhook_id", "outbox", ["webhook_id"])
    op.create_index("ix_outbox_due", "outbox", ["status", "next_attempt_at"])
    op.create_table(
        "file_triggers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "pipeline_item_id",
            sa.String(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("secret_name", sa.String(), nullable=False),
        sa.Column("prefix", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
    )
    op.create_index("ix_file_triggers_tenant_id", "file_triggers", ["tenant_id"])
    op.create_table(
        "file_trigger_seen",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "trigger_id",
            sa.String(),
            sa.ForeignKey("file_triggers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(), nullable=False),
        sa.Column("etag", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("trigger_id", "object_key", "etag", name="uq_fts"),
    )


def downgrade() -> None:
    op.drop_table("file_trigger_seen")
    op.drop_index("ix_file_triggers_tenant_id", table_name="file_triggers")
    op.drop_table("file_triggers")
    op.drop_index("ix_outbox_due", table_name="outbox")
    op.drop_index("ix_outbox_webhook_id", table_name="outbox")
    op.drop_table("outbox")
    op.drop_index("ix_outbound_webhooks_tenant_id", table_name="outbound_webhooks")
    op.drop_table("outbound_webhooks")
