import type {
  EquipmentState,
  Position,
  SimulationEvent,
  Store,
  WorldState,
} from "./types";

function asPosition(value: unknown): Position | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as { x?: unknown; z?: unknown };
  return typeof candidate.x === "number" && typeof candidate.z === "number"
    ? { x: candidate.x, z: candidate.z }
    : null;
}

export function buildWorld(store: Store, events: SimulationEvent[], step: number): WorldState {
  const world: WorldState = {
    staffPositions: Object.fromEntries(store.agents.map((agent) => [agent.id, agent.position])),
    customerPositions: Object.fromEntries(
      store.customers.map((customer) => [customer.id, customer.position]),
    ),
    activeCustomers: Object.fromEntries(
      store.customers.map((customer) => [customer.id, customer.active]),
    ),
    equipmentStates: Object.fromEntries(
      store.equipment.map((equipment) => [equipment.id, equipment.state]),
    ),
    customerCount: store.customers.filter((customer) => customer.active).length,
  };
  const awaitingExitCommit = new Set<string>();

  for (const event of events.slice(0, step)) {
    const nextPosition = asPosition(event.data.to);
    if (event.type === "agent_moved" && event.agent_id && nextPosition) {
      world.staffPositions[event.agent_id] = nextPosition;
    }
    if (event.type === "customer_moved" && event.agent_id && nextPosition) {
      world.customerPositions[event.agent_id] = nextPosition;
    }
    if (event.type === "customer_exited" && event.agent_id) {
      if (nextPosition) world.customerPositions[event.agent_id] = nextPosition;
      awaitingExitCommit.add(event.agent_id);
    }
    if (event.type === "customer_count_changed" && typeof event.data.customer_count === "number") {
      for (const customerId of awaitingExitCommit) {
        world.activeCustomers[customerId] = false;
      }
      awaitingExitCommit.clear();
      world.customerCount = event.data.customer_count;
    }
    if (event.type === "equipment_state_changed" && event.target_id) {
      world.equipmentStates[event.target_id] = event.data.to as EquipmentState;
    }
  }
  return world;
}
