export type Recorded = { id: string; spec: unknown };

export const mapInstances: MockMap[] = [];

export class MockMap {
  opts: { style: string; center: [number, number]; zoom: number };
  handlers: Record<string, Array<() => void>> = {};
  sources: Recorded[] = [];
  layers: { id: string; [k: string]: unknown }[] = [];
  controls: unknown[] = [];
  removed = false;

  constructor(opts: MockMap["opts"]) {
    this.opts = opts;
    mapInstances.push(this);
  }

  on(event: string, cb: () => void) {
    (this.handlers[event] ??= []).push(cb);
    if (event === "load") cb();
    return this;
  }
  fire(event: string) {
    this.handlers[event]?.forEach((cb) => cb());
  }
  addSource(id: string, spec: unknown) {
    this.sources.push({ id, spec });
  }
  addLayer(layer: { id: string; [k: string]: unknown }) {
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
  loaded() {
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
