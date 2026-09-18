// SPDX-License-Identifier: Apache-2.0
// desktop-etl/e2e/specs/golden-path.spec.js
//
// Chemin d'or bout-en-bout contre la vraie application Tauri (pas de mock
// réseau, pas de sidecar simulé) : palette -> canevas -> connexion ->
// paramétrage -> Enregistrer -> Exécuter -> statut "succeeded" -> fichier
// .gpkg réel sur disque. Sélecteurs vérifiés empiriquement contre le DOM
// réel par le contrôleur (session séparée avec accès Windows/CDP) --
// cf. desktop-etl-phase-fg-task-7-brief.md.
import { mkdtempSync, existsSync, statSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const GEOJSON_INPUT = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", properties: { label: "a" }, geometry: { type: "Point", coordinates: [1, 2] } },
    { type: "Feature", properties: { label: "b" }, geometry: { type: "Point", coordinates: [3, 4] } },
  ],
};

describe("desktop-etl golden path", () => {
  let workDir;
  let inputPath;
  let outputPath;

  before(() => {
    workDir = mkdtempSync(join(tmpdir(), "geostudio-e2e-"));
    inputPath = join(workDir, "input.geojson");
    outputPath = join(workDir, "output.gpkg");
    writeFileSync(inputPath, JSON.stringify(GEOJSON_INPUT));
  });

  after(() => {
    try {
      rmSync(workDir, { recursive: true, force: true });
    } catch {
      // Nettoyage best-effort : un échec ici ne doit jamais faire échouer
      // un test qui a déjà réussi (ou déjà échoué pour une autre raison).
    }
  });

  // Connecte la poignée source d'un nœud à la poignée cible d'un autre.
  // Essaie d'abord `dragAndDrop` (WebdriverIO dispatche de vrais événements
  // pointer natifs sous le capot, ce qui a des chances de suffire à
  // déclencher la logique de connexion de @xyflow/react) ; si aucune arête
  // n'apparaît, se rabat sur une séquence `performActions` manuelle
  // (pointerDown/pointerMove/pointerUp) -- c'est la voie qui a dû être
  // utilisée via CDP brut lors de la vérification manuelle du contrôleur,
  // les MouseEvent synthétiques classiques n'y suffisant pas.
  async function connectHandles(sourceHandle, targetHandle) {
    await sourceHandle.dragAndDrop(targetHandle);
    const edgesAfterDragAndDrop = await $$(".react-flow__edge");
    if (edgesAfterDragAndDrop.length > 0) return;

    const sourceLocation = await sourceHandle.getLocation();
    const sourceSize = await sourceHandle.getSize();
    const targetLocation = await targetHandle.getLocation();
    const targetSize = await targetHandle.getSize();
    const sx = Math.round(sourceLocation.x + sourceSize.width / 2);
    const sy = Math.round(sourceLocation.y + sourceSize.height / 2);
    const tx = Math.round(targetLocation.x + targetSize.width / 2);
    const ty = Math.round(targetLocation.y + targetSize.height / 2);

    await browser.performActions([
      {
        type: "pointer",
        id: "mouse-connect",
        parameters: { pointerType: "mouse" },
        actions: [
          { type: "pointerMove", duration: 0, x: sx, y: sy },
          { type: "pointerDown", button: 0 },
          {
            type: "pointerMove",
            duration: 200,
            x: Math.round((sx + tx) / 2),
            y: Math.round((sy + ty) / 2),
          },
          { type: "pointerMove", duration: 200, x: tx, y: ty },
          { type: "pointerUp", button: 0 },
        ],
      },
    ]);
    await browser.releaseActions();

    const edgesAfterFallback = await $$(".react-flow__edge");
    if (edgesAfterFallback.length === 0) {
      throw new Error("connectHandles: aucune arête créée (dragAndDrop et performActions ont échoué)");
    }
  }

  it("creates, runs, and confirms a file-to-file pipeline", async function () {
    // Démarrage de l'app (spawn du sidecar + retry côté entry.tsx) peut
    // prendre plusieurs secondes ; exécution réelle du pipeline est rapide
    // (fichier à 2 features) mais on garde une marge généreuse pour l'IPC.
    this.timeout(120_000);

    // 1. Signal de disponibilité : la palette n'apparaît qu'une fois la
    // connexion au sidecar établie et le catalogue d'op chargé.
    const readerButton = await $("button=reader.file");
    await readerButton.waitForExist({ timeout: 30_000 });

    // 2. Ajout des deux nœuds (clic palette, pas de drag requis pour AJOUTER
    // un nœud -- le drag ne sert qu'à CONNECTER deux nœuds entre eux).
    await readerButton.click();
    const writerButton = await $("button=writer.file");
    await writerButton.click();

    await browser.waitUntil(async () => (await $$(".react-flow__node")).length === 2, {
      timeout: 10_000,
      timeoutMsg: "les deux nœuds reader.file/writer.file ne sont jamais apparus sur le canevas",
    });
    const nodes = await $$(".react-flow__node");
    const readerNode = nodes[0];
    const writerNode = nodes[1];

    // 3. Connexion reader.file (sortie, poignée droite) -> writer.file
    // (entrée, poignée gauche).
    const sourceHandle = await readerNode.$(".react-flow__handle-right.source");
    const targetHandle = await writerNode.$(".react-flow__handle-left.target");
    await connectHandles(sourceHandle, targetHandle);

    // 4. Sélection + paramétrage de reader.file.
    await readerNode.click();
    const readerPathInput = await $('input[aria-label="path"]');
    await readerPathInput.waitForExist({ timeout: 10_000 });
    await readerPathInput.setValue(inputPath);

    // 5. Sélection + paramétrage de writer.file. Le driver GDAL a un défaut
    // serveur ("GPKG") mais le champ n'est jamais pré-rempli côté client
    // (params: {} à la création du nœud) -- le remplir explicitement est
    // nécessaire, pas seulement prudent.
    await writerNode.click();
    const writerPathInput = await $('input[aria-label="path"]');
    await writerPathInput.waitForExist({ timeout: 10_000 });
    await writerPathInput.setValue(outputPath);
    const writerDriverInput = await $('input[aria-label="driver"]');
    await writerDriverInput.setValue("GPKG");

    // 6. Enregistrement -- fait passer la page de /pipelines/new à
    // /pipelines/{pk}/edit (MemoryRouter), ce qui révèle le panneau
    // d'exécution (PipelineRunPanel n'est monté que si pk !== null).
    const saveButton = await $("button=Enregistrer");
    await saveButton.waitForEnabled({ timeout: 10_000 });
    await saveButton.click();

    const runButton = await $("button=Exécuter");
    await runButton.waitForExist({ timeout: 20_000 });

    // 7. Exécution.
    await runButton.click();

    // 8. Attente du statut terminal. STATUS_LABEL rend "succeeded" en dur
    // (littéral anglais, jamais traduit -- cf. PipelineRunPanel.tsx).
    const successStatus = await $("*=succeeded");
    await successStatus.waitForExist({ timeout: 30_000 });

    // 9. Preuve réelle : le fichier .gpkg a bien été écrit sur disque par le
    // sidecar (le statut UI seul ne le prouve pas).
    expect(existsSync(outputPath)).toBe(true);
    expect(statSync(outputPath).size).toBeGreaterThan(0);
  });
});
