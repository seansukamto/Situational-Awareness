import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  createStaffProfile,
  listAvatars,
  listStaffProfiles,
  resetStaffPin,
  updateStaffProfile,
} from "../api";
import type { Project, StaffProfileCreate, StaffRole } from "../types";


function minuteToTime(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}


function timeToMinute(value: string): number {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}


function roleLabel(role: StaffRole): string {
  return role.replaceAll("_", " ").replace(/\b\w/g, (value) => value.toUpperCase());
}


function initialValues(project: Project): StaffProfileCreate {
  return {
    display_name: "",
    role: "closing_associate",
    avatar_id: "associate",
    authorized_zone_ids: project.store.zones.map((zone) => zone.id),
    authorized_equipment_ids: project.store.equipment
      .filter((equipment) => equipment.criticality !== "protected")
      .map((equipment) => equipment.id),
    default_shift_start: project.store.opening_minute,
    default_shift_end: project.store.closing_minute,
    join_pin: "",
  };
}


export function StaffConfigurationPage({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [values, setValues] = useState<StaffProfileCreate>(() => initialValues(project));
  const staff = useQuery({
    queryKey: ["staff", project.id],
    queryFn: () => listStaffProfiles(project.id),
  });
  const avatars = useQuery({ queryKey: ["avatars"], queryFn: listAvatars });
  const avatarMap = useMemo(
    () => new Map((avatars.data ?? []).map((avatar) => [avatar.id, avatar])),
    [avatars.data],
  );
  const create = useMutation({
    mutationFn: () => createStaffProfile(project.id, values),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["staff", project.id] });
      setValues(initialValues(project));
      setShowCreate(false);
    },
  });
  const update = useMutation({
    mutationFn: ({ staffId, active }: { staffId: string; active: boolean }) => (
      updateStaffProfile(project.id, staffId, { active })
    ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["staff", project.id] }),
  });
  const resetPin = useMutation({
    mutationFn: ({ staffId, pin }: { staffId: string; pin: string }) => (
      resetStaffPin(project.id, staffId, pin)
    ),
  });

  const toggleZone = (zoneId: string) => setValues((current) => ({
    ...current,
    authorized_zone_ids: current.authorized_zone_ids.includes(zoneId)
      ? current.authorized_zone_ids.filter((id) => id !== zoneId)
      : [...current.authorized_zone_ids, zoneId],
  }));
  const toggleEquipment = (equipmentId: string) => setValues((current) => ({
    ...current,
    authorized_equipment_ids: current.authorized_equipment_ids.includes(equipmentId)
      ? current.authorized_equipment_ids.filter((id) => id !== equipmentId)
      : [...current.authorized_equipment_ids, equipmentId],
  }));

  return (
    <section className="staff-config-page" aria-label="Staff configuration">
      <div className="staff-config-hero">
        <div>
          <span className="kicker">Player roster</span>
          <h1>Build the store team.</h1>
          <p>Each profile controls the name, role, safe task boundary, shift, and local 3D character used in the staff game.</p>
        </div>
        <div className="staff-roster-stats">
          <span><b>{(staff.data ?? []).filter((item) => item.active).length}</b> active players</span>
          <span><b>{avatars.data?.length ?? 0}</b> local characters</span>
          <button type="button" onClick={() => setShowCreate(true)}>＋ Add staff player</button>
        </div>
      </div>

      {staff.isLoading && <div className="staff-empty-card">Loading the staff roster…</div>}
      {!staff.isLoading && !staff.data?.length && (
        <div className="staff-empty-card">
          <span>01</span>
          <h2>No staff players yet</h2>
          <p>Create the roster before opening a daily task market.</p>
          <button type="button" onClick={() => setShowCreate(true)}>Create first staff profile</button>
        </div>
      )}

      <div className="staff-roster-grid">
        {(staff.data ?? []).map((profile, index) => {
          const avatar = avatarMap.get(profile.avatar_id);
          return (
            <article className={`staff-profile-card ${profile.active ? "" : "inactive"}`} key={profile.id}>
              <div className={`staff-avatar-tile avatar-${profile.avatar_id}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{profile.display_name.slice(0, 1).toUpperCase()}</strong>
                <small>3D</small>
              </div>
              <div className="staff-profile-copy">
                <span>{profile.active ? "Active player" : "Inactive profile"}</span>
                <h2>{profile.display_name}</h2>
                <p>{avatar?.label ?? profile.avatar_id} · {roleLabel(profile.role)}</p>
                <div>
                  <small>{minuteToTime(profile.default_shift_start)}–{minuteToTime(profile.default_shift_end)}</small>
                  <small>{profile.authorized_zone_ids.length || "All"} zones</small>
                  <small>{profile.authorized_equipment_ids.length || "Role"} loads</small>
                </div>
              </div>
              <div className="staff-profile-actions">
                <button
                  type="button"
                  onClick={() => {
                    const pin = window.prompt(`New 4–8 digit PIN for ${profile.display_name}`);
                    if (pin) resetPin.mutate({ staffId: profile.id, pin });
                  }}
                >Reset PIN</button>
                <button
                  type="button"
                  onClick={() => update.mutate({ staffId: profile.id, active: !profile.active })}
                >{profile.active ? "Deactivate" : "Reactivate"}</button>
              </div>
            </article>
          );
        })}
      </div>

      {showCreate && (
        <div className="modal-backdrop" role="presentation">
          <section className="staff-create-modal" role="dialog" aria-modal="true" aria-labelledby="staff-create-title">
            <button className="modal-close" type="button" aria-label="Close" onClick={() => setShowCreate(false)}>×</button>
            <span className="kicker">New player</span>
            <h2 id="staff-create-title">Create staff profile</h2>
            <form onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
              <div className="staff-form-grid">
                <label><span>Display name</span><input required minLength={2} maxLength={80} value={values.display_name} onChange={(event) => setValues({ ...values, display_name: event.target.value })} /></label>
                <label><span>Role</span><select value={values.role} onChange={(event) => setValues({ ...values, role: event.target.value as StaffRole })}><option value="closing_associate">Closing associate</option><option value="manager">Manager</option><option value="cashier">Cashier</option></select></label>
                <label><span>Shift start</span><input type="time" value={minuteToTime(values.default_shift_start)} onChange={(event) => setValues({ ...values, default_shift_start: timeToMinute(event.target.value) })} /></label>
                <label><span>Shift end</span><input type="time" value={minuteToTime(values.default_shift_end)} onChange={(event) => setValues({ ...values, default_shift_end: timeToMinute(event.target.value) })} /></label>
                <label><span>Join PIN</span><input required inputMode="numeric" pattern="[0-9]{4,8}" placeholder="4–8 digits" value={values.join_pin} onChange={(event) => setValues({ ...values, join_pin: event.target.value })} /></label>
              </div>

              <fieldset className="avatar-picker">
                <legend>3D character</legend>
                {(avatars.data ?? []).map((avatar) => (
                  <button type="button" key={avatar.id} className={values.avatar_id === avatar.id ? "selected" : ""} onClick={() => setValues({ ...values, avatar_id: avatar.id })}>
                    <span>{avatar.label.slice(0, 1)}</span><strong>{avatar.label}</strong><small>{avatar.description}</small>
                  </button>
                ))}
              </fieldset>

              <fieldset className="authorization-picker">
                <legend>Authorized zones</legend>
                {project.store.zones.map((zone) => <label key={zone.id}><input type="checkbox" checked={values.authorized_zone_ids.includes(zone.id)} onChange={() => toggleZone(zone.id)} /><span>{zone.label}</span></label>)}
              </fieldset>
              <fieldset className="authorization-picker">
                <legend>Authorized equipment</legend>
                {project.store.equipment.filter((item) => item.criticality !== "protected").map((item) => <label key={item.id}><input type="checkbox" checked={values.authorized_equipment_ids.includes(item.id)} onChange={() => toggleEquipment(item.id)} /><span>{item.label}</span></label>)}
              </fieldset>

              {create.isError && <p className="form-error">{create.error.message}</p>}
              <div className="run-create-actions"><button type="button" onClick={() => setShowCreate(false)}>Cancel</button><button className="primary" type="submit" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create player"}</button></div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
