"use strict";

(() => {
  const address = "DE:MO:00:00:00:01";
  const nowIso = () => new Date().toISOString();
  const makeSlot = (number, statusCode, overrides = {}) => ({
    slot: number,
    battery_type_code: 0,
    battery_type: "Li-Ion",
    mode_code: statusCode === 2 ? 3 : 0,
    mode: statusCode === 2 ? "Entladen" : "Laden",
    status_code: statusCode,
    status: { 0: "Bereit", 1: "Laden", 2: "Entladen", 3: "Pause", 4: "Fertig" }[statusCode],
    active: [1, 2, 3].includes(statusCode),
    time_s: 4280 + number * 317,
    voltage_v: 3.61 + number * 0.09,
    current_a: statusCode === 2 ? -1.0 : statusCode === 1 ? 1.25 : 0,
    capacity_mah: statusCode === 0 ? 0 : 640 + number * 171,
    temperature_c: 25 + number,
    resistance_mohm: 28 + number * 3,
    cycle_count: 1,
    ...overrides,
  });
  const device = {
    address,
    alias: "Workbench",
    enabled: true,
    released: false,
    serial_number: "DEMO-1000",
    state: "connected",
    connected: true,
    error: null,
    last_update: nowIso(),
    version: { firmware: "1.25", hardware: "2.2" },
    basic: { input_voltage_v: 12.184, fan_mode: 0 },
    slots: [
      makeSlot(1, 1),
      makeSlot(2, 2, { voltage_v: 3.482, capacity_mah: 1814 }),
      makeSlot(3, 3, { voltage_v: 4.118, capacity_mah: 1980 }),
      makeSlot(4, 4, { voltage_v: 4.196, capacity_mah: 2051 }),
    ],
    battery_ids: { 1: 1, 2: 2, 3: 3, 4: 4 },
    profile_ids: {},
    programs: {
      1: { label: "Standard charge", source: "automatic" },
      2: { label: "Capacity test", source: "automatic" },
      3: { label: "Refresh", source: "automatic" },
      4: { label: "Gentle charge", source: "automatic" },
    },
  };

  const automaticPrograms = [
    ["gentle_charge", "Gentle charge", "Charges at 0.5 C.", 0, 0.5],
    ["standard_charge", "Standard charge", "Charges at 1 C.", 0, 1],
    ["capacity_test", "Capacity test", "Discharges at 1 C and records capacity.", 3, 0.5],
    ["refresh", "Refresh", "Charge, discharge and recharge.", 1, 0.5],
    ["cycle", "Cycle C-D-C", "One complete C-D-C cycle.", 4, 0.5],
  ].map(([key, label, description, modeCode, rate]) => ({
    key, label, description, mode_code: modeCode,
    charge_c_rate: rate, discharge_c_rate: 1, cycle_count: 1,
    cycle_mode: 1, charge_rest_min: 5, discharge_rest_min: 5,
    temp_limit_c: 45, time_limit_mode: "manual", time_limit_min: 360,
    mode: ["Charge", "Refresh", "", "Capacity test", "Cycle"][modeCode],
    is_builtin: true, category_key: "automatic",
  }));
  const batteryOptions = {
    battery_types: [{ code: 0, name: "Li-Ion" }, { code: 1, name: "LiFePO4" }],
    modes: [{ code: 0, name: "Charge" }, { code: 1, name: "Refresh" }, { code: 3, name: "Capacity test" }, { code: 4, name: "Cycle" }],
    c_rates: [0.25, 0.5, 1, 1.5, 2],
    current_limits_ma: { charge_min: 50, charge_max: 3000, discharge_min: 50, discharge_max: 2000, step: 10 },
    time_limit_modes: [{ value: "automatic", label: "Automatic" }, { value: "manual", label: "Manual" }, { value: "off", label: "Off" }],
    default_manual_time_limit_min: 360,
    cycle_modes: [{ code: 0, name: "C-D" }, { code: 1, name: "C-D-C" }, { code: 2, name: "D-C" }, { code: 3, name: "D-C-D" }],
    automatic_programs: automaticPrograms,
  };
  const profileOptions = {
    battery_types: [
      { code: 0, name: "Li-Ion", nickel: false, modes: [{ code: 0, name: "Charge" }, { code: 1, name: "Refresh" }, { code: 2, name: "Storage" }, { code: 3, name: "Discharge" }, { code: 4, name: "Cycle" }], defaults: { charge_min_mv: 4000, charge_max_mv: 4250, charge_default_mv: 4200, discharge_min_mv: 2500, discharge_max_mv: 3650, discharge_default_mv: 3000, keep_min_mv: 3980, keep_max_mv: 4180, keep_default_mv: 4150 } },
      { code: 1, name: "LiFePO4", nickel: false, modes: [{ code: 0, name: "Charge" }, { code: 1, name: "Refresh" }, { code: 2, name: "Storage" }, { code: 3, name: "Discharge" }, { code: 4, name: "Cycle" }], defaults: { charge_min_mv: 3400, charge_max_mv: 3650, charge_default_mv: 3600, discharge_min_mv: 2000, discharge_max_mv: 3150, discharge_default_mv: 2900, keep_min_mv: 3380, keep_max_mv: 3580, keep_default_mv: 3550 } },
    ],
    time_limit_modes: batteryOptions.time_limit_modes,
    automatic_time_limit_factor: 1.5,
    default_manual_time_limit_min: 360,
  };
  const categories = [
    { key: "automatic", name: "Automatic profiles", description: "Capacity-based programs.", is_builtin: true, sort_order: 0 },
    { key: "lithium", name: "Lithium profiles", description: "Profiles for lithium cells.", is_builtin: true, sort_order: 1 },
    { key: "general", name: "General", description: "Other profiles.", is_builtin: true, sort_order: 2 },
  ];
  const profileDefaults = { battery_type_code: 0, battery_type: "Li-Ion", capacity_mah: 3000, charge_current_ma: 1000, discharge_current_ma: 700, charge_voltage_mv: 4200, discharge_voltage_mv: 3000, charge_end_current_ma: 100, discharge_end_current_ma: 100, charge_rest_min: 0, discharge_rest_min: 0, cycle_count: 1, cycle_mode: 0, delta_peak_mv: 0, trickle_current_ma: 0, keep_voltage_mv: 4150, temp_limit_c: 45, time_limit_mode: "manual", time_limit_min: 360, effective_time_limit_min: 360, category_key: "lithium" };
  const profiles = [
    { ...profileDefaults, id: 1, name: "Li-Ion storage", description: "Storage voltage with conservative current.", mode_code: 2, mode: "Storage", charge_voltage_mv: 3800, is_builtin: true },
    { ...profileDefaults, id: 2, name: "18650 capacity check", description: "Personal capacity-test profile.", mode_code: 3, mode: "Discharge", discharge_current_ma: 1000, time_limit_mode: "automatic", effective_time_limit_min: 270, is_builtin: false },
  ];
  const standardProgram = { mode_code: 3, mode: "Capacity test", charge_c_rate: 0.5, discharge_c_rate: 1, cycle_count: 1, cycle_mode: 0, time_limit_mode: "manual", time_limit_min: 360 };
  const batteries = [1, 2, 3, 4].map((id) => ({
    id, code: String(id).padStart(3, "0"), name: id === 2 ? "Reference cell" : "", battery_type_code: 0,
    battery_type: "Li-Ion", nominal_capacity_mah: 2500, notes: "", manufacturer: "DemoCell", model: "INR18650", form_factor: "18650", origin: "", in_service_since: "2025-01-15", protected: false, archived: false, archived_at: "", standard_program: standardProgram,
    statistics: { run_count: 3, completed_run_count: 3, latest_capacity_mah: 2380 - id * 7, soh_percent: 95 - id, latest_resistance_mohm: 27 + id, resistance_change_percent: 1.2 },
  }));
  const start = Date.now() - 2 * 60 * 60 * 1000;
  const points = Array.from({ length: 121 }, (_, index) => {
    const phase = index < 55 ? 1 : index < 63 ? 3 : 2;
    const dischargeIndex = Math.max(0, index - 63);
    return {
      recorded_at: new Date(start + index * 60000).toISOString(), run_id: 101,
      profile_id: 2, battery_id: 2, battery_type_code: 0, mode_code: 1,
      status_code: phase, active: true, time_s: index * 60,
      voltage_v: phase === 1 ? 3.55 + index * 0.011 : phase === 3 ? 4.16 : 4.15 - dischargeIndex * 0.014,
      current_a: phase === 1 ? 1.0 : phase === 2 ? -1.0 : 0,
      capacity_mah: phase === 2 ? dischargeIndex * 41 : Math.min(index * 38, 2050),
      temperature_c: 25 + Math.round(Math.sin(index / 18) * 3), resistance_mohm: 29, cycle_count: 1,
    };
  });
  const run = { id: 101, address, slot: 2, battery_id: 2, battery_code: "002", nominal_capacity_mah: 2500, battery_type_code: 0, battery_type: "Li-Ion", mode_code: 3, mode: "Capacity test", started_at: new Date(start).toISOString(), ended_at: new Date(start + 120 * 60000).toISOString(), sample_count: points.length, max_voltage_v: 4.17, max_current_a: 1, max_capacity_mah: 2381, capacity_actual_mah: 2381, capacity_ratio_percent: 95.2, max_temperature_c: 29, measured_resistance_mohm: 29, capacity_soh_percent: 95.2 };

  function payload() {
    device.last_update = nowIso();
    return { devices: [device], discovered: [{ address, name: "Charger", rssi: -54, last_seen: nowIso(), registered: true }], timestamp: nowIso() };
  }

  async function api(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    if (method !== "GET") throw new Error("Demo mode is read-only");
    if (path === "/api/health") return { ok: true, version: "1.0.0-demo", fixes: ["Interactive sample data without charger access"], archived_battery_retention_days: 30 };
    if (path === "/api/profiles/options") return profileOptions;
    if (path === "/api/batteries/options") return batteryOptions;
    if (path === "/api/settings") return { default_program: "", phase_opacity_percent: 15, theme: "system", login_enabled: false, login_username: "" };
    if (path === "/api/profiles") return { profiles };
    if (path === "/api/profile-categories") return { categories };
    if (path.startsWith("/api/batteries?") || path === "/api/batteries") return { batteries };
    if (/^\/api\/batteries\/\d+$/.test(path)) return { battery: batteries.find((item) => item.id === Number(path.split("/").at(-1))), runs: [run] };
    if (path.startsWith("/api/batteries/") && path.includes("/compare")) return { runs: [{ ...run, points }] };
    if (path.startsWith("/api/recordings/history")) return { address, slot: 2, since: points[0].recorded_at, until: points.at(-1).recorded_at, total_points: points.length, returned_points: points.length, sample_step: 1, points };
    if (path.startsWith("/api/recordings/runs?")) return { runs: [run] };
    if (/\/api\/recordings\/runs\/\d+\/chart$/.test(path)) return { ...run, since: points[0].recorded_at, until: points.at(-1).recorded_at, total_points: points.length, points, capacity_target_mah: 2500 };
    if (/\/api\/recordings\/runs\/\d+\/report$/.test(path)) return { ...run, rating: "ok", duration_s: 7200, energy_wh: 8.7, start_voltage_v: 4.17, end_voltage_v: 3.02, minimum_voltage_v: 3.02, maximum_voltage_v: 4.17, maximum_temperature_c: 29, temperature_limit_c: 45, start_resistance_mohm: 29, end_resistance_mohm: 30, last_status: "Finished", warnings: [] };
    if (path.startsWith("/api/notifications")) return { notifications: [{ id: 1, created_at: run.ended_at, kind: "run_completed", title: "Slot 4 finished", message: "Battery 004 completed successfully", run_id: 101, battery_id: 4, read: false }], unread_count: 1 };
    if (path.includes("/curve")) return { interval_s: 60, points: points.map((item, index) => ({ index, voltage_v: item.voltage_v })) };
    throw new Error(`No demo response for ${path}`);
  }

  window.MC3000_DEMO = { api, payload };

  window.addEventListener("load", () => {
    const parameters = new URLSearchParams(location.search);
    if (parameters.get("demo") !== "1") return;
    const view = {
      profiles: "profilesView",
      batteries: "batteryManagerView",
      recordings: "recordingsView",
      settings: "settingsView",
    }[parameters.get("view")];
    window.setTimeout(() => {
      if (parameters.get("lang") === "en") window.MC3000_I18N?.setLanguage("en");
      if (parameters.get("theme") === "dark" && typeof window.applyTheme === "function") {
        window.applyTheme("dark");
      }
      if (view) document.querySelector(`[data-view="${view}"]`)?.click();
    }, 400);
  });
})();
