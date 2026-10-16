// SPDX-License-Identifier: Apache-2.0
//
// REV-284 (d) — « audit lecteur d'écran réel » remplacé par un automatisme.
// Un lecteur d'écran ne consomme pas le DOM mais l'arbre d'accessibilité : on
// l'interroge donc directement (`ariaSnapshot()`, `getByRole`) sur les pages
// clés, là où `a11y-audit.spec.ts` (axe-core) vérifie des règles WCAG
// statiques. Ici : repères, h1 unique, ordre des titres, noms accessibles
// de tous les contrôles, états aria-*, annonces role=status/alert, focus
// visible et piégeage dans les dialogues.
//
// Limite acceptée et consignée (backlog REV-284) : aucun vrai moteur de
// lecture vocale (NVDA/JAWS/VoiceOver) n'est piloté ; on prouve que l'arbre
// qu'ils consomment est correct, pas leur rendu sonore.
import { expect, test, type Page } from "@playwright/test";
import { ADMIN_ME, ANALYST_ME, mockCollection, mockCore, mockFormApp, mockMe } from "./mocks";

// Rôles interactifs dont le nom accessible est obligatoire (WCAG 4.1.2).
const NAMED_ROLES = [
  "button",
  "link",
  "textbox",
  "searchbox",
  "combobox",
  "checkbox",
  "radio",
  "switch",
  "slider",
  "spinbutton",
  "tab",
  "menuitem",
  "menuitemcheckbox",
  "menuitemradio",
];

// Ligne d'ariaSnapshot d'un rôle SANS nom : `- button`, `- button:`,
// `- button [disabled]`, `- button: texte` (le nom est entre guillemets
// juste après le rôle quand il existe : `- button "Nom"`).
const UNNAMED = new RegExp(`^\\s*- '?(${NAMED_ROLES.join("|")})(?: \\[[^\\]]+\\])*(?::.*)?'?$`);

interface TreeAuditOptions {
  /** Page de l'app (chrome avec `nav`) ou page publique/embarquée (sans). */
  nav: boolean;
}

function parseSnapshot(snapshot: string) {
  const lines = snapshot.split("\n");
  const unnamed = lines.filter((l) => UNNAMED.test(l)).map((l) => l.trim());
  const levels = lines
    .map((l) => /^\s*- heading .*\[level=(\d)\]/.exec(l))
    .filter((m): m is RegExpExecArray => m !== null)
    .map((m) => Number(m[1]));
  return { unnamed, levels };
}

/** Un titre ne saute jamais un niveau en descendant (h2 -> h4 interdit). */
function headingJumps(levels: number[]): string[] {
  const jumps: string[] = [];
  for (let i = 1; i < levels.length; i++) {
    if (levels[i] > levels[i - 1] + 1) jumps.push(`h${levels[i - 1]} -> h${levels[i]}`);
  }
  return jumps;
}

async function auditTree(page: Page, { nav }: TreeAuditOptions) {
  // Repères : exactement un <main>, et la navigation de domaines sur le chrome.
  await expect(page.getByRole("main")).toHaveCount(1);
  if (nav) await expect(page.getByRole("navigation", { name: "Domaines" })).toHaveCount(1);
  // Un seul h1 exposé dans l'arbre.
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);

  const { unnamed, levels } = parseSnapshot(await page.locator("body").ariaSnapshot());
  expect(unnamed, "contrôles interactifs sans nom accessible").toEqual([]);
  expect(levels[0], "le premier titre est un h1").toBe(1);
  expect(headingJumps(levels), "saut de niveau de titre").toEqual([]);
}

// --- Pages -------------------------------------------------------------

async function setupPublicSite(page: Page) {
  await mockCore(page);
  await page.route("https://core.test/v1/public/sites/*", (route) =>
    route.fulfill({
      json: {
        pk: "site-1",
        resourceType: "site",
        slug: "mon-portail",
        title: "Mon Portail",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: null,
        isPublished: true,
      },
    }),
  );
  await page.route("https://core.test/v1/public/configs/by-item/site-1", (route) =>
    route.fulfill({
      json: {
        id: "cfg-site",
        itemId: "site-1",
        kind: "site",
        version: 1,
        config: {
          version: 1,
          kind: "site",
          theme: {},
          dataSources: [],
          layout: {
            type: "grid",
            breakpoints: {},
            items: [
              {
                id: "t1",
                widget: "text",
                x: 0,
                y: 0,
                w: 4,
                h: 2,
                props: { text: "Bienvenue sur le portail" },
              },
            ],
          },
          messages: [],
          pages: [],
        },
      },
    }),
  );
}

async function setupEmbed(page: Page) {
  await page.route("**/v1/share-links/*", (route) =>
    route.fulfill({
      json: { itemId: "app-1", title: "App de démo", resourceType: "app", expiresAt: "2099-01-01" },
    }),
  );
  await page.route("**/v1/configs/by-item/app-1*", (route) =>
    route.fulfill({
      json: {
        config: {
          kind: "app",
          theme: {},
          dataSources: [
            { id: "ds1", type: "features", service: "core", layer: "incidents", query: {} },
          ],
          messages: [],
          layout: {
            type: "grid",
            items: [
              { id: "w1", widget: "table", x: 0, y: 0, w: 4, h: 4, props: { dataSourceId: "ds1" } },
            ],
          },
        },
      },
    }),
  );
  await page.route("**/v1/collections/incidents/schema*", (route) =>
    route.fulfill({ json: { collection: "incidents", pk: "id", geometry: null, fields: [] } }),
  );
  await page.route("**/v1/collections/incidents/items*", (route) =>
    route.fulfill({
      json: { type: "FeatureCollection", features: [], numberMatched: 0, numberReturned: 0 },
    }),
  );
}

interface PageCase {
  name: string;
  nav: boolean;
  setup: (page: Page) => Promise<void>;
  url: string;
  ready: (page: Page) => Promise<void>;
}

const PAGES: PageCase[] = [
  {
    name: "catalogue",
    nav: true,
    setup: mockCore,
    url: "/",
    ready: (p) => expect(p.getByRole("heading", { name: "Alpha" })).toBeVisible(),
  },
  {
    name: "éditeur de carte",
    nav: true,
    setup: mockCore,
    url: "/maps/map-1",
    ready: (p) => expect(p.locator("canvas.maplibregl-canvas").first()).toBeVisible(),
  },
  {
    name: "builder d'app",
    nav: true,
    setup: mockCore,
    url: "/apps/1/edit",
    ready: (p) => expect(p.getByText("Titre version 2")).toBeVisible(),
  },
  {
    name: "SQL Lab",
    nav: true,
    setup: async (p) => {
      await mockCore(p);
      await mockMe(p, ANALYST_ME);
    },
    url: "/analytics/sql",
    ready: (p) => expect(p.getByRole("heading", { name: "SQL Lab" })).toBeVisible(),
  },
  {
    name: "administration (collections)",
    nav: true,
    setup: async (p) => {
      await mockCore(p);
      await mockMe(p, ADMIN_ME);
      await p.route("https://core.test/v1/collections/candidates", (r) =>
        r.fulfill({ json: { candidates: [] } }),
      );
      await p.route("https://core.test/v1/collections*", (r) =>
        r.fulfill({ json: { collections: [mockCollection()] } }),
      );
    },
    url: "/admin/collections",
    ready: (p) => expect(p.getByText("Points d'intérêt")).toBeVisible(),
  },
  {
    name: "page publique (item)",
    nav: false,
    setup: mockCore,
    url: "/public/items/8",
    ready: (p) => expect(p.getByText("Detail de l'article")).toBeVisible(),
  },
  {
    name: "embed",
    nav: false,
    setup: setupEmbed,
    url: "/embed/e2e-sr-embed-token",
    ready: (p) => expect(p.getByRole("main")).toBeVisible(),
  },
  {
    name: "site public",
    nav: false,
    setup: setupPublicSite,
    url: "/sites/mon-portail",
    ready: (p) => expect(p.getByText("Bienvenue sur le portail")).toBeVisible(),
  },
  {
    name: "formulaire (app runtime)",
    nav: false,
    setup: mockFormApp,
    url: "/apps/form-1",
    ready: (p) => expect(p.getByRole("button", { name: "Envoyer" })).toBeVisible(),
  },
];

test.describe("arbre d'accessibilité des pages clés", () => {
  for (const c of PAGES) {
    test(`${c.name} : repères, h1 unique, ordre des titres, noms accessibles`, async ({ page }) => {
      await c.setup(page);
      await page.goto(c.url);
      await c.ready(page);
      await auditTree(page, { nav: c.nav });
    });
  }
});

// Le détecteur lui-même : un défaut injecté doit être vu (falsification).
test.describe("détecteur d'arbre d'accessibilité", () => {
  test("repère un bouton sans nom et un saut de titre", () => {
    const { unnamed, levels } = parseSnapshot(
      [
        '- heading "A" [level=1]',
        '- button "ok"',
        "- button",
        "- link [disabled]:",
        '- heading "B" [level=3]',
      ].join("\n"),
    );
    expect(unnamed).toEqual(["- button", "- link [disabled]:"]);
    expect(headingJumps(levels)).toEqual(["h1 -> h3"]);
  });
});

// --- États aria -------------------------------------------------------

test.describe("états aria exposés", () => {
  test("catalogue : un panneau déplié expose aria-expanded, une case son état coché", async ({
    page,
  }) => {
    await mockCore(page);
    await page.goto("/");
    const toggle = page.getByRole("button", { name: "Afficher la carte" });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.click();
    await expect(page.getByRole("button", { name: /Masquer la carte/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  test("éditeur de carte : les cases à cocher exposent [checked] dans l'arbre", async ({
    page,
  }) => {
    await mockCore(page);
    await page.goto("/maps/map-1");
    const box = page.getByRole("checkbox", { name: "Afficher les attributs au clic" });
    await expect(box).toBeChecked();
    await box.uncheck();
    await expect(box).not.toBeChecked();
    await expect(page.locator("body")).toContainText("Afficher les attributs au clic");
    expect(await page.locator("body").ariaSnapshot()).toMatch(
      /- checkbox "Afficher les attributs au clic"(?! \[checked\])/,
    );
  });

  test("triptyque étroit : les onglets de volet exposent aria-selected (un seul actif)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockCore(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
    expect(await page.getByRole("tab").count()).toBeGreaterThan(1);
    await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1);
    await expect(page.locator('[role="tab"]:not([aria-selected])')).toHaveCount(0);
  });
});

// --- Annonces role=status / role=alert -----------------------------------

test.describe("annonces vocales après les actions clés", () => {
  test("catalogue : la recherche annonce le nombre de résultats (status)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/");
    await expect(page.getByRole("status").filter({ hasText: /élément/ })).toHaveCount(1);
    await page.route("**/items?*", (route) =>
      route.fulfill({ json: { items: [], total: 0, page: 1, pageSize: 12 } }),
    );
    await page.getByRole("textbox", { name: "Rechercher" }).fill("introuvable-sr");
    await expect(page.getByRole("status").filter({ hasText: "Aucun résultat" })).toHaveCount(1);
  });

  test("formulaire : une soumission vide annonce l'erreur (alert) et marque le champ invalide", async ({
    page,
  }) => {
    await mockFormApp(page);
    await page.goto("/apps/form-1");
    await page.getByRole("button", { name: "Envoyer" }).click();
    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.getByLabel("titre", { exact: false }).first()).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });
});

// --- Focus : visible et piégé dans les dialogues ------------------------

async function focusIsVisible(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return false;
    const s = getComputedStyle(el);
    return (
      (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) ||
      (s.boxShadow !== "none" && s.boxShadow !== "")
    );
  });
}

test.describe("focus clavier", () => {
  test("catalogue : chaque arrêt de tabulation montre un indicateur de focus", async ({ page }) => {
    await mockCore(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
    const hidden: string[] = [];
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press("Tab");
      if (!(await focusIsVisible(page))) {
        hidden.push(
          await page.evaluate(() => {
            const el = document.activeElement!;
            return `${el.tagName} ${el.getAttribute("aria-label") ?? el.textContent?.slice(0, 20)}`;
          }),
        );
      }
    }
    expect(hidden, "éléments focalisés sans indicateur visible").toEqual([]);
  });

  test("dialogue « Nouvel élément » : le focus entre, reste piégé (Tab/Maj+Tab) et revient à l'ouverture", async ({
    page,
  }) => {
    await mockCore(page);
    await page.goto("/");
    const trigger = page.getByRole("button", { name: "Nouveau" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
    await expect(dialog).toBeVisible();
    const inside = () => page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'));
    expect(await inside()).toBe(true);
    for (let i = 0; i < 15; i++) {
      await page.keyboard.press("Tab");
      expect(await inside(), `Tab n°${i + 1} sort du dialogue`).toBe(true);
    }
    for (let i = 0; i < 15; i++) {
      await page.keyboard.press("Shift+Tab");
      expect(await inside(), `Maj+Tab n°${i + 1} sort du dialogue`).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
});
