# Repro c02 : files procrastinate déclarées par les tâches vs files réellement consommées
# par les workers de docker-compose.yml.
import os, re
os.environ.setdefault("CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
from app.jobs import app
app.perform_import_paths()
declared = {}
for name, task in app.tasks.items():
    if name.startswith("builtin:"):
        continue
    declared.setdefault(task.queue, []).append(name)
compose = open("../docker-compose.yml").read()
consumed = set()
for m in re.finditer(r"procrastinate --app app\.jobs\.app worker -q ([a-z0-9,]+)", compose):
    consumed |= set(m.group(1).split(","))
print("consumed by compose workers:", sorted(consumed))
for q in sorted(declared):
    flag = "OK" if q in consumed else "NEVER CONSUMED"
    print(f"{q:10s} {flag:15s} {sorted(declared[q])}")
