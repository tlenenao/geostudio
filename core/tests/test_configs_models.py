from sqlalchemy import select

from app.db import Base, make_engine, make_session_factory, init_db
from app.configs.models import Config, ConfigRevision


def test_can_persist_config_and_revision():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    try:
        init_db(engine)
        Session = make_session_factory(engine)

        with Session() as session:
            config = Config(id="c1", kind="app", item_id=None, current_version=1)
            session.add(config)
            session.add(ConfigRevision(config_id="c1", version=1, data={"kind": "app"}))
            session.commit()

        with Session() as session:
            loaded = session.scalar(select(Config).where(Config.id == "c1"))
            assert loaded is not None
            assert loaded.kind == "app"
            assert loaded.current_version == 1
            rev = session.scalar(select(ConfigRevision).where(ConfigRevision.config_id == "c1"))
            assert rev.data == {"kind": "app"}
    finally:
        engine.dispose()


def test_base_metadata_has_both_tables():
    assert "configs" in Base.metadata.tables
    assert "config_revisions" in Base.metadata.tables
