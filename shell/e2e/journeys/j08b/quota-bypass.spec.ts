import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { apiFor } from "./helpers";

test.setTimeout(120_000);

function inCore(code: string, args: string[] = []): string {
  return execFileSync("docker", ["exec", "-i", "geostudio-core-1", "python", "-", ...args], {
    input: code,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"], // stderr capté : QuotaExceededError attendue (j08b-010)
  });
}

// Finding j08b-010 : le corps du job d'ingestion (run_import) crée collection + item sans jamais
// consulter les quotas d'items/collections (seul le quota de stockage est vérifié à la route).
bug(
  "j08b-010 : un import terminé ne dépasse pas les quotas d'items et de collections",
  async () => {
    const creator = await apiFor("creator");
    const me = await creator.get("/v1/me");
    const code = readFileSync(join(process.cwd(), "e2e/journeys/j08b/import_sim.py"), "utf8");
    let raw: string;
    try {
      raw = inCore(code, ["default", me.body.id, `aud-j08b-imp-${Date.now().toString(36)}`]);
    } catch (e) {
      // Corrigé côté produit : run_import refuse (QuotaExceededError) au lieu de dépasser le quota.
      const stderr = String((e as { stderr?: unknown }).stderr ?? "");
      expect(stderr).toMatch(/QuotaExceededError/);
      return;
    }
    const out = JSON.parse(raw.trim().split("\n").pop() as string);
    expect(out.items_after).toBeLessThanOrEqual(Number(out.limit_items));
    expect(out.collections_after).toBeLessThanOrEqual(Number(out.limit_collections));
  },
);

// Finding j08b-011 : aucun bucket tenant-préfixé n'a de règle de cycle de vie, et le job d'ingestion
// ne supprime jamais le fichier source : tout import reste compté dans le quota de stockage.
bug("j08b-011 : le bucket des imports a une règle d'expiration des fichiers sources", async () => {
  const py = `
import boto3, os, json
c = boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT_URL'],
    aws_access_key_id=os.environ['S3_ACCESS_KEY'], aws_secret_access_key=os.environ['S3_SECRET_KEY'])
try:
    print(json.dumps(c.get_bucket_lifecycle_configuration(Bucket=os.environ['S3_UPLOADS_BUCKET'])['Rules']))
except Exception as e:
    print(json.dumps([]))
`;
  const rules = JSON.parse(inCore(py).trim());
  expect(rules.length).toBeGreaterThan(0);
});
