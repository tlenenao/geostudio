/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect, type Page } from "@playwright/test";
import { type PersonaName } from "../_fixtures/env";
import { openAs, spaGoto } from "../j06/helpers";
import { apiFor, getSeed, jwtClaims } from "./mcp";

test.setTimeout(120_000);

const HISTORY_KEY = "geostudio.copilot.history";

// Force copilotEnabled=true sur GET /v1/instance : la vraie capacité est éteinte sur
// cette stack (CORE_LLM_PROVIDER vide). Le reste de la page, le jeton OIDC et l'API
// restent réels ; seul POST /v1/copilot/turn est simulé.
async function enableCopilot(page: Page) {
  await page.route("**/v1/instance", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, copilotEnabled: true } });
  });
}

interface Turn {
  body: any;
  headers: Record<string, string>;
}

async function stubTurn(
  page: Page,
  answer: (n: number, body: any) => { status?: number; json?: unknown },
) {
  const turns: Turn[] = [];
  await page.route("**/v1/copilot/turn", async (route) => {
    const body = route.request().postDataJSON();
    turns.push({ body, headers: route.request().headers() });
    const a = answer(turns.length, body);
    await route.fulfill({
      status: a.status ?? 200,
      contentType: "application/json",
      json: a.json ?? { reply: "ok", clientOps: [] },
    });
  });
  return turns;
}

async function openBuilder(page: Page, persona: PersonaName, pk: string) {
  await openAs(page, persona);
  await spaGoto(page, `/apps/${pk}/edit`);
}

async function ask(page: Page, message: string) {
  await page.getByLabel("Message au copilote").fill(message);
  await page.getByRole("button", { name: "Envoyer" }).click();
}

async function newApp(persona: PersonaName, title: string, shared = false): Promise<string> {
  const api = await apiFor(persona);
  const r = await api.send("POST", "/v1/configs", {
    title,
    config: { version: 1, kind: "app", layout: { type: "grid", items: [] } },
  });
  expect(r.status).toBe(201);
  if (shared) {
    const p = await api.send("PATCH", `/v1/items/${r.body.itemId}`, { isPublished: true });
    expect(p.status).toBe(200);
    const s = await api.send("PUT", `/v1/items/${r.body.itemId}/sharing`, {
      public: true,
      groups: [],
    });
    expect([200, 204]).toContain(s.status);
  }
  return r.body.itemId as string;
}

test.describe("j11 copilote : capacité éteinte côté UI", () => {
  test("le panneau copilote est absent du builder, de SQL Lab et de la requête visuelle", async ({
    page,
  }) => {
    const seed = await getSeed();
    await openBuilder(page, "creator", seed.appPk);
    await expect(page.getByRole("button", { name: "Enregistrer" })).toBeVisible();
    await expect(page.getByLabel("Message au copilote")).toHaveCount(0);
    await spaGoto(page, "/analytics/sql");
    await expect(page.getByLabel("Message au copilote")).toHaveCount(0);
  });

  // FINDING j11-006 : aucun texte ne dit que le copilote existe mais n'est pas configuré ;
  // la fonction est simplement invisible, l'utilisateur ne peut pas la découvrir.
  test("j11-006 : le builder explique que le copilote est indisponible quand aucun fournisseur LLM n'est configuré", async ({
    page,
  }) => {
    const seed = await getSeed();
    await openBuilder(page, "creator", seed.appPk);
    await expect(page.getByRole("button", { name: "Enregistrer" })).toBeVisible();
    await expect(page.getByText(/copilote.*(indisponible|non configuré)/i)).toBeVisible();
  });
});

test.describe("j11 copilote : builder avec cœur simulé sur /copilot/turn", () => {
  test("un tour envoie l'item, la surface, la config courante, les outils client et un vrai jeton d'audience MCP", async ({
    page,
  }) => {
    const pk = await newApp("creator", "aud-j11-ui-1");
    await enableCopilot(page);
    const turns = await stubTurn(page, () => ({ json: { reply: "Bonjour.", clientOps: [] } }));
    await openBuilder(page, "creator", pk);
    await ask(page, "Explique cette app");
    await expect.poll(() => turns.length).toBe(1);
    const { body, headers } = turns[0];
    expect(body.itemId).toBe(pk);
    expect(body.surface).toBe("app_builder");
    expect(body.message).toBe("Explique cette app");
    expect(body.currentConfig.kind).toBe("app");
    expect(body.clientTools.map((t: any) => t.name).sort()).toEqual([
      "addDataSource",
      "addWidget",
      "removeWidget",
      "setFilter",
      "updateWidgetProps",
    ]);
    // Jeton MCP : obtenu par signinSilent (iframe), audience distincte du jeton REST.
    expect(jwtClaims(body.mcpToken).aud).toContain("geostudio-mcp");
    expect(headers.authorization).toMatch(/^Bearer /);
    expect(headers.authorization.slice(7)).not.toBe(body.mcpToken);
  });

  // FINDING j11-007 : sous OIDC, useMcpToken appelle signinSilent() à CHAQUE tour (le cache
  // vit dans le hook, donc dans un composant que le remontage détruit) ; react-oidc-context
  // passe alors isLoading=true, RequireAuth rend « Connexion… » et démonte tout le shell.
  // Le brouillon non enregistré, la pile d'annulation, la conversation et la réponse du tour
  // (clientOps) sont perdus ; le mode mock (E2E historiques) contourne ce chemin.
  bug(
    "j11-007 : la réponse du copilote est appliquée au brouillon sans perdre le brouillon en cours",
    async ({ page }) => {
      const pk = await newApp("creator", "aud-j11-ui-2");
      await enableCopilot(page);
      await stubTurn(page, () => ({
        json: {
          reply: "Fait.",
          clientOps: [
            { op: "addWidget", args: { type: "indicator" } },
            { op: "save_app_config", args: {} },
          ],
        },
      }));
      await openBuilder(page, "creator", pk);
      await page.getByRole("button", { name: "Texte" }).click();
      await expect(
        page.getByRole("button", {
          name: /^Sélectionner (Texte|Table|Bouton|Filtre|Formulaire|Carte|Section riche)/,
        }),
      ).toHaveCount(1);
      await ask(page, "Ajoute un indicateur");
      await expect(page.getByText("Fait.")).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: /^Sélectionner (Texte|Table|Bouton|Filtre|Formulaire|Carte|Section riche)/,
        }),
      ).toHaveCount(2);
      await expect(page.getByText("Action inconnue ignorée : save_app_config")).toBeVisible();
    },
  );

  test("l'échange est consigné dans l'historique localStorage même si le panneau est remonté", async ({
    page,
  }) => {
    const pk = await newApp("creator", "aud-j11-ui-4");
    await enableCopilot(page);
    await stubTurn(page, () => ({ json: { reply: "ok", clientOps: [] } }));
    await openBuilder(page, "creator", pk);
    // P07.07/08 : clé suffixée du compte et de l'item (geostudio.copilot.history.<sub>.<item>).
    const readHistory = () =>
      page.evaluate((prefix) => {
        const k = Object.keys(localStorage).find((x) => x.startsWith(prefix));
        return JSON.parse((k && localStorage.getItem(k)) || "[]");
      }, HISTORY_KEY);
    await page.evaluate((prefix) => {
      for (const k of Object.keys(localStorage)) {
        if (k.startsWith(prefix)) localStorage.removeItem(k);
      }
    }, HISTORY_KEY);
    await ask(page, "premier");
    await expect.poll(async () => (await readHistory()).length).toBe(1);
    const stored = await readHistory();
    expect(stored[0]).toMatchObject({ message: "premier", opsCount: 0, status: "ok" });
  });

  // FINDING j11-010 : un lecteur (Enregistrer désactivé) peut néanmoins utiliser le copilote
  // et modifier le brouillon local ; le panneau n'est pas mis en lecture seule.
  test("j11-010 : un lecteur sur une app partagée ne peut pas utiliser le copilote d'édition", async ({
    page,
  }) => {
    const pk = await newApp("creator", "aud-j11-ui-7", true);
    await enableCopilot(page);
    await stubTurn(page, () => ({ json: { reply: "ajouté", clientOps: [] } }));
    await openBuilder(page, "reader", pk);
    await expect(page.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
    await expect(page.getByLabel("Message au copilote")).toBeDisabled();
  });
});

test.describe("j11 copilote : SQL Lab", () => {
  // Même racine que j11-007 : le remontage consécutif à signinSilent efface le brouillon SQL
  // que le tour vient d'insérer.
  test("j11-007 : le brouillon SQL proposé reste dans l'éditeur et n'est jamais exécuté sans clic", async ({
    page,
  }) => {
    await enableCopilot(page);
    let executed = false;
    await page.route("**/v1/analytics/sql", async (route) => {
      executed = true;
      await route.continue();
    });
    const turns = await stubTurn(page, () => ({
      json: {
        reply: "Voici un brouillon.",
        clientOps: [{ op: "applySqlDraft", args: { sql: "SELECT 1 AS un" } }],
      },
    }));
    await openAs(page, "analyst");
    await spaGoto(page, "/analytics/sql");
    await ask(page, "un");
    await expect(page.getByLabel("Requête SQL")).toHaveText("SELECT 1 AS un");
    expect(executed).toBe(false);
    expect(turns[0].body.surface).toBe("sql_lab");
    expect(turns[0].body.itemId).toBeUndefined();
    expect(Array.isArray(turns[0].body.currentConfig.collections)).toBe(true);
    await expect(page.getByText("Brouillon SQL inséré.")).toBeVisible();
  });
});
