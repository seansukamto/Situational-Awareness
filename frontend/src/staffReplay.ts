import type { GameDayEvent, Position, StaffProfile, Store } from "./types";


export type StaffReplayState = {
  staffPositions: Record<string, Position>;
  activeStaff: Record<string, boolean>;
  staffPoints: Record<string, number>;
  staffTaskLabels: Record<string, string | null>;
};


function initialPosition(store: Store, profile: StaffProfile, index: number): Position {
  const zone = store.zones.find((item) => profile.authorized_zone_ids.includes(item.id))
    ?? store.zones[index % Math.max(store.zones.length, 1)];
  if (!zone) return { x: index * 0.7, z: 0 };
  const column = index % 3;
  const row = Math.floor(index / 3) % 3;
  return {
    x: zone.center.x + (column - 1) * Math.min(zone.width / 5, 0.8),
    z: zone.center.z + (row - 1) * Math.min(zone.depth / 5, 0.8),
  };
}


function eventDestination(store: Store, event: GameDayEvent): Position | null {
  const equipment = event.target_id
    ? store.equipment.find((item) => item.id === event.target_id)
    : null;
  if (equipment) return equipment.position;
  const zone = event.zone_id ? store.zones.find((item) => item.id === event.zone_id) : null;
  return zone?.center ?? null;
}


export function eventLocalMinute(event: GameDayEvent, timezone: string): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(event.occurred_at));
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? 0);
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? 0);
  return hour * 60 + minute;
}


export function buildStaffReplay(
  store: Store,
  staff: StaffProfile[],
  events: GameDayEvent[],
  step: number,
): StaffReplayState {
  const state: StaffReplayState = {
    staffPositions: Object.fromEntries(staff.map((profile, index) => [
      profile.id,
      initialPosition(store, profile, index),
    ])),
    activeStaff: Object.fromEntries(staff.map((profile) => [profile.id, false])),
    staffPoints: Object.fromEntries(staff.map((profile) => [profile.id, 0])),
    staffTaskLabels: Object.fromEntries(staff.map((profile) => [profile.id, null])),
  };

  for (const event of events.slice(0, step)) {
    if (!event.staff_id) continue;
    if (event.type === "staff_joined") state.activeStaff[event.staff_id] = true;
    if (event.type === "task_claimed" || event.type === "task_completed") {
      state.activeStaff[event.staff_id] = true;
      const destination = eventDestination(store, event);
      if (destination) state.staffPositions[event.staff_id] = destination;
      state.staffTaskLabels[event.staff_id] = event.message.replace(/ was (claimed|completed)\.$/, "");
    }
    if (event.type === "points_awarded") {
      const points = typeof event.data.points === "number" ? event.data.points : 0;
      state.staffPoints[event.staff_id] = (state.staffPoints[event.staff_id] ?? 0) + points;
      state.staffTaskLabels[event.staff_id] = null;
    }
  }
  return state;
}
