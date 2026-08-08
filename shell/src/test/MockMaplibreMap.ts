// SPDX-License-Identifier: Apache-2.0
export type Recorded = { id: string; spec: unknown };

export const mapInstances: MockMap[] = [];

export class MockMap {
  opts: { style: string; center: [number, number]; zoom: number };
  handlers: Record<string, Array<() => void>> = {};
  layerHandlers: Record<string, Array<(e: unknown) => void>> = {};
  sources: Recorded[] = [];
  layers: { id: string; [k: string]: unknown }[] = [];
  controls: unknown[] = [];
  removed = false;
  throwOnAddLayer = new Set<string>();
  flyToArgs: unknown[] = [];
  fitBoundsArgs: unknown[] = [];
  bounds: [[number, number], [number, number]] = [[0, 0], [0, 0]];

  constructor(opts: MockMap["opts"]) {
    this.opts = opts;
    mapInstances.push(this);
  }

  on(event: string, arg2: string | (() => void), cb?: (e: unknown) => void) {
    if (typeof arg2 === "string" && cb) {
      const key = `${event}:${arg2}`;
      (this.layerHandlers[key] ??= []).push(cb);
    } else if (typeof arg2 === "function") {
      (this.handlers[event] ??= []).push(arg2);
      if (event === "load") arg2();
    }
    return this;
  }
  off(event: string, layerId: string, cb: (e: unknown) => void) {
    const key = `${event}:${layerId}`;
    this.layerHandlers[key] = (this.layerHandlers[key] ?? []).filter((h) => h !== cb);
  }
  once(event: string, cb: () => void) {
    const wrapped = () => {
      this.handlers[event] = (this.handlers[event] ?? []).filter((h) => h !== wrapped);
      cb();
    };
    (this.handlers[event] ??= []).push(wrapped);
    return this;
  }
  fire(event: string) {
    // Iterate a snapshot: `once` handlers mutate this.handlers[event] while
    // firing, which would otherwise desync a live forEach mid-iteration.
    [...(this.handlers[event] ?? [])].forEach((cb) => cb());
  }
  fireOnLayer(event: string, layerId: string, payload: unknown) {
    this.layerHandlers[`${event}:${layerId}`]?.forEach((cb) => cb(payload));
  }
  addSource(id: string, spec: unknown) {
    const rec: Recorded & { setData?: (d: unknown) => void } = { id, spec };
    rec.setData = (d: unknown) => {
      rec.spec = { ...(rec.spec as object), data: d };
    };
    this.sources.push(rec);
  }
  flyTo(opts: unknown) {
    this.flyToArgs.push(opts);
  }
  fitBounds(bounds: unknown, opts?: unknown) {
    this.fitBoundsArgs.push({ bounds, opts });
  }
  addLayer(layer: { id: string; [k: string]: unknown }) {
    if (this.throwOnAddLayer.has(layer.id)) throw new Error(`boom ${layer.id}`);
    this.layers.push(layer);
  }
  getLayer(id: string) {
    return this.layers.find((l) => l.id === id);
  }
  getSource(id: string) {
    return this.sources.find((s) => s.id === id);
  }
  removeLayer(id: string) {
    this.layers = this.layers.filter((l) => l.id !== id);
  }
  removeSource(id: string) {
    this.sources = this.sources.filter((s) => s.id !== id);
  }
  getCenter() {
    return { lng: this.opts.center[0], lat: this.opts.center[1] };
  }
  getZoom() {
    return this.opts.zoom;
  }
  getBounds() {
    return { toArray: () => this.bounds };
  }
  loaded() {
    return true;
  }
  isStyleLoaded() {
    return true;
  }
  addControl(control: unknown) {
    this.controls.push(control);
    return this;
  }
  removeControl(control: unknown) {
    this.controls = this.controls.filter((c) => c !== control);
    return this;
  }
  remove() {
    this.removed = true;
  }
}
