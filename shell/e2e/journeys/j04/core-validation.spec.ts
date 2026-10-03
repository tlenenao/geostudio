import { expect, test } from "@playwright/test";
import { getSeed, baseApp, grid } from "./seed";

// finding j04-013 : le cœur (REST) n'applique aucune validation sémantique à une config d'app.
test("j04-013 : le cœur refuse une config d'app invalide (CEL cassé, ids de widget dupliqués, taille négative)", async () => {
  const s = await getSeed();
  const bad = baseApp({
    layout: grid([
      { id: "w", widget: "text", x: 0, y: 0, w: 4, h: 2, props: {}, visibleWhen: "1 +" },
      { id: "w", widget: "text", x: 0, y: 0, w: 0, h: -3, props: {} },
    ]),
    messages: [{ id: "m", from: "w", event: "changed", to: "absent", action: "set", when: "1 +" }],
  });
  const r = await s.creator.send("POST", "/v1/configs", {
    title: `${s.tag}-invalide`,
    config: bad,
  });
  // Observé : 201 (la validation CEL n'existe que dans le shell, qui bloque « Enregistrer »).
  expect(r.status).toBeGreaterThanOrEqual(400);
});
