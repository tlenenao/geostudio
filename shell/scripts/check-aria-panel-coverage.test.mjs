// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { detectViolations } from "./check-aria-panel-coverage.mjs";

describe("detectViolations", () => {
  it("détecte un bouton qui ouvre un panneau en ligne sans aria-expanded/aria-controls", () => {
    const content = `
      export function X() {
        const [open, setOpen] = useState(false);
        return (
          <div>
            <button type="button" onClick={() => setOpen(true)}>Ouvrir</button>
            {open && <div role="region">Panneau</div>}
          </div>
        );
      }
    `;
    const violations = detectViolations(content);
    expect(violations).toHaveLength(1);
    expect(violations[0].snippet).toContain("setOpen(true)");
  });

  it("détecte un composant <Button> (kit) au même titre qu'un <button> natif", () => {
    const content = `
      export function X() {
        return <Button onClick={() => setDrawerOpen(true)}>Ouvrir</Button>;
      }
    `;
    expect(detectViolations(content)).toHaveLength(1);
  });

  it("ne détecte pas un déclencheur câblé via aria-expanded/aria-controls explicites", () => {
    const content = `
      export function X() {
        return (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen(true)}
          >
            Ouvrir
          </button>
        );
      }
    `;
    expect(detectViolations(content)).toHaveLength(0);
  });

  it("ne détecte pas un déclencheur câblé via usePanelTrigger (spread triggerProps)", () => {
    const content = `
      export function X() {
        const panel = usePanelTrigger(open);
        return (
          <Button {...panel.triggerProps} onClick={() => setOpen(true)}>
            Ouvrir
          </Button>
        );
      }
    `;
    expect(detectViolations(content)).toHaveLength(0);
  });

  it("ignore un bouton qui referme un panneau (setXxx(false) seul, sans true ni négation)", () => {
    // Doctrine du détecteur : aria-expanded/aria-controls sont l'affaire du
    // déclencheur qui OUVRE, pas du bouton "Annuler"/"Fermer" à l'intérieur
    // du panneau — cf. commentaire TOGGLE_CALL_RE du script.
    const content = `
      export function X() {
        return <Button onClick={() => setOpen(false)}>Fermer</Button>;
      }
    `;
    expect(detectViolations(content)).toHaveLength(0);
  });

  it("détecte un toggle par négation (setXxx(!xxx))", () => {
    const content = `
      export function X() {
        return <button onClick={() => setOpen(!open)}>Bascule</button>;
      }
    `;
    const violations = detectViolations(content);
    expect(violations).toHaveLength(1);
  });

  it("détecte un toggle par méthode .toggle(", () => {
    const content = `
      export function X() {
        return <button onClick={() => menu.toggle()}>Menu</button>;
      }
    `;
    expect(detectViolations(content)).toHaveLength(1);
  });

  it("ignore un bouton sans rapport avec la visibilité d'un panneau", () => {
    const content = `
      export function X() {
        return <Button onClick={() => save()}>Enregistrer</Button>;
      }
    `;
    expect(detectViolations(content)).toHaveLength(0);
  });

  it("ne casse pas sur un onClick multi-lignes avec des accolades et des comparaisons imbriquées", () => {
    // Reproduit le patron réel trouvé sur ce dépôt (CollectionsAdminPage.tsx) :
    // plusieurs instructions dans le corps, dont une comparaison (`a > b`)
    // qui ne doit jamais être confondue avec la fermeture de balise par le
    // scanner à profondeur d'accolades.
    const content = `
      export function X() {
        return (
          <Button
            size="sm"
            onClick={() => {
              const ok = a > b;
              setEditing(null);
              setRegistering(true);
            }}
          >
            Ajouter
          </Button>
        );
      }
    `;
    const violations = detectViolations(content);
    expect(violations).toHaveLength(1);
    expect(violations[0].snippet).toContain("setRegistering(true)");
  });

  it("ignore un commentaire qui contient un faux onClick de bascule", () => {
    const content = `
      // onClick={() => setOpen(true)} — ancien code, retiré
      export function X() {
        return <p>ok</p>;
      }
    `;
    expect(detectViolations(content)).toHaveLength(0);
  });
});
