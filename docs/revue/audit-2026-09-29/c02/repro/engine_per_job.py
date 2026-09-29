# Repro c02 : app.jobs.common.session_factory() crée un Engine (et son pool) à chaque appel
# de job, jamais disposé. On vérifie si l'Engine est libéré par simple refcount (sans gc).
import gc, os, sys, tempfile, weakref
gc.disable()
d = tempfile.mkdtemp(dir=sys.argv[1])
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{d}/x.db"
from sqlalchemy import text
from app.jobs.common import session_factory
refs = []
for _ in range(20):
    f = session_factory()
    with f() as s:
        s.execute(text("select 1"))
    refs.append(weakref.ref(f.kw["bind"]))
    del f, s
alive = sum(1 for r in refs if r() is not None)
print("engines created:", len(refs), "still alive without gc:", alive)
n_fd = len(os.listdir("/proc/self/fd"))
print("open fds before gc:", n_fd)
gc.collect()
print("still alive after gc:", sum(1 for r in refs if r() is not None), "open fds after gc:", len(os.listdir("/proc/self/fd")))
