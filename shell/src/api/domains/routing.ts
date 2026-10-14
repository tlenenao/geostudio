// SPDX-License-Identifier: Apache-2.0
// ARC-34 : routage (Valhalla derrière le cœur). Service absent = ApiError 503 lisible.
import type { ItemClient, RouteCosting, RoutePoint, RouteResult } from "../types";
import type { ItemClientBase } from "../base";

type RoutingMethods = Pick<ItemClient, "computeRoute">;

export function createRoutingMethods(base: Pick<ItemClientBase, "request">): RoutingMethods {
  return {
    async computeRoute(points: RoutePoint[], costing: RouteCosting = "auto"): Promise<RouteResult> {
      return base.request<RouteResult>("POST", "/routing/route", { points, costing });
    },
  };
}
