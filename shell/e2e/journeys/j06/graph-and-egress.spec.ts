import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { corePython } from "./helpers";

// Vérifications au niveau module dans le conteneur cœur (image de prod, Python 3.12) :
// la validation de graphe et la garde d'egress sont des fonctions pures, exécutables
// même quand CORE_ETL_ENABLED est faux et que les routes ne sont pas montées.

const GRAPH_PROBE = (nodesJs: string, edgesJs: string) => `
import json
from app.configs.schemas import PipelinePayload
from app.configs.pipeline_validation import _check_acyclic, _check_topology
R={"id":"r","kind":"reader","op":"reader.collection","params":{"collectionId":"c"}}
W={"id":"w","kind":"writer","op":"writer.collection","params":{"collectionId":"c"}}
F={"id":"f","kind":"transform","op":"transform.filter","params":{"expr":"1=1"}}
nodes=${nodesJs}
edges=${edgesJs}
try:
    p=PipelinePayload.model_validate({"nodes":nodes,"edges":edges})
    _check_acyclic(p.nodes,p.edges); _check_topology(p.edges)
    print("ACCEPTED")
except Exception as e:
    print("REJECTED", str(e)[:100])
`;

const graph = (nodes: string, edges: string) => corePython(GRAPH_PROBE(nodes, edges)).trim();

test.describe("j06 validation de graphe à l'enregistrement", () => {
  test("un cycle est rejeté", () => {
    const out = graph("[R,W,F]", '[{"id":"a","from":"f","to":"w"},{"id":"b","from":"w","to":"f"}]');
    expect(out).toMatch(/^REJECTED/);
  });

  test("deux arêtes primaires entrantes sur un même nœud sont rejetées", () => {
    const out = graph(
      '[R,{**R,"id":"r2"},W]',
      '[{"id":"a","from":"r","to":"w"},{"id":"b","from":"r2","to":"w"}]',
    );
    expect(out).toMatch(/^REJECTED/);
  });

  test("un graphe sans écriture est rejeté", () => {
    expect(graph("[R]", "[]")).toMatch(/^REJECTED/);
  });

  // Finding j06-002 : run_pipeline fait `assert pred_id is not None` sur ces graphes.
  bug("j06-002 : un writer sans arête entrante est rejeté à l'enregistrement", () => {
    expect(graph("[R,W]", "[]")).toMatch(/^REJECTED/);
  });

  bug("j06-002 : un transform sans arête entrante est rejeté à l'enregistrement", () => {
    expect(graph("[R,F,W]", '[{"id":"e","from":"r","to":"w"}]')).toMatch(/^REJECTED/);
  });

  bug("j06-002 : une arête entrante sur un reader est rejetée à l'enregistrement", () => {
    expect(
      graph(
        '[R,W,{**R,"id":"r2"}]',
        '[{"id":"e","from":"r","to":"r2"},{"id":"e2","from":"r2","to":"w"}]',
      ),
    ).toMatch(/^REJECTED/);
  });

  bug("j06-002 : une arête sortante d'un writer est rejetée à l'enregistrement", () => {
    expect(
      graph(
        '[R,W,{**W,"id":"w2"}]',
        '[{"id":"e","from":"r","to":"w"},{"id":"e2","from":"w","to":"w2"}]',
      ),
    ).toMatch(/^REJECTED/);
  });
});

const egress = (url: string) =>
  corePython(`
from app.pipelines.egress import assert_egress_allowed as a
try:
    a(${JSON.stringify(url)}); print("ALLOWED")
except Exception as e:
    print("BLOCKED")
`).trim();

test.describe("j06 garde d'egress SSRF de reader.connector.rest", () => {
  for (const url of [
    "http://127.0.0.1/",
    "http://localhost/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[::ffff:169.254.169.254]/",
    "http://2130706433/",
    "http://0x7f.1/",
    "http://0.0.0.0/",
    "ftp://example.org/",
    "file:///etc/passwd",
  ]) {
    test(`bloque ${url}`, () => {
      expect(egress(url)).toBe("BLOCKED");
    });
  }

  // Finding j06-003 : 100.64.0.0/10 (CGNAT, métadonnées Alibaba en 100.100.100.200) et fec0::/10 passent.
  test("j06-003 : bloque 100.100.100.200 (CGNAT / métadonnées Alibaba)", () => {
    expect(egress("http://100.100.100.200/")).toBe("BLOCKED");
  });

  test("j06-003 : bloque [fec0::1] (site-local IPv6 déprécié)", () => {
    expect(egress("http://[fec0::1]/")).toBe("BLOCKED");
  });
});
