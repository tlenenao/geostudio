import os
os.environ.setdefault("CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
os.environ.setdefault("CORE_ENV", "development")
import app.main  # noqa: F401
from sqlalchemy import text
from app.db import init_db, make_engine
eng = make_engine("sqlite+pysqlite:///:memory:")
init_db(eng)
qs = {
 "audit_log (usage.summarize)": "SELECT * FROM audit_log WHERE tenant_id='t' AND created_at >= '2026-01-01'",
 "config_revisions (_latest_revision)": "SELECT * FROM config_revisions WHERE config_id='c' ORDER BY version DESC",
 "configs (get_config_by_item)": "SELECT * FROM configs WHERE item_id='i'",
 "report_runs (get_latest_run)": "SELECT * FROM report_runs WHERE tenant_id='t' AND report_item_id='r' ORDER BY created_at DESC LIMIT 1",
 "pipeline_runs (témoin SP-49)": "SELECT * FROM pipeline_runs WHERE tenant_id='t' AND pipeline_item_id='r' ORDER BY created_at DESC LIMIT 1",
 "group_members (groups of user)": "SELECT * FROM group_members WHERE user_id='u'",
}
with eng.connect() as c:
    for k, q in qs.items():
        plan = " | ".join(r[-1] for r in c.execute(text("EXPLAIN QUERY PLAN " + q)))
        print(f"{k}: {plan}")
    c.execute(text("INSERT INTO tenants (id, slug, name, created_at) VALUES ('t','t','t','2026-01-01')")) if False else None
with eng.begin() as c:
    cols = [r[1] for r in c.execute(text("PRAGMA table_info(config_revisions)"))]
    print("config_revisions cols:", cols)
    idx = list(c.execute(text("PRAGMA index_list(config_revisions)")))
    print("config_revisions index_list:", idx)
