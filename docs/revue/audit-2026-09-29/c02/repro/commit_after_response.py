# Repro c02 : l'exit d'une dépendance yield (commit) s'exécute-t-il avant l'envoi de la réponse ?
import fastapi
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

events = []

def dep():
    yield "s"
    events.append("commit-attempt")
    raise RuntimeError("commit failed (simulated IntegrityError at COMMIT)")

app = FastAPI()

@app.post("/w")
def w(s=Depends(dep)):
    events.append("handler")
    return {"ok": True}

c = TestClient(app, raise_server_exceptions=False)
r = c.post("/w")
print("fastapi", fastapi.__version__, "status", r.status_code, r.text, events)
