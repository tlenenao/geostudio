/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { apiFor, meId, openAs, psql, type Api } from "./helpers";

// Notifications in-app : API REST (droits, préférence, pagination) et cloche du shell.
test.setTimeout(120_000);
const tag = stamp("j09");
let reader: Api;
let readerId: string;

test.beforeAll(async () => {
  reader = await apiFor("reader");
  readerId = await meId(reader);
});

function seed(rows: { key: string; kind: string; status: string; title: string; err?: string }[]) {
  psql(`DELETE FROM notifications WHERE recipient_user_id='${readerId}'`);
  const values = rows
    .map(
      (r, i) =>
        `(md5('${tag}${r.key}'),'default','${readerId}','${r.kind}','${r.status}',NULL,NULL,'${r.title}',${
          r.err ? `'${r.err}'` : "NULL"
        },now() - interval '${i} minute')`,
    )
    .join(",");
  psql(
    `INSERT INTO notifications (id, tenant_id, recipient_user_id, kind, status, item_id, item_resource_type, item_title, error_message, created_at) VALUES ${values}`,
  );
}

const idOf = (key: string) => psql(`SELECT md5('${tag}${key}')`).trim();

test.describe("j09 notifications : API", () => {
  test("liste, compteur, lecture et préférence suivent les droits de l'utilisateur", async () => {
    seed([
      { key: "ok", kind: "ingestion", status: "success", title: `${tag}-ok` },
      { key: "ko", kind: "report", status: "failure", title: `${tag}-ko`, err: "boom" },
    ]);
    await reader.send("PATCH", "/v1/notifications/preference", { value: "all" });
    expect((await reader.get("/v1/notifications/unread-count")).body.count).toBe(2);

    await reader.send("PATCH", "/v1/notifications/preference", { value: "failures_only" });
    const failures = await reader.get("/v1/notifications");
    expect(failures.body.notifications.map((n: any) => n.status)).toEqual(["failure"]);
    expect((await reader.get("/v1/notifications/unread-count")).body.count).toBe(1);

    await reader.send("PATCH", "/v1/notifications/preference", { value: "none" });
    expect((await reader.get("/v1/notifications")).body.total).toBe(0);
    expect((await reader.get("/v1/notifications/unread-count")).body.count).toBe(0);

    await reader.send("PATCH", "/v1/notifications/preference", { value: "all" });
    const read = await reader.send("POST", `/v1/notifications/${idOf("ok")}/read`);
    expect(read.status).toBe(200);
    expect(read.body.readAt).not.toBeNull();
    expect((await reader.get("/v1/notifications/unread-count")).body.count).toBe(1);
    expect((await reader.send("POST", "/v1/notifications/read-all")).status).toBe(204);
    expect((await reader.get("/v1/notifications/unread-count")).body.count).toBe(0);

    const bad = await reader.send("PATCH", "/v1/notifications/preference", { value: "tout" });
    expect(bad.status).toBe(400);
    const admin = await apiFor("admin");
    expect((await admin.send("POST", `/v1/notifications/${idOf("ok")}/read`)).status).toBe(404);
    expect((await admin.send("POST", "/v1/notifications/inexistante/read")).status).toBe(404);
    const anon = await fetch(`${process.env.CORE_URL ?? "http://localhost:8200"}/v1/notifications`);
    expect(anon.status).toBe(401);
  });

  // Bug confirmé : voir docs/revue/audit-2026-09-29/j09/findings.jsonl
  test("j09-005 : une pagination invalide (page=0) est refusée en 422, jamais en 500", async () => {
    const r = await reader.get("/v1/notifications?page=0");
    expect(r.status).toBe(422);
  });
});

test.describe("j09 notifications : cloche du shell", () => {
  test("le badge compte les non-lues, la liste est rendue en texte brut et « tout marquer lu » vide le badge", async ({
    page,
  }) => {
    seed([
      { key: "ok", kind: "ingestion", status: "success", title: `${tag}-ok` },
      { key: "ko", kind: "report", status: "failure", title: `${tag}-ko`, err: "boom <b>html</b>" },
    ]);
    await reader.send("PATCH", "/v1/notifications/preference", { value: "all" });
    await openAs(page, "reader");
    const bell = page.getByRole("button", { name: "Notifications" });
    await expect(bell).toContainText("2");
    await bell.click();
    await expect(page.getByText(`${tag}-ok`)).toBeVisible();
    await expect(page.getByText("boom <b>html</b>")).toBeVisible();
    await expect(page.getByText("Échec", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Tout marquer comme lu" }).click();
    await expect(bell).not.toContainText("2");
  });

  test("j09-006 : le sélecteur de préférence a un nom accessible distinct de celui de la cloche", async ({
    page,
  }) => {
    seed([{ key: "ok", kind: "ingestion", status: "success", title: `${tag}-ok` }]);
    await openAs(page, "reader");
    await page.getByRole("button", { name: "Notifications" }).click();
    const name = await page.getByRole("combobox").first().getAttribute("aria-label");
    expect(name).not.toBe("Notifications");
  });

  test("j09-007 : au-delà de 20 notifications, les plus anciennes restent accessibles", async ({
    page,
  }) => {
    seed(
      Array.from({ length: 25 }, (_, i) => ({
        key: `n${i}`,
        kind: "ingestion",
        status: "success",
        title: `${tag}-n${i}`,
      })),
    );
    await reader.send("PATCH", "/v1/notifications/preference", { value: "all" });
    await openAs(page, "reader");
    await page.getByRole("button", { name: /Notifications/ }).click();
    await expect(page.getByText(`${tag}-n0`)).toBeVisible();
    await expect(page.getByText(`${tag}-n24`)).toBeVisible();
  });
});
