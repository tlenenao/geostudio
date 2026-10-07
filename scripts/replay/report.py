"""Agrège un dossier .replay-results/<ts> en tableau Markdown (stdout + report.md)."""

import pathlib
import re
import sys

out = pathlib.Path(sys.argv[1])
rows = ["| Stage | RC | Log |", "|---|---|---|"]
notes = []
for line in (out / "summary.txt").read_text().splitlines():
    m = re.match(r"STAGE=(\S+) RC=(\d+)", line)
    if m:
        rows.append(f"| {m[1]} | {m[2]} | `{out}/{m[1]}.log` |")
    elif line.strip():
        notes.append(f"- {line}")  # lignes libres (STAGE-NOTE...) conservées telles quelles
results = [
    line
    for f in sorted(out.glob("*.log"))
    for line in f.read_text().splitlines()
    if line.startswith("RESULT ")
]
body = "\n".join(rows) + "\n\n## Notes\n\n" + "\n".join(notes) + "\n\n## Mesures\n\n"
body += "\n".join(f"- `{r}`" for r in results) + "\n"
(out / "report.md").write_text(body)
print(body)
