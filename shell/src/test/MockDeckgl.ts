// SPDX-License-Identifier: Apache-2.0
export const overlayInstances: MockMapboxOverlay[] = [];

export class MockDeckLayer {
  deckType: string;
  props: Record<string, unknown>;
  constructor(props: Record<string, unknown>) {
    this.props = props;
    this.deckType = (this.constructor as typeof MockDeckLayer).typeName;
  }
  static typeName = "MockDeckLayer";
}

export class HeatmapLayer extends MockDeckLayer {
  static typeName = "HeatmapLayer";
}
export class HexagonLayer extends MockDeckLayer {
  static typeName = "HexagonLayer";
}
export class ColumnLayer extends MockDeckLayer {
  static typeName = "ColumnLayer";
}
export class Tile3DLayer extends MockDeckLayer {
  static typeName = "Tile3DLayer";
}

export class MockMapboxOverlay {
  props: { layers: MockDeckLayer[] };
  // Kept verbatim so tests can assert on construction-time options that are
  // not layer props (e.g. `interleaved`).
  constructorProps: Record<string, unknown>;
  constructor(props: { layers?: MockDeckLayer[] } & Record<string, unknown> = {}) {
    this.constructorProps = props;
    this.props = { layers: props.layers ?? [] };
    overlayInstances.push(this);
  }
  setProps(props: { layers: MockDeckLayer[] }) {
    this.props = { ...this.props, ...props };
  }
  // MapboxOverlay implements the maplibre IControl interface.
  onAdd() {
    return document.createElement("div");
  }
  onRemove() {}
}
