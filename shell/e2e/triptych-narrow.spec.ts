// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME, ANALYST_ME } from "./mocks";

const NARROW_WIDTH = 390;
const NARROW_HEIGHT = 844;
// Premier viewport "large" sous le seuil de useNarrowViewport.ts
// (NARROW_QUERY = "(max-width: 899px)", relevé par SP-33 — cf.
// docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md)
// — le point de vérification demandé par la revue transverse SP-30l
// (finding 2), reconduit par SP-33 au nouveau seuil : le seuil seul ne
// prouve rien, il faut vérifier que la grille triptyque tient bien juste
// au-dessus, pas seulement loin en-dessous.
const WIDE_BOUNDARY_WIDTH = 900;
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

// SP-33 (docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md)
// a donné à la colonne centrale (work) de TriptychLayout.tsx un plancher
// CSS explicite (minmax(360px,1fr), au lieu d'un `1fr` nu sans plancher
// réel) et relevé le seuil de useNarrowViewport.ts en conséquence (899px)
// — la famine de colonne centrale documentée par la revue transverse SP-30l
// (round 2, 2026-09-02) est corrigée. SP-36 puis SP-37 ont depuis fermé les
// deux défauts pré-existants et sans rapport de l'écran Cartes (titre de
// couche à largeur nulle ; colonne browse trop étroite pour LayersPanel) —
// plus aucun écran de ce fichier ne porte de wideBoundaryKnownIssue.

const SCREENS: Array<{
  name: string;
  path: string;
  before?: (page: Page) => Promise<void>;
  // Onglets à ne pas soumettre à expectNoClippedContent — réservé à un défaut
  // déjà connu, documenté et hors périmètre (jamais une façon de faire
  // disparaître un vrai problème découvert par cette tâche).
  // Échappatoire délibérée : aucun SCREENS n'en a plus besoin depuis SP-36
  // (l'écran Cartes était le seul consommateur), mais le champ et la branche
  // qui le lit restent en place pour le prochain écran qui en aurait besoin —
  // pas du code mort à retirer.
  skipClipCheckForTabs?: string[];
  // Raison de test.skip() pour le groupe de largeur "juste au-dessus du
  // seuil" de cet écran — réservé à un défaut pré-existant, distinct du
  // mécanisme corrigé par SP-33 ci-dessus. Jamais un moyen de faire
  // disparaître un échec sans le documenter.
  // Échappatoire délibérée : aucun SCREENS n'en a plus besoin depuis SP-37
  // (l'écran Cartes était le seul consommateur), mais le champ et la
  // branche `test.skip()` qui le lit restent en place pour le prochain
  // écran qui en aurait besoin — pas du code mort à retirer.
  wideBoundaryKnownIssue?: string;
  // Ancre positive pour la boucle 900px (Task 4, SP-60/GAP-69) : un
  // sélecteur que seul cet écran, une fois réellement rendu (pas bloqué en
  // Chargement…), satisfait. Sans elle, expectNoClippedContent() peut
  // mesurer 0 offenseur sur un écran encore en train de charger et
  // "passer" sans avoir rien exercé (REV-075) — falsifié en Task 4 en
  // retirant temporairement le mock AUTOMATISATION_OPS_CATALOG : le test
  // "Automatisation à 900 px" passait alors même que la page restait
  // bloquée sur <p role="status">Chargement…</p>.
  readyAnchor?: (page: Page) => Promise<unknown>;
}> = [
  {
    name: "Catalogue",
    path: "/",
    // SP-33 : les 5 offenseurs mesurés à 641px (résumés d'items à
    // clientWidth 0) relevaient uniquement de la famine de colonne
    // centrale, désormais corrigée.
    readyAnchor: (p) => p.getByRole("heading", { name: "Alpha" }).waitFor(),
  },
  {
    name: "Cartes",
    path: "/maps/map-1",
    // SP-36 a fermé le mécanisme (b) (titre de couche à largeur nulle).
    // SP-37 (docs/superpowers/specs/2026-09-04-sp37-layerspanel-colonne-browse-design.md)
    // ferme le mécanisme (a) restant (colonne browse trop étroite pour le
    // contenu de LayersPanel) : deux offenseurs distincts trouvés et
    // corrigés — la ligne d'ajout de champ de PopupEditor.tsx (flex-wrap
    // manquant) et le champ de fichier d'upload d'icône de
    // MapSymbologyEditor.tsx (aucune classe de largeur). Ré-mesuré
    // empiriquement après les deux correctifs : plus aucun offenseur, ni à
    // 390px ni à 900px. Le lot "Carte" est clos (CLAUDE.md).
    // Ancre : LayersPanel.tsx:411 (« Ajouter une couche ») vit dans l'onglet
    // "browse" (Couches), non actif par défaut en layout étroit
    // (defaultTabId="map") — non monté tant que cet onglet n'est pas
    // sélectionné (TriptychLayout.tsx:32-50, seul l'onglet actif est monté à
    // 390px ; à 900px les trois colonnes sont montées simultanément, cf.
    // ligne 22-30 du même fichier — l'ancre doit donc marcher dans les deux
    // régimes). data-testid="map-container" de MapView.tsx vit dans l'onglet
    // "work" (Carte), actif par défaut dans les deux régimes — mais son
    // canevas WebGL maplibre-gl reste mesuré "hidden" (état par défaut de
    // waitFor()) par Playwright en tête headless, sans rapport avec un vrai
    // défaut de mise en page (expectNoClippedContent ne vérifie d'ailleurs
    // jamais sa visibilité, seulement scrollWidth/clientWidth). Attendre sa
    // seule présence dans le DOM (state: "attached") plutôt que sa
    // visibilité contourne cet artefact d'environnement tout en prouvant la
    // même chose : MapEditorPage a quitté son garde de chargement.
    readyAnchor: (p) => p.getByTestId("map-container").waitFor({ state: "attached" }),
  },
  {
    name: "Apps & sites",
    path: "/apps/1/edit",
    // SP-33 : les 2 offenseurs mesurés à 641px relevaient uniquement de la
    // famine de colonne centrale, désormais corrigée.
    // Ancre : le bouton de bascule de mode "Édition" n'existe que dans le
    // rendu chargé d'AppBuilderPage.tsx (garde query.isLoading/
    // itemQuery.isLoading ci-dessus renvoie <p role="status"> tant que ce
    // n'est pas résolu).
    readyAnchor: (p) => p.getByRole("button", { name: "Édition" }).waitFor(),
  },
  {
    name: "Analytique",
    path: "/analytics/sql",
    before: (p) => mockMe(p, ANALYST_ME),
    // SP-33 : l'offenseur mesuré à 641px relevait uniquement de la famine
    // de colonne centrale, désormais corrigée.
    // SqlLabPage.tsx ne fait aucun appel réseau au montage (pas de garde de
    // chargement) : le h1 "SQL Lab" est disponible dès le premier rendu,
    // mais posé quand même pour uniformité et comme filet si ça change.
    readyAnchor: (p) => p.getByRole("heading", { name: "SQL Lab" }).waitFor(),
  },
  {
    name: "Automatisation",
    path: "/pipelines/new",
    before: (p) =>
      p.route("https://core.test/v1/pipelines/ops", async (route) => {
        await route.fulfill({ json: AUTOMATISATION_OPS_CATALOG });
      }),
    // Le mock ci-dessus fait quitter à la page son état "Chargement…" (cf.
    // commentaire sur AUTOMATISATION_OPS_CATALOG), condition nécessaire
    // pour atteindre la grille TriptychLayout et l'exercer réellement —
    // sans rapport avec SP-33. SP-33 : les 2 offenseurs mesurés à 641px
    // une fois la page chargée relevaient uniquement de la famine de
    // colonne centrale, désormais corrigée.
    // Ancre : "reader.collection" (clé de AUTOMATISATION_OPS_CATALOG) est
    // rendu tel quel par PipelinePalette une fois opsQuery.data résolu —
    // mais la palette vit dans l'onglet "browse" ("Étapes"), non actif par
    // défaut en layout étroit (defaultTabId="canvas") : ancre déplacée sur
    // le h2 du panneau canevas lui-même (PipelineBuilderPage.tsx:178,
    // "Pipeline" — /pipelines/new n'a pas de titre initial), rendu dans
    // l'onglet actif par défaut, étroit ou large.
    readyAnchor: (p) => p.getByRole("heading", { name: "Pipeline" }).waitFor(),
  },
  {
    name: "Tâches",
    path: "/tasks",
    // Écart trouvé par rapport au texte de la spec SP-60 (piège CLAUDE.md
    // n°3) : SP-47 a remplacé TasksComingSoonPage par UsagePage sur
    // "/tasks" — cet écran rend bien une grille TriptychLayout aujourd'hui,
    // contrairement à ce que §2.1 de la spec affirmait. GET /usage/tasks
    // n'était mocké nulle part dans mocks.ts ; sans ce mock, tasksQuery
    // n'aurait jamais résolu de façon déterministe. Réponse vide (aucune
    // tâche) : suffisant pour quitter l'état de chargement et atteindre
    // l'EmptyState "Aucune tâche récente." (UsagePage.tsx). L'utilisateur
    // par défaut (DEFAULT_ME) porte "tasks.view" mais pas "tasks.view_all"
    // — summaryQuery reste "enabled: false", aucun mock supplémentaire
    // requis.
    before: (p) =>
      p.route(/https:\/\/core\.test\/usage\/tasks(\?.*)?$/, async (route) => {
        await route.fulfill({ json: { tasks: [], total: 0 } });
      }),
    readyAnchor: (p) => p.getByText("Aucune tâche récente.").waitFor(),
  },
  {
    name: "Administration",
    path: "/admin/extensions",
    before: (p) => mockMe(p, ADMIN_ME),
    // SP-33 : l'offenseur mesuré à 641px relevait uniquement de la famine
    // de colonne centrale, désormais corrigée.
    // Ancre : l'en-tête de colonne "Étiquette" n'apparaît que lorsque
    // extensionsQuery.data est résolu (même un tableau vide, cf.
    // AdminExtensionsPage.tsx) — le h1 "Extensions" juste au-dessus, lui,
    // est rendu inconditionnellement et ne prouverait rien.
    readyAnchor: (p) => p.getByText("Étiquette").waitFor(),
  },
  {
    name: "Paramètres",
    path: "/settings",
    // SettingsComingSoonPage.tsx ne rend qu'un <EmptyState> — aucune grille
    // TriptychLayout à cet écran (confirmé par lecture directe du fichier,
    // pas supposé) : passage réel et significatif, pas vacant. Aucun appel
    // réseau non plus (rendu synchrone) : l'ancre est un filet de
    // cohérence, pas une preuve de settle nécessaire ici.
    readyAnchor: (p) => p.getByText("Les paramètres d'instance arrivent avec SP-33.").waitFor(),
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
    if (screen.readyAnchor) await screen.readyAnchor(page);
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
// à ~540px. Ce groupe vérifie que le premier viewport classé "large" sous
// le seuil courant rend la grille trois colonnes sans contenu clippé. Pas
// d'assertion BottomNav/onglets ici : au-dessus du seuil, le mode large
// (DomainBar + grille) est attendu, pas le mode étroit.
//
// Round 2 (2026-09-02) : une fois le check lui-même corrigé pour mesurer
// l'état stabilisé (cf. expectNoClippedContent ci-dessus) plutôt que le
// premier échantillon, la majorité de ces tests échouaient pour de vrai à
// l'ancien seuil (640px).
//
// SP-33 (docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md) :
// plancher explicite sur la colonne centrale + seuil relevé à 899px
// (WIDE_BOUNDARY_WIDTH = 900 ci-dessus). SP-36 puis SP-37 ont depuis fermé
// les deux défauts pré-existants et sans rapport de l'écran Cartes (cf.
// son entrée dans SCREENS) — plus aucun écran de ce fichier ne porte de
// wideBoundaryKnownIssue. Tâches/Paramètres n'ont jamais été concernés
// (aucune grille TriptychLayout ne s'y rend).
for (const screen of SCREENS) {
  test(`${screen.name} à 900 px (juste au-dessus du seuil relevé) : aucun contenu clippé`, async ({
    page,
  }) => {
    test.skip(screen.wideBoundaryKnownIssue !== undefined, screen.wideBoundaryKnownIssue);
    await page.setViewportSize({ width: WIDE_BOUNDARY_WIDTH, height: WIDE_HEIGHT });
    await mockCore(page);
    if (screen.before) {
      await screen.before(page);
    }
    await page.goto(screen.path);

    if (screen.readyAnchor) await screen.readyAnchor(page);
    await expectNoClippedContent(page);
  });
}

// Task 3 (round 2 de correction SP-30l, puis SP-33) : rien ne protège la
// valeur du seuil elle-même — sans ce test, régresser NARROW_QUERY vers son
// ancienne valeur laisserait toute la suite committée verte, puisque les
// groupes 390px/900px ci-dessus ne testent jamais un viewport à l'intérieur
// de la bande 391-899px. 700px est choisi à l'intérieur de cette bande :
// sous le seuil actuel (899px) il doit rendre le mode ÉTROIT (BottomNav
// "Navigation" + onglets), pas la grille desktop (DomainBar "Domaines",
// aucun role="tab"). Si le seuil régressait sous 700px, AppLayout.tsx
// basculerait sur DomainBar et TriptychLayout.tsx sur sa grille — ce test
// échouerait pour de vrai (vérifié : DomainBar/BottomNav utilisent des
// libellés aria-label distincts, "Domaines"/"Navigation",
// catalog.fr.ts:48-49 — pas une coïncidence de sélecteur).
test("700 px (bande 391-899, sous le seuil relevé) : mode étroit, pas la grille desktop", async ({
  page,
}) => {
  await page.setViewportSize({ width: 700, height: 900 });
  await mockCore(page);
  await page.goto("/");

  await expect(page.getByRole("navigation", { name: "Navigation" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Domaines" })).toHaveCount(0);
  await expect(page.getByRole("tab").first()).toBeVisible();
});

// SP-37 (docs/superpowers/specs/2026-09-04-sp37-layerspanel-colonne-browse-design.md) :
// contrairement aux offenseurs génériques mesurés par les deux boucles
// ci-dessus (déclenchés par le simple chargement de la page), celui-ci
// n'apparaît qu'une fois la section "Ajouter des icônes" de
// MapSymbologyEditor.tsx ouverte et un champ icône recalculé — d'où un test
// dédié plutôt qu'une entrée SCREENS générique. Valeurs de domaine COURTES
// ("A"/"B") délibérément : l'offenseur (un <input type="file"> sans classe
// de largeur) est inconditionnel, indépendant de la longueur du texte —
// contrairement à l'offenseur de PopupEditor.tsx (Task 1 de ce plan), pas
// besoin d'un texte long pour le démontrer.
test("Cartes à 900 px : la section icônes de la symbologie ne clippe pas une fois ouverte", async ({
  page,
}) => {
  await page.setViewportSize({ width: WIDE_BOUNDARY_WIDTH, height: WIDE_HEIGHT });
  await mockCore(page);
  await page.route("**/collections/communes/aggregate", async (route) => {
    await route.fulfill({
      json: { categoryKey: "type_zone", rows: [{ type_zone: "A" }, { type_zone: "B" }] },
    });
  });
  await page.goto("/maps/map-1");

  await page.getByRole("button", { name: "Ajouter des icônes" }).click();
  await page.getByLabel("Champ icône").fill("type_zone");
  await page.getByRole("button", { name: "Recalculer les valeurs" }).click();
  await expect(page.getByLabel("Ajouter une icône au tenant (PNG ou SVG)")).toBeVisible();

  // Ancre le mécanisme réellement gardé par le groupe générique 900px
  // ci-dessus pour "Cartes" (Task 1, PopupEditor.tsx) : cette ligne "Ajouter
  // un champ" ne rend que si le popup de la fixture map-1 a
  // value !== undefined && !advanced (PopupEditor.tsx:79-80). Sans cette
  // assertion, un futur changement de la fixture qui viderait ou
  // avancerait ce popup ferait toujours passer le test générique — plus
  // rien à cliper, donc plus rien à garder — sans qu'aucun test ne le
  // signale.
  await expect(page.getByLabel("Nom du champ à ajouter")).toBeVisible();

  await expectNoClippedContent(page);
});
