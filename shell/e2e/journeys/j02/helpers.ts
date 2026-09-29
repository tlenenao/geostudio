import { execFileSync } from "node:child_process";
import type { Page } from "@playwright/test";

export function psql(sql: string): string {
  return execFileSync(
    "docker",
    [
      "exec",
      "geostudio-postgis-1",
      "psql",
      "-U",
      "gis",
      "-d",
      "gis",
      "-At",
      "-v",
      "ON_ERROR_STOP=1",
      "-c",
      sql,
    ],
    { stdio: ["ignore", "pipe", "ignore"] },
  ).toString();
}

// Navigation client (pas de rechargement) : l'authentification OIDC du shell
// vit en mémoire, un `page.goto` la perd (cf. finding j02-004).
export async function spaGo(page: Page, path: string, settleMs = 1500): Promise<void> {
  await page.evaluate((p) => {
    window.history.pushState({}, "", p);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
  await page.waitForTimeout(settleMs);
}

export function seedNotifications(readerId: string, itemId: string, appId: string, tag: string) {
  psql(`DELETE FROM notifications WHERE recipient_user_id='${readerId}'`);
  psql(
    `INSERT INTO notifications (id, tenant_id, recipient_user_id, kind, status, item_id, item_resource_type, item_title, error_message, created_at) VALUES ` +
      `(md5('${tag}ok'),'default','${readerId}','ingestion','success','${itemId}','dataset','${tag}-notif-ok',NULL,now()),` +
      `(md5('${tag}ko'),'default','${readerId}','report','failure','${appId}','app','${tag}-notif-ko','boom <b>html</b>',now() - interval '1 minute')`,
  );
  return { okId: `md5('${tag}ok')`, koId: `md5('${tag}ko')` };
}
