class GaugeExtensionWidget extends HTMLElement {
  constructor() {
    super();
    this._count = 0;
    this._initialized = false;
  }

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

  reset() {
    this._count = Number(this._props?.initial ?? 0);
    this._render();
  }

  _increment() {
    this._count += 1;
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

if (!customElements.get("gauge-extension-widget")) {
  customElements.define("gauge-extension-widget", GaugeExtensionWidget);
}
