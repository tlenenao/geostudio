class ThrowingExtensionWidget extends HTMLElement {
  set props(value) {
    this._props = value || {};
  }

  get props() {
    return this._props;
  }

  connectedCallback() {
    this.textContent = "widget qui plante";
  }

  boom() {
    throw new Error("boom");
  }
}

if (!customElements.get("throwing-extension-widget")) {
  customElements.define("throwing-extension-widget", ThrowingExtensionWidget);
}
