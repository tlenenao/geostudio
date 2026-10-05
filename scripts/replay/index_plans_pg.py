# ruff: noqa: E501
"""Plans d'index sur Postgres réel (REV-279 c).

Échoue (rc 1) si une requête chaude fait un Seq Scan sur une grosse table.
Une table < 1000 lignes est INCONCLUSIVE (Postgres choisit un Seq Scan sur du vide) :
rc 0 mais REV-279 (c) n'est fermée que sans INCONCLUSIF ni SEQSCAN.
Peuple la base via les journeys (t03b) ; PLAN_MIN_ROWS surcharge le seuil (tests).
"""

import os
import sys

from sqlalchemy import create_engine, text

MIN_ROWS = int(os.environ.get("PLAN_MIN_ROWS", "1000"))

QUERIES = {
    "audit_log (usage.summarize)": "SELECT * FROM audit_log WHERE tenant_id='t0' AND created_at >= now() - interval '30 days'",
    "config_revisions (_latest_revision)": "SELECT * FROM config_revisions WHERE config_id='c0' ORDER BY version DESC LIMIT 1",
    "configs (get_config_by_item)": "SELECT * FROM configs WHERE item_id='i0'",
    "report_runs (get_latest_run)": "SELECT * FROM report_runs WHERE tenant_id='t0' AND report_item_id='r0' ORDER BY created_at DESC LIMIT 1",
    "pipeline_runs (témoin SP-49)": "SELECT * FROM pipeline_runs WHERE tenant_id='t0' AND pipeline_item_id='r0' ORDER BY created_at DESC LIMIT 1",
    "group_members (groups of user)": "SELECT * FROM group_members WHERE user_id='u0'",
}


def main() -> int:
    eng = create_engine(os.environ["CORE_TEST_DATABASE_URL"])
    bad = []
    with eng.connect() as c:
        for name, q in QUERIES.items():
            table = q.split(" FROM ")[1].split()[0]
            c.execute(text(f"ANALYZE {table}"))
            n = c.execute(text("SELECT count(*) FROM " + table)).scalar() or 0
            plan = "\n".join(r[0] for r in c.execute(text("EXPLAIN " + q)))
            if n < MIN_ROWS:
                verdict = f"INCONCLUSIF (table < {MIN_ROWS} lignes)"
            else:
                verdict = "SEQSCAN" if "Seq Scan" in plan else "INDEX"
            print(f"RESULT plan name={name!r} rows={n} verdict={verdict}")
            print(plan)
            if verdict == "SEQSCAN":
                bad.append(name)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
