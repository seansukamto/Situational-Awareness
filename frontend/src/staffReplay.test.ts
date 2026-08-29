import { describe, expect, it } from "vitest";

import { buildReplayTimeline, buildStaffReplay, eventLocalMinute } from "./staffReplay";
import type { GameDay, GameDayEvent, StaffProfile, Store } from "./types";


const store: Store = {
  id: "store",
  name: "Store",
  timezone: "Asia/Singapore",
  floor_area_m2: 100,
  opening_minute: 600,
  closing_minute: 1320,
  zones: [
    { id: "sales", label: "Sales", center: { x: 1, z: 2 }, width: 6, depth: 4 },
    { id: "stock", label: "Stockroom", center: { x: -3, z: 4 }, width: 4, depth: 3 },
  ],
  equipment: [{
    id: "lights",
    label: "Lights",
    zone_id: "sales",
    position: { x: 4, z: 5 },
    state: "on",
    power_kw_by_state: { on: 1, standby: 0.1, off: 0 },
    criticality: "non_critical",
    customer_facing: false,
  }],
  agents: [],
  customers: [],
  tariff_sgd_per_kwh: 0.3,
  grid_emission_factor_kg_per_kwh: 0.4,
};

const staff: StaffProfile = {
  id: "staff_1",
  project_id: "project",
  display_name: "Ava",
  normalized_name: "ava",
  role: "closing_associate",
  avatar_id: "associate",
  authorized_zone_ids: ["sales", "stock"],
  authorized_equipment_ids: ["lights"],
  default_shift_start: 600,
  default_shift_end: 1320,
  active: true,
  created_at: "2026-08-29T00:00:00Z",
  updated_at: "2026-08-29T00:00:00Z",
};

const gameDay: GameDay = {
  id: "game",
  project_id: "project",
  local_date: "2026-08-29",
  timezone: "Asia/Singapore",
  start_minute: 600,
  end_minute: 1320,
  status: "completed",
  join_token: "demo",
  policy_version: "policy",
  scoring_version: "scoring",
  created_at: "2026-08-29T12:30:00Z",
  started_at: "2026-08-29T12:30:00Z",
  completed_at: "2026-08-29T12:30:00Z",
};

function event(seq: number, type: string, data: Record<string, unknown> = {}): GameDayEvent {
  return {
    seq,
    game_day_id: "game",
    occurred_at: "2026-08-29T12:30:00Z",
    type,
    message: type === "task_claimed" ? "Switch off lights was claimed." : "Event",
    staff_id: "staff_1",
    task_instance_id: type === "staff_joined" ? null : "task_1",
    zone_id: type === "task_claimed" ? "sales" : null,
    target_id: type === "task_claimed" ? "lights" : null,
    source: "staff",
    evidence_kind: "measured",
    data,
  };
}

describe("staff-only day replay", () => {
  it("reconstructs joins, task destinations, and individual points from the ledger", () => {
    const events = [event(1, "staff_joined"), event(2, "task_claimed"), event(3, "points_awarded", { points: 25 })];
    const beforeJoin = buildStaffReplay(store, [staff], events, 0);
    expect(beforeJoin.activeStaff.staff_1).toBe(false);

    const afterClaim = buildStaffReplay(store, [staff], events, 2);
    expect(afterClaim.activeStaff.staff_1).toBe(true);
    expect(afterClaim.staffPositions.staff_1).toEqual({ x: 4, z: 5 });
    expect(afterClaim.staffTaskLabels.staff_1).toBe("Switch off lights");

    const afterPoints = buildStaffReplay(store, [staff], events, 3);
    expect(afterPoints.staffPoints.staff_1).toBe(25);
    expect(afterPoints.staffTaskLabels.staff_1).toBeNull();
  });

  it("converts immutable UTC event timestamps into the store's local day minute", () => {
    expect(eventLocalMinute(event(1, "staff_joined"), "Asia/Singapore")).toBe(20 * 60 + 30);
  });

  it("projects a compressed demo interaction across the scheduled workday", () => {
    const events = [
      event(1, "day_started"),
      event(2, "staff_joined"),
      event(3, "task_claimed"),
      event(4, "task_completed"),
      event(5, "points_awarded", { points: 25 }),
      event(6, "day_completed"),
    ];
    const timeline = buildReplayTimeline(gameDay, [staff], events);
    const minuteByType = new Map(timeline.map((item) => [item.event.type, item.minute]));

    expect(minuteByType.get("day_started")).toBe(600);
    expect(minuteByType.get("staff_joined")).toBe(600);
    expect(minuteByType.get("task_claimed")).toBeGreaterThan(600);
    expect(minuteByType.get("task_completed")).toBeGreaterThan(minuteByType.get("task_claimed")!);
    expect(minuteByType.get("day_completed")).toBe(1320);
  });

  it("moves idle joined staff through authorized work zones during their shift", () => {
    const joined = [event(1, "staff_joined")];
    const first = buildStaffReplay(store, [staff], joined, 1, 610);
    const later = buildStaffReplay(store, [staff], joined, 1, 720);
    const afterShift = buildStaffReplay(store, [staff], joined, 1, 1321);

    expect(first.activeStaff.staff_1).toBe(true);
    expect(later.staffPositions.staff_1).not.toEqual(first.staffPositions.staff_1);
    expect(afterShift.activeStaff.staff_1).toBe(false);
  });
});
