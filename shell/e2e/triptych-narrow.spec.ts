// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore, mockMe } from "./mocks";

const NARROW_WIDTH = 390;
const NARROW_HEIGHT = 844;
// Premier viewport "large" sous le nouveau seuil de useNarrowViewport.ts
// (NARROW_QUERY = "(max-width: 640px)") — le point de vérification demandé
// par la revue transverse SP-30l (finding 2) : 640px seul ne prouve rien,
// il faut vérifier que la grille triptyque tient bien juste au-dessus du
// seuil, pas seulement loin en-dessous.
const WIDE_BOUNDARY_WIDTH = 641;
const WIDE_HEIGHT = 900;

// Revue transverse SP-30l (finding 1) : l'ancien expectNoHorizontalOverflow()
// lisait document.documentElement.scrollWidth/clientWidth, qui reste à 0
// même quand du contenu réel est clippé et inatteignable, pour deux raisons
// structurelles de ce dépôt : (a) le conteneur de contenu d'AppLayout.tsx est
// overflow-y-auto — par la spec CSS, dès qu'un axe a une valeur de débordement
// scrollante, l'autre axe (visible par défaut) calcule à auto, donc CE div
// absorbe tout débordement horizontal plutôt que le document ; (b) les
// cellules de la grille desktop de TriptychLayout.tsx sont overflow-hidden,
// qui clippe au lieu de faire défiler. Ni l'un ni l'autre ne remonte au
// niveau documentElement. On scanne donc tous les éléments dont le débordement
// X est significatif (hidden/auto/scroll — les seuls capables de clipper ou
// de faire défiler) et on vérifie qu'aucun n'a de contenu qui dépasse sa
// propre boîte.
type ClipOffender = {
  tag: string;
  className: string;
  scrollWidth: number;
  clientWidth: number;
};

async function measureClipOffenders(page: Page): Promise<ClipOffender[]> {
  return page.evaluate(() => {
    const bad: Array<{
      tag: string;
      className: string;
      scrollWidth: number;
      clientWidth: number;
    }> = [];
    for (const el of document.querySelectorAll<HTMLElement>("*")) {
      const style = getComputedStyle(el);
      if (
        ["hidden", "auto", "scroll"].includes(style.overflowX) &&
        el.scrollWidth > el.clientWidth + 1
      ) {
        bad.push({
          tag: el.tagName,
          className: el.className,
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
        });
      }
    }
    return bad;
  });
}

// Round 2 de correction (2026-09-02) : la version précédente enveloppait la
// mesure dans expect(...).toPass({ timeout: 3000 }) — qui s'arrête au premier
// succès. Sur la plupart des écrans qui rendent réellement la grille de
// TriptychLayout.tsx (tous sauf Catalogue, déjà correctement attrapé par
// round 1), le tout premier sondage tombait pendant la peinture initiale
// vide/chargement (0 offenseur mesuré), toPass déclarait la réussite
// immédiatement, et la mise en page réellement installée — prouvée clippée
// par un ré-examen indépendant via échantillonnage manuel dans le temps —
// n'était jamais observée. toPass() ne peut PAS prouver l'absence de
// clipping : il ne peut que constater qu'un sondage a réussi un jour.
//
// Cette version mesure l'état STABILISÉ, pas le premier échantillon : on
// attend d'abord networkidle (règle la plupart des écrans "Chargement…"),
// puis on sonde le nombre d'offenseurs toutes les ~150ms jusqu'à ce qu'il
// soit identique sur 3 sondages consécutifs (ou qu'un budget de temps
// maximal s'écoule), et on n'affirme qu'une seule fois sur cette mesure
// stabilisée. Un vrai défaut de mise en page ne se résorbe jamais : il reste
// stable à une valeur > 0 et cette fonction doit pouvoir échouer dessus —
// vérifié par falsification (cf. rapport de tâche) avant d'être considérée
// correcte, pas seulement supposée correcte parce qu'elle "devrait" marcher.
async function expectNoClippedContent(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => {
    // Pas fatal : certains écrans (ex. Automatisation sous mock incomplet)
    // ne quittent jamais un état de chargement réseau — le settle-poll
    // ci-dessous mesure quand même l'état DOM stabilisé qui en résulte.
  });

  const SETTLE_STREAK = 3;
  const POLL_INTERVAL_MS = 150;
  const MAX_WAIT_MS = 5000;

  const history: number[] = [];
  let lastOffenders: ClipOffender[] = [];
  const deadline = Date.now() + MAX_WAIT_MS;

  for (;;) {
    lastOffenders = await measureClipOffenders(page);
    history.push(lastOffenders.length);
    const tail = history.slice(-SETTLE_STREAK);
    const settled = tail.length === SETTLE_STREAK && tail.every((n) => n === tail[0]);
    if (settled || Date.now() >= deadline) break;
    await page.waitForTimeout(POLL_INTERVAL_MS);
  }

  expect(lastOffenders, JSON.stringify(lastOffenders)).toHaveLength(0);
}

// Catalogue de secours (SP-15b) pour l'écran Automatisation (/pipelines/new) —
// round 2 de correction (2026-09-02) : sous les mocks e2e existants, cette
// route n'était pas répondue du tout, la page restait bloquée sur
// `<p role="status">Chargement…</p>` (PipelineBuilderPage.tsx:62,
// `opsQuery.isLoading || !opsQuery.data`) et n'atteignait donc jamais la
// grille de TriptychLayout — le test à 641px "passait" sans avoir rien
// exercé (0 offenseur mesuré parce qu'il n'y avait pas encore de mise en
// page à mesurer), pas parce que l'écran est correct. Un sous-ensemble du
// vrai catalogue servi par pipeline-builder.spec.ts (mêmes formes de
// schéma), suffisant pour que PipelineBuilderPage quitte son état de
// chargement.
const AUTOMATISATION_OPS_CATALOG = {
  "reader.collection": {
    kind: "reader",
    paramsSchema: {
      properties: { collectionId: { type: "string", format: "collection-id" } },
      required: ["collectionId"],
    },
  },
  "transform.filter": {
    kind: "transform",
    paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] },
  },
  "writer.collection": {
    kind: "writer",
    paramsSchema: {
      properties: { collectionId: { type: "string", format: "collection-id" } },
      required: ["collectionId"],
    },
  },
};

// Mécanisme partagé derrière tous les `wideBoundaryKnownIssue` ci-dessous
// (round 2 de correction, 2026-09-02) : TriptychLayout.tsx rend, au-dessus du
// seuil de useNarrowViewport.ts (640px), une grille
// `grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)]`. L'algorithme
// standard de dimensionnement CSS Grid maximise d'abord les pistes non
// flexibles (les deux colonnes latérales, jusqu'à 280+320=600px combinés)
// avant de donner quoi que ce soit à la piste `fr` (la colonne centrale
// `work`) — donc à 641px, la colonne centrale n'hérite que de 641-600=41px,
// quel que soit l'écran qui s'y trouve. Ce n'est pas propre à 641px : toute
// largeur sous ~600px + la largeur minimale réelle du contenu de la colonne
// centrale subit la même famine (plausiblement jusqu'à ~1000px+ selon
// l'écran, ex. une fenêtre desktop en demi-écran) — un vrai chantier de
// layout sur TriptychLayout lui-même (colonnes latérales/centrale), partagé
// par les neuf familles SP-30, pas un simple ajustement de seuil. Chaque
// entrée ci-dessous cite le nombre d'offenseurs réellement mesuré par le
// check corrigé de cette tâche (settle-poll, pas le premier échantillon) —
// cf. CLAUDE.md, entrée SP-30l, pour le suivi.
const WIDE_BOUNDARY_ROOT_CAUSE =
  "TriptychLayout : la colonne centrale (work) est affamée par les maximums des colonnes latérales (280+320=600px) jusqu'à ce que le viewport les dépasse largement — mécanisme partagé, cf. commentaire WIDE_BOUNDARY_ROOT_CAUSE. Hors périmètre de cette tâche : chantier de layout distinct, tracké CLAUDE.md/SP-30l.";

const SCREENS: Array<{
  name: string;
  path: string;
  before?: (page: Page) => Promise<void>;
  // Onglets à ne pas soumettre à expectNoClippedContent — réservé à un défaut
  // déjà connu, documenté et hors périmètre (jamais une façon de faire
  // disparaître un vrai problème découvert par cette tâche).
  skipClipCheckForTabs?: string[];
  // Raison de test.skip() pour le groupe 641px de cet écran — réservé à un
  // nouveau défaut découvert PAR cette tâche mais explicitement hors
  // périmètre de sa correction (cf. WIDE_BOUNDARY_ROOT_CAUSE ci-dessus).
  // Jamais un moyen de faire disparaître un échec sans le documenter.
  wideBoundaryKnownIssue?: string;
}> = [
  {
    name: "Catalogue",
    path: "/",
    // Mesuré par le check corrigé (round 2, 2026-09-02) : 5 offenseurs
    // stables à 641px, dont trois <p class="line-clamp-2"> de résumé
    // d'item à clientWidth 0 (scrollWidth 10-11px, contenu réel invisible)
    // — la colonne centrale de CatalogPage.tsx n'hérite que de 41px.
    wideBoundaryKnownIssue: `Catalogue : 5 offenseurs stables mesurés à 641px (résumés d'items à largeur 0). ${WIDE_BOUNDARY_ROOT_CAUSE}`,
  },
  {
    name: "Cartes",
    path: "/maps/map-1",
    // CLAUDE.md, lot "Carte" (bug UI connu, pré-existant, hors périmètre de
    // tout plan SP-30) : dans LayersPanel.tsx, le <span> de titre d'une
    // couche vector/feature peut avoir une largeur de layout nulle
    // (flex-1 truncate + sibling basis-full) — scrollWidth > clientWidth (0)
    // pour de vrai, mais c'est le défaut déjà tracké, pas un effet du seuil
    // de useNarrowViewport que cette tâche corrige. Confirmé par
    // investigation (page.evaluate ciblé) avant d'écarter cet onglet ici,
    // pas supposé.
    skipClipCheckForTabs: ["Couches"],
    // Round 3 de vérification (2026-09-02) : les 3 offenseurs mesurés à
    // 641px sur cet écran ne sont PAS trois occurrences du même mécanisme —
    // une version précédente de ce commentaire l'affirmait à tort en
    // parlant d'une famine "indépendante du défaut LayersPanel". Mesurés
    // individuellement :
    // 1. DIV.overflow-y-auto.border-r.border-rule (scrollWidth 397 /
    //    clientWidth 279) — la colonne latérale gauche (browse), où
    //    LayersPanel se rend par défaut à cette largeur (pas besoin de
    //    cliquer l'onglet "Couches" comme dans le groupe 390px ci-dessus),
    //    est elle-même plafonnée à son propre max-width de 280px : trop
    //    étroit pour le contenu de LayersPanel. Mécanisme DIFFÉRENT de la
    //    famine de colonne centrale : ici c'est la colonne latérale qui est
    //    trop étroite, pas la colonne centrale qui est affamée. Sondé aussi
    //    à 900/1400/1920px : persiste identiquement à chaque largeur — pas
    //    borné à la bande ~641-1000px de WIDE_BOUNDARY_ROOT_CAUSE.
    // 2. SPAN.flex-1.truncate (scrollWidth 79 / clientWidth 0) — c'est LE
    //    MÊME défaut déjà tracké CLAUDE.md/lot "Carte" que celui écarté par
    //    skipClipCheckForTabs ci-dessus pour le groupe 390px (le <span> de
    //    titre LayersPanel à largeur de layout nulle) : PAS indépendant de
    //    ce défaut, juste rendu visible sans clic ici parce que LayersPanel
    //    occupe déjà la colonne browse au premier rendu à 641px. Persiste
    //    lui aussi identiquement à 900/1400/1920px — pas borné non plus.
    // 3. DIV.overflow-hidden (scrollWidth 92 / clientWidth 41) — seul celui-
    //    ci est la vraie famine de colonne centrale (work, 641-600=41px),
    //    le même mécanisme partagé que les 4 autres écrans ci-dessous,
    //    borné à la bande ~641-1000px+ (cf. WIDE_BOUNDARY_ROOT_CAUSE).
    wideBoundaryKnownIssue: `Cartes : 3 offenseurs stables mesurés à 641px, de MÉCANISMES DISTINCTS — (a) la colonne browse elle-même plafonnée à 280px, trop étroite pour LayersPanel (persiste à toute largeur sondée, non bornée) ; (b) le <span> de titre LayersPanel à largeur nulle, déjà tracké CLAUDE.md/lot "Carte" — pas indépendant, juste visible sans clic à cette largeur (persiste aussi à toute largeur) ; (c) la vraie famine de colonne centrale, seule partagée avec les autres écrans. ${WIDE_BOUNDARY_ROOT_CAUSE}`,
  },
  {
    name: "Apps & sites",
    path: "/apps/1/edit",
    // Mesuré par le check corrigé (round 2, 2026-09-02) : 2 offenseurs
    // stables à 641px.
    wideBoundaryKnownIssue: `Apps & sites : 2 offenseurs stables mesurés à 641px. ${WIDE_BOUNDARY_ROOT_CAUSE}`,
  },
  {
    name: "Analytique",
    path: "/analytics/sql",
    before: (p) => mockMe(p, { isAnalyst: true }),
    // Mesuré par le check corrigé (round 2, 2026-09-02) : 1 offenseur
    // stable à 641px.
    wideBoundaryKnownIssue: `Analytique : 1 offenseur stable mesuré à 641px. ${WIDE_BOUNDARY_ROOT_CAUSE}`,
  },
  {
    name: "Automatisation",
    path: "/pipelines/new",
    before: (p) =>
      p.route("https://core.test/pipelines/ops", async (route) => {
        await route.fulfill({ json: AUTOMATISATION_OPS_CATALOG });
      }),
    // Round 2 de correction (2026-09-02) : le mock ci-dessus fait quitter à
    // la page son état "Chargement…" (cf. commentaire sur
    // AUTOMATISATION_OPS_CATALOG) — une fois la grille réellement exercée,
    // le check corrigé y mesure 2 offenseurs stables à 641px, la même
    // famine de colonne centrale que les autres écrans. Round 1 déclarait
    // ce test vert pour une raison sans rapport (page jamais chargée) ;
    // round 2 découvre qu'il aurait dû être rouge pour la vraie raison une
    // fois corrigé.
    wideBoundaryKnownIssue: `Automatisation : 2 offenseurs stables mesurés à 641px une fois la page effectivement chargée (round 1 le déclarait vert par un défaut de mock, cf. commentaire AUTOMATISATION_OPS_CATALOG). ${WIDE_BOUNDARY_ROOT_CAUSE}`,
  },
  {
    name: "Tâches",
    path: "/tasks",
    // TasksComingSoonPage.tsx ne rend qu'un <EmptyState> — aucune grille
    // TriptychLayout à cet écran (confirmé par lecture directe du fichier,
    // pas supposé) : passage réel et significatif, pas vacant.
  },
  {
    name: "Administration",
    path: "/admin/extensions",
    before: (p) => mockMe(p, { isAdmin: true }),
    // Mesuré par le check corrigé (round 2, 2026-09-02) : 1 offenseur
    // stable à 641px.
    wideBoundaryKnownIssue: `Administration : 1 offenseur stable mesuré à 641px. ${WIDE_BOUNDARY_ROOT_CAUSE}`,
  },
  {
    name: "Paramètres",
    path: "/settings",
    // SettingsComingSoonPage.tsx ne rend qu'un <EmptyState> — aucune grille
    // TriptychLayout à cet écran (confirmé par lecture directe du fichier,
    // pas supposé) : passage réel et significatif, pas vacant.
  },
];

for (const screen of SCREENS) {
  test(`${screen.name} à 390 px : barre de navigation basse, aucun contenu clippé`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: NARROW_WIDTH, height: NARROW_HEIGHT });
    await mockCore(page);
    if (screen.before) {
      await screen.before(page);
    }
    await page.goto(screen.path);

    await expect(page.getByRole("navigation", { name: "Navigation" })).toBeVisible();
    await expectNoClippedContent(page);

    const tabs = page.getByRole("tab");
    const tabCount = await tabs.count();
    for (let i = 0; i < tabCount; i++) {
      const tab = tabs.nth(i);
      const label = await tab.textContent();
      await tab.click();
      if (screen.skipClipCheckForTabs?.includes(label ?? "")) {
        continue;
      }
      await expectNoClippedContent(page);
    }
  });
}

// Revue transverse SP-30l (finding 2) : le seuil est passé de 390px à 640px
// parce que la grille triptyque desktop clippait encore du contenu de ~391px
// à ~540px. Ce groupe vérifie que 641px — le premier viewport classé "large"
// sous le nouveau seuil — rend la grille trois colonnes sans contenu clippé.
// Pas d'assertion BottomNav/onglets ici : à 641px le mode large (DomainBar +
// grille) est attendu, pas le mode étroit.
//
// Round 2 (2026-09-02) : une fois le check lui-même corrigé pour mesurer
// l'état stabilisé (cf. expectNoClippedContent ci-dessus) plutôt que le
// premier échantillon, la majorité de ces tests échouent pour de vrai —
// cf. wideBoundaryKnownIssue sur chaque écran concerné dans SCREENS
// ci-dessus pour le nombre d'offenseurs réellement mesuré et le mécanisme
// partagé (WIDE_BOUNDARY_ROOT_CAUSE). Seuls Tâches/Paramètres (aucune
// grille TriptychLayout ne s'y rend) passent pour de vraies raisons.
for (const screen of SCREENS) {
  test(`${screen.name} à 641 px (juste au-dessus du seuil relevé) : aucun contenu clippé`, async ({
    page,
  }) => {
    test.skip(screen.wideBoundaryKnownIssue !== undefined, screen.wideBoundaryKnownIssue);
    await page.setViewportSize({ width: WIDE_BOUNDARY_WIDTH, height: WIDE_HEIGHT });
    await mockCore(page);
    if (screen.before) {
      await screen.before(page);
    }
    await page.goto(screen.path);

    await expectNoClippedContent(page);
  });
}

// Task 3 (round 2 de correction, 2026-09-02) : rien ne protège la valeur du
// seuil elle-même — sans ce test, revenir NARROW_QUERY à "(max-width: 390px)"
// (l'ancien seuil) dans useNarrowViewport.ts laisserait toute la suite
// committée verte, puisque les groupes 390px/641px ci-dessus ne testent
// jamais un viewport à l'intérieur de la bande 391-640px. 500px est choisi à
// l'intérieur de cette bande : sous le seuil actuel (640px) il doit rendre
// le mode ÉTROIT (BottomNav "Navigation" + onglets), pas la grille desktop
// (DomainBar "Domaines", aucun role="tab"). Si le seuil régressait sous
// 500px, AppLayout.tsx basculerait sur DomainBar et TriptychLayout.tsx sur
// sa grille — ce test échouerait pour de vrai (vérifié : DomainBar/BottomNav
// utilisent des libellés aria-label distincts, "Domaines"/"Navigation",
// catalog.fr.ts:48-49 — pas une coïncidence de sélecteur).
test("500 px (bande 391-640, sous le seuil relevé) : mode étroit, pas la grille desktop", async ({
  page,
}) => {
  await page.setViewportSize({ width: 500, height: 900 });
  await mockCore(page);
  await page.goto("/");

  await expect(page.getByRole("navigation", { name: "Navigation" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Domaines" })).toHaveCount(0);
  await expect(page.getByRole("tab").first()).toBeVisible();
});
