# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import inspect

import app.main  # noqa: F401 -- enregistre tous les modèles sur Base.metadata
from app.db import Base, make_engine


def test_notifications_tables_created_via_create_all():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = inspect(engine).get_table_names()
    assert "notifications" in tables
    assert "notification_preferences" in tables
