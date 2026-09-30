# Repro c02 : les tools MCP sont des `async def` qui font des I/O synchrones (SQLAlchemy,
# httpx.Client, DuckDB). Ils s'exécutent donc SUR la boucle asyncio d'uvicorn et la
# bloquent : pendant qu'un tool travaille, même GET /health (route sync) ne répond pas.
# On remplace resolve_actor (1re I/O sync de list_items) par un time.sleep(2) pour
# matérialiser une requête lente, puis on mesure le RECOUVREMENT des intervalles
# (piège n°7 : pas une assertion de durée).
import os, sys, threading, time, json
scratch = sys.argv[1]
os.environ.update({
    "CORE_AUTH_MODE": "mock", "CORE_ENV": "development",
    "CORE_SECRETS_MASTER_KEY": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    "DATABASE_URL": f"sqlite+pysqlite:///{scratch}/loop.db",
    "CORE_BASE_URL": "http://127.0.0.1:8765",
})
import httpx, uvicorn
from app.db import init_db, make_engine
init_db(make_engine(os.environ["DATABASE_URL"]))
import app.mcp.tools.catalog as catalog
def slow_resolve_actor(session, token):
    t0 = time.monotonic(); time.sleep(2.0); marks["tool"] = (t0, time.monotonic())
    raise ValueError("slow tool done")
catalog.resolve_actor = slow_resolve_actor
from app.main import create_app
marks = {}
server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=8765, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started: time.sleep(0.05)
base = "http://127.0.0.1:8765"
H = {"Accept": "application/json, text/event-stream", "Authorization": "Bearer x"}
c = httpx.Client(base_url=base, timeout=30)
r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}, headers=H)
sid = r.headers["mcp-session-id"]; H2 = {**H, "mcp-session-id": sid}
c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=H2)
def call():
    httpx.post(base + "/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_items", "arguments": {}}}, headers=H2, timeout=30)
t = threading.Thread(target=call); t.start()
time.sleep(0.5)  # le tool est entré dans son sleep ; on envoie /health pendant ce temps
h0 = time.monotonic(); hr = httpx.get(base + "/health", timeout=30); h1 = time.monotonic()
t.join()
tool0, tool1 = marks["tool"]
print(f"tool sleeping: [{0:.2f}, {tool1-tool0:.2f}] s ; /health sent at {h0-tool0:.2f} s, answered at {h1-tool0:.2f} s (status {hr.status_code})")
print("health answered only after tool finished (loop blocked):", h0 < tool1 and h1 >= tool1)
server.should_exit = True
