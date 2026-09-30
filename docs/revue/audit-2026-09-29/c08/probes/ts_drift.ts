// Sonde c08 : les types manuscrits du shell acceptent-ils la forme générée depuis l'OpenAPI ?
import type { components } from "../../../../../shell/src/api/generated/core-schema";
import type { AppConfig, PipelineNode, Variable, DataSource, MapConfig } from "../../../../../shell/src/api/types";
type G = components["schemas"];
declare const b: G["BuilderConfig"];
declare const gp: NonNullable<G["BuilderConfig"]["pipeline"]>["nodes"][number];
export const v: Variable = {} as NonNullable<G["BuilderConfig"]["variables"]>[number];
export const ds: DataSource = {} as NonNullable<G["BuilderConfig"]["dataSources"]>[number];
export const pn: PipelineNode = gp;
export const mc: MapConfig = {} as NonNullable<G["BuilderConfig"]["map"]>;
export const ac: AppConfig = b;
