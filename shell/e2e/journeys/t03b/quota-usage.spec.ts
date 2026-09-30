import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";
import { bug } from "../_fixtures/verify";
import { timed } from "./helpers";

// Octets réellement présents dans les buckets S3 (comptés dans le conteneur cœur).
function bucketBytes(envVar: string): number {
  const py =
    "import boto3,os;c=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL']," +
    "aws_access_key_id=os.environ['S3_ACCESS_KEY'],aws_secret_access_key=os.environ['S3_SECRET_KEY']);" +
    "print(sum(o['Size'] for p in c.get_paginator('list_objects_v2').paginate(Bucket=os.environ[sys.argv[1]]) for o in p.get('Contents',[])))";
  return Number(
    execFileSync(
      "docker",
      ["exec", "geostudio-core-1", "python", "-c", "import sys\n" + py, envVar],
      {
        encoding: "utf8",
      },
    ).trim(),
  );
}

test.describe("t03b quotas et usage (CORE_QUOTAS_ENABLED=true)", () => {
  test("GET /admin/usage avec 2 500 objets sous le préfixe du tenant : réponse en moins de 1,5 s", async () => {
    // Le calcul du stockage liste chaque bucket préfixé par tenant, page de 1 000, dans la requête.
    const py =
      "import boto3,os;c=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL']," +
      "aws_access_key_id=os.environ['S3_ACCESS_KEY'],aws_secret_access_key=os.environ['S3_SECRET_KEY']);" +
      "b=os.environ['S3_ATTACHMENTS_BUCKET']\n" +
      "try: c.create_bucket(Bucket=b)\nexcept Exception: pass\n" +
      "[c.put_object(Bucket=b,Key='default/t03b-usage/%d.txt'%i,Body=b'x') for i in range(2500)]";
    execFileSync("docker", ["exec", "geostudio-core-1", "python", "-c", py], { stdio: "pipe" });
    const r = await timed("admin", "/v1/admin/usage");
    console.log("T03B usage2500", r.status, r.ms, "ms", r.text());
    expect(r.status).toBe(200);
    expect(JSON.parse(r.text()).storageBytes).toBeGreaterThanOrEqual(2500);
    expect(r.ms).toBeLessThan(1500);
  });

  bug(
    "t03b-006 : storageBytes de /admin/usage inclut les sorties de pipeline (bucket exports) et le lakehouse",
    async () => {
      // Constat : après ~97 Mo écrits par writer.export et ~35 Mo de GeoParquet CDC, storageBytes ne
      // compte que les 4 buckets préfixés par tenant + les ExportJob/AppExportJob.
      const real = bucketBytes("S3_EXPORTS_BUCKET") + bucketBytes("S3_CDC_BUCKET");
      const r = await timed("admin", "/v1/admin/usage");
      const used = JSON.parse(r.text()).storageBytes as number;
      console.log("T03B usageSousCompte", used, "octets comptés pour", real, "octets réels");
      expect(used).toBeGreaterThanOrEqual(real * 0.5);
    },
  );
});
