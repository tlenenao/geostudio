# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import inspect

from app.db import Base, make_engine


def test_attachments_table_created_via_create_all():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    from app.attachments import models  # noqa: F401 -- enregistre sur Base.metadata
    from app.collections import models as collections_models  # noqa: F401
    from app.roles import models as roles_models  # noqa: F401
    from app.tenants import models as tenants_models  # noqa: F401
    from app.users import models as users_models  # noqa: F401

    Base.metadata.create_all(engine)
    tables = inspect(engine).get_table_names()
    assert "attachments" in tables
    columns = {c["name"] for c in inspect(engine).get_columns("collections")}
    assert "attachment_fields" in columns
