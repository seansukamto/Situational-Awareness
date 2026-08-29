import { describe, expect, it } from "vitest";

import type { SimulationEvent, Store } from "./types";
import { buildWorld } from "./world";

const store: Store = {
  id: "store",
  name: "Test store",
  timezone: "Asia/Singapore",
  floor_area_m2: 100,
  opening_minute: 480,
  closing_minute: 1320,
  zones: [],
  equipment: [{
    id: "lights",
    label: "Lights",
    zone_id: "floor",
    position: { x: 0, z: 0 },
    state: "on",
    power_kw_by_state: { on: 1, standby: 0.1, off: 0 },
    criticality: "non_critical",
    customer_facing: true,
  }],
  agents: [{
    id: "staff",
    label: "Staff",
    role: "closing_associate",
    zone_id: "floor",
    position: { x: 0, z: 0 },
    checklist_completed: false,
    shift_ended: false,
  }],
  customers: [{
    id: "customer",
    label: "Customer",
    segment: "browser",
    zone_id: "floor",
    position: { x: 1, z: 1 },
    active: true,
    satisfaction: 0.9,
  }],
  tariff_sgd_per_kwh: 0.32,
  grid_emission_factor_kg_per_kwh: 0.4,
};

const events: SimulationEvent[] = [
  { seq: 1, at_minute: 1320, type: "agent_moved", message: "moved", agent_id: "staff", target_id: "lights", data: { to: { x: 2, z: 3 } } },
  { seq: 2, at_minute: 1321, type: "equipment_state_changed", message: "off", agent_id: "staff", target_id: "lights", data: { to: "off" } },
  { seq: 3, at_minute: 1322, type: "customer_exited", message: "left", agent_id: "customer", target_id: null, data: { to: { x: -6, z: -3 } } },
  { seq: 4, at_minute: 1322, type: "customer_count_changed", message: "empty", agent_id: null, target_id: null, data: { customer_count: 0 } },
];

describe("buildWorld", () => {
  it("reconstructs authoritative state at a replay step", () => {
    const world = buildWorld(store, events, events.length);
    expect(world.staffPositions.staff).toEqual({ x: 2, z: 3 });
    expect(world.equipmentStates.lights).toBe("off");
    expect(world.activeCustomers.customer).toBe(false);
    expect(world.customerCount).toBe(0);
  });

  it("does not apply future events", () => {
    const world = buildWorld(store, events, 1);
    expect(world.equipmentStates.lights).toBe("on");
    expect(world.activeCustomers.customer).toBe(true);
  });

  it("lets a customer animate to the exit before removing the character", () => {
    const exiting = buildWorld(store, events, 3);
    expect(exiting.customerPositions.customer).toEqual({ x: -6, z: -3 });
    expect(exiting.activeCustomers.customer).toBe(true);

    const exited = buildWorld(store, events, 4);
    expect(exited.activeCustomers.customer).toBe(false);
  });
});
