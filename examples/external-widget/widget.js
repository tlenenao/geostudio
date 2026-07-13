// widget.js — GeoStudio external Web Component widget example.
//
// Zero build step, zero dependency: this file is exactly what a third-party
// author would write and host themselves. It only relies on browser-native
// APIs (customElements, CustomEvent) — see manifest.json next to this file
// and docs/guides/2026-07-13-ecrire-un-widget-web-component.md.
class ExternalExampleWidget extends HTMLElement {
  constructor() {
    super();
    this._count = 0;
    this._initialized = false;
  }

  // GeoStudio assigns props/data/user/navigate as DOM properties (never as
  // serialized attributes) right after mounting the element.
  set props(value) {
    this._props = value || {};
    if (!this._initialized) {
      this._count = Number(this._props.initial ?? 0);
      this._initialized = true;
    }
    this._render();
  }

  get props() {
    return this._props;
  }

  connectedCallback() {
    this._render();
  }

  // Public method invoked when a composed action from the GeoStudio action
  // bus targets this widget's "reset" action (declared in manifest.json).
  reset() {
    this._count = Number(this._props?.initial ?? 0);
    this._render();
  }

  _increment() {
    this._count += 1;
    // Dispatched as a CustomEvent; GeoStudio relays it to the action bus
    // under the manifest's "changed" event.
    this.dispatchEvent(new CustomEvent("changed", { detail: { count: this._count } }));
    this._render();
  }

  _render() {
    this.innerHTML = "";
    const wrapper = document.createElement("div");
    wrapper.style.cssText =
      "display:flex;height:100%;flex-direction:column;align-items:center;justify-content:center;" +
      "gap:.25rem;font-family:var(--gs-font,system-ui,sans-serif);";
    const span = document.createElement("span");
    span.textContent = String(this._count);
    // GeoStudio's theme is inherited through the --gs-* CSS variables it
    // sets on an ancestor — a widget just needs to consume them.
    span.style.cssText = "font-size:1.5rem;font-weight:600;color:var(--gs-color-text,#0f172a);";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "+1";
    button.addEventListener("click", () => this._increment());
    wrapper.appendChild(span);
    wrapper.appendChild(button);
    this.appendChild(wrapper);
  }
}

// customElements.define as a side effect of importing this module is the
// entire contract — GeoStudio requires no other export.
if (!customElements.get("external-example-widget")) {
  customElements.define("external-example-widget", ExternalExampleWidget);
}
