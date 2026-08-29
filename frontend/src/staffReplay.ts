import type { GameDay, GameDayEvent, Position, StaffProfile, Store } from "./types";


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


function idleWorkPosition(
  store: Store,
  profile: StaffProfile,
  staffIndex: number,
  minute: number,
): Position {
  const authorizedZones = store.zones.filter((zone) => (
    !profile.authorized_zone_ids.length || profile.authorized_zone_ids.includes(zone.id)
  ));
  const zones = authorizedZones.length ? authorizedZones : store.zones;
  if (!zones.length) return initialPosition(store, profile, staffIndex);
  const workPeriod = Math.max(0, Math.floor((minute - profile.default_shift_start) / 35));
  const zone = zones[(workPeriod + staffIndex) % zones.length];
  const phase = (workPeriod * 3 + staffIndex * 5) % 8;
  const xDirection = phase % 2 === 0 ? -1 : 1;
  const zDirection = Math.floor(phase / 2) % 2 === 0 ? -1 : 1;
  const xOffset = Math.min(zone.width * 0.22, 1.05) * xDirection;
  const zOffset = Math.min(zone.depth * 0.22, 1.05) * zDirection;
  return { x: zone.center.x + xOffset, z: zone.center.z + zOffset };
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


function eventLocalDate(event: GameDayEvent, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(event.occurred_at));
  const year = parts.find((part) => part.type === "year")?.value ?? "0000";
  const month = parts.find((part) => part.type === "month")?.value ?? "00";
  const day = parts.find((part) => part.type === "day")?.value ?? "00";
  return `${year}-${month}-${day}`;
}


export type TimedGameDayEvent = { event: GameDayEvent; minute: number };


export function buildReplayTimeline(
  gameDay: GameDay,
  staff: StaffProfile[],
  events: GameDayEvent[],
): TimedGameDayEvent[] {
  const actual = events.map((event) => ({
    event,
    minute: Math.max(
      gameDay.start_minute,
      Math.min(gameDay.end_minute, eventLocalMinute(event, gameDay.timezone)),
    ),
  }));
  const actualMinutes = actual.map((item) => item.minute);
  const actualSpan = actualMinutes.length
    ? Math.max(...actualMinutes) - Math.min(...actualMinutes)
    : 0;
  const eventsMatchGameDate = events.every((event) => (
    eventLocalDate(event, gameDay.timezone) === gameDay.local_date
  ));
  if (eventsMatchGameDate && actualSpan >= 60) {
    return actual.sort((left, right) => left.minute - right.minute || left.event.seq - right.event.seq);
  }

  const staffById = new Map(staff.map((profile) => [profile.id, profile]));
  const joinedStaffIds = events
    .filter((event) => event.type === "staff_joined" && event.staff_id)
    .map((event) => event.staff_id as string);
  const joinOrder = new Map(joinedStaffIds.map((staffId, index) => [staffId, index]));
  const claimedTaskIds = events
    .filter((event) => event.type === "task_claimed" && event.task_instance_id)
    .map((event) => event.task_instance_id as string);
  const uniqueClaimedTaskIds = [...new Set(claimedTaskIds)];
  const firstWorkMinute = gameDay.start_minute + 90;
  const lastWorkMinute = Math.max(firstWorkMinute, gameDay.end_minute - 120);
  const workSpacing = uniqueClaimedTaskIds.length
    ? (lastWorkMinute - firstWorkMinute) / (uniqueClaimedTaskIds.length + 1)
    : 0;
  const taskMinute = new Map(uniqueClaimedTaskIds.map((taskId, index) => [
    taskId,
    Math.round(firstWorkMinute + workSpacing * (index + 1)),
  ]));
  const completionMinute = new Map<string, number>();

  const projected = events.map((event) => {
    let minute = actual.find((item) => item.event.seq === event.seq)?.minute
      ?? gameDay.start_minute;
    if (event.type === "day_created" || event.type === "day_started") {
      minute = gameDay.start_minute;
    } else if (event.type === "task_released") {
      minute = Math.min(gameDay.end_minute, gameDay.start_minute + 10);
    } else if (event.type === "staff_joined" && event.staff_id) {
      const profile = staffById.get(event.staff_id);
      minute = Math.max(
        gameDay.start_minute,
        Math.min(
          gameDay.end_minute,
          (profile?.default_shift_start ?? gameDay.start_minute)
            + (joinOrder.get(event.staff_id) ?? 0) * 4,
        ),
      );
    } else if (event.type === "task_claimed" && event.task_instance_id) {
      minute = taskMinute.get(event.task_instance_id) ?? firstWorkMinute;
    } else if (event.type === "task_completed" && event.task_instance_id) {
      minute = Math.min(
        gameDay.end_minute - 2,
        (taskMinute.get(event.task_instance_id) ?? firstWorkMinute) + 25,
      );
      completionMinute.set(event.task_instance_id, minute);
    } else if (event.type === "points_awarded" && event.task_instance_id) {
      minute = Math.min(
        gameDay.end_minute - 1,
        (completionMinute.get(event.task_instance_id)
          ?? (taskMinute.get(event.task_instance_id) ?? firstWorkMinute) + 25) + 1,
      );
    } else if (event.type === "day_completed") {
      minute = gameDay.end_minute;
    }
    return { event, minute };
  });
  return projected.sort((left, right) => left.minute - right.minute || left.event.seq - right.event.seq);
}


export function buildStaffReplay(
  store: Store,
  staff: StaffProfile[],
  events: GameDayEvent[],
  step: number,
  minute?: number,
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
  staff.forEach((profile, index) => {
    if (!state.activeStaff[profile.id] || minute == null) return;
    const insideShift = minute >= profile.default_shift_start
      && minute <= profile.default_shift_end;
    state.activeStaff[profile.id] = insideShift;
    if (insideShift && !state.staffTaskLabels[profile.id]) {
      state.staffPositions[profile.id] = idleWorkPosition(store, profile, index, minute);
    }
  });
  return state;
}
