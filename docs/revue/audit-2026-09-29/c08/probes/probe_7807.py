import os
os.environ["CORE_AUTH_MODE"]="mock"; os.environ["CORE_ENV"]="development"
os.environ["CORE_SECRETS_MASTER_KEY"]="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
from fastapi.testclient import TestClient
from app.main import create_app
c=TestClient(create_app())
for m,p,kw in [("get","/v1/nope",{}),("delete","/health",{}),("put","/v1/configs/by-item/x",{"json":{"kind":"bogus"}}),("post","/v1/groups",{"json":{}})]:
    r=getattr(c,m)(p,headers={"Authorization":"Bearer mock"},**kw)
    print(m,p,r.status_code,r.headers.get("content-type"),r.text[:150])
