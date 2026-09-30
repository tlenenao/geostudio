# Exécuté dans le conteneur worker : rejoue la tâche procrastinate appexport
# sans passer par .defer() (AppNotOpen côté cœur) et sans put_bucket_cors
# quand PATCH_CORS=1 (MinIO répond NotImplemented, j10b-002).
import json
import os
import sys

import app.appexport.jobs as J
from app.appexport import repository as r
from app.db import request_scoped_session
from app.jobs.common import session_factory

if os.environ.get("PATCH_CORS") == "1":
    J.ensure_uploads_bucket = lambda c, b: None
jid = sys.argv[1]
J.build_app_export_task(jid, "default")
with request_scoped_session(session_factory()) as s:
    j = r.get_job(s, tenant_id="default", job_id=jid)
    out = {"status": j.status, "error": j.error, "key": j.result_key}
    if j.result_key:
        b = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
        body = J.s3_client_from_env().get_object(Bucket=b, Key=j.result_key)["Body"].read()
        open(f"/tmp/{jid}.zip", "wb").write(body)
    print("RESULT=" + json.dumps(out))
