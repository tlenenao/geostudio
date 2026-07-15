// SPDX-License-Identifier: Apache-2.0
import { LitElement, css, html } from "lit";
import { registerWcWidget } from "../wc/registerWcWidget";
import type { WcWidgetManifest } from "../wc/manifest";

// Vanilla Lit reactive-properties API (no decorators): this project's
// tsconfig (useDefineForClassFields + no experimentalDecorators) drives
// esbuild to emit standard TC39 decorators, which lit/decorators.js does
// not yet fully support ("Unsupported decorator location: field").
export class GsCounter extends LitElement {
  static properties = {
    props: { attribute: false },
    count: { state: true },
  };

  static styles = css`
    :host {
      display: flex;
      height: 100%;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 0.25rem;
      font-family: var(--gs-font, system-ui, sans-serif);
    }
    span {
      font-size: 1.5rem;
      font-weight: 600;
      color: var(--gs-color-text, #0f172a);
    }
    button {
      border: 1px solid var(--gs-color-border, #cbd5e1);
      border-radius: var(--gs-radius, 0.375rem);
      padding: 0.25rem 0.5rem;
      font-size: 0.875rem;
      background: var(--gs-color-surface, #f8fafc);
      cursor: pointer;
    }
  `;

  declare props: { initial?: number };
  declare count: number;
  private initialized = false;

  constructor() {
    super();
    this.props = {};
    this.count = 0;
  }

  protected willUpdate(): void {
    if (!this.initialized) {
      this.count = Number(this.props?.initial ?? 0);
      this.initialized = true;
    }
  }

  reset(): void {
    this.count = Number(this.props?.initial ?? 0);
  }

  private increment(): void {
    this.count += 1;
    this.dispatchEvent(new CustomEvent("changed", { detail: { count: this.count } }));
  }

  protected render() {
    return html`
      <span>${this.count}</span>
      <button type="button" @click=${this.increment}>+1</button>
    `;
  }
}

if (!customElements.get("gs-counter")) {
  customElements.define("gs-counter", GsCounter);
}

export const counterWcManifest: WcWidgetManifest = {
  type: "example.counter-wc",
  tag: "gs-counter",
  label: "Compteur (WC)",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
  events: ["changed"],
  actions: ["reset"],
  defaultSize: { w: 2, h: 2 },
};

export function registerCounterWcExampleWidget(): void {
  registerWcWidget(counterWcManifest);
}
