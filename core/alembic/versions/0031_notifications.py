# SPDX-License-Identifier: Apache-2.0
"""app.notifications — notifications + notification_preferences (chantier
4.19, docs/superpowers/specs/2026-09-04-sp39-notifications-in-app-design.md)

Deux tables neuves, aucune donnée existante à migrer (contrairement à
0030_roles.py) : create_table/drop_table suffisent dans les deux sens.

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("recipient_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "item_id",
            sa.String(),
            sa.ForeignKey("items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("item_resource_type", sa.String(), nullable=True),
        sa.Column("item_title", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["tenant_id", "recipient_user_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["tenant_id", "recipient_user_id", "read_at"],
    )
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("value", sa.String(), nullable=False, server_default="all"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_table("notifications")
