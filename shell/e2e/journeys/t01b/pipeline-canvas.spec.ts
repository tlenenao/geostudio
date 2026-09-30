import { expect, test } from "@playwright/test";
import { bug, getA11ySeed, go, seriousViolations, session } from "./helpers";

test.setTimeout(120_000);

// Canvas DAG de pipeline (CORE_ETL_ENABLED=true) : éditeur jamais atteignable lors de la 1re passe.
test.describe("t01b pipelines : éditeur DAG", () => {
  test("axe : aucune violation critique/grave en clair (/pipelines/:id/edit, nœud sélectionné)", async ({
    browser,
  }) => {
    const s = await getA11ySeed();
    const { ctx, page } = await session(browser, "creator");
    await go(page, `/pipelines/${s.pipelineId}/edit`, 3500);
    await page.locator(".react-flow__node").first().click();
    expect(await seriousViolations(page)).toEqual([]);
    await ctx.close();
  });

  // t01b-007 : finding (cause commune : t01-005). Titres de nœuds noirs sur fond sombre.
  bug(
    "t01b-007 : en thème sombre, le titre d'un nœud du canevas atteint 4,5:1 de contraste",
    async ({ browser }) => {
      const s = await getA11ySeed();
      const { ctx, page } = await session(browser, "creator", "dark");
      await go(page, `/pipelines/${s.pipelineId}/edit`, 3500);
      const ratios = await page.evaluate(() => {
        const lum = (css: string) => {
          const [r, g, b] = (css.match(/[\d.]+/g) ?? ["0", "0", "0"]).slice(0, 3).map((v) => {
            const c = Number(v) / 255;
            return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        };
        return [...document.querySelectorAll(".react-flow__node")].map((n) => {
          const fg = lum(getComputedStyle(n.querySelector(".font-medium")!).color);
          const bg = lum(getComputedStyle(n.firstElementChild!).backgroundColor);
          return (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
        });
      });
      expect(Math.min(...ratios)).toBeGreaterThanOrEqual(4.5);
      await ctx.close();
    },
  );

  // t01b-008 : finding (bug fonctionnel, pas seulement clavier). Une arête ne devient jamais
  // « selected » (handleEdgesChange ignore les changements de sélection, les arêtes sont
  // reconstruites à chaque rendu) : ni clic souris + Suppr, ni Entrée + Suppr ne la retirent.
  bug(
    "t01b-008 : une arête peut être supprimée (sélection puis Suppr), à la souris comme au clavier",
    async ({ browser }) => {
      const s = await getA11ySeed();
      const { ctx, page } = await session(browser, "creator");
      await go(page, `/pipelines/${s.pipelineId}/edit`, 3500);
      const edges = page.locator(".react-flow__edge");
      const pt = await page.evaluate(() => {
        const path = document.querySelector<SVGPathElement>(".react-flow__edge-path")!;
        const p = path.getPointAtLength(path.getTotalLength() * 0.25);
        const m = path.getScreenCTM()!;
        return { x: p.x * m.a + p.y * m.c + m.e, y: p.x * m.b + p.y * m.d + m.f };
      });
      await page.mouse.click(pt.x, pt.y);
      await page.keyboard.press("Delete");
      await page.waitForTimeout(500);
      const afterMouse = await edges.count();
      await edges
        .first()
        .focus()
        .catch(() => undefined);
      await page.keyboard.press("Enter");
      await page.keyboard.press("Delete");
      await page.waitForTimeout(500);
      expect({ afterMouse, afterKeyboard: await edges.count() }).toEqual({
        afterMouse: 0,
        afterKeyboard: 0,
      });
      await ctx.close();
    },
  );

  // t01b-001 : finding. Le parcours « ↝ puis clic sur le nœud cible » n'a pas d'équivalent clavier.
  bug(
    "t01b-001 : Entrée sur un nœud cible achève la connexion amorcée par le bouton ↝",
    async ({ browser }) => {
      const s = await getA11ySeed();
      const { ctx, page } = await session(browser, "creator");
      await go(page, `/pipelines/${s.pipelineId}/edit`, 3500);
      await page.getByRole("button", { name: /^transform\.filter/ }).focus();
      await page.keyboard.press("Enter");
      const edges = page.locator(".react-flow__edge");
      const before = await edges.count();
      await page.getByRole("button", { name: "Connecter depuis reader.collection" }).focus();
      await page.keyboard.press("Enter");
      await page.locator(".react-flow__node").filter({ hasText: "transform.filter" }).focus();
      await page.keyboard.press("Enter");
      await page.waitForTimeout(500);
      expect(await edges.count()).toBe(before + 1);
      await ctx.close();
    },
  );

  // t01b-002 : finding. Nœud et arête focalisés au clavier : ni contour ni ombre.
  bug(
    "t01b-002 : un nœud du canevas atteint au clavier porte un indicateur de focus visible",
    async ({ browser }) => {
      const s = await getA11ySeed();
      const { ctx, page } = await session(browser, "creator");
      await go(page, `/pipelines/${s.pipelineId}/edit`, 3500);
      await page.getByRole("button", { name: /^writer\.export/ }).focus();
      let indicator = "none";
      for (let i = 0; i < 8; i++) {
        await page.keyboard.press("Tab");
        indicator = await page.evaluate(() => {
          const a = document.activeElement as HTMLElement;
          if (!a.classList.contains("react-flow__node")) return "continue";
          const cs = getComputedStyle(a);
          return cs.outlineStyle !== "none" || cs.boxShadow !== "none" ? "visible" : "none";
        });
        if (indicator !== "continue") break;
      }
      expect(indicator).toBe("visible");
      await ctx.close();
    },
  );

  // t01b-003 : finding. Nom accessible d'un bouton de palette = op collée à sa description.
  bug(
    "t01b-003 : le nom d'un bouton de palette sépare l'opération de sa description",
    async ({ browser }) => {
      const s = await getA11ySeed();
      const { ctx, page } = await session(browser, "creator");
      await go(page, `/pipelines/${s.pipelineId}/edit`, 3500);
      const name = await page
        .getByRole("button", { name: /^reader\.connector\.rest/ })
        .evaluate((b) => b.textContent ?? "");
      expect(name).toMatch(/^reader\.connector\.rest[\s:—-]/);
      await ctx.close();
    },
  );

  // t01b-004 : finding. 55+ boutons de palette avant d'atteindre le canevas, sans raccourci.
  bug(
    "t01b-004 : le canevas est atteignable en moins de 30 tabulations depuis la palette",
    async ({ browser }) => {
      const s = await getA11ySeed();
      const { ctx, page } = await session(browser, "creator");
      await go(page, `/pipelines/${s.pipelineId}/edit`, 3500);
      await page.getByRole("searchbox", { name: "Rechercher une opération" }).focus();
      let presses = 0;
      for (; presses < 120; presses++) {
        await page.keyboard.press("Tab");
        const inCanvas = await page.evaluate(
          () => !!document.activeElement?.closest(".react-flow__node,.react-flow__edge"),
        );
        if (inCanvas) break;
      }
      expect(presses).toBeLessThan(30);
      await ctx.close();
    },
  );

  // t01b-005 : finding. Contrôles React Flow non traduits ; nœuds/arêtes sans nom utile.
  bug(
    "t01b-005 : les contrôles du canevas et les arêtes sont nommés en français",
    async ({ browser }) => {
      const s = await getA11ySeed();
      const { ctx, page } = await session(browser, "creator");
      await go(page, `/pipelines/${s.pipelineId}/edit`, 3500);
      await expect(page.getByRole("button", { name: "Zoom In" })).toHaveCount(0);
      const edgeName = await page.locator(".react-flow__edge").first().getAttribute("aria-label");
      expect(edgeName).not.toMatch(/^Edge from /);
      await ctx.close();
    },
  );

  // t01b-006 : finding. Boutons × / ↝ (16 px), « + » d'arête (20 px), case de planification (13 px).
  bug(
    "t01b-006 : les commandes de nœud et d'arête mesurent au moins 24×24 px",
    async ({ browser }) => {
      const s = await getA11ySeed();
      const { ctx, page } = await session(browser, "creator");
      await go(page, `/pipelines/${s.pipelineId}/edit`, 3500);
      const small = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("button,input")]
          .map((el) => ({ el, b: el.getBoundingClientRect() }))
          .filter(({ b }) => b.width > 0 && (b.width < 24 || b.height < 24))
          .map(
            ({ el, b }) =>
              `${el.getAttribute("aria-label") ?? el.tagName}:${Math.round(b.width)}x${Math.round(b.height)}`,
          ),
      );
      expect(small).toEqual([]);
      await ctx.close();
    },
  );
});
