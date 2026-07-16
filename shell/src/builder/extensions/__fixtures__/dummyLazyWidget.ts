// SPDX-License-Identifier: Apache-2.0
class DummyLazyWidget extends HTMLElement {}
if (!customElements.get("test-lazy-ready-widget")) {
  customElements.define("test-lazy-ready-widget", DummyLazyWidget);
}
