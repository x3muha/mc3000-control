"use strict";

const appState = {
  devices: [],
  discovered: [],
  profiles: [],
  profileCategories: [],
  profileOptions: null,
  profileCategory: "all",
  pendingAutomaticProgram: null,
  batteries: [],
  showArchivedBatteries: false,
  batteryOptions: null,
  selectedBattery: null,
  batteryRuns: [],
  batteryComparison: null,
  archivedBatteryRetentionDays: 30,
  history: null,
  curve: null,
  runChart: null,
  notifications: [],
  packBuilder: null,
  settings: {
    default_program: "",
    phase_opacity_percent: 15,
    theme: "system",
    login_enabled: false,
    login_username: "",
  },
  timestamp: null,
  currentView: "devicesView",
  connectionScanRunning: false,
  connectionScanCompleted: false,
};

const CREATE_NUMBERED_BATTERY_VALUE = "__create_numbered_battery__";

const histories = new Map();
const chartPointers = new WeakMap();
const chartGeometries = new WeakMap();
const chartZoomRanges = new Map();
let websocket = null;
let reconnectTimer = null;
let toastTimer = null;
let historyTimer = null;
let historyResizeTimer = null;
let batteryResizeTimer = null;
let pointerPosition = null;
let hoveredSparklineKey = null;
const themeMediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

const elements = {
  appVersion: document.getElementById("appVersion"),
  appVersionTitle: document.getElementById("appVersionTitle"),
  appFixes: document.getElementById("appFixes"),
  connectionSummary: document.getElementById("connectionSummary"),
  notificationButton: document.getElementById("notificationButton"),
  notificationCount: document.getElementById("notificationCount"),
  notificationDialog: document.getElementById("notificationDialog"),
  notificationList: document.getElementById("notificationList"),
  connectionManagerDialog: document.getElementById("connectionManagerDialog"),
  connectionManagerRegistered: document.getElementById("connectionManagerRegistered"),
  connectionManagerDiscovered: document.getElementById("connectionManagerDiscovered"),
  connectionManagerScanButton: document.getElementById("connectionManagerScanButton"),
  connectionManagerScanStatus: document.getElementById("connectionManagerScanStatus"),
  emptyState: document.getElementById("emptyState"),
  deviceList: document.getElementById("deviceList"),
  toast: document.getElementById("toast"),
  renameDialog: document.getElementById("renameDialog"),
  renameForm: document.getElementById("renameForm"),
  renameAddress: document.getElementById("renameAddress"),
  renameAlias: document.getElementById("renameAlias"),
  renameSerialNumber: document.getElementById("renameSerialNumber"),
  slotConfigurationDialog: document.getElementById("slotConfigurationDialog"),
  slotConfigurationForm: document.getElementById("slotConfigurationForm"),
  slotConfigurationTitle: document.getElementById("slotConfigurationTitle"),
  slotConfigurationAddress: document.getElementById("slotConfigurationAddress"),
  slotConfigurationSlot: document.getElementById("slotConfigurationSlot"),
  slotConfigurationStartAfter: document.getElementById("slotConfigurationStartAfter"),
  slotConfigurationFacts: document.getElementById("slotConfigurationFacts"),
  slotConfigurationBattery: document.getElementById("slotConfigurationBattery"),
  slotConfigurationProgram: document.getElementById("slotConfigurationProgram"),
  slotConfigurationCapacityField: document.getElementById("slotConfigurationCapacityField"),
  slotConfigurationCapacity: document.getElementById("slotConfigurationCapacity"),
  slotConfigurationTimeLimitModeField: document.getElementById("slotConfigurationTimeLimitModeField"),
  slotConfigurationTimeLimitMode: document.getElementById("slotConfigurationTimeLimitMode"),
  slotConfigurationTimeLimitField: document.getElementById("slotConfigurationTimeLimitField"),
  slotConfigurationTimeLimitHours: document.getElementById("slotConfigurationTimeLimitHours"),
  slotConfigurationPreview: document.getElementById("slotConfigurationPreview"),
  slotConfigurationSubmit: document.getElementById("slotConfigurationSubmit"),
  deviceConfigurationDialog: document.getElementById("deviceConfigurationDialog"),
  deviceConfigurationForm: document.getElementById("deviceConfigurationForm"),
  deviceConfigurationTitle: document.getElementById("deviceConfigurationTitle"),
  deviceConfigurationAddress: document.getElementById("deviceConfigurationAddress"),
  deviceConfigurationStartAfter: document.getElementById("deviceConfigurationStartAfter"),
  deviceConfigurationFacts: document.getElementById("deviceConfigurationFacts"),
  deviceConfigurationProgram: document.getElementById("deviceConfigurationProgram"),
  deviceConfigurationSlots: document.getElementById("deviceConfigurationSlots"),
  deviceConfigurationTimeLimitModeField: document.getElementById("deviceConfigurationTimeLimitModeField"),
  deviceConfigurationTimeLimitMode: document.getElementById("deviceConfigurationTimeLimitMode"),
  deviceConfigurationTimeLimitField: document.getElementById("deviceConfigurationTimeLimitField"),
  deviceConfigurationTimeLimitHours: document.getElementById("deviceConfigurationTimeLimitHours"),
  deviceConfigurationPreview: document.getElementById("deviceConfigurationPreview"),
  deviceConfigurationSubmit: document.getElementById("deviceConfigurationSubmit"),
  curveDialog: document.getElementById("curveDialog"),
  curveTitle: document.getElementById("curveTitle"),
  curveCanvas: document.getElementById("curveCanvas"),
  curveMeta: document.getElementById("curveMeta"),
  profileCategoryFilters: document.getElementById("profileCategoryFilters"),
  profileCategoryDescription: document.getElementById("profileCategoryDescription"),
  profileList: document.getElementById("profileList"),
  profileDialog: document.getElementById("profileDialog"),
  profileDialogTitle: document.getElementById("profileDialogTitle"),
  profileForm: document.getElementById("profileForm"),
  profileId: document.getElementById("profileId"),
  profileName: document.getElementById("profileName"),
  profileDescription: document.getElementById("profileDescription"),
  profileCategory: document.getElementById("profileCategory"),
  profileBatteryType: document.getElementById("profileBatteryType"),
  profileMode: document.getElementById("profileMode"),
  profileCapacity: document.getElementById("profileCapacity"),
  profileChargeCurrent: document.getElementById("profileChargeCurrent"),
  profileDischargeCurrent: document.getElementById("profileDischargeCurrent"),
  profileChargeVoltage: document.getElementById("profileChargeVoltage"),
  profileDischargeVoltage: document.getElementById("profileDischargeVoltage"),
  profileChargeEndCurrent: document.getElementById("profileChargeEndCurrent"),
  profileDischargeEndCurrent: document.getElementById("profileDischargeEndCurrent"),
  profileChargeRest: document.getElementById("profileChargeRest"),
  profileDischargeRest: document.getElementById("profileDischargeRest"),
  profileCycleCount: document.getElementById("profileCycleCount"),
  profileCycleMode: document.getElementById("profileCycleMode"),
  profileDeltaPeak: document.getElementById("profileDeltaPeak"),
  profileTrickleCurrent: document.getElementById("profileTrickleCurrent"),
  profileKeepVoltage: document.getElementById("profileKeepVoltage"),
  profileTempLimit: document.getElementById("profileTempLimit"),
  profileTimeLimitMode: document.getElementById("profileTimeLimitMode"),
  profileTimeLimitField: document.getElementById("profileTimeLimitField"),
  profileTimeLimit: document.getElementById("profileTimeLimit"),
  profileValidationHint: document.getElementById("profileValidationHint"),
  automaticProfileDialog: document.getElementById("automaticProfileDialog"),
  automaticProfileDialogTitle: document.getElementById("automaticProfileDialogTitle"),
  automaticProfileForm: document.getElementById("automaticProfileForm"),
  automaticProfileKey: document.getElementById("automaticProfileKey"),
  automaticProfileName: document.getElementById("automaticProfileName"),
  automaticProfileDescription: document.getElementById("automaticProfileDescription"),
  automaticProfileCategory: document.getElementById("automaticProfileCategory"),
  automaticProfileMode: document.getElementById("automaticProfileMode"),
  automaticProfileChargeRate: document.getElementById("automaticProfileChargeRate"),
  automaticProfileDischargeRate: document.getElementById("automaticProfileDischargeRate"),
  automaticProfileChargeRest: document.getElementById("automaticProfileChargeRest"),
  automaticProfileDischargeRest: document.getElementById("automaticProfileDischargeRest"),
  automaticProfileCycleCount: document.getElementById("automaticProfileCycleCount"),
  automaticProfileCycleMode: document.getElementById("automaticProfileCycleMode"),
  automaticProfileTempLimit: document.getElementById("automaticProfileTempLimit"),
  automaticProfileTimeLimitMode: document.getElementById("automaticProfileTimeLimitMode"),
  automaticProfileTimeLimitField: document.getElementById("automaticProfileTimeLimitField"),
  automaticProfileTimeLimitHours: document.getElementById("automaticProfileTimeLimitHours"),
  automaticProfileValidationHint: document.getElementById("automaticProfileValidationHint"),
  applyProfileDialog: document.getElementById("applyProfileDialog"),
  applyProfileForm: document.getElementById("applyProfileForm"),
  applyProfileId: document.getElementById("applyProfileId"),
  applyProfileFacts: document.getElementById("applyProfileFacts"),
  applyProfileDevice: document.getElementById("applyProfileDevice"),
  applyProfileConfirmation: document.getElementById("applyProfileConfirmation"),
  historyDevice: document.getElementById("historyDevice"),
  historySlot: document.getElementById("historySlot"),
  historyHours: document.getElementById("historyHours"),
  historySummary: document.getElementById("historySummary"),
  voltageCurrentChart: document.getElementById("voltageCurrentChart"),
  temperatureResistanceChart: document.getElementById("temperatureResistanceChart"),
  capacityChart: document.getElementById("capacityChart"),
  recordingRuns: document.getElementById("recordingRuns"),
  batteryLookupForm: document.getElementById("batteryLookupForm"),
  batteryLookup: document.getElementById("batteryLookup"),
  batteryList: document.getElementById("batteryList"),
  batteryArchiveToggle: document.getElementById("batteryArchiveToggle"),
  batteryArchiveAction: document.getElementById("batteryArchiveAction"),
  batteryDeleteAction: document.getElementById("batteryDeleteAction"),
  batteryDetailEmpty: document.getElementById("batteryDetailEmpty"),
  batteryDetail: document.getElementById("batteryDetail"),
  batteryDetailType: document.getElementById("batteryDetailType"),
  batteryDetailTitle: document.getElementById("batteryDetailTitle"),
  batteryDetailMeta: document.getElementById("batteryDetailMeta"),
  batteryStats: document.getElementById("batteryStats"),
  batteryRuns: document.getElementById("batteryRuns"),
  batteryCompareMetric: document.getElementById("batteryCompareMetric"),
  batteryCompareLegend: document.getElementById("batteryCompareLegend"),
  batteryCompareChart: document.getElementById("batteryCompareChart"),
  packBuilderForm: document.getElementById("packBuilderForm"),
  packCellsPerGroup: document.getElementById("packCellsPerGroup"),
  packGroupCount: document.getElementById("packGroupCount"),
  packCapacitySpread: document.getElementById("packCapacitySpread"),
  packResistanceSpread: document.getElementById("packResistanceSpread"),
  packBatterySelection: document.getElementById("packBatterySelection"),
  packBuilderResult: document.getElementById("packBuilderResult"),
  batteryDialog: document.getElementById("batteryDialog"),
  batteryDialogTitle: document.getElementById("batteryDialogTitle"),
  batteryForm: document.getElementById("batteryForm"),
  batteryId: document.getElementById("batteryId"),
  batteryCode: document.getElementById("batteryCode"),
  batteryName: document.getElementById("batteryName"),
  batteryType: document.getElementById("batteryType"),
  batteryCapacity: document.getElementById("batteryCapacity"),
  batteryManufacturer: document.getElementById("batteryManufacturer"),
  batteryModel: document.getElementById("batteryModel"),
  batteryFormFactor: document.getElementById("batteryFormFactor"),
  batteryOrigin: document.getElementById("batteryOrigin"),
  batteryInServiceSince: document.getElementById("batteryInServiceSince"),
  batteryProtected: document.getElementById("batteryProtected"),
  batteryNotes: document.getElementById("batteryNotes"),
  standardProgramDialog: document.getElementById("standardProgramDialog"),
  standardProgramForm: document.getElementById("standardProgramForm"),
  standardProgramTitle: document.getElementById("standardProgramTitle"),
  standardBatteryId: document.getElementById("standardBatteryId"),
  standardBatteryFacts: document.getElementById("standardBatteryFacts"),
  standardMode: document.getElementById("standardMode"),
  standardChargeRate: document.getElementById("standardChargeRate"),
  standardDischargeRate: document.getElementById("standardDischargeRate"),
  standardCycleCount: document.getElementById("standardCycleCount"),
  standardCycleMode: document.getElementById("standardCycleMode"),
  standardTimeLimitMode: document.getElementById("standardTimeLimitMode"),
  standardTimeLimitField: document.getElementById("standardTimeLimitField"),
  standardTimeLimitHours: document.getElementById("standardTimeLimitHours"),
  standardProgramPreview: document.getElementById("standardProgramPreview"),
  settingsForm: document.getElementById("settingsForm"),
  settingsTheme: document.getElementById("settingsTheme"),
  settingsDefaultProgram: document.getElementById("settingsDefaultProgram"),
  settingsPhaseOpacity: document.getElementById("settingsPhaseOpacity"),
  settingsPhaseOpacityValue: document.getElementById("settingsPhaseOpacityValue"),
  settingsLoginEnabled: document.getElementById("settingsLoginEnabled"),
  settingsLoginFields: document.getElementById("settingsLoginFields"),
  settingsLoginUsername: document.getElementById("settingsLoginUsername"),
  settingsLoginPassword: document.getElementById("settingsLoginPassword"),
  settingsLogoutButton: document.getElementById("settingsLogoutButton"),
  restoreBackupFile: document.getElementById("restoreBackupFile"),
  runReportDialog: document.getElementById("runReportDialog"),
  runReportTitle: document.getElementById("runReportTitle"),
  runReportContent: document.getElementById("runReportContent"),
  runChartDialog: document.getElementById("runChartDialog"),
  runChartTitle: document.getElementById("runChartTitle"),
  runChartMeta: document.getElementById("runChartMeta"),
  runVoltageCurrentChart: document.getElementById("runVoltageCurrentChart"),
  runTemperatureResistanceChart: document.getElementById("runTemperatureResistanceChart"),
  runCapacityLegend: document.getElementById("runCapacityLegend"),
  runCapacityChart: document.getElementById("runCapacityChart"),
};

[elements.curveDialog, elements.runChartDialog].forEach(
  (dialog) => enableBackdropClose(dialog),
);

function enableBackdropClose(dialog) {
  let startedOutside = false;
  const isOutside = (event) => {
    const bounds = dialog.getBoundingClientRect();
    return event.clientX < bounds.left
      || event.clientX > bounds.right
      || event.clientY < bounds.top
      || event.clientY > bounds.bottom;
  };
  dialog.addEventListener("pointerdown", (event) => {
    startedOutside = isOutside(event);
  });
  dialog.addEventListener("click", (event) => {
    if (startedOutside && isOutside(event)) dialog.close();
    startedOutside = false;
  });
}

function connectWebsocket() {
  clearTimeout(reconnectTimer);
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  websocket = new WebSocket(`${protocol}//${location.host}/ws`);

  websocket.addEventListener("open", () => {
    elements.connectionSummary.textContent = "Live-Verbindung aktiv";
  });

  websocket.addEventListener("message", (event) => {
    applyPayload(JSON.parse(event.data));
  });

  websocket.addEventListener("close", () => {
    elements.connectionSummary.textContent = "Verbindung wird wiederhergestellt...";
    reconnectTimer = setTimeout(connectWebsocket, 1800);
  });

  websocket.addEventListener("error", () => websocket.close());
}

function applyPayload(payload) {
  appState.devices = payload.devices || [];
  appState.discovered = payload.discovered || [];
  appState.timestamp = payload.timestamp || null;
  collectHistory();
  render();
}

function collectHistory() {
  for (const device of appState.devices) {
    if (!device.last_update) continue;
    for (const slot of device.slots || []) {
      if (!slot) continue;
      const key = historyKey(device.address, slot.slot);
      const history = histories.get(key) || [];
      if (history.at(-1)?.stamp === device.last_update) continue;
      history.push({
        stamp: device.last_update,
        voltage: Number(slot.voltage_v) || 0,
        current: Number(slot.current_a) || 0,
        statusCode: Number(slot.status_code),
      });
      if (history.length > 240) history.splice(0, history.length - 240);
      histories.set(key, history);
    }
  }
}

function render() {
  elements.emptyState.hidden = appState.devices.length > 0;
  elements.deviceList.innerHTML = appState.devices.map(renderDevice).join("");
  renderConnectionManager();
  renderHistoryDevices();
  updateSummary();
  requestAnimationFrame(drawSparklines);
}

function renderConnectionManager() {
  const discoveredByAddress = new Map(
    appState.discovered.map((device) => [device.address, device]),
  );
  elements.connectionManagerRegistered.innerHTML = appState.devices.length
    ? appState.devices.map((device) => {
      const discovered = discoveredByAddress.get(device.address);
      const active = (device.slots || []).some((slot) => slot?.active);
      const stateLabel = deviceStateLabel(device.state);
      let connectionAction;
      if (device.connected) {
        connectionAction = `
          <button data-action="release" data-address="${escapeHtml(device.address)}">
            Bluetooth trennen
          </button>
        `;
      } else {
        connectionAction = `
          <button class="primary" data-action="resume" data-address="${escapeHtml(device.address)}">
            Verbinden
          </button>
        `;
      }
      return `
        <article class="connection-manager-device">
          <div class="connection-manager-device-main">
            <div class="connection-manager-device-title">
              <strong>${escapeHtml(device.alias)}</strong>
              <span class="status-pill ${escapeHtml(device.state)}">${escapeHtml(stateLabel)}</span>
            </div>
            <span>${escapeHtml(device.address)}</span>
            <small>Modell MC3000 · SK-100083${device.serial_number ? ` · SN ${escapeHtml(device.serial_number)}` : ""}</small>
            ${renderConnectionQuality(device, discovered)}
          </div>
          <div class="connection-manager-actions">
            ${connectionAction}
            <button data-action="rename" data-address="${escapeHtml(device.address)}">Gerätedaten</button>
            <button
              class="danger-quiet"
              data-action="remove-device"
              data-address="${escapeHtml(device.address)}"
              ${active ? "disabled" : ""}
              title="${active ? "Ein laufendes Programm schützt das Ladegerät vor dem Entfernen" : "Ladegerät aus MC3000 Control entfernen"}"
            >Entfernen</button>
          </div>
        </article>
      `;
    }).join("")
    : '<p class="connection-manager-empty">Noch kein Ladegerät eingerichtet.</p>';

  const registeredAddresses = new Set(
    appState.devices.map((device) => device.address),
  );
  const candidates = appState.discovered.filter(
    (device) => !device.registered && !registeredAddresses.has(device.address),
  );
  elements.connectionManagerDiscovered.innerHTML = candidates.length
    ? candidates.map((device) => `
      <article class="connection-manager-device">
        <div class="connection-manager-device-main">
          <div class="connection-manager-device-title">
            <strong>${escapeHtml(device.name || "MC3000")}</strong>
            <span class="status-pill waiting">Gefunden</span>
          </div>
          <span>${escapeHtml(device.address)}</span>
          <small>${signalText(device.rssi)}</small>
        </div>
        <div class="connection-manager-actions">
          <button
            class="primary"
            data-action="enroll"
            data-address="${escapeHtml(device.address)}"
          >Verbinden</button>
        </div>
      </article>
    `).join("")
    : `<p class="connection-manager-empty">${
      appState.connectionScanRunning
        ? "Bluetooth-Suche läuft..."
        : appState.connectionScanCompleted
          ? "Keine neuen MC3000 gefunden."
          : "Mit „Neu suchen“ nach MC3000-Ladegeräten suchen."
    }</p>`;

  elements.connectionManagerScanButton.disabled = appState.connectionScanRunning;
  elements.connectionManagerScanButton.textContent = appState.connectionScanRunning
    ? "Suche läuft..."
    : "Neu suchen";
  elements.connectionManagerScanStatus.textContent = appState.connectionScanRunning
    ? "Die Suche läuft parallel zu bestehenden Verbindungen."
    : appState.connectionScanCompleted
      ? `${candidates.length} neue Ladegeräte gefunden.`
      : "Suche noch nicht gestartet.";
}

function renderDevice(device) {
  const connected = Boolean(device.connected);
  const released = Boolean(device.released);
  const slots = (device.slots || []).filter(Boolean);
  const stateLabel = deviceStateLabel(device.state);
  const version = device.version
    ? `FW ${escapeHtml(device.version.firmware)} · HW ${escapeHtml(device.version.hardware)}`
    : "Version --";
  const input = device.basic
    ? `Eingang ${formatNumber(device.basic.input_voltage_v, 3)} V`
    : "Eingang --";
  const fan = device.basic
    ? `Lüfterregelung ${fanModeLabel(device.basic.fan_mode)}`
    : "Lüfterregelung --";
  const updated = device.last_update ? `Stand ${formatTime(device.last_update)}` : "Noch keine Messwerte";
  const discovered = appState.discovered.find(
    (candidate) => candidate.address === device.address,
  );
  const canStartAll = connected && slots.some(
    (slot) => (
      !slot.active
      && Number(slot.voltage_v) > 0
      && Number(slot.status_code) < 128
    ),
  );

  let content;
  if (slots.length) {
    content = `<div class="slots">${Array.from({ length: 4 }, (_, index) => {
      const slot = device.slots[index];
      return renderSlot(device, slot, index + 1);
    }).join("")}</div>`;
  } else {
    const message = released
      ? "Bluetooth-Verbindung getrennt"
      : device.error || "Warte auf Bluetooth-Verbindung";
    content = `<div class="device-message"><div><strong>${escapeHtml(stateLabel)}</strong><br>${escapeHtml(message)}</div></div>`;
  }

  return `
    <section class="device" data-address="${escapeHtml(device.address)}">
      <header class="device-head">
        <div>
          <div class="device-title">
            <h2>${escapeHtml(device.alias)}</h2>
            <span class="status-pill ${escapeHtml(device.state)}">${escapeHtml(stateLabel)}</span>
          </div>
          <div class="device-meta">
            <span>${version}</span>
            <span>${input}</span>
            <span>Modell SK-100083${device.serial_number ? ` · SN ${escapeHtml(device.serial_number)}` : ""}</span>
            <span>${fan}</span>
            <span>${updated}</span>
            ${renderConnectionQuality(device, discovered)}
          </div>
        </div>
        <div class="device-actions">
          <button data-action="configure-device" data-address="${escapeHtml(device.address)}" ${canStartAll ? "" : "disabled"}>Alle Programme</button>
          <button class="primary" data-action="start-all" data-address="${escapeHtml(device.address)}" ${canStartAll ? "" : "disabled"}>▶ Alle starten</button>
          <button class="danger" data-action="stop-all" data-address="${escapeHtml(device.address)}" ${connected ? "" : "disabled"}>Alles stoppen</button>
        </div>
      </header>
      ${content}
    </section>
  `;
}

function renderConnectionQuality(device, discovered) {
  let quality = "bad";
  let label = "Schlecht";
  let detail = "Keine aktuellen Telemetriedaten";
  const rssi = Number(discovered?.rssi);
  if (Number.isFinite(rssi)) {
    quality = rssi >= -65 ? "good" : rssi >= -80 ? "okay" : "bad";
    label = quality === "good" ? "Gut" : quality === "okay" ? "Okay" : "Schlecht";
    detail = `zuletzt gemessen: ${formatInteger(rssi)} dBm`;
  } else if (device.connected && device.last_update) {
    const ageSeconds = Math.max(
      0,
      (Date.now() - new Date(device.last_update).getTime()) / 1000,
    );
    quality = ageSeconds <= 5 ? "good" : ageSeconds <= 15 ? "okay" : "bad";
    label = quality === "good" ? "Gut" : quality === "okay" ? "Okay" : "Schlecht";
    detail = `Telemetrie vor ${formatInteger(ageSeconds)} s`;
  }
  return `<span class="connection-quality ${quality}" title="Verbindungsqualität: ${escapeHtml(detail)}"><i></i>${label}</span>`;
}

function renderSlot(device, slot, slotNumber) {
  if (!slot) {
    return `
      <article class="slot">
        <div class="slot-head"><span class="slot-number">SLOT ${slotNumber}</span><span class="slot-state">Keine Daten</span></div>
      </article>
    `;
  }

  const statusClass = slot.status_code >= 128 ? "error" : slot.active ? "active" : "";
  const connected = Boolean(device.connected);
  const canStart =
    connected && !slot.active && slot.voltage_v > 0 && slot.status_code < 128;
  const canStop = connected && slot.active;
  const batteryId = device.battery_ids?.[slotNumber] ?? device.battery_ids?.[String(slotNumber)];
  const assignedBattery = findBattery(Number(batteryId));
  const selectedProgram =
    device.programs?.[slotNumber] ?? device.programs?.[String(slotNumber)];
  return `
    <article class="slot ${statusClass}">
      <div class="slot-head">
        <span class="slot-number">SLOT ${slotNumber}</span>
        <span class="slot-state">${escapeHtml(slot.status)}</span>
      </div>
      <div class="slot-kind">
        <strong>${escapeHtml(slot.battery_type)}</strong>
        <span>${escapeHtml(slot.mode)}</span>
      </div>
      <div class="slot-program-state ${selectedProgram ? "selected" : "empty"}">
        <span>STARTPROGRAMM</span>
        <strong>${escapeHtml(selectedProgram?.label || "Kein Programm gewählt")}</strong>
        ${assignedBattery
          ? `<small>Batterie ${escapeHtml(assignedBattery.code)}</small>`
          : "<small>Keine Batterie zugeordnet</small>"}
      </div>
      <div class="slot-main">
        <div class="slot-electric slot-voltage">
          <span>Spannung</span>
          <strong>${formatNumber(slot.voltage_v, 3)} <small>V</small></strong>
        </div>
        <div class="slot-electric slot-current">
          <span>Strom</span>
          <strong>${formatNumber(slot.current_a, 3)} <small>A</small></strong>
        </div>
      </div>
      <canvas class="sparkline" data-history="${escapeHtml(historyKey(device.address, slotNumber))}"></canvas>
      <dl class="slot-metrics">
        <div><dt>Kapazität</dt><dd>${formatInteger(slot.capacity_mah)} mAh</dd></div>
        <div><dt>Temperatur</dt><dd>${formatInteger(slot.temperature_c)} °C</dd></div>
        <div><dt>Innenwiderstand</dt><dd>${formatInteger(slot.resistance_mohm)} mΩ</dd></div>
        <div><dt>Zeit</dt><dd>${formatDuration(slot.time_s)}</dd></div>
      </dl>
      <div class="slot-secondary-actions ${assignedBattery ? "with-battery" : ""}">
        <button class="slot-configuration-button" data-action="configure-slot" data-address="${escapeHtml(device.address)}" data-slot="${slotNumber}" ${connected && !slot.active ? "" : "disabled"}>Programm wählen</button>
        ${assignedBattery ? `<button class="slot-battery-button" data-action="edit-slot-battery" data-address="${escapeHtml(device.address)}" data-slot="${slotNumber}">Batteriedaten</button>` : ""}
      </div>
      <div class="slot-actions">
        <button class="primary" data-action="start" data-address="${escapeHtml(device.address)}" data-slot="${slotNumber}" ${canStart ? "" : "disabled"}>▶ Start</button>
        <button class="danger" data-action="stop" data-address="${escapeHtml(device.address)}" data-slot="${slotNumber}" ${canStop ? "" : "disabled"}>■ Stop</button>
        <button class="icon-button" data-action="curve" data-address="${escapeHtml(device.address)}" data-slot="${slotNumber}" title="Gespeicherte Spannungskurve" aria-label="Gespeicherte Spannungskurve">⌁</button>
      </div>
    </article>
  `;
}

function updateSummary() {
  const total = appState.devices.length;
  const connected = appState.devices.filter((device) => device.connected).length;
  if (!total) {
    elements.connectionSummary.textContent = "Keine Ladegeräte eingerichtet";
    return;
  }
  elements.connectionSummary.textContent = `${connected} von ${total} Ladegeräten verbunden`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 401) {
    location.assign("/login");
    throw new Error("Anmeldung erforderlich");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body;
}

async function runConnectionScan() {
  if (appState.connectionScanRunning) return;
  appState.connectionScanRunning = true;
  renderConnectionManager();
  try {
    const result = await api("/api/scan", { method: "POST" });
    appState.discovered = result.discovered || [];
    appState.connectionScanCompleted = true;
  } finally {
    appState.connectionScanRunning = false;
    renderConnectionManager();
  }
}

function nextDeviceAlias() {
  const aliases = new Set(appState.devices.map((device) => device.alias));
  let number = 1;
  while (aliases.has(`MC3000 ${number}`)) number += 1;
  return `MC3000 ${number}`;
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  const address = button.dataset.address;
  const slot = Number(button.dataset.slot);

  try {
    if (action === "show-view") {
      showView(button.dataset.view);
    } else if (action === "open-connection-manager") {
      if (!elements.connectionManagerDialog.open) {
        elements.connectionManagerDialog.showModal();
      }
      await runConnectionScan();
    } else if (action === "scan-devices") {
      await runConnectionScan();
    } else if (action === "enroll") {
      button.disabled = true;
      const result = await api("/api/devices", {
        method: "POST",
        body: JSON.stringify({
          address,
          alias: nextDeviceAlias(),
        }),
      });
      if (!appState.devices.some((device) => device.address === address)) {
        appState.devices.push(result.device);
      }
      appState.discovered = appState.discovered.map((device) => (
        device.address === address ? { ...device, registered: true } : device
      ));
      render();
      showToast("Ladegerät wird verbunden");
    } else if (action === "rename") {
      const device = findDevice(address);
      elements.renameAddress.value = address;
      elements.renameAlias.value = device?.alias || "";
      elements.renameSerialNumber.value = device?.serial_number || "";
      elements.renameDialog.showModal();
      elements.renameAlias.select();
    } else if (action === "release") {
      await api(`/api/devices/${encodeURIComponent(address)}/release`, { method: "POST" });
      showToast("Bluetooth-Verbindung wurde getrennt");
    } else if (action === "resume") {
      await api(`/api/devices/${encodeURIComponent(address)}/resume`, { method: "POST" });
      showToast("Der Pi verbindet das Ladegerät wieder");
    } else if (action === "remove-device") {
      const device = findDevice(address);
      const confirmed = window.confirm(
        `${device?.alias || "Dieses Ladegerät"} wirklich entfernen?\n\n`
        + "Nur dieses Ladegerät wird getrennt und aus MC3000 Control entfernt. "
        + "Batterieakten und Messdaten bleiben erhalten.",
      );
      if (!confirmed) return;
      button.disabled = true;
      await api(`/api/devices/${encodeURIComponent(address)}`, { method: "DELETE" });
      appState.devices = appState.devices.filter(
        (candidate) => candidate.address !== address,
      );
      appState.discovered = appState.discovered.map((candidate) => (
        candidate.address === address
          ? { ...candidate, registered: false }
          : candidate
      ));
      render();
      showToast("Ladegerät wurde entfernt");
    } else if (action === "start") {
      const device = findDevice(address);
      const selectedProgram =
        device?.programs?.[slot] ?? device?.programs?.[String(slot)];
      if (!selectedProgram) {
        openSlotConfigurationDialog(address, slot, true);
        return;
      }
      button.disabled = true;
      await api(`/api/devices/${encodeURIComponent(address)}/slots/${slot}/start`, {
        method: "POST",
      });
      showToast(`Slot ${slot} wurde gestartet`);
    } else if (action === "start-all") {
      const device = findDevice(address);
      const startableSlots = (device?.slots || []).filter((candidate) => (
        candidate
        && !candidate.active
        && Number(candidate.voltage_v) > 0
        && Number(candidate.status_code) < 128
      ));
      const hasMissingProgram = startableSlots.some((candidate) => !(
        device?.programs?.[candidate.slot]
        ?? device?.programs?.[String(candidate.slot)]
      ));
      if (hasMissingProgram) {
        openDeviceConfigurationDialog(address, true);
        return;
      }
      button.disabled = true;
      const result = await api(`/api/devices/${encodeURIComponent(address)}/start-all`, {
        method: "POST",
      });
      showToast(`Slots ${result.slots.join(", ")} wurden gestartet`);
    } else if (action === "configure-device") {
      openDeviceConfigurationDialog(address, false);
    } else if (action === "stop") {
      await api(`/api/devices/${encodeURIComponent(address)}/slots/${slot}/stop`, { method: "POST" });
      showToast(`Slot ${slot} wurde gestoppt`);
    } else if (action === "stop-all") {
      await api(`/api/devices/${encodeURIComponent(address)}/stop-all`, { method: "POST" });
      showToast("Alle Slots dieses Ladegeräts wurden gestoppt");
    } else if (action === "curve") {
      await openCurve(address, slot);
    } else if (action === "configure-slot") {
      openSlotConfigurationDialog(address, slot, false);
    } else if (action === "edit-slot-battery") {
      const device = findDevice(address);
      const batteryId =
        device?.battery_ids?.[slot] ?? device?.battery_ids?.[String(slot)];
      let battery = findBattery(Number(batteryId));
      if (!battery && batteryId) {
        await loadBatteries();
        battery = findBattery(Number(batteryId));
      }
      if (!battery) {
        showToast("Die Batterieakte wurde nicht gefunden", true);
        return;
      }
      openBatteryDialog(battery);
    } else if (action === "filter-profiles") {
      const category = button.dataset.profileCategory;
      if (["all", "own", ...appState.profileCategories.map((item) => item.key)].includes(category)) {
        appState.profileCategory = category;
        renderProfiles();
      }
    } else if (action === "delete-profile-category") {
      const category = appState.profileCategories.find(
        (item) => item.key === button.dataset.profileCategory,
      );
      if (!category || category.is_builtin) return;
      if (!window.confirm(`Kategorie „${category.name}“ löschen? Zugeordnete Profile wechseln zu Allgemein.`)) return;
      await api(`/api/profile-categories/${encodeURIComponent(category.key)}`, {
        method: "DELETE",
      });
      appState.profileCategory = "all";
      await loadProfiles();
      await loadBatteryOptions();
      showToast("Kategorie wurde gelöscht");
    } else if (action === "use-automatic-profile") {
      const programKey = button.dataset.programKey;
      const automaticProgram = (
        appState.batteryOptions?.automatic_programs || []
      ).find((program) => program.key === programKey);
      if (!automaticProgram) return;
      appState.pendingAutomaticProgram = programKey;
      showView("devicesView");
      showToast(
        `${automaticProgram.label}: jetzt beim gewünschten Slot „Programm wählen“`,
      );
    } else if (action === "new-profile") {
      openProfileDialog();
    } else if (action === "edit-profile") {
      openProfileDialog(findProfile(Number(button.dataset.profileId)));
    } else if (action === "duplicate-profile") {
      duplicateProfile(findProfile(Number(button.dataset.profileId)));
    } else if (action === "edit-automatic-profile") {
      openAutomaticProfileDialog(
        findAutomaticProfile(button.dataset.programKey),
      );
    } else if (action === "duplicate-automatic-profile") {
      duplicateAutomaticProfile(
        findAutomaticProfile(button.dataset.programKey),
      );
    } else if (action === "apply-profile") {
      openApplyProfileDialog(findProfile(Number(button.dataset.profileId)));
    } else if (action === "delete-profile") {
      await deleteProfile(Number(button.dataset.profileId));
    } else if (action === "new-battery") {
      openBatteryDialog();
    } else if (action === "toggle-battery-archive") {
      appState.showArchivedBatteries = !appState.showArchivedBatteries;
      appState.selectedBattery = null;
      appState.batteryRuns = [];
      await loadBatteries();
      renderBatteryDetail();
    } else if (action === "select-battery") {
      await selectBattery(Number(button.dataset.batteryId));
    } else if (action === "edit-battery") {
      openBatteryDialog(appState.selectedBattery);
    } else if (action === "archive-battery") {
      await archiveBattery();
    } else if (action === "delete-battery-permanently") {
      await deleteBatteryPermanently();
    } else if (action === "standard-program") {
      openStandardProgramDialog(appState.selectedBattery);
    } else if (action === "battery-qr") {
      openBatteryQrLabel();
    } else if (action === "battery-sheet-pdf") {
      if (appState.selectedBattery) {
        window.location.assign(`/api/batteries/${appState.selectedBattery.id}/sheet.pdf`);
      }
    } else if (action === "export-battery") {
      if (appState.selectedBattery) {
        window.location.assign(`/api/batteries/${appState.selectedBattery.id}/export.csv`);
      }
    } else if (action === "compare-battery-runs") {
      await loadBatteryComparison();
    } else if (action === "refresh-history") {
      await loadHistory();
    } else if (action === "reset-chart-zoom") {
      resetChartZoom(button.dataset.chartGroup);
    } else if (action === "export-history") {
      exportHistory();
    } else if (action === "run-report") {
      await openRunReport(Number(button.dataset.runId));
    } else if (action === "run-chart") {
      await openRunChart(Number(button.dataset.runId));
    } else if (action === "run-pdf") {
      window.location.assign(`/api/recordings/runs/${button.dataset.runId}/report.pdf`);
    } else if (action === "delete-run") {
      await deleteRun(Number(button.dataset.runId));
    } else if (action === "notifications") {
      await openNotifications();
    } else if (action === "mark-notifications-read") {
      await markNotificationsRead();
    } else if (action === "enable-browser-notifications") {
      await enableBrowserNotifications();
    } else if (action === "download-backup") {
      window.location.assign("/api/admin/backup");
    } else if (action === "logout") {
      await api("/api/auth/logout", { method: "POST" });
      location.assign("/login");
    } else if (action === "close-dialog") {
      document.getElementById(button.dataset.dialog)?.close();
    } else if (action === "close-curve") {
      elements.curveDialog.close();
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    if (["start", "start-all"].includes(action) && button.isConnected) {
      button.disabled = false;
    }
  }
});

elements.renameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api(`/api/devices/${encodeURIComponent(elements.renameAddress.value)}/details`, {
      method: "PUT",
      body: JSON.stringify({
        alias: elements.renameAlias.value,
        serial_number: elements.renameSerialNumber.value,
      }),
    });
    elements.renameDialog.close();
    showToast("Gerätedaten wurden gespeichert");
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const wasEnabled = Boolean(appState.settings?.login_enabled);
    const passwordChanged = Boolean(elements.settingsLoginPassword.value);
    const settings = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        default_program: elements.settingsDefaultProgram.value,
        phase_opacity_percent: Number(elements.settingsPhaseOpacity.value),
        theme: elements.settingsTheme.value,
        login_enabled: elements.settingsLoginEnabled.checked,
        login_username: elements.settingsLoginUsername.value,
        login_password: elements.settingsLoginPassword.value,
      }),
    });
    appState.settings = settings;
    applyTheme(settings.theme);
    elements.settingsLoginPassword.value = "";
    showToast("Einstellungen wurden gespeichert");
    if (settings.login_enabled && (!wasEnabled || passwordChanged)) {
      setTimeout(() => location.assign("/login"), 400);
    }
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.settingsLoginEnabled.addEventListener("change", () => {
  updateLoginSettingsVisibility();
});

elements.settingsPhaseOpacity.addEventListener("input", () => {
  elements.settingsPhaseOpacityValue.textContent =
    `${elements.settingsPhaseOpacity.value} %`;
});

elements.settingsTheme.addEventListener("change", () => {
  applyTheme(elements.settingsTheme.value);
});

elements.packBuilderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const batteryIds = [...elements.packBatterySelection.querySelectorAll(
    'input[name="packBattery"]:checked',
  )].map((input) => Number(input.value));
  if (batteryIds.length < 2) {
    showToast("Mindestens zwei getestete Zellen auswählen", true);
    return;
  }
  try {
    appState.packBuilder = await api("/api/batteries/pack-builder", {
      method: "POST",
      body: JSON.stringify({
        battery_ids: batteryIds,
        cells_per_group: Number(elements.packCellsPerGroup.value),
        group_count: Number(elements.packGroupCount.value),
        max_capacity_spread_percent: Number(elements.packCapacitySpread.value),
        max_resistance_spread_percent: Number(elements.packResistanceSpread.value),
      }),
    });
    renderPackBuilderResult();
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.restoreBackupFile.addEventListener("change", async () => {
  const file = elements.restoreBackupFile.files?.[0];
  if (!file) return;
  const confirmation = window.prompt(
    "Die aktuelle Datenbank wird ersetzt. Zum Fortfahren WIEDERHERSTELLEN eingeben:",
  );
  if (confirmation !== "WIEDERHERSTELLEN") {
    elements.restoreBackupFile.value = "";
    showToast("Wiederherstellung wurde abgebrochen");
    return;
  }
  try {
    const response = await fetch(
      "/api/admin/restore?confirmation=WIEDERHERSTELLEN",
      {
        method: "POST",
        headers: { "Content-Type": "application/zip" },
        body: file,
      },
    );
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    showToast("Backup eingespielt. Dienst startet neu.");
    setTimeout(() => location.reload(), 3500);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    elements.restoreBackupFile.value = "";
  }
});

elements.slotConfigurationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const address = elements.slotConfigurationAddress.value;
  const slot = Number(elements.slotConfigurationSlot.value);
  const programValue = elements.slotConfigurationProgram.value;
  if (!programValue) {
    showToast("Ein Startprogramm auswählen", true);
    return;
  }
  const profileId = programValue.startsWith("profile:")
    ? Number(programValue.split(":")[1])
    : null;
  const automaticProgram = programValue.startsWith("automatic:")
    ? programValue.split(":")[1]
    : null;
  const startAfter = elements.slotConfigurationStartAfter.value === "1";
  const createBattery = isNewBatterySelection(
    elements.slotConfigurationBattery.value,
  );
  try {
    const result = await api(`/api/devices/${encodeURIComponent(address)}/slots/${slot}/configuration`, {
      method: "PUT",
      body: JSON.stringify({
        battery_id: elements.slotConfigurationBattery.value && !createBattery
          ? Number(elements.slotConfigurationBattery.value)
          : null,
        create_battery: createBattery,
        program_source: profileId
          ? "profile"
          : automaticProgram
            ? "automatic"
            : "standard",
        profile_id: profileId,
        automatic_program: automaticProgram,
        capacity_mah: automaticProgram || profileId || createBattery
          ? Number(elements.slotConfigurationCapacity.value)
          : null,
        time_limit_mode: automaticProgram
          ? elements.slotConfigurationTimeLimitMode.value
          : "manual",
        time_limit_min: automaticProgram
          ? hoursToMinutes(elements.slotConfigurationTimeLimitHours.value)
          : 360,
      }),
    });
    if (result.battery && createBattery) {
      await loadBatteries();
    }
    if (startAfter) {
      await api(`/api/devices/${encodeURIComponent(address)}/slots/${slot}/start`, {
        method: "POST",
      });
    }
    elements.slotConfigurationDialog.close();
    showToast(
      startAfter
        ? `Slot ${slot} wurde mit dem gewählten Programm gestartet`
        : `Startprogramm für Slot ${slot} wurde übernommen`,
    );
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.deviceConfigurationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (elements.deviceConfigurationSubmit.disabled) return;
  const address = elements.deviceConfigurationAddress.value;
  const assignments = [...elements.deviceConfigurationSlots.querySelectorAll(
    "select[data-slot]",
  )].map((select) => {
    const createBattery = isNewBatterySelection(select.value);
    return {
      slot: Number(select.dataset.slot),
      battery_id: select.value && !createBattery ? Number(select.value) : null,
      create_battery: createBattery,
      capacity_mah: Number(
        elements.deviceConfigurationSlots.querySelector(
          `input[data-capacity-slot="${select.dataset.slot}"]`,
        )?.value,
      ) || null,
    };
  });
  const trackedBatteryIds = assignments
    .map((item) => item.battery_id)
    .filter((batteryId) => batteryId != null);
  if (new Set(trackedBatteryIds).size !== trackedBatteryIds.length) {
    showToast("Jede Batterienummer darf nur einmal verwendet werden", true);
    return;
  }
  const programValue = elements.deviceConfigurationProgram.value;
  if (!programValue) {
    showToast("Ein gemeinsames Startprogramm auswählen", true);
    return;
  }
  const profileId = programValue.startsWith("profile:")
    ? Number(programValue.split(":")[1])
    : null;
  const automaticProgram = programValue.startsWith("automatic:")
    ? programValue.split(":")[1]
    : null;
  const startAfter = elements.deviceConfigurationStartAfter.value === "1";
  const submitLabel = elements.deviceConfigurationSubmit.textContent;
  elements.deviceConfigurationSubmit.disabled = true;
  elements.deviceConfigurationSubmit.textContent = "Übertrage alle Slots...";
  try {
    const result = await api(
      `/api/devices/${encodeURIComponent(address)}/configuration`,
      {
        method: "PUT",
        body: JSON.stringify({
          slots: assignments,
          program_source: profileId
            ? "profile"
            : automaticProgram
              ? "automatic"
              : "standard",
          profile_id: profileId,
          automatic_program: automaticProgram,
          time_limit_mode: automaticProgram
            ? elements.deviceConfigurationTimeLimitMode.value
            : "manual",
          time_limit_min: automaticProgram
            ? hoursToMinutes(elements.deviceConfigurationTimeLimitHours.value)
            : 360,
        }),
      },
    );
    if (result.created_batteries?.length) {
      await loadBatteries();
    }
    if (startAfter) {
      await api(`/api/devices/${encodeURIComponent(address)}/start-all`, {
        method: "POST",
      });
    }
    elements.deviceConfigurationDialog.close();
    showToast(
      startAfter
        ? `Slots ${result.slots.join(", ")} wurden gestartet`
        : `Programme für Slots ${result.slots.join(", ")} wurden übernommen`,
    );
  } catch (error) {
    showToast(error.message, true);
  } finally {
    elements.deviceConfigurationSubmit.disabled = false;
    elements.deviceConfigurationSubmit.textContent = submitLabel;
  }
});

elements.profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const profileId = Number(elements.profileId.value);
  try {
    const path = profileId ? `/api/profiles/${profileId}` : "/api/profiles";
    await api(path, {
      method: profileId ? "PUT" : "POST",
      body: JSON.stringify(profileFormPayload()),
    });
    elements.profileDialog.close();
    appState.profileCategory = elements.profileCategory.value;
    await loadProfiles();
    showToast(profileId ? "Profil wurde aktualisiert" : "Profil wurde erstellt");
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.automaticProfileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const programKey = elements.automaticProfileKey.value;
  try {
    const path = programKey
      ? `/api/automatic-profiles/${encodeURIComponent(programKey)}`
      : "/api/automatic-profiles";
    await api(path, {
      method: programKey ? "PUT" : "POST",
      body: JSON.stringify(automaticProfileFormPayload()),
    });
    elements.automaticProfileDialog.close();
    appState.profileCategory = elements.automaticProfileCategory.value;
    await loadBatteryOptions();
    showToast(
      programKey
        ? "Automatikprofil wurde aktualisiert"
        : "Automatikprofil wurde erstellt",
    );
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.applyProfileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const profileId = Number(elements.applyProfileId.value);
  const slots = [...document.querySelectorAll('input[name="applySlot"]:checked')]
    .map((input) => Number(input.value));
  if (!slots.length) {
    showToast("Mindestens einen Slot auswählen", true);
    return;
  }
  try {
    await api(`/api/profiles/${profileId}/apply`, {
      method: "POST",
      body: JSON.stringify({
        address: elements.applyProfileDevice.value,
        slots,
        confirmation: elements.applyProfileConfirmation.value,
      }),
    });
    elements.applyProfileDialog.close();
    showToast("Profil wurde übertragen. Es wurde nicht gestartet.");
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.batteryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const batteryId = Number(elements.batteryId.value);
  try {
    const result = await api(
      batteryId ? `/api/batteries/${batteryId}` : "/api/batteries",
      {
        method: batteryId ? "PUT" : "POST",
        body: JSON.stringify({
          code: elements.batteryCode.value,
          name: elements.batteryName.value,
          battery_type_code: Number(elements.batteryType.value),
          nominal_capacity_mah: Number(elements.batteryCapacity.value),
          manufacturer: elements.batteryManufacturer.value,
          model: elements.batteryModel.value,
          form_factor: elements.batteryFormFactor.value,
          origin: elements.batteryOrigin.value,
          in_service_since: elements.batteryInServiceSince.value,
          protected: elements.batteryProtected.checked,
          notes: elements.batteryNotes.value,
          archived: elements.batteryForm.dataset.archived === "true",
        }),
      },
    );
    elements.batteryDialog.close();
    await loadBatteries();
    await selectBattery(result.battery.id);
    showToast(batteryId ? "Batterie wurde aktualisiert" : "Batterie wurde angelegt");
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.batteryLookupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = elements.batteryLookup.value.trim().toUpperCase();
  if (!code) return;
  const battery = appState.batteries.find(
    (candidate) => candidate.code.toUpperCase() === code,
  );
  if (battery) {
    await selectBattery(battery.id);
    return;
  }
  openBatteryDialog({ code });
});

elements.standardProgramForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const batteryId = Number(elements.standardBatteryId.value);
  try {
    await api(`/api/batteries/${batteryId}/standard-program`, {
      method: "PUT",
      body: JSON.stringify({
        mode_code: Number(elements.standardMode.value),
        charge_c_rate: Number(elements.standardChargeRate.value),
        discharge_c_rate: Number(elements.standardDischargeRate.value),
        cycle_count: Number(elements.standardCycleCount.value),
        cycle_mode: Number(elements.standardCycleMode.value),
        time_limit_mode: elements.standardTimeLimitMode.value,
        time_limit_min: hoursToMinutes(elements.standardTimeLimitHours.value),
      }),
    });
    elements.standardProgramDialog.close();
    await selectBattery(batteryId);
    showToast("Standardprogramm wurde gespeichert");
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.batteryRuns.addEventListener("change", (event) => {
  if (!event.target.matches('input[name="compareRun"]')) return;
  const selected = selectedBatteryRunIds();
  if (selected.length > 5) {
    event.target.checked = false;
    showToast("Höchstens fünf Läufe vergleichen", true);
  }
});

elements.profileBatteryType.addEventListener("change", () => {
  updateProfileModeOptions();
  refreshProfileLimits(true);
});
elements.profileCategory.addEventListener("change", () => {
  void createCategoryFromSelect(elements.profileCategory);
});
elements.automaticProfileCategory.addEventListener("change", () => {
  void createCategoryFromSelect(elements.automaticProfileCategory);
});
elements.profileMode.addEventListener("change", () => refreshProfileLimits(true));
elements.profileTimeLimitMode.addEventListener("change", updateProfileTimeLimitFields);
elements.automaticProfileMode.addEventListener(
  "change",
  updateAutomaticProfileFields,
);
elements.automaticProfileTimeLimitMode.addEventListener(
  "change",
  updateAutomaticProfileFields,
);
[
  elements.profileCapacity,
  elements.profileChargeCurrent,
  elements.profileDischargeCurrent,
  elements.profileChargeRest,
  elements.profileDischargeRest,
  elements.profileCycleCount,
  elements.profileCycleMode,
  elements.profileTimeLimit,
].forEach((input) => input.addEventListener(
  "input",
  () => refreshProfileLimits(false),
));
elements.applyProfileDevice.addEventListener("change", updateApplySlotState);
[
  elements.historyDevice,
  elements.historySlot,
  elements.historyHours,
].forEach((input) => input.addEventListener("change", () => {
  resetChartZoom("history", false);
  loadHistory();
}));
elements.slotConfigurationBattery.addEventListener("change", () => {
  elements.slotConfigurationBattery.dataset.selectedValue =
    elements.slotConfigurationBattery.value;
  const battery = findBattery(Number(elements.slotConfigurationBattery.value));
  if (
    battery
    && !elements.slotConfigurationProgram.value.startsWith("profile:")
  ) {
    elements.slotConfigurationCapacity.value = String(battery.nominal_capacity_mah);
  }
  updateSlotProgramOptions();
});
elements.slotConfigurationProgram.addEventListener(
  "change",
  updateSlotConfigurationProgram,
);
elements.slotConfigurationCapacity.addEventListener("input", renderSlotConfigurationPreview);
elements.slotConfigurationTimeLimitMode.addEventListener(
  "change",
  renderSlotConfigurationPreview,
);
elements.slotConfigurationTimeLimitHours.addEventListener(
  "input",
  renderSlotConfigurationPreview,
);
elements.deviceConfigurationSlots.addEventListener("change", (event) => {
  if (event.target.matches("select[data-slot]")) {
    event.target.dataset.selectedValue = event.target.value;
    const battery = findBattery(Number(event.target.value));
    const capacity = elements.deviceConfigurationSlots.querySelector(
      `input[data-capacity-slot="${event.target.dataset.slot}"]`,
    );
    if (
      battery
      && capacity
      && !elements.deviceConfigurationProgram.value.startsWith("profile:")
    ) {
      capacity.value = String(battery.nominal_capacity_mah);
    }
    refreshDeviceConfigurationBatteryOptions();
    updateDeviceConfigurationProgramOptions();
  }
});
elements.deviceConfigurationSlots.addEventListener("input", (event) => {
  if (event.target.matches("input[data-capacity-slot]")) {
    renderDeviceConfigurationPreview();
  }
});
elements.deviceConfigurationProgram.addEventListener(
  "change",
  updateDeviceConfigurationProgram,
);
elements.deviceConfigurationTimeLimitMode.addEventListener(
  "change",
  renderDeviceConfigurationPreview,
);
elements.deviceConfigurationTimeLimitHours.addEventListener(
  "input",
  renderDeviceConfigurationPreview,
);
elements.standardMode.addEventListener("change", updateStandardProgramFields);
elements.standardTimeLimitMode.addEventListener(
  "change",
  updateStandardProgramFields,
);
[
  elements.standardChargeRate,
  elements.standardDischargeRate,
  elements.standardCycleCount,
  elements.standardCycleMode,
  elements.standardTimeLimitHours,
].forEach((input) => input.addEventListener("input", renderStandardProgramPreview));
elements.batteryCompareMetric.addEventListener("change", () => {
  drawBatteryComparison(appState.batteryComparison);
});
window.addEventListener("resize", () => {
  clearTimeout(historyResizeTimer);
  historyResizeTimer = setTimeout(() => {
    if (appState.currentView === "recordingsView" && appState.history) {
      drawHistoryCharts(appState.history.points || []);
    }
    if (elements.runChartDialog.open && appState.runChart) {
      drawRunCharts(appState.runChart);
    }
  }, 120);
  clearTimeout(batteryResizeTimer);
  batteryResizeTimer = setTimeout(() => {
    if (appState.currentView === "batteryManagerView") {
      drawBatteryComparison(appState.batteryComparison);
    }
  }, 120);
});

function showView(viewId) {
  appState.currentView = viewId;
  document.querySelectorAll(".app-view").forEach((view) => {
    view.hidden = view.id !== viewId;
  });
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewId);
  });
  clearInterval(historyTimer);
  historyTimer = null;
  if (viewId === "devicesView") {
    render();
  } else if (viewId === "profilesView") {
    renderProfiles();
  } else if (viewId === "batteryManagerView") {
    renderBatteries();
    if (appState.selectedBattery) {
      requestAnimationFrame(() => drawBatteryComparison(appState.batteryComparison));
    }
  } else if (viewId === "recordingsView") {
    loadHistory();
    loadRecordingRuns();
    historyTimer = setInterval(() => {
      loadHistory({ quiet: true });
      loadRecordingRuns({ quiet: true });
    }, 15000);
  } else if (viewId === "settingsView") {
    renderSettings();
  }
}

async function loadReferenceData() {
  try {
    const [health, options, batteryOptions, settings] = await Promise.all([
      api("/api/health"),
      api("/api/profiles/options"),
      api("/api/batteries/options"),
      api("/api/settings"),
      loadProfiles(),
      loadBatteries(),
    ]);
    appState.profileOptions = options;
    appState.batteryOptions = batteryOptions;
    appState.settings = settings;
    applyTheme(settings.theme);
    renderVersionInfo(health);
    renderProfileBatteryOptions();
    renderBatteryTypeOptions();
    renderSettings();
    const hashMatch = location.hash.match(/^#battery=(\d+)$/);
    if (hashMatch) {
      showView("batteryManagerView");
      await selectBattery(Number(hashMatch[1]));
    }
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderVersionInfo(health) {
  const version = String(health?.version || "--");
  const fixes = Array.isArray(health?.fixes) ? health.fixes : [];
  appState.archivedBatteryRetentionDays = Math.max(
    1,
    Number(health?.archived_battery_retention_days) || 30,
  );
  elements.appVersion.textContent = version;
  elements.appVersionTitle.textContent = version;
  elements.appFixes.innerHTML = fixes.length
    ? fixes.map((fix) => `<li>${escapeHtml(fix)}</li>`).join("")
    : "<li>Keine Fix-Hinweise hinterlegt.</li>";
}

function renderSettings() {
  const automaticPrograms = appState.batteryOptions?.automatic_programs || [];
  elements.settingsDefaultProgram.innerHTML = [
    '<option value="">Kein Programm vorauswählen</option>',
    '<option value="standard">Standardprogramm der Batterie</option>',
    ...automaticPrograms.map((program) => (
      `<option value="automatic:${escapeHtml(program.key)}">${escapeHtml(program.label)} · ${escapeHtml(automaticProgramRateLabel(program))}</option>`
    )),
  ].join("");
  const selected = appState.settings?.default_program || "";
  if ([...elements.settingsDefaultProgram.options].some(
    (option) => option.value === selected,
  )) {
    elements.settingsDefaultProgram.value = selected;
  }
  elements.settingsTheme.value = ["system", "light", "dark"].includes(
    appState.settings?.theme,
  ) ? appState.settings.theme : "system";
  const phaseOpacity = Math.max(
    15,
    Math.min(25, Number(appState.settings?.phase_opacity_percent) || 15),
  );
  elements.settingsPhaseOpacity.value = String(phaseOpacity);
  elements.settingsPhaseOpacityValue.textContent = `${phaseOpacity} %`;
  elements.settingsLoginEnabled.checked = Boolean(
    appState.settings?.login_enabled,
  );
  elements.settingsLoginUsername.value =
    appState.settings?.login_username || "";
  elements.settingsLoginPassword.value = "";
  updateLoginSettingsVisibility();
}

function updateLoginSettingsVisibility() {
  const enabled = elements.settingsLoginEnabled.checked;
  elements.settingsLoginFields.hidden = !enabled;
  elements.settingsLoginUsername.required = enabled;
  elements.settingsLogoutButton.hidden = !appState.settings?.login_enabled;
}

function applyTheme(preference, redraw = true) {
  const normalized = ["system", "light", "dark"].includes(preference)
    ? preference
    : "system";
  const effective = normalized === "system"
    ? (themeMediaQuery.matches ? "dark" : "light")
    : normalized;
  appState.settings = { ...appState.settings, theme: normalized };
  document.documentElement.dataset.theme = effective;
  try {
    localStorage.setItem("mc3000-theme", normalized);
  } catch (_error) {
    // Private browsing can disable persistent storage; the active theme still works.
  }
  if (redraw) requestAnimationFrame(redrawThemeSensitiveCharts);
}

function redrawThemeSensitiveCharts() {
  drawSparklines();
  if (appState.currentView === "recordingsView" && appState.history) {
    drawHistoryCharts(appState.history.points || []);
  }
  if (appState.batteryComparison) {
    drawBatteryComparison(appState.batteryComparison);
  }
  if (elements.runChartDialog.open && appState.runChart) {
    drawRunCharts(appState.runChart);
  }
  if (elements.curveDialog.open && appState.curve) {
    drawCurve(elements.curveCanvas, appState.curve.points || []);
  }
}

themeMediaQuery.addEventListener("change", () => {
  if (appState.settings?.theme === "system") applyTheme("system");
});

async function loadProfiles() {
  const [data, categories] = await Promise.all([
    api("/api/profiles"),
    api("/api/profile-categories"),
  ]);
  appState.profiles = data.profiles || [];
  appState.profileCategories = categories.categories || [];
  renderProfiles();
  render();
}

async function loadBatteryOptions() {
  appState.batteryOptions = await api("/api/batteries/options");
  renderSettings();
  renderProfiles();
  render();
}

function renderProfiles() {
  if (!elements.profileList) return;
  const category = appState.profileCategory;
  const automaticPrograms = appState.batteryOptions?.automatic_programs || [];
  const ownProfiles = appState.profiles.filter((profile) => !profile.is_builtin);
  const ownAutomaticPrograms = automaticPrograms.filter(
    (program) => !program.is_builtin,
  );
  const categories = [
    {
      key: "all",
      label: "Alle Profile",
      count: automaticPrograms.length + appState.profiles.length,
      description: "Alle Automatikprogramme und gespeicherten Profile.",
      is_builtin: true,
    },
    {
      key: "own",
      label: "Eigene Profile",
      count: ownAutomaticPrograms.length + ownProfiles.length,
      description: "Selbst angelegte und duplizierte Profile.",
      is_builtin: true,
    },
    ...appState.profileCategories.map((item) => ({
      key: item.key,
      label: item.name,
      count: automaticPrograms.filter(
        (program) => program.category_key === item.key,
      ).length + appState.profiles.filter(
        (profile) => profile.category_key === item.key,
      ).length,
      description: item.description || `Profile in „${item.name}“.`,
      is_builtin: item.is_builtin,
    })),
  ];
  if (elements.profileCategoryFilters) {
    elements.profileCategoryFilters.innerHTML = categories.map((item) => `
      <span class="profile-category-entry">
        <button
          class="profile-category-button ${item.key === category ? "active" : ""}"
          data-action="filter-profiles"
          data-profile-category="${escapeHtml(item.key)}"
          aria-pressed="${item.key === category ? "true" : "false"}"
        >
          ${escapeHtml(item.label)}
          <span>${formatInteger(item.count)}</span>
        </button>
        ${item.is_builtin ? "" : `<button class="profile-category-delete" data-action="delete-profile-category" data-profile-category="${escapeHtml(item.key)}" title="Kategorie löschen">×</button>`}
      </span>
    `).join("");
  }
  const selectedCategory = categories.find((item) => item.key === category)
    || categories[0];
  if (elements.profileCategoryDescription) {
    elements.profileCategoryDescription.textContent =
      selectedCategory.description;
  }

  const visibleAutomaticPrograms = category === "own"
    ? ownAutomaticPrograms
    : category === "all"
      ? automaticPrograms
      : automaticPrograms.filter((program) => program.category_key === category);
  const storedProfiles = category === "own"
    ? ownProfiles
    : category === "all"
      ? appState.profiles
      : appState.profiles.filter((profile) => profile.category_key === category);
  const automaticRows = visibleAutomaticPrograms.map(
    (program) => renderAutomaticProfileRow(program),
  );
  const storedRows = storedProfiles.map((profile) => `
      <tr>
        <td>
          <strong>${escapeHtml(profile.name)}</strong>
          ${profile.description ? `<small>${escapeHtml(profile.description)}</small>` : ""}
          <small>${profile.is_builtin ? "Mitgeliefertes Profil" : "Eigenes Profil"}</small>
        </td>
        <td>${escapeHtml(profileCategoryName(profile.category_key))}</td>
        <td>${escapeHtml(profile.battery_type)}</td>
        <td>
          ${escapeHtml(profile.mode)}
          <small>${escapeHtml(profileTimeLimitLabel(profile))}</small>
        </td>
        <td>${formatNumber(profile.charge_current_ma / 1000, 2)} A</td>
        <td>${formatNumber(profile.charge_voltage_mv / 1000, 2)} V</td>
        <td class="row-actions">
          <button class="primary" data-action="apply-profile" data-profile-id="${profile.id}">Anwenden</button>
          <button data-action="duplicate-profile" data-profile-id="${profile.id}">Duplizieren</button>
          <button data-action="edit-profile" data-profile-id="${profile.id}">Bearbeiten</button>
          <button class="icon-button" data-action="delete-profile" data-profile-id="${profile.id}" title="Profil löschen" aria-label="Profil löschen">×</button>
        </td>
      </tr>
    `);
  const rows = [...automaticRows, ...storedRows];
  elements.profileList.innerHTML = rows.length
    ? rows.join("")
    : `<tr><td colspan="7" class="table-empty">${category === "own"
      ? "Noch keine eigenen Profile vorhanden"
      : "In dieser Kategorie sind noch keine Profile vorhanden"}</td></tr>`;
}

function renderAutomaticProfileRow(program) {
  const mode = (appState.batteryOptions?.modes || []).find(
    (candidate) => Number(candidate.code) === Number(program.mode_code),
  )?.name || "Automatik";
  return `
    <tr class="automatic-profile-row">
      <td>
        <strong>${escapeHtml(program.label)}</strong>
        <small>${escapeHtml(program.description)}</small>
        <small>${program.is_builtin ? "Mitgeliefertes" : "Eigenes"} Automatikprofil · Strom nach Kapazität</small>
      </td>
      <td>${escapeHtml(profileCategoryName(program.category_key))}</td>
      <td>Li-Ion / LiFePO4</td>
      <td>
        ${escapeHtml(mode)}
        <small>${escapeHtml(automaticProfileTimeLimitLabel(program))}</small>
      </td>
      <td>${escapeHtml(automaticProgramRateLabel(program))}</td>
      <td>Nach Akkutyp</td>
      <td class="row-actions">
        <button
          class="primary"
          data-action="use-automatic-profile"
          data-program-key="${escapeHtml(program.key)}"
        >Bei Slot wählen</button>
        <button
          data-action="duplicate-automatic-profile"
          data-program-key="${escapeHtml(program.key)}"
        >Duplizieren</button>
        <button
          data-action="edit-automatic-profile"
          data-program-key="${escapeHtml(program.key)}"
        >Bearbeiten</button>
      </td>
    </tr>
  `;
}

function profileCategoryName(key) {
  return appState.profileCategories.find((item) => item.key === key)?.name
    || "Allgemein";
}

function renderProfileCategoryOptions(select, selectedKey) {
  select.innerHTML = [
    ...appState.profileCategories.map((category) => (
      `<option value="${escapeHtml(category.key)}">${escapeHtml(category.name)}</option>`
    )),
    '<option value="__new__">＋ Neue Kategorie…</option>',
  ].join("");
  const fallback = appState.profileCategories.some(
    (category) => category.key === selectedKey,
  ) ? selectedKey : "general";
  select.value = fallback;
  select.dataset.previousValue = fallback;
}

async function createCategoryFromSelect(select) {
  if (select.value !== "__new__") {
    select.dataset.previousValue = select.value;
    return;
  }
  const previous = select.dataset.previousValue || "general";
  const name = window.prompt("Name der neuen Profilkategorie:");
  if (!name?.trim()) {
    select.value = previous;
    return;
  }
  try {
    const result = await api("/api/profile-categories", {
      method: "POST",
      body: JSON.stringify({ name: name.trim() }),
    });
    const categories = await api("/api/profile-categories");
    appState.profileCategories = categories.categories || [];
    renderProfileCategoryOptions(select, result.category.key);
    select.value = result.category.key;
    select.dataset.previousValue = result.category.key;
    renderProfiles();
    showToast(`Kategorie „${result.category.name}“ wurde angelegt`);
  } catch (error) {
    select.value = previous;
    showToast(error.message, true);
  }
}

function renderProfileBatteryOptions() {
  const options = appState.profileOptions?.battery_types || [];
  elements.profileBatteryType.innerHTML = options.map((battery) => (
    `<option value="${battery.code}">${escapeHtml(battery.name)}</option>`
  )).join("");
  updateProfileModeOptions();
}

function updateProfileModeOptions(selectedMode = null) {
  const battery = selectedBatteryOption();
  const previous = selectedMode ?? Number(elements.profileMode.value);
  elements.profileMode.innerHTML = (battery?.modes || []).map((mode) => (
    `<option value="${mode.code}">${escapeHtml(mode.name)}</option>`
  )).join("");
  if ([...elements.profileMode.options].some((option) => Number(option.value) === previous)) {
    elements.profileMode.value = String(previous);
  }
}

function duplicateAutomaticProfile(program) {
  if (!program) return;
  const originalName = String(program.label || "Automatikprofil")
    .replace(/\s+\(Kopie(?: \d+)?\)$/u, "");
  const existingNames = new Set(
    (appState.batteryOptions?.automatic_programs || []).map(
      (candidate) => candidate.label,
    ),
  );
  let copyName = "";
  for (let copyNumber = 1; !copyName; copyNumber += 1) {
    const suffix = copyNumber === 1 ? " (Kopie)" : ` (Kopie ${copyNumber})`;
    const baseName = originalName.slice(0, 80 - suffix.length).trimEnd();
    const candidateName = `${baseName}${suffix}`;
    if (!existingNames.has(candidateName)) copyName = candidateName;
  }
  openAutomaticProfileDialog(
    { ...program, key: "", label: copyName },
    { duplicate: true },
  );
  elements.automaticProfileName.select();
}

function openAutomaticProfileDialog(program, { duplicate = false } = {}) {
  if (!program || !appState.batteryOptions) return;
  elements.automaticProfileDialogTitle.textContent = duplicate
    ? "Automatikprofil duplizieren"
    : "Automatikprofil bearbeiten";
  elements.automaticProfileKey.value = duplicate ? "" : program.key;
  elements.automaticProfileName.value = program.label || "";
  elements.automaticProfileDescription.value = program.description || "";
  renderProfileCategoryOptions(
    elements.automaticProfileCategory,
    program.category_key || "automatic",
  );
  elements.automaticProfileMode.innerHTML = (
    appState.batteryOptions.modes || []
  ).map((mode) => (
    `<option value="${mode.code}">${escapeHtml(mode.name)}</option>`
  )).join("");
  elements.automaticProfileMode.value = String(program.mode_code ?? 0);
  elements.automaticProfileChargeRate.value =
    String(program.charge_c_rate ?? 0.5);
  elements.automaticProfileDischargeRate.value =
    String(program.discharge_c_rate ?? 1);
  elements.automaticProfileChargeRest.value =
    String(program.charge_rest_min ?? 0);
  elements.automaticProfileDischargeRest.value =
    String(program.discharge_rest_min ?? 0);
  elements.automaticProfileCycleCount.value =
    String(program.cycle_count ?? 1);
  elements.automaticProfileCycleMode.innerHTML = (
    appState.batteryOptions.cycle_modes || []
  ).map((mode) => (
    `<option value="${mode.code}">${escapeHtml(mode.name)}</option>`
  )).join("");
  elements.automaticProfileCycleMode.value =
    String(program.cycle_mode ?? 0);
  elements.automaticProfileTempLimit.value =
    String(program.temp_limit_c ?? 45);
  elements.automaticProfileTimeLimitMode.value =
    program.time_limit_mode ?? "manual";
  elements.automaticProfileTimeLimitHours.value =
    String(Number(program.time_limit_min ?? 360) / 60);
  updateAutomaticProfileFields();
  elements.automaticProfileDialog.showModal();
  elements.automaticProfileName.focus();
}

function updateAutomaticProfileFields() {
  const mode = Number(elements.automaticProfileMode.value);
  const cycle = mode === 4;
  elements.automaticProfileChargeRate.closest("label").hidden = mode === 3;
  elements.automaticProfileDischargeRate.closest("label").hidden = mode === 0;
  elements.automaticProfileCycleCount.closest("label").hidden = !cycle;
  elements.automaticProfileCycleMode.closest("label").hidden = !cycle;
  elements.automaticProfileCycleCount.disabled = !cycle;
  elements.automaticProfileCycleMode.disabled = !cycle;
  const manual = elements.automaticProfileTimeLimitMode.value === "manual";
  elements.automaticProfileTimeLimitField.hidden = !manual;
  elements.automaticProfileTimeLimitHours.required = manual;
  elements.automaticProfileValidationHint.textContent = (
    "Lade- und Entladestrom werden aus der Kapazität im Slot berechnet und "
    + "automatisch auf 3,00 A Laden bzw. 2,00 A Entladen begrenzt. "
    + "Die Endspannungen richten sich weiterhin nach Li-Ion oder LiFePO4."
  );
}

function automaticProfileFormPayload() {
  return {
    label: elements.automaticProfileName.value,
    description: elements.automaticProfileDescription.value,
    category_key: elements.automaticProfileCategory.value,
    mode_code: Number(elements.automaticProfileMode.value),
    charge_c_rate: Number(elements.automaticProfileChargeRate.value),
    discharge_c_rate: Number(elements.automaticProfileDischargeRate.value),
    charge_rest_min: Number(elements.automaticProfileChargeRest.value),
    discharge_rest_min: Number(elements.automaticProfileDischargeRest.value),
    cycle_count: Number(elements.automaticProfileCycleCount.value),
    cycle_mode: Number(elements.automaticProfileCycleMode.value),
    temp_limit_c: Number(elements.automaticProfileTempLimit.value),
    time_limit_mode: elements.automaticProfileTimeLimitMode.value,
    time_limit_min: hoursToMinutes(
      elements.automaticProfileTimeLimitHours.value,
    ),
  };
}

function duplicateProfile(profile) {
  if (!profile) return;
  const originalName = String(profile.name || "Profil")
    .replace(/\s+\(Kopie(?: \d+)?\)$/u, "");
  const existingNames = new Set(appState.profiles.map((candidate) => candidate.name));
  let copyName = "";
  for (let copyNumber = 1; !copyName; copyNumber += 1) {
    const suffix = copyNumber === 1 ? " (Kopie)" : ` (Kopie ${copyNumber})`;
    const baseName = originalName.slice(0, 80 - suffix.length).trimEnd();
    const candidateName = `${baseName}${suffix}`;
    if (!existingNames.has(candidateName)) {
      copyName = candidateName;
    }
  }
  openProfileDialog(
    { ...profile, id: null, name: copyName },
    { duplicate: true },
  );
  elements.profileName.select();
}

function openProfileDialog(profile = null, { duplicate = false } = {}) {
  if (!appState.profileOptions) {
    showToast("Profiloptionen werden noch geladen", true);
    return;
  }
  elements.profileDialogTitle.textContent = duplicate
    ? "Ladeprofil duplizieren"
    : profile
      ? "Ladeprofil bearbeiten"
      : "Ladeprofil erstellen";
  elements.profileId.value = profile?.id || "";
  elements.profileName.value = profile?.name || "";
  elements.profileDescription.value = profile?.description || "";
  renderProfileCategoryOptions(
    elements.profileCategory,
    profile?.category_key || "general",
  );
  elements.profileBatteryType.value = String(profile?.battery_type_code ?? 0);
  updateProfileModeOptions(profile?.mode_code ?? 0);
  elements.profileMode.value = String(profile?.mode_code ?? 0);

  const defaults = selectedBatteryOption()?.defaults || {};
  elements.profileCapacity.value = profile?.capacity_mah ?? 2000;
  elements.profileChargeCurrent.value = (profile?.charge_current_ma ?? 1000) / 1000;
  elements.profileDischargeCurrent.value = (profile?.discharge_current_ma ?? 500) / 1000;
  elements.profileChargeVoltage.value = (profile?.charge_voltage_mv ?? defaults.charge_default_mv ?? 4200) / 1000;
  elements.profileDischargeVoltage.value = (profile?.discharge_voltage_mv ?? defaults.discharge_default_mv ?? 3000) / 1000;
  elements.profileChargeEndCurrent.value = (profile?.charge_end_current_ma ?? 100) / 1000;
  elements.profileDischargeEndCurrent.value = (profile?.discharge_end_current_ma ?? 500) / 1000;
  elements.profileChargeRest.value = profile?.charge_rest_min ?? 0;
  elements.profileDischargeRest.value = profile?.discharge_rest_min ?? 0;
  elements.profileCycleCount.value = profile?.cycle_count ?? 1;
  elements.profileCycleMode.value = String(profile?.cycle_mode ?? 0);
  elements.profileDeltaPeak.value = profile?.delta_peak_mv ?? 0;
  elements.profileTrickleCurrent.value = profile?.trickle_current_ma ?? 0;
  elements.profileKeepVoltage.value = (profile?.keep_voltage_mv ?? defaults.keep_default_mv ?? 4150) / 1000;
  elements.profileTempLimit.value = profile?.temp_limit_c ?? 45;
  elements.profileTimeLimitMode.value = profile?.time_limit_mode ?? "manual";
  elements.profileTimeLimit.value = (profile?.time_limit_min ?? 360) / 60;
  refreshProfileLimits(false);
  updateProfileTimeLimitFields();
  elements.profileDialog.showModal();
  elements.profileName.focus();
}

function refreshProfileLimits(resetValues) {
  const battery = selectedBatteryOption();
  if (!battery) return;
  const modeCode = Number(elements.profileMode.value);
  const defaults = { ...battery.defaults };
  const storageDefaults = {
    0: [3650, 4000, 3800],
    1: [3150, 3400, 3300],
    2: [3750, 4100, 3900],
    8: [2250, 2600, 2400],
  };
  if (modeCode === 2 && storageDefaults[battery.code]) {
    [defaults.charge_min_mv, defaults.charge_max_mv, defaults.charge_default_mv] =
      storageDefaults[battery.code];
  }

  setVoltageInputLimits(
    elements.profileChargeVoltage,
    defaults.charge_min_mv,
    defaults.charge_max_mv,
  );
  setVoltageInputLimits(
    elements.profileDischargeVoltage,
    defaults.discharge_min_mv,
    defaults.discharge_max_mv,
  );
  setVoltageInputLimits(
    elements.profileKeepVoltage,
    defaults.keep_min_mv,
    defaults.keep_max_mv,
  );
  if (resetValues) {
    elements.profileChargeVoltage.value = defaults.charge_default_mv / 1000;
    elements.profileDischargeVoltage.value = defaults.discharge_default_mv / 1000;
    elements.profileKeepVoltage.value = defaults.keep_default_mv / 1000;
    if (!battery.nickel) {
      elements.profileDeltaPeak.value = 0;
      elements.profileTrickleCurrent.value = 0;
    }
  }
  elements.profileDeltaPeak.disabled = !battery.nickel;
  elements.profileTrickleCurrent.disabled = !battery.nickel;
  const breakIn = battery.nickel && modeCode === 2;
  const previousCycleMode = Number(elements.profileCycleMode.value);
  elements.profileCycleMode.innerHTML = breakIn
    ? '<option value="0">C&gt;D&gt;C</option><option value="1">D&gt;C&gt;D</option>'
    : [
      '<option value="0">C&gt;D</option>',
      '<option value="1">C&gt;D&gt;C</option>',
      '<option value="2">D&gt;C</option>',
      '<option value="3">D&gt;C&gt;D</option>',
    ].join("");
  if ([...elements.profileCycleMode.options].some(
    (option) => Number(option.value) === previousCycleMode,
  )) {
    elements.profileCycleMode.value = String(previousCycleMode);
  }
  const cycleRelevant = modeCode === 4 || breakIn;
  elements.profileCycleCount.disabled = !cycleRelevant;
  elements.profileCycleMode.disabled = !cycleRelevant;
  elements.profileValidationHint.textContent =
    `Zulässige Endspannungen: ${formatNumber(defaults.charge_min_mv / 1000, 2)} bis ${formatNumber(defaults.charge_max_mv / 1000, 2)} V beim Laden, ` +
    `${formatNumber(defaults.discharge_min_mv / 1000, 2)} bis ${formatNumber(defaults.discharge_max_mv / 1000, 2)} V beim Entladen. ` +
    profileTimeLimitPreview();
}

function profileFormPayload() {
  return {
    name: elements.profileName.value,
    description: elements.profileDescription.value,
    category_key: elements.profileCategory.value,
    battery_type_code: Number(elements.profileBatteryType.value),
    mode_code: Number(elements.profileMode.value),
    capacity_mah: Number(elements.profileCapacity.value),
    charge_current_ma: toMilli(elements.profileChargeCurrent.value),
    discharge_current_ma: toMilli(elements.profileDischargeCurrent.value),
    charge_voltage_mv: toMilli(elements.profileChargeVoltage.value),
    discharge_voltage_mv: toMilli(elements.profileDischargeVoltage.value),
    charge_end_current_ma: toMilli(elements.profileChargeEndCurrent.value),
    discharge_end_current_ma: toMilli(elements.profileDischargeEndCurrent.value),
    charge_rest_min: Number(elements.profileChargeRest.value),
    discharge_rest_min: Number(elements.profileDischargeRest.value),
    cycle_count: Number(elements.profileCycleCount.value),
    cycle_mode: Number(elements.profileCycleMode.value),
    delta_peak_mv: Number(elements.profileDeltaPeak.value),
    trickle_current_ma: Number(elements.profileTrickleCurrent.value),
    keep_voltage_mv: toMilli(elements.profileKeepVoltage.value),
    temp_limit_c: Number(elements.profileTempLimit.value),
    time_limit_mode: elements.profileTimeLimitMode.value,
    time_limit_min: hoursToMinutes(elements.profileTimeLimit.value),
  };
}

function openApplyProfileDialog(profile) {
  if (!profile) return;
  elements.applyProfileId.value = String(profile.id);
  elements.applyProfileFacts.innerHTML = `
    <strong>${escapeHtml(profile.name)}</strong>
    <span>${escapeHtml(profile.battery_type)} · ${escapeHtml(profile.mode)}</span>
    <span>${formatNumber(profile.charge_current_ma / 1000, 2)} A · ${formatNumber(profile.charge_voltage_mv / 1000, 2)} V · ${escapeHtml(profileTimeLimitLabel(profile))}</span>
  `;
  elements.applyProfileDevice.innerHTML = appState.devices.map((device) => (
    `<option value="${escapeHtml(device.address)}" ${device.connected ? "" : "disabled"}>${escapeHtml(device.alias)}</option>`
  )).join("");
  const connected = appState.devices.find((device) => device.connected);
  if (!connected) {
    showToast("Kein MC3000 ist verbunden", true);
    return;
  }
  elements.applyProfileDevice.value = connected.address;
  document.querySelectorAll('input[name="applySlot"]').forEach((input) => {
    input.checked = false;
  });
  elements.applyProfileConfirmation.value = "";
  updateApplySlotState();
  elements.applyProfileDialog.showModal();
}

function updateApplySlotState() {
  const device = findDevice(elements.applyProfileDevice.value);
  document.querySelectorAll('input[name="applySlot"]').forEach((input) => {
    const slot = device?.slots?.[Number(input.value) - 1];
    input.disabled = !device?.connected || Boolean(slot?.active);
    if (input.disabled) input.checked = false;
  });
}

async function deleteProfile(profileId) {
  const profile = findProfile(profileId);
  if (!profile || !window.confirm(`Profil "${profile.name}" wirklich löschen?`)) return;
  await api(`/api/profiles/${profileId}`, { method: "DELETE" });
  await loadProfiles();
  showToast("Profil wurde gelöscht");
}

async function loadBatteries() {
  const data = await api(
    appState.showArchivedBatteries
      ? "/api/batteries?include_archived=true"
      : "/api/batteries",
  );
  appState.batteries = data.batteries || [];
  if (appState.selectedBattery) {
    const current = findBattery(appState.selectedBattery.id);
    if (current) appState.selectedBattery = current;
  }
  renderBatteries();
  render();
}

function renderBatteries() {
  if (!elements.batteryList) return;
  const visibleBatteries = appState.showArchivedBatteries
    ? appState.batteries.filter((battery) => battery.archived)
    : appState.batteries.filter((battery) => !battery.archived);
  elements.batteryArchiveToggle.textContent = appState.showArchivedBatteries
    ? "Aktive Batterien"
    : "Archiv öffnen";
  elements.batteryList.innerHTML = visibleBatteries.length
    ? visibleBatteries.map((battery) => {
      const active = battery.id === appState.selectedBattery?.id;
      const statistics = battery.statistics || {};
      const soh = statistics.soh_percent;
      const capacityRatio = statistics.latest_capacity_ratio_percent;
      const measuredCapacity = soh != null
        ? statistics.latest_capacity_mah
        : statistics.latest_capacity_result_mah;
      const percentageLabel = soh != null
        ? `SOH ${formatNumber(soh, 1)} %`
        : capacityRatio != null
          ? `Soll/Ist ${formatNumber(capacityRatio, 1)} %`
          : null;
      return `
        <button class="battery-list-item ${active ? "active" : ""}" data-action="select-battery" data-battery-id="${battery.id}">
          <span>
            <strong>${escapeHtml(battery.code)}</strong>
            <small>${escapeHtml(battery.name || battery.battery_type)}</small>
          </span>
          <span class="battery-list-result">
            ${percentageLabel
              ? `<small>Kapazität ${measuredCapacity == null ? "--" : formatInteger(measuredCapacity)} mAh</small>
                <strong class="battery-list-value">${percentageLabel}</strong>`
              : "<small>Noch keine Messung</small>"}
          </span>
        </button>
      `;
    }).join("")
    : `<div class="battery-list-empty">${appState.showArchivedBatteries
      ? "Das Archiv ist leer"
      : "Noch keine Batterien angelegt"}</div>`;
  renderBatterySuggestions();
  renderPackBatterySelection();
}

function renderPackBatterySelection() {
  const eligible = appState.batteries.filter(
    (battery) => (
      !battery.archived
      && Number(battery.statistics?.latest_capacity_mah) > 0
    ),
  );
  elements.packBatterySelection.innerHTML = eligible.length
    ? eligible.map((battery) => `
      <label>
        <input type="checkbox" name="packBattery" value="${battery.id}">
        <span>
          <strong>${escapeHtml(battery.code)}</strong>
          <small>${formatInteger(battery.statistics.latest_capacity_mah)} mAh · ${battery.statistics.latest_resistance_mohm == null ? "IR fehlt" : `${formatInteger(battery.statistics.latest_resistance_mohm)} mΩ`}</small>
        </span>
      </label>
    `).join("")
    : '<p class="form-note">Es gibt noch keine Zellen mit abgeschlossenem Kapazitätstest.</p>';
}

function renderPackBuilderResult() {
  const result = appState.packBuilder;
  if (!result) {
    elements.packBuilderResult.innerHTML = "";
    return;
  }
  elements.packBuilderResult.innerHTML = `
    <div class="pack-result-head ${result.all_groups_within_limits ? "ok" : "warning"}">
      <strong>${result.all_groups_within_limits ? "Passende Gruppen gefunden" : "Gruppen mit Abweichungen gefunden"}</strong>
      <span>${result.eligible_cell_count} Zellen ausgewertet</span>
    </div>
    <div class="pack-groups">
      ${result.groups.map((group) => `
        <article class="pack-group ${group.within_limits ? "ok" : "warning"}">
          <header><strong>Gruppe ${group.number}</strong><span>${formatInteger(group.average_capacity_mah)} mAh Mittelwert</span></header>
          <div class="pack-cells">
            ${group.cells.map((cell) => `
              <span><strong>${escapeHtml(cell.code)}</strong><small>${formatInteger(cell.capacity_mah)} mAh · ${cell.resistance_mohm == null ? "IR fehlt" : `${formatInteger(cell.resistance_mohm)} mΩ`}</small></span>
            `).join("")}
          </div>
          <p>Kapazitätsabweichung ${formatNumber(group.capacity_spread_percent, 2)} % · Widerstandsabweichung ${group.resistance_spread_percent == null ? "--" : `${formatNumber(group.resistance_spread_percent, 2)} %`}</p>
          ${group.warnings.map((warning) => `<small class="pack-warning">${escapeHtml(warning)}</small>`).join("")}
        </article>
      `).join("")}
    </div>
  `;
}

function renderBatteryTypeOptions() {
  elements.batteryType.innerHTML = (appState.batteryOptions?.battery_types || [])
    .map((battery) => (
      `<option value="${battery.code}">${escapeHtml(battery.name)}</option>`
    )).join("");
}

function openBatteryDialog(battery = null) {
  elements.batteryDialogTitle.textContent = battery?.id
    ? "Batterie bearbeiten"
    : "Batterie anlegen";
  elements.batteryId.value = battery?.id || "";
  elements.batteryForm.dataset.archived = String(Boolean(battery?.archived));
  elements.batteryCode.value = battery?.code || "";
  elements.batteryName.value = battery?.name || "";
  elements.batteryType.value = String(battery?.battery_type_code ?? 0);
  elements.batteryCapacity.value = battery?.nominal_capacity_mah ?? 2000;
  elements.batteryManufacturer.value = battery?.manufacturer || "";
  elements.batteryModel.value = battery?.model || "";
  elements.batteryFormFactor.value = battery?.form_factor || "";
  elements.batteryOrigin.value = battery?.origin || "";
  elements.batteryInServiceSince.value = battery?.in_service_since || "";
  elements.batteryProtected.checked = Boolean(battery?.protected);
  elements.batteryNotes.value = battery?.notes || "";
  elements.batteryDialog.showModal();
  elements.batteryCode.focus();
  if (battery?.code) elements.batteryCode.select();
}

async function selectBattery(batteryId) {
  const data = await api(`/api/batteries/${batteryId}`);
  appState.selectedBattery = data.battery;
  appState.batteryRuns = data.runs || [];
  appState.batteryComparison = null;
  renderBatteries();
  renderBatteryDetail();
}

function renderBatteryDetail() {
  const battery = appState.selectedBattery;
  elements.batteryDetailEmpty.hidden = Boolean(battery);
  elements.batteryDetail.hidden = !battery;
  if (!battery) return;
  const statistics = battery.statistics || {};
  const soh = statistics.soh_percent;
  const latestResistance = statistics.latest_resistance_mohm;
  const resistanceChange = statistics.resistance_change_percent;
  const archivedAt = battery.archived_at ? new Date(battery.archived_at) : null;
  const archiveHistoryExpiresAt = archivedAt && !Number.isNaN(archivedAt.getTime())
    ? new Date(
      archivedAt.getTime()
      + appState.archivedBatteryRetentionDays * 24 * 60 * 60 * 1000,
    )
    : null;
  elements.batteryDetailType.textContent = battery.battery_type.toUpperCase();
  elements.batteryDetailTitle.textContent = battery.name
    ? `${battery.code} · ${battery.name}`
    : battery.code;
  elements.batteryDetailMeta.textContent = [
    `${formatInteger(battery.nominal_capacity_mah)} mAh Nennkapazität`,
    battery.manufacturer,
    battery.model,
    battery.form_factor,
    battery.origin ? `Herkunft: ${battery.origin}` : "",
    battery.in_service_since ? `in Betrieb seit ${formatDate(battery.in_service_since)}` : "",
    battery.protected ? "mit Protection" : "ohne Protection",
    `angelegt ${formatDate(battery.created_at)}`,
    battery.archived && archivedAt ? `archiviert ${formatDate(archivedAt)}` : "",
    battery.archived && archiveHistoryExpiresAt
      ? `Messwerte bis ${formatDate(archiveHistoryExpiresAt)}`
      : "",
  ].filter(Boolean).join(" · ");
  elements.batteryArchiveAction.textContent = battery.archived
    ? "Wiederherstellen"
    : "Archivieren";
  elements.batteryArchiveAction.classList.toggle("danger-quiet", !battery.archived);
  elements.batteryDeleteAction.hidden = !battery.archived;
  elements.batteryStats.innerHTML = `
    <div>
      <span>Kapazitäts-SOH</span>
      <strong>${soh == null ? "--" : `${formatNumber(soh, 1)} %`}</strong>
      <small>${soh == null ? "Noch kein Kapazitätstest" : `Lauf ${statistics.soh_basis_run_id}`}</small>
    </div>
    <div>
      <span>Letztes Soll / Ist</span>
      <strong>${statistics.latest_capacity_ratio_percent == null ? "--" : `${formatNumber(statistics.latest_capacity_ratio_percent, 1)} %`}</strong>
      <small>${statistics.latest_capacity_ratio_percent == null
        ? "Noch keine abgeschlossene Entladephase"
        : `Soll ${formatInteger(statistics.latest_capacity_target_mah)} / Ist ${formatInteger(statistics.latest_capacity_result_mah)} mAh · Lauf ${statistics.latest_capacity_result_run_id}`}</small>
    </div>
    <div>
      <span>Innenwiderstand</span>
      <strong>${latestResistance == null ? "--" : `${formatInteger(latestResistance)} mΩ`}</strong>
      <small>${resistanceChange == null ? "Noch kein Trend" : `${resistanceChange >= 0 ? "+" : ""}${formatNumber(resistanceChange, 1)} % seit erster Messung`}</small>
    </div>
    <div>
      <span>Programmläufe</span>
      <strong>${formatInteger(statistics.run_count || 0)}</strong>
      <small>${formatInteger(statistics.capacity_test_count || 0)} Kapazitätstests</small>
    </div>
  `;
  renderBatteryRuns();
  renderBatteryComparisonLegend(null);
  requestAnimationFrame(() => drawBatteryComparison(null));
}

function renderBatteryRuns() {
  elements.batteryRuns.innerHTML = appState.batteryRuns.length
    ? appState.batteryRuns.map((run) => {
      const device = findDevice(run.address);
      return `
        <tr>
          <td><input type="checkbox" name="compareRun" value="${run.id}" aria-label="Lauf ${run.id} auswählen"></td>
          <td>${formatDateTime(run.started_at)}</td>
          <td>${escapeHtml(run.mode)}${run.ended_at ? "" : " · läuft"}</td>
          <td>${escapeHtml(device?.alias || "MC3000")} · Slot ${run.slot}</td>
          <td>${run.capacity_actual_mah == null
            ? run.max_capacity_mah == null ? "--" : `${formatInteger(run.max_capacity_mah)} mAh`
            : `${formatInteger(run.capacity_actual_mah)} mAh`}</td>
          <td>${renderCapacityRatio(run)}</td>
          <td>${run.measured_resistance_mohm == null ? "--" : `${formatInteger(run.measured_resistance_mohm)} mΩ`}</td>
          <td>${renderRunActions(run)}</td>
        </tr>
      `;
    }).join("")
    : '<tr><td colspan="8" class="table-empty">Noch kein Programmlauf für diese Batterie gespeichert</td></tr>';
}

async function archiveBattery() {
  const battery = appState.selectedBattery;
  if (!battery) return;
  if (battery.archived) {
    await api(`/api/batteries/${battery.id}`, {
      method: "PUT",
      body: JSON.stringify({
        code: battery.code,
        name: battery.name,
        battery_type_code: battery.battery_type_code,
        nominal_capacity_mah: battery.nominal_capacity_mah,
        notes: battery.notes,
        manufacturer: battery.manufacturer,
        model: battery.model,
        form_factor: battery.form_factor,
        origin: battery.origin,
        in_service_since: battery.in_service_since,
        protected: battery.protected,
        archived: false,
      }),
    });
    showToast("Batterie wurde wiederhergestellt");
  } else {
    if (!window.confirm(
      `Batterie "${battery.code}" archivieren? Die Messwerte bleiben danach noch ${appState.archivedBatteryRetentionDays} Tage erhalten.`,
    )) return;
    await api(`/api/batteries/${battery.id}`, { method: "DELETE" });
    showToast("Batterie wurde archiviert");
  }
  appState.selectedBattery = null;
  appState.batteryRuns = [];
  appState.batteryComparison = null;
  await loadBatteries();
  renderBatteryDetail();
}

async function deleteBatteryPermanently() {
  const battery = appState.selectedBattery;
  if (!battery?.archived) return;
  const confirmation = window.prompt(
    `Batterie "${battery.code}" endgültig löschen? Alle Messwerte, Läufe und Berichte werden unwiderruflich entfernt. Zur Bestätigung die Batterienummer eingeben:`,
    "",
  );
  if (confirmation === null) return;
  if (confirmation.trim().toUpperCase() !== battery.code) {
    showToast("Batterienummer stimmt nicht überein", true);
    return;
  }
  await api(`/api/batteries/${battery.id}/permanent`, {
    method: "DELETE",
    body: JSON.stringify({ confirmation }),
  });
  showToast(`Batterie ${battery.code} wurde endgültig gelöscht`);
  appState.selectedBattery = null;
  appState.batteryRuns = [];
  appState.batteryComparison = null;
  await loadBatteries();
  renderBatteryDetail();
}

function renderBatterySuggestions() {
  const fields = [
    ["batteryManufacturerSuggestions", "manufacturer"],
    ["batteryModelSuggestions", "model"],
    ["batteryFormFactorSuggestions", "form_factor"],
    ["batteryOriginSuggestions", "origin"],
  ];
  fields.forEach(([elementId, key]) => {
    const values = [...new Set(
      appState.batteries
        .map((battery) => String(battery[key] || "").trim())
        .filter(Boolean),
    )].sort((left, right) => left.localeCompare(right, "de"));
    document.getElementById(elementId).innerHTML = values.map(
      (value) => `<option value="${escapeHtml(value)}"></option>`,
    ).join("");
  });
}

function openStandardProgramDialog(battery) {
  if (!battery) return;
  elements.standardBatteryId.value = String(battery.id);
  elements.standardProgramTitle.textContent = `Batterie ${battery.code}`;
  elements.standardBatteryFacts.innerHTML = `
    <strong>${escapeHtml(battery.name || battery.code)}</strong>
    <span>${escapeHtml(battery.battery_type)} · ${formatInteger(battery.nominal_capacity_mah)} mAh</span>
    <span>Wird später direkt am gewählten Slot verwendet</span>
  `;
  elements.standardMode.innerHTML = (appState.batteryOptions?.modes || [])
    .map((mode) => `<option value="${mode.code}">${escapeHtml(mode.name)}</option>`)
    .join("");
  elements.standardCycleMode.innerHTML = (appState.batteryOptions?.cycle_modes || [])
    .map((mode) => `<option value="${mode.code}">${escapeHtml(mode.name)}</option>`)
    .join("");
  elements.standardMode.value = String(battery.standard_mode_code ?? 0);
  elements.standardChargeRate.value = String(battery.standard_charge_c_rate ?? 0.5);
  elements.standardDischargeRate.value = String(
    battery.standard_discharge_c_rate ?? 0.5,
  );
  elements.standardCycleCount.value = String(battery.standard_cycle_count ?? 1);
  elements.standardCycleMode.value = String(battery.standard_cycle_mode ?? 0);
  elements.standardTimeLimitMode.value =
    battery.standard_time_limit_mode ?? "manual";
  elements.standardTimeLimitHours.value = String(
    Number(battery.standard_time_limit_min ?? 360) / 60,
  );
  updateStandardProgramFields();
  elements.standardProgramDialog.showModal();
}

function openSlotConfigurationDialog(address, slotNumber, startAfterSelection = false) {
  const device = findDevice(address);
  const slot = device?.slots?.[slotNumber - 1];
  if (!device?.connected || !slot) {
    showToast("Slot ist nicht erreichbar", true);
    return;
  }
  if (slot.active) {
    showToast("Aktiven Slot zuerst stoppen", true);
    return;
  }
  elements.slotConfigurationAddress.value = address;
  elements.slotConfigurationSlot.value = String(slotNumber);
  elements.slotConfigurationStartAfter.value = startAfterSelection ? "1" : "0";
  elements.slotConfigurationSubmit.textContent = startAfterSelection
    ? "Übernehmen und starten"
    : "Für Slot übernehmen";
  elements.slotConfigurationTitle.textContent = `${device.alias} · Slot ${slotNumber}`;
  elements.slotConfigurationFacts.innerHTML = `
    <strong>${escapeHtml(slot.battery_type)} · ${escapeHtml(slot.mode)}</strong>
    <span>${formatNumber(slot.voltage_v, 3)} V · ${escapeHtml(slot.status)}</span>
  `;
  const assignedBatteryId =
    device.battery_ids?.[slotNumber] ?? device.battery_ids?.[String(slotNumber)];
  const assignedBattery = findBattery(Number(assignedBatteryId));
  setConfigurationBatteryOptions(
    elements.slotConfigurationBattery,
    assignedBattery?.id,
    managedBatteryTypeCodes().has(Number(slot.battery_type_code)),
    assignedBatteryIdsExcept([{ address, slot: slotNumber }]),
  );
  elements.slotConfigurationCapacity.value = String(
    assignedBattery?.nominal_capacity_mah ?? 2000,
  );
  elements.slotConfigurationTimeLimitMode.value = "manual";
  elements.slotConfigurationTimeLimitHours.value = "6";
  updateSlotProgramOptions();

  const selectedProgram =
    device.programs?.[slotNumber] ?? device.programs?.[String(slotNumber)];
  let selectedValue = "";
  if (selectedProgram?.source === "profile" && selectedProgram.profile_id) {
    selectedValue = `profile:${selectedProgram.profile_id}`;
    elements.slotConfigurationCapacity.value = String(
      selectedProgram.details?.capacity_mah
        ?? findProfile(Number(selectedProgram.profile_id))?.capacity_mah
        ?? elements.slotConfigurationCapacity.value,
    );
  } else if (
    selectedProgram?.source === "automatic"
    && selectedProgram.details?.key
  ) {
    selectedValue = `automatic:${selectedProgram.details.key}`;
    elements.slotConfigurationCapacity.value = String(
      selectedProgram.details.capacity_mah
        ?? elements.slotConfigurationCapacity.value,
    );
  } else if (selectedProgram?.source === "standard") {
    selectedValue = "standard";
  }
  if (!selectedValue) {
    selectedValue = appState.settings?.default_program || "";
  }
  if (appState.pendingAutomaticProgram) {
    const pendingValue = `automatic:${appState.pendingAutomaticProgram}`;
    const available = [...elements.slotConfigurationProgram.options].some(
      (option) => option.value === pendingValue,
    );
    appState.pendingAutomaticProgram = null;
    if (available) {
      selectedValue = pendingValue;
      elements.slotConfigurationCapacity.value = String(
        assignedBattery?.nominal_capacity_mah
          ?? elements.slotConfigurationCapacity.value,
      );
    } else {
      showToast(
        "Dieses Automatikprogramm ist für den erkannten Akkutyp nicht verfügbar",
        true,
      );
    }
  }
  if ([...elements.slotConfigurationProgram.options].some(
    (option) => option.value === selectedValue,
  )) {
    elements.slotConfigurationProgram.value = selectedValue;
    if (
      selectedValue.startsWith("profile:")
      && selectedProgram?.source !== "profile"
    ) {
      const profile = findProfile(Number(selectedValue.split(":")[1]));
      elements.slotConfigurationCapacity.value = String(
        profile?.capacity_mah ?? elements.slotConfigurationCapacity.value,
      );
    } else if (selectedValue.startsWith("automatic:")) {
      setAutomaticTimeLimitInputs(
        findAutomaticProfile(selectedValue.split(":")[1]),
        elements.slotConfigurationTimeLimitMode,
        elements.slotConfigurationTimeLimitHours,
      );
    }
  }
  renderSlotConfigurationPreview();
  elements.slotConfigurationDialog.showModal();
}

function assignedBatteryIdsExcept(ignoredAssignments = []) {
  const ignored = new Set(ignoredAssignments.map(
    ({ address, slot }) => `${String(address).toUpperCase()}::${Number(slot)}`,
  ));
  const assigned = new Set();
  appState.devices.forEach((device) => {
    Object.entries(device.battery_ids || {}).forEach(([slot, batteryId]) => {
      const key = `${String(device.address).toUpperCase()}::${Number(slot)}`;
      const numericBatteryId = Number(batteryId);
      if (!ignored.has(key) && Number.isFinite(numericBatteryId)) {
        assigned.add(numericBatteryId);
      }
    });
  });
  return assigned;
}

function configurationBatteryOptions(
  selectedId = null,
  allowCreate = true,
  unavailableBatteryIds = new Set(),
) {
  const numericSelectedId = Number(selectedId);
  return [
    '<option value="">Keine Batterie · ohne Langzeitakte</option>',
    ...(allowCreate
      ? [`<option value="${CREATE_NUMBERED_BATTERY_VALUE}">＋ Neue Batterie automatisch anlegen</option>`]
      : []),
    ...appState.batteries
      .filter((battery) => (
        !battery.archived
        && (
          Number(battery.id) === numericSelectedId
          || !unavailableBatteryIds.has(Number(battery.id))
        )
      ))
      .map((battery) => `
      <option value="${battery.id}" ${Number(battery.id) === Number(selectedId) ? "selected" : ""}>
        ${escapeHtml(battery.code)} · ${escapeHtml(battery.name || battery.battery_type)} · ${formatInteger(battery.nominal_capacity_mah)} mAh
      </option>
    `),
  ].join("");
}

function isNewBatterySelection(value) {
  return value === CREATE_NUMBERED_BATTERY_VALUE;
}

function setConfigurationBatteryOptions(
  select,
  selectedId = null,
  allowCreate = true,
  unavailableBatteryIds = new Set(),
) {
  select.innerHTML = configurationBatteryOptions(
    selectedId,
    allowCreate,
    unavailableBatteryIds,
  );
  select.value = selectedId == null ? "" : String(selectedId);
  select.dataset.selectedValue = select.value;
}

function refreshDeviceConfigurationBatteryOptions() {
  const selects = [...elements.deviceConfigurationSlots.querySelectorAll(
    "select[data-slot]",
  )];
  const address = elements.deviceConfigurationAddress.value;
  const ignoredAssignments = selects.map((select) => ({
    address,
    slot: Number(select.dataset.slot),
  }));
  const assignedElsewhere = assignedBatteryIdsExcept(ignoredAssignments);
  const selectedValues = new Map(selects.map((select) => [select, select.value]));
  const device = findDevice(address);

  selects.forEach((select) => {
    const selectedValue = selectedValues.get(select) || "";
    const selectedId = Number(selectedValue) || null;
    const unavailable = new Set(assignedElsewhere);
    selectedValues.forEach((otherValue, otherSelect) => {
      if (otherSelect === select || isNewBatterySelection(otherValue)) return;
      const otherBatteryId = Number(otherValue);
      if (Number.isFinite(otherBatteryId) && otherBatteryId > 0) {
        unavailable.add(otherBatteryId);
      }
    });
    const slot = device?.slots?.[Number(select.dataset.slot) - 1];
    setConfigurationBatteryOptions(
      select,
      selectedId,
      managedBatteryTypeCodes().has(Number(slot?.battery_type_code)),
      unavailable,
    );
    if (isNewBatterySelection(selectedValue)) {
      select.value = selectedValue;
      select.dataset.selectedValue = selectedValue;
    }
  });
}

function updateSlotProgramOptions() {
  const previous = elements.slotConfigurationProgram.value;
  const battery = findBattery(Number(elements.slotConfigurationBattery.value));
  const createsBattery = isNewBatterySelection(
    elements.slotConfigurationBattery.value,
  );
  const batteryTypeCode = configuredSlotBatteryType(battery);
  const compatibleProfiles = appState.profiles.filter(
    (profile) => profile.battery_type_code === batteryTypeCode,
  );
  const automaticPrograms = managedBatteryTypeCodes().has(batteryTypeCode)
    ? (appState.batteryOptions?.automatic_programs || [])
    : [];
  elements.slotConfigurationProgram.innerHTML = [
    '<option value="">Programm wählen</option>',
    '<optgroup label="Automatik nach Kapazität">',
    ...automaticPrograms.map((program) => (
      `<option value="automatic:${escapeHtml(program.key)}">${escapeHtml(program.label)} · ${escapeHtml(automaticProgramRateLabel(program))}</option>`
    )),
    "</optgroup>",
    '<optgroup label="Gespeicherte Programme">',
    ...(battery || createsBattery
      ? [`<option value="standard">${battery
        ? `Batterie-Standard · ${escapeHtml(standardProgramLabel(battery))}`
        : "Standardprogramm der neuen Batterie"}</option>`]
      : []),
    ...compatibleProfiles.map((profile) => (
      `<option value="profile:${profile.id}">${escapeHtml(profile.name)} · ${escapeHtml(profile.mode)}</option>`
    )),
    "</optgroup>",
  ].join("");
  if ([...elements.slotConfigurationProgram.options].some(
    (option) => option.value === previous,
  )) {
    elements.slotConfigurationProgram.value = previous;
  }
  renderSlotConfigurationPreview();
}

function updateSlotConfigurationProgram() {
  const programValue = elements.slotConfigurationProgram.value;
  const battery = findBattery(Number(elements.slotConfigurationBattery.value));
  if (programValue.startsWith("profile:")) {
    const profile = findProfile(Number(programValue.split(":")[1]));
    if (profile) {
      elements.slotConfigurationCapacity.value = String(profile.capacity_mah);
    }
  } else if (programValue.startsWith("automatic:") && battery) {
    elements.slotConfigurationCapacity.value = String(
      battery.nominal_capacity_mah,
    );
  }
  if (programValue.startsWith("automatic:")) {
    setAutomaticTimeLimitInputs(
      findAutomaticProfile(programValue.split(":")[1]),
      elements.slotConfigurationTimeLimitMode,
      elements.slotConfigurationTimeLimitHours,
    );
  }
  renderSlotConfigurationPreview();
}

function renderSlotConfigurationPreview() {
  const battery = findBattery(Number(elements.slotConfigurationBattery.value));
  const createsBattery = isNewBatterySelection(
    elements.slotConfigurationBattery.value,
  );
  const programValue = elements.slotConfigurationProgram.value;
  const profile = programValue.startsWith("profile:")
    ? findProfile(Number(programValue.split(":")[1]))
    : null;
  const automatic = programValue.startsWith("automatic:")
    ? (appState.batteryOptions?.automatic_programs || []).find(
      (program) => program.key === programValue.split(":")[1],
    )
    : null;
  const usesCapacity = Boolean(profile || automatic || createsBattery);
  elements.slotConfigurationPreview.classList.remove("error");
  elements.slotConfigurationCapacityField.hidden = !usesCapacity;
  elements.slotConfigurationCapacity.required = usesCapacity;
  elements.slotConfigurationCapacity.min = profile && !createsBattery ? "0" : "100";
  elements.slotConfigurationTimeLimitModeField.hidden = !automatic;
  const manualTimeLimit = automatic
    && elements.slotConfigurationTimeLimitMode.value === "manual";
  elements.slotConfigurationTimeLimitField.hidden = !manualTimeLimit;
  elements.slotConfigurationTimeLimitHours.required = Boolean(manualTimeLimit);
  if (!programValue) {
    elements.slotConfigurationPreview.innerHTML = `
      <strong>Kein Startprogramm gewählt</strong>
      <span>Programm festlegen; eine Batterieakte ist optional.</span>
    `;
    return;
  }
  if (profile) {
    const capacity = Number(elements.slotConfigurationCapacity.value);
    const capacityError = savedProfileCapacityError(profile, capacity);
    const timeLimit = savedProfileTimeLimitPreview(profile, capacity);
    elements.slotConfigurationPreview.classList.toggle(
      "error",
      Boolean(capacityError),
    );
    elements.slotConfigurationPreview.innerHTML = `
      <strong>${escapeHtml(profile.name)} · ${formatInteger(capacity)} mAh</strong>
      <span>${escapeHtml(profile.mode)} · ${formatNumber(profile.charge_current_ma / 1000, 2)} A Laden · ${formatNumber(profile.discharge_current_ma / 1000, 2)} A Entladen · ${escapeHtml(timeLimit.label)}</span>
      <small>${capacityError
        ? escapeHtml(capacityError)
        : battery
          ? `Batterie ${escapeHtml(battery.code)} wird diesem Programmlauf zugeordnet.`
          : createsBattery
            ? "Die neue Batterieakte wird beim Übernehmen automatisch angelegt."
          : "Keine Batterieakte: Die Messung bleibt im normalen Verlauf."}</small>
    `;
    return;
  }
  if (automatic) {
    const capacity = Number(elements.slotConfigurationCapacity.value);
    const capacityError = automaticProgramCapacityError(capacity);
    const timeLimit = automaticProgramTimeLimitPreview(
      automatic,
      capacity,
      elements.slotConfigurationTimeLimitMode.value,
      hoursToMinutes(elements.slotConfigurationTimeLimitHours.value),
    );
    elements.slotConfigurationPreview.classList.toggle("error", Boolean(capacityError));
    elements.slotConfigurationPreview.innerHTML = `
      <strong>${escapeHtml(automatic.label)} · ${formatInteger(capacity)} mAh</strong>
      <span>${escapeHtml(automaticProgramCurrentLabel(automatic, capacity))}</span>
      <small>${escapeHtml(capacityError || `${automatic.description} · ${timeLimit.label}`)}${!battery && !capacityError
        ? createsBattery
          ? " · Neue Batterieakte wird beim Übernehmen angelegt."
          : " · Ohne Langzeitakte."
        : ""}</small>
    `;
    return;
  }
  if (!battery && !createsBattery) {
    elements.slotConfigurationPreview.classList.add("error");
    elements.slotConfigurationPreview.innerHTML = `
      <strong>Batterie-Standard nicht verfügbar</strong>
      <span>Dafür eine Batterieakte auswählen oder ein anderes Programm verwenden.</span>
    `;
    return;
  }
  if (createsBattery) {
    const capacity = Number(elements.slotConfigurationCapacity.value);
    const capacityError = automaticProgramCapacityError(capacity);
    elements.slotConfigurationPreview.classList.toggle(
      "error",
      Boolean(capacityError),
    );
    elements.slotConfigurationPreview.innerHTML = `
      <strong>Neue Batterie · ${formatInteger(capacity)} mAh</strong>
      <span>Automatische Nummer · erkannte Chemie · Standardprogramm</span>
      <small>${escapeHtml(capacityError || "Die Stammdaten können danach direkt am Slot ergänzt werden.")}</small>
    `;
    return;
  }
  elements.slotConfigurationPreview.innerHTML = `
    <strong>${escapeHtml(standardProgramLabel(battery))}</strong>
    <span>${standardProgramCurrentLabel(battery)}</span>
    <small>Aus Chemie und ${formatInteger(battery.nominal_capacity_mah)} mAh berechnet.</small>
  `;
}

function configuredSlotBatteryType(battery = null) {
  if (battery) return Number(battery.battery_type_code);
  const device = findDevice(elements.slotConfigurationAddress.value);
  const slot = device?.slots?.[Number(elements.slotConfigurationSlot.value) - 1];
  return Number(slot?.battery_type_code);
}

function managedBatteryTypeCodes() {
  return new Set(
    (appState.batteryOptions?.battery_types || []).map(
      (batteryType) => Number(batteryType.code),
    ),
  );
}

function programPhaseSequence(modeCode, cycleMode, chargeLabel, dischargeLabel) {
  const mode = Number(modeCode);
  if (mode === 0) return [chargeLabel];
  if (mode === 3) return [dischargeLabel];
  if (mode === 1) return [chargeLabel, dischargeLabel, chargeLabel];
  if (mode === 4) {
    return {
      0: [chargeLabel, dischargeLabel],
      1: [chargeLabel, dischargeLabel, chargeLabel],
      2: [dischargeLabel, chargeLabel],
      3: [dischargeLabel, chargeLabel, dischargeLabel],
    }[Number(cycleMode)] || [chargeLabel, dischargeLabel];
  }
  return [chargeLabel, dischargeLabel];
}

function automaticProgramRateLabel(program) {
  const parts = programPhaseSequence(
    program.mode_code,
    program.cycle_mode,
    `${formatNumber(program.charge_c_rate, 2)} C Laden`,
    `${formatNumber(program.discharge_c_rate, 2)} C Entladen`,
  );
  const cycleSuffix = Number(program.mode_code) === 4
    && Number(program.cycle_count) > 1
    ? ` · ${formatInteger(program.cycle_count)} Zyklen`
    : "";
  return `${parts.join(" → ")}${cycleSuffix}`;
}

function automaticProgramCurrentLabel(program, capacity) {
  const parts = programPhaseSequence(
    program.mode_code,
    program.cycle_mode,
    `${formatNumber(calculatedCurrentMa(capacity, program.charge_c_rate, "charge") / 1000, 2)} A Laden`,
    `${formatNumber(calculatedCurrentMa(capacity, program.discharge_c_rate, "discharge") / 1000, 2)} A Entladen`,
  );
  const cycleSuffix = Number(program.mode_code) === 4
    && Number(program.cycle_count) > 1
    ? ` · ${formatInteger(program.cycle_count)} Zyklen`
    : "";
  return `${parts.join(" → ")}${cycleSuffix}`;
}

function automaticProgramTimeLimitPreview(
  program,
  capacity,
  timeLimitMode,
  manualMinutes,
) {
  const modeName = (appState.batteryOptions?.modes || []).find(
    (candidate) => Number(candidate.code) === Number(program.mode_code),
  )?.name || "Laden";
  return timeLimitPreview(timeLimitMode, manualMinutes, {
    mode: modeName,
    capacityMah: capacity,
    chargeCurrentMa: calculatedCurrentMa(
      capacity,
      program.charge_c_rate,
      "charge",
    ),
    dischargeCurrentMa: calculatedCurrentMa(
      capacity,
      program.discharge_c_rate,
      "discharge",
    ),
    chargeRestMin: Number(program.charge_rest_min) || 0,
    dischargeRestMin: Number(program.discharge_rest_min) || 0,
    cycleCount: Number(program.cycle_count) || 1,
    cycleMode: Number(program.cycle_mode) || 0,
  });
}

function automaticProfileTimeLimitLabel(program) {
  if (program.time_limit_mode === "off") return "Zeitlimit aus";
  if (program.time_limit_mode === "automatic") {
    return "Zeitlimit automatisch nach Kapazität";
  }
  return `Zeitlimit manuell · ${formatTimeLimitMinutes(program.time_limit_min)}`;
}

function setAutomaticTimeLimitInputs(program, modeInput, hoursInput) {
  if (!program) return;
  modeInput.value = program.time_limit_mode || "manual";
  hoursInput.value = String(Number(program.time_limit_min ?? 360) / 60);
}

function automaticProgramCapacityError(capacity) {
  if (!Number.isFinite(capacity) || capacity < 100 || capacity > 50000) {
    return "Kapazität muss zwischen 100 und 50000 mAh liegen.";
  }
  return "";
}

function savedProfileCapacityError(profile, capacity) {
  if (!Number.isFinite(capacity) || capacity < 0 || capacity > 50000) {
    return "Kapazität muss zwischen 0 und 50000 mAh liegen.";
  }
  if (profile.mode === "Break-in" && capacity < 100) {
    return "Break-in benötigt mindestens 100 mAh Kapazität.";
  }
  if (profile.time_limit_mode === "automatic" && capacity <= 0) {
    return "Das automatische Zeitlimit benötigt eine Akkukapazität.";
  }
  return "";
}

function calculatedCurrentMa(capacity, cRate, direction) {
  const limits = appState.batteryOptions?.current_limits_ma || {};
  const minimum = Number(limits[`${direction}_min`]) || 50;
  const maximum = Number(limits[`${direction}_max`])
    || (direction === "charge" ? 3000 : 2000);
  const step = Number(limits.step) || 10;
  const calculated = Math.round(Number(capacity) * Number(cRate) / step) * step;
  return Math.min(maximum, Math.max(minimum, calculated));
}

function hoursToMinutes(hours) {
  return Math.round(Number(hours) * 60);
}

function formatTimeLimitMinutes(minutes) {
  const value = Number(minutes);
  if (!Number.isFinite(value) || value <= 0) return "aus";
  if (value % 60 === 0) return `${formatInteger(value / 60)} Std.`;
  return `${formatNumber(value / 60, 2)} Std. (${formatInteger(value)} min)`;
}

function profileTimeLimitLabel(profile) {
  if (profile.time_limit_mode === "off") return "Zeitlimit aus";
  const effective = Number(
    profile.effective_time_limit_min ?? profile.time_limit_min,
  );
  return profile.time_limit_mode === "automatic"
    ? `Zeitlimit automatisch · ${formatTimeLimitMinutes(effective)}`
    : `Zeitlimit manuell · ${formatTimeLimitMinutes(effective)}`;
}

function savedProfileTimeLimitPreview(profile, capacity) {
  return timeLimitPreview(
    profile.time_limit_mode,
    Number(profile.time_limit_min),
    {
      mode: profile.mode,
      capacityMah: capacity,
      chargeCurrentMa: Number(profile.charge_current_ma),
      dischargeCurrentMa: Number(profile.discharge_current_ma),
      chargeRestMin: Number(profile.charge_rest_min),
      dischargeRestMin: Number(profile.discharge_rest_min),
      cycleCount: Number(profile.cycle_count),
      cycleMode: Number(profile.cycle_mode),
    },
  );
}

function timeLimitPreview(mode, manualMinutes, settings) {
  if (mode === "off") return { minutes: 0, label: "Zeitlimit aus" };
  if (mode === "manual") {
    return {
      minutes: manualMinutes,
      label: `Zeitlimit manuell · ${formatTimeLimitMinutes(manualMinutes)}`,
    };
  }
  const minutes = automaticTimeLimitMinutes(settings);
  return {
    minutes,
    label: `Zeitlimit automatisch · ${formatTimeLimitMinutes(minutes)}`,
  };
}

function automaticTimeLimitMinutes(settings) {
  const mode = String(settings.mode || "");
  let chargePhases = 0;
  let dischargePhases = 0;
  let useLongestPhase = false;
  if (mode === "Laden") {
    chargePhases = 1;
  } else if (mode === "Entladen") {
    dischargePhases = 1;
  } else if (mode === "Lagern") {
    chargePhases = 1;
    dischargePhases = 1;
    useLongestPhase = true;
  } else if (mode === "Refresh") {
    chargePhases = 2;
    dischargePhases = 1;
  } else if (mode === "Zyklus" || mode === "Break-in") {
    const cycleCount = Math.max(1, Number(settings.cycleCount) || 1);
    const cycleMode = Number(settings.cycleMode);
    chargePhases = cycleCount + (cycleMode === 1 ? 1 : 0);
    dischargePhases = cycleCount + (cycleMode === 3 ? 1 : 0);
  } else {
    chargePhases = 1;
  }
  const capacity = Number(settings.capacityMah);
  const chargeMinutes = chargePhases
    ? capacity / Number(settings.chargeCurrentMa) * 60
    : 0;
  const dischargeMinutes = dischargePhases
    ? capacity / Number(settings.dischargeCurrentMa) * 60
    : 0;
  let duration = useLongestPhase
    ? Math.max(chargeMinutes, dischargeMinutes)
    : chargePhases * chargeMinutes + dischargePhases * dischargeMinutes;
  duration *= Number(appState.profileOptions?.automatic_time_limit_factor) || 1.5;
  const phaseCount = chargePhases + dischargePhases;
  if (phaseCount > 1) {
    duration += (phaseCount - 1) * Math.max(
      Number(settings.chargeRestMin) || 0,
      Number(settings.dischargeRestMin) || 0,
    );
  }
  return Math.max(1, Math.min(1440, Math.ceil(duration)));
}

function selectedProfileModeName() {
  const option = selectedBatteryOption();
  return option?.modes?.find(
    (mode) => Number(mode.code) === Number(elements.profileMode.value),
  )?.name || "Laden";
}

function profileTimeLimitPreview() {
  const preview = timeLimitPreview(
    elements.profileTimeLimitMode.value,
    hoursToMinutes(elements.profileTimeLimit.value),
    {
      mode: selectedProfileModeName(),
      capacityMah: Number(elements.profileCapacity.value),
      chargeCurrentMa: toMilli(elements.profileChargeCurrent.value),
      dischargeCurrentMa: toMilli(elements.profileDischargeCurrent.value),
      chargeRestMin: Number(elements.profileChargeRest.value),
      dischargeRestMin: Number(elements.profileDischargeRest.value),
      cycleCount: Number(elements.profileCycleCount.value),
      cycleMode: Number(elements.profileCycleMode.value),
    },
  );
  return preview.label;
}

function updateProfileTimeLimitFields() {
  const manual = elements.profileTimeLimitMode.value === "manual";
  elements.profileTimeLimitField.hidden = !manual;
  elements.profileTimeLimit.required = manual;
  refreshProfileLimits(false);
}

function standardProgramLabel(battery) {
  const mode = (appState.batteryOptions?.modes || []).find(
    (candidate) => candidate.code === Number(battery.standard_mode_code ?? 0),
  );
  return mode?.name || "Standardprogramm";
}

function standardProgramCurrentLabel(battery) {
  const mode = Number(battery.standard_mode_code ?? 0);
  const chargeRate = Number(battery.standard_charge_c_rate ?? 0.5);
  const dischargeRate = Number(battery.standard_discharge_c_rate ?? 0.5);
  const chargeCurrent = calculatedCurrentMa(
    battery.nominal_capacity_mah,
    chargeRate,
    "charge",
  );
  const dischargeCurrent = calculatedCurrentMa(
    battery.nominal_capacity_mah,
    dischargeRate,
    "discharge",
  );
  const parts = programPhaseSequence(
    mode,
    battery.standard_cycle_mode,
    `${formatNumber(chargeRate, 2)} C Laden · ${formatNumber(chargeCurrent / 1000, 2)} A`,
    `${formatNumber(dischargeRate, 2)} C Entladen · ${formatNumber(dischargeCurrent / 1000, 2)} A`,
  );
  if (mode === 4) {
    parts.push(`${formatInteger(battery.standard_cycle_count ?? 1)} Zyklen`);
  }
  const timeLimit = timeLimitPreview(
    battery.standard_time_limit_mode ?? "manual",
    Number(battery.standard_time_limit_min ?? 360),
    {
      mode: standardProgramLabel(battery),
      capacityMah: battery.nominal_capacity_mah,
      chargeCurrentMa: chargeCurrent,
      dischargeCurrentMa: dischargeCurrent,
      chargeRestMin: mode === 1 || mode === 4 ? 5 : 0,
      dischargeRestMin: mode === 1 || mode === 4 ? 5 : 0,
      cycleCount: Number(battery.standard_cycle_count ?? 1),
      cycleMode: Number(battery.standard_cycle_mode ?? 0),
    },
  );
  parts.push(timeLimit.label);
  return parts.join(" · ");
}

function openDeviceConfigurationDialog(address, startAfterSelection = false) {
  const device = findDevice(address);
  if (!device?.connected) {
    showToast("Ladegerät ist nicht verbunden", true);
    return;
  }
  let slots = (device.slots || []).filter(
    (slot) => (
      slot
      && !slot.active
      && Number(slot.voltage_v) > 0
      && Number(slot.status_code) < 128
    ),
  );
  if (startAfterSelection) {
    const slotsWithoutProgram = slots.filter((slot) => !(
      device.programs?.[slot.slot]
      ?? device.programs?.[String(slot.slot)]
    ));
    if (slotsWithoutProgram.length) slots = slotsWithoutProgram;
  }
  if (!slots.length) {
    showToast("Kein belegter, startbereiter Slot gefunden", true);
    return;
  }

  elements.deviceConfigurationAddress.value = address;
  elements.deviceConfigurationStartAfter.value = startAfterSelection ? "1" : "0";
  elements.deviceConfigurationSubmit.textContent = startAfterSelection
    ? "Übernehmen und alle starten"
    : "Programme übernehmen";
  elements.deviceConfigurationTitle.textContent = `${device.alias} · Alle Programme`;
  elements.deviceConfigurationFacts.innerHTML = `
    <strong>${slots.length} belegte Slots</strong>
    <span>Gemeinsames Ladeprofil oder Standardprogramm jeder Batterie</span>
  `;
  const assignedElsewhere = assignedBatteryIdsExcept(slots.map((slot) => ({
    address,
    slot: Number(slot.slot),
  })));
  elements.deviceConfigurationSlots.innerHTML = slots.map((slot) => {
    const assignedId =
      device.battery_ids?.[slot.slot] ?? device.battery_ids?.[String(slot.slot)];
    let selectedId = Number(assignedId) || null;
    if (!findBattery(selectedId) || assignedElsewhere.has(selectedId)) {
      selectedId = null;
    }
    return `
      <div class="device-configuration-slot">
        <div>
          <strong>Slot ${slot.slot}</strong>
          <span>${formatNumber(slot.voltage_v, 3)} V · ${escapeHtml(slot.status)}</span>
        </div>
        <select
          data-slot="${slot.slot}"
          data-selected-value="${selectedId ?? ""}"
          aria-label="Batterieakte für Slot ${slot.slot}"
        >
          ${configurationBatteryOptions(
            selectedId,
            managedBatteryTypeCodes().has(Number(slot.battery_type_code)),
            assignedElsewhere,
          )}
        </select>
        <label class="device-capacity-field" hidden>
          Kapazität (mAh)
          <input
            type="number"
            min="100"
            max="50000"
            step="10"
            value="${findBattery(selectedId)?.nominal_capacity_mah ?? 2000}"
            data-capacity-slot="${slot.slot}"
          >
        </label>
      </div>
    `;
  }).join("");
  refreshDeviceConfigurationBatteryOptions();
  elements.deviceConfigurationTimeLimitMode.value = "manual";
  elements.deviceConfigurationTimeLimitHours.value = "6";
  elements.deviceConfigurationProgram.innerHTML = "";
  updateDeviceConfigurationProgramOptions();
  const defaultProgram = appState.settings?.default_program || "";
  if ([...elements.deviceConfigurationProgram.options].some(
    (option) => option.value === defaultProgram,
  )) {
    elements.deviceConfigurationProgram.value = defaultProgram;
    updateDeviceConfigurationProgram();
  }
  elements.deviceConfigurationDialog.showModal();
}

function updateDeviceConfigurationProgramOptions() {
  const previous = elements.deviceConfigurationProgram.value;
  const assignments = [...elements.deviceConfigurationSlots.querySelectorAll(
    "select[data-slot]",
  )].map((select) => {
    const battery = findBattery(Number(select.value));
    return {
      slot: Number(select.dataset.slot),
      battery,
      createsBattery: isNewBatterySelection(select.value),
      batteryTypeCode: configuredDeviceSlotBatteryType(select, battery),
    };
  });
  const batteryTypes = new Set(
    assignments.map((item) => item.batteryTypeCode),
  );
  const compatibleProfiles = batteryTypes.size === 1
    ? appState.profiles.filter(
      (profile) => profile.battery_type_code === assignments[0].batteryTypeCode,
    )
    : [];
  const automaticPrograms = assignments.every(
    (item) => managedBatteryTypeCodes().has(item.batteryTypeCode),
  )
    ? (appState.batteryOptions?.automatic_programs || [])
    : [];
  const allTracked = assignments.every(
    (item) => item.battery || item.createsBattery,
  );
  elements.deviceConfigurationProgram.innerHTML = [
    '<option value="">Programm wählen</option>',
    '<optgroup label="Automatik nach Kapazität">',
    ...automaticPrograms.map((program) => (
      `<option value="automatic:${escapeHtml(program.key)}">${escapeHtml(program.label)} · ${escapeHtml(automaticProgramRateLabel(program))}</option>`
    )),
    "</optgroup>",
    '<optgroup label="Gespeicherte Programme">',
    ...(allTracked
      ? ['<option value="standard">Standardprogramm jeder Batterie</option>']
      : []),
    ...compatibleProfiles.map((profile) => (
      `<option value="profile:${profile.id}">${escapeHtml(profile.name)} · ${escapeHtml(profile.mode)}</option>`
    )),
    "</optgroup>",
  ].join("");
  if ([...elements.deviceConfigurationProgram.options].some(
    (option) => option.value === previous,
  )) {
    elements.deviceConfigurationProgram.value = previous;
  }
  renderDeviceConfigurationPreview();
}

function updateDeviceConfigurationProgram() {
  const programValue = elements.deviceConfigurationProgram.value;
  const profile = programValue.startsWith("profile:")
    ? findProfile(Number(programValue.split(":")[1]))
    : null;
  elements.deviceConfigurationSlots.querySelectorAll(
    "input[data-capacity-slot]",
  ).forEach((input) => {
    if (profile) {
      input.value = String(profile.capacity_mah);
      return;
    }
    if (!programValue.startsWith("automatic:")) return;
    const batterySelect = elements.deviceConfigurationSlots.querySelector(
      `select[data-slot="${input.dataset.capacitySlot}"]`,
    );
    const battery = findBattery(Number(batterySelect?.value));
    if (battery) input.value = String(battery.nominal_capacity_mah);
  });
  if (programValue.startsWith("automatic:")) {
    setAutomaticTimeLimitInputs(
      findAutomaticProfile(programValue.split(":")[1]),
      elements.deviceConfigurationTimeLimitMode,
      elements.deviceConfigurationTimeLimitHours,
    );
  }
  renderDeviceConfigurationPreview();
}

function renderDeviceConfigurationPreview() {
  const assignments = [...elements.deviceConfigurationSlots.querySelectorAll(
    "select[data-slot]",
  )].map((select) => ({
    slot: Number(select.dataset.slot),
    battery: findBattery(Number(select.value)),
    createsBattery: isNewBatterySelection(select.value),
  }));
  const trackedAssignments = assignments.filter((item) => item.battery);
  const duplicate = new Set(
    trackedAssignments.map((item) => item.battery.id),
  ).size !== trackedAssignments.length;
  elements.deviceConfigurationPreview.classList.toggle(
    "error",
    duplicate,
  );
  if (duplicate) {
    elements.deviceConfigurationPreview.innerHTML = `
      <strong>Batterienummer mehrfach ausgewählt</strong>
      <span>Eine gespeicherte Batterie kann nicht gleichzeitig in mehreren Slots liegen.</span>
      <small>„Keine Batterie“ darf dagegen für beliebig viele normale Akkus verwendet werden.</small>
    `;
    return;
  }

  const programValue = elements.deviceConfigurationProgram.value;
  const profile = programValue.startsWith("profile:")
    ? findProfile(Number(programValue.split(":")[1]))
    : null;
  const automatic = programValue.startsWith("automatic:")
    ? (appState.batteryOptions?.automatic_programs || []).find(
      (program) => program.key === programValue.split(":")[1],
    )
    : null;
  const usesCapacity = Boolean(profile || automatic);
  elements.deviceConfigurationTimeLimitModeField.hidden = !automatic;
  const manualTimeLimit = automatic
    && elements.deviceConfigurationTimeLimitMode.value === "manual";
  elements.deviceConfigurationTimeLimitField.hidden = !manualTimeLimit;
  elements.deviceConfigurationTimeLimitHours.required = Boolean(manualTimeLimit);
  elements.deviceConfigurationSlots.querySelectorAll(
    ".device-capacity-field",
  ).forEach((field) => {
    const input = field.querySelector("input");
    const select = elements.deviceConfigurationSlots.querySelector(
      `select[data-slot="${input.dataset.capacitySlot}"]`,
    );
    const createsBattery = isNewBatterySelection(select?.value);
    field.hidden = !usesCapacity && !createsBattery;
    input.required = usesCapacity || createsBattery;
    input.min = profile && !createsBattery ? "0" : "100";
  });
  if (!programValue) {
    elements.deviceConfigurationPreview.innerHTML = `
      <strong>Kein gemeinsames Startprogramm gewählt</strong>
      <span>Ein Programm für alle belegten Slots auswählen.</span>
    `;
    return;
  }
  if (profile) {
    const configuredProfiles = assignments.map((item) => {
      const capacity = Number(
        elements.deviceConfigurationSlots.querySelector(
          `input[data-capacity-slot="${item.slot}"]`,
        )?.value,
      );
      return {
        slot: item.slot,
        capacity,
        error: savedProfileCapacityError(profile, capacity),
        timeLimit: savedProfileTimeLimitPreview(profile, capacity),
      };
    });
    const firstError = configuredProfiles.find((item) => item.error);
    elements.deviceConfigurationPreview.classList.toggle(
      "error",
      Boolean(firstError),
    );
    elements.deviceConfigurationPreview.innerHTML = `
      <strong>${escapeHtml(profile.name)} für alle ${assignments.length} Slots</strong>
      <span>${escapeHtml(profile.mode)} · ${formatNumber(profile.charge_current_ma / 1000, 2)} A Laden · ${formatNumber(profile.discharge_current_ma / 1000, 2)} A Entladen</span>
      <small>${firstError
        ? escapeHtml(`Slot ${firstError.slot}: ${firstError.error}`)
        : configuredProfiles.map((item, index) => (
          `Slot ${item.slot}: ${configurationBatteryLabel(assignments[index].battery, assignments[index].createsBattery)} · ${formatInteger(item.capacity)} mAh · ${escapeHtml(item.timeLimit.label)}`
        )).join(" · ")}</small>
    `;
    return;
  }
  if (automatic) {
    const configuredPrograms = assignments.map((item) => {
      const capacity = Number(
        elements.deviceConfigurationSlots.querySelector(
          `input[data-capacity-slot="${item.slot}"]`,
        )?.value,
      );
      return {
        slot: item.slot,
        capacity,
        error: automaticProgramCapacityError(capacity),
        timeLimit: automaticProgramTimeLimitPreview(
          automatic,
          capacity,
          elements.deviceConfigurationTimeLimitMode.value,
          hoursToMinutes(elements.deviceConfigurationTimeLimitHours.value),
        ),
      };
    });
    const firstError = configuredPrograms.find((item) => item.error);
    elements.deviceConfigurationPreview.classList.toggle("error", Boolean(firstError));
    elements.deviceConfigurationPreview.innerHTML = `
      <strong>${escapeHtml(automatic.label)} für alle ${assignments.length} Slots</strong>
      <span>${assignments.map((item, index) => {
        const capacity = configuredPrograms[index].capacity;
        return `Slot ${item.slot}: ${configurationBatteryLabel(item.battery, item.createsBattery)} · ${formatInteger(capacity)} mAh · ${escapeHtml(automaticProgramCurrentLabel(automatic, capacity))} · ${escapeHtml(configuredPrograms[index].timeLimit.label)}`;
      }).join("<br>")}</span>
      <small>${escapeHtml(firstError ? `Slot ${firstError.slot}: ${firstError.error}` : automatic.description)}</small>
    `;
    return;
  }
  if (assignments.some((item) => !item.battery && !item.createsBattery)) {
    elements.deviceConfigurationPreview.classList.add("error");
    elements.deviceConfigurationPreview.innerHTML = `
      <strong>Batterie-Standard nicht für alle Slots verfügbar</strong>
      <span>Für das Batterie-Standardprogramm braucht jeder Slot eine Batterieakte.</span>
      <small>Alternativ ein Automatikprogramm oder ein gespeichertes Profil wählen.</small>
    `;
    return;
  }
  elements.deviceConfigurationPreview.innerHTML = `
    <strong>Individuelle Standardprogramme</strong>
    <span>${assignments.map((item) => {
      if (item.battery) {
        return `Slot ${item.slot}: ${escapeHtml(item.battery.code)} · ${escapeHtml(standardProgramLabel(item.battery))} · ${standardProgramCurrentLabel(item.battery)}`;
      }
      const capacity = Number(
        elements.deviceConfigurationSlots.querySelector(
          `input[data-capacity-slot="${item.slot}"]`,
        )?.value,
      );
      return `Slot ${item.slot}: Neue Batterie · ${formatInteger(capacity)} mAh · Standardprogramm`;
    }).join("<br>")}</span>
    <small>Danach mit „Alle starten“ gemeinsam beginnen.</small>
  `;
}

function configuredDeviceSlotBatteryType(select, battery = null) {
  if (battery) return Number(battery.battery_type_code);
  const device = findDevice(elements.deviceConfigurationAddress.value);
  const slot = device?.slots?.[Number(select.dataset.slot) - 1];
  return Number(slot?.battery_type_code);
}

function configurationBatteryLabel(battery, createsBattery = false) {
  return battery
    ? escapeHtml(battery.code)
    : createsBattery
      ? "Neue Batterie"
    : "Keine Batterieakte";
}

function updateStandardProgramFields() {
  const mode = Number(elements.standardMode.value);
  const cycle = mode === 4;
  elements.standardChargeRate.closest("label").hidden = mode === 3;
  elements.standardDischargeRate.closest("label").hidden = mode === 0;
  elements.standardCycleCount.disabled = !cycle;
  elements.standardCycleMode.disabled = !cycle;
  elements.standardCycleCount.closest("label").hidden = !cycle;
  elements.standardCycleMode.closest("label").hidden = !cycle;
  const manualTimeLimit = elements.standardTimeLimitMode.value === "manual";
  elements.standardTimeLimitField.hidden = !manualTimeLimit;
  elements.standardTimeLimitHours.required = manualTimeLimit;
  renderStandardProgramPreview();
}

function renderStandardProgramPreview() {
  const battery = findBattery(Number(elements.standardBatteryId.value))
    || appState.selectedBattery;
  if (!battery) return;
  const chargeRate = Number(elements.standardChargeRate.value);
  const dischargeRate = Number(elements.standardDischargeRate.value);
  const mode = Number(elements.standardMode.value);
  const usesCharge = mode !== 3;
  const usesDischarge = mode !== 0;
  const chargeCurrent = calculatedCurrentMa(
    battery.nominal_capacity_mah,
    chargeRate,
    "charge",
  );
  const dischargeCurrent = calculatedCurrentMa(
    battery.nominal_capacity_mah,
    dischargeRate,
    "discharge",
  );
  const chargeVoltage = battery.battery_type_code === 1 ? 3.6 : 4.2;
  const dischargeVoltage = battery.battery_type_code === 1 ? 2.9 : 3.0;
  const modeName = (appState.batteryOptions?.modes || []).find(
    (candidate) => Number(candidate.code) === mode,
  )?.name || "Laden";
  const timeLimit = timeLimitPreview(
    elements.standardTimeLimitMode.value,
    hoursToMinutes(elements.standardTimeLimitHours.value),
    {
      mode: modeName,
      capacityMah: battery.nominal_capacity_mah,
      chargeCurrentMa: chargeCurrent,
      dischargeCurrentMa: dischargeCurrent,
      chargeRestMin: mode === 1 || mode === 4 ? 5 : 0,
      dischargeRestMin: mode === 1 || mode === 4 ? 5 : 0,
      cycleCount: Number(elements.standardCycleCount.value),
      cycleMode: Number(elements.standardCycleMode.value),
    },
  );
  elements.standardProgramPreview.classList.remove("error");
  elements.standardProgramPreview.innerHTML = `
    <div><span>Ladestrom</span><strong>${usesCharge ? `${formatNumber(chargeCurrent / 1000, 2)} A` : "--"}</strong></div>
    <div><span>Entladestrom</span><strong>${usesDischarge ? `${formatNumber(dischargeCurrent / 1000, 2)} A` : "--"}</strong></div>
    <div><span>Spannungsgrenzen</span><strong>${formatNumber(chargeVoltage, 2)} / ${formatNumber(dischargeVoltage, 2)} V</strong></div>
    <div><span>Temperaturlimit</span><strong>45 °C</strong></div>
    <div><span>Zeitlimit</span><strong>${escapeHtml(timeLimit.label.replace("Zeitlimit ", ""))}</strong></div>
  `;
}

function selectedBatteryRunIds() {
  return [...document.querySelectorAll('input[name="compareRun"]:checked')]
    .map((input) => Number(input.value));
}

async function loadBatteryComparison() {
  const battery = appState.selectedBattery;
  const runIds = selectedBatteryRunIds();
  if (!battery || !runIds.length) {
    showToast("Mindestens einen Programmlauf auswählen", true);
    return;
  }
  const data = await api(
    `/api/batteries/${battery.id}/compare?run_ids=${runIds.join(",")}&limit=1200`,
  );
  resetChartZoom("battery-comparison", false);
  appState.batteryComparison = data;
  renderBatteryComparisonLegend(data);
  drawBatteryComparison(data);
}

function renderBatteryComparisonLegend(data) {
  const colors = comparisonColors();
  elements.batteryCompareLegend.innerHTML = data?.runs?.length
    ? data.runs.map((run, index) => `
      <span><i style="background:${colors[index]}"></i>${formatDate(run.started_at)} · ${escapeHtml(run.mode)}</span>
    `).join("")
    : '<span>Noch keine Läufe ausgewählt</span>';
}

function drawBatteryComparison(data) {
  const canvas = elements.batteryCompareChart;
  if (!canvas || canvas.offsetParent === null) return;
  const { context, width, height } = prepareCanvas(canvas);
  const palette = chartPalette();
  context.clearRect(0, 0, width, height);
  context.fillStyle = palette.background;
  context.fillRect(0, 0, width, height);
  const runs = data?.runs || [];
  if (!runs.length) {
    context.fillStyle = palette.text;
    context.font = "13px system-ui";
    context.textAlign = "center";
    context.fillText("Keine Vergleichsdaten ausgewählt", width / 2, height / 2);
    return;
  }

  const metrics = {
    voltage_v: { unit: "V", digits: 3 },
    current_a: { unit: "A", digits: 3 },
    capacity_mah: { unit: "mAh", digits: 0 },
    temperature_c: { unit: "°C", digits: 0 },
    resistance_mohm: { unit: "mΩ", digits: 0 },
  };
  const key = elements.batteryCompareMetric.value;
  const metric = metrics[key];
  const sourcePoints = runs.flatMap((run) => run.points || []);
  if (!sourcePoints.length) {
    chartGeometries.delete(canvas);
    updateChartZoomControls("battery-comparison");
    context.fillStyle = palette.text;
    context.font = "13px system-ui";
    context.textAlign = "center";
    context.fillText("Für diese Läufe liegen keine Messpunkte vor", width / 2, height / 2);
    return;
  }
  const margin = { top: 18, right: 20, bottom: 32, left: 68 };
  const chartWidth = Math.max(1, width - margin.left - margin.right);
  const chartHeight = Math.max(1, height - margin.top - margin.bottom);
  const fullEnd = Math.max(
    1,
    ...runs.map((run) => comparisonElapsedTimes(run.points || []).at(-1) || 0),
  );
  const { start: viewStart, end: viewEnd } = chartViewRange(
    "battery-comparison",
    0,
    fullEnd,
  );
  const elapsedRange = Math.max(viewEnd - viewStart, 1);
  const visibleRuns = runs.map((run) => {
    const elapsed = comparisonElapsedTimes(run.points || []);
    const visible = chartPointsInRange(run.points || [], elapsed, viewStart, viewEnd);
    return { run, points: visible.points, elapsed: visible.times };
  });
  const allPoints = visibleRuns.flatMap((entry) => entry.points);
  const scale = seriesScale(allPoints.length ? allPoints : sourcePoints, key);
  chartGeometries.set(canvas, {
    group: "battery-comparison",
    left: margin.left,
    top: margin.top,
    width: chartWidth,
    height: chartHeight,
    start: viewStart,
    end: viewEnd,
    fullStart: 0,
    fullEnd,
    formatter: formatDurationShort,
  });
  updateChartZoomControls("battery-comparison");

  context.strokeStyle = palette.grid;
  context.lineWidth = 1;
  for (let row = 0; row <= 4; row += 1) {
    const y = margin.top + (chartHeight / 4) * row;
    context.beginPath();
    context.moveTo(margin.left, y);
    context.lineTo(margin.left + chartWidth, y);
    context.stroke();
  }
  drawAxisLabels(
    context,
    scale,
    margin.left - 8,
    margin.top,
    chartHeight,
    { ...metric, color: palette.text },
    "right",
  );
  context.fillStyle = palette.text;
  context.font = "11px system-ui";
  [viewStart, viewStart + elapsedRange / 2, viewEnd].forEach((value, index) => {
    context.textAlign = ["left", "center", "right"][index];
    context.fillText(
      formatDurationShort(value),
      margin.left + (chartWidth / 2) * index,
      margin.top + chartHeight + 21,
    );
  });

  const colors = comparisonColors();
  context.save();
  context.beginPath();
  context.rect(margin.left, margin.top, chartWidth, chartHeight);
  context.clip();
  visibleRuns.forEach(({ points, elapsed }, runIndex) => {
    context.strokeStyle = colors[runIndex];
    context.lineWidth = 2;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.beginPath();
    points.forEach((point, index) => {
      const x = margin.left
        + ((elapsed[index] - viewStart) / elapsedRange) * chartWidth;
      const value = Number(point[key]) || 0;
      const y = margin.top + chartHeight
        - ((value - scale.min) / scale.range) * chartHeight;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.stroke();
  });
  context.restore();
  drawBatteryComparisonHover(
    canvas,
    context,
    visibleRuns,
    key,
    metric,
    scale,
    colors,
    margin,
    chartWidth,
    chartHeight,
    viewStart,
    viewEnd,
  );
  drawChartSelectionOverlay(canvas, context);
}

function drawBatteryComparisonHover(
  canvas,
  context,
  visibleRuns,
  key,
  metric,
  scale,
  colors,
  margin,
  chartWidth,
  chartHeight,
  viewStart,
  viewEnd,
) {
  const palette = chartPalette();
  const pointer = chartPointers.get(canvas);
  if (
    !pointer
    || pointer.dragging
    || pointer.anchorX != null
    || pointer.x < margin.left
    || pointer.x > margin.left + chartWidth
    || pointer.y < margin.top
    || pointer.y > margin.top + chartHeight
  ) return;

  const elapsedRange = Math.max(viewEnd - viewStart, 1);
  const elapsedTarget = viewStart
    + ((pointer.x - margin.left) / chartWidth) * elapsedRange;
  const pointX = margin.left
    + ((elapsedTarget - viewStart) / elapsedRange) * chartWidth;
  const lines = [`Laufzeit ${formatDurationShort(elapsedTarget)}`];

  context.save();
  context.strokeStyle = palette.crosshair;
  context.lineWidth = 1;
  context.setLineDash([4, 4]);
  context.beginPath();
  context.moveTo(pointX, margin.top);
  context.lineTo(pointX, margin.top + chartHeight);
  context.stroke();
  context.setLineDash([]);

  visibleRuns.forEach(({ run, points, elapsed }, runIndex) => {
    if (!points.length) return;
    const index = nearestValueIndex(elapsed, elapsedTarget);
    if (elapsed[index] < viewStart || elapsed[index] > viewEnd) return;
    const point = points[index];
    const x = margin.left
      + ((elapsed[index] - viewStart) / elapsedRange) * chartWidth;
    const value = Number(point[key]) || 0;
    const y = margin.top + chartHeight
      - ((value - scale.min) / scale.range) * chartHeight;
    drawHoverPoint(context, x, y, colors[runIndex]);
    lines.push(
      `${formatDate(run.started_at)}: ${formatNumber(value, metric.digits)} ${metric.unit}`,
    );
  });

  drawChartTooltip(
    context,
    lines,
    pointX,
    margin.top + 8,
    margin.left,
    margin.left + chartWidth,
  );
  context.restore();
}

function comparisonElapsedTimes(points) {
  if (!points.length) return [];
  const start = new Date(points[0].recorded_at).getTime();
  return points.map((point) => Math.max(
    0,
    (new Date(point.recorded_at).getTime() - start) / 1000,
  ));
}

function comparisonColors() {
  const palette = chartPalette();
  return [
    palette.green,
    palette.blue,
    palette.amber,
    palette.purple,
    palette.red,
  ];
}

async function openCurve(address, slot) {
  const device = findDevice(address);
  appState.curve = null;
  chartPointers.delete(elements.curveCanvas);
  resetChartZoom("curve", false);
  elements.curveTitle.textContent = `${device?.alias || "MC3000"} · Slot ${slot}`;
  elements.curveMeta.textContent = "Lade Daten...";
  elements.curveDialog.showModal();
  const data = await api(`/api/devices/${encodeURIComponent(address)}/slots/${slot}/curve`);
  appState.curve = data;
  drawCurve(elements.curveCanvas, data.points || []);
  elements.curveMeta.textContent = data.points?.length
    ? `${data.points.length} Punkte · Intervall ${data.interval_s} s`
    : "Keine gespeicherte Spannungskurve";
}

function renderHistoryDevices() {
  const current = elements.historyDevice.value;
  elements.historyDevice.innerHTML = appState.devices.map((device) => (
    `<option value="${escapeHtml(device.address)}">${escapeHtml(device.alias)}</option>`
  )).join("");
  if (appState.devices.some((device) => device.address === current)) {
    elements.historyDevice.value = current;
  }
}

async function loadHistory({ quiet = false } = {}) {
  const address = elements.historyDevice.value;
  const slot = Number(elements.historySlot.value);
  const hours = Number(elements.historyHours.value);
  if (!address) {
    elements.historySummary.textContent = "Kein Ladegerät eingerichtet";
    drawHistoryCharts([]);
    return;
  }
  try {
    const data = await api(
      `/api/recordings/history?address=${encodeURIComponent(address)}&slot=${slot}&hours=${hours}&limit=2000`,
    );
    appState.history = data;
    drawHistoryCharts(data.points || []);
    renderHistorySummary(data);
  } catch (error) {
    if (!quiet) showToast(error.message, true);
  }
}

async function loadRecordingRuns({ quiet = false } = {}) {
  try {
    const data = await api("/api/recordings/runs?limit=50");
    elements.recordingRuns.innerHTML = data.runs?.length
      ? data.runs.map(renderRecordingRun).join("")
      : '<tr><td colspan="9" class="table-empty">Noch kein Lade- oder Entladevorgang aufgezeichnet</td></tr>';
  } catch (error) {
    if (!quiet) showToast(error.message, true);
  }
}

function renderRecordingRun(run) {
  const device = findDevice(run.address);
  const end = run.ended_at ? new Date(run.ended_at) : new Date();
  const start = new Date(run.started_at);
  const duration = Math.max(0, Math.round((end - start) / 1000));
  return `
    <tr>
      <td>${formatDateTime(run.started_at)}</td>
      <td>${escapeHtml(device?.alias || run.address)}</td>
      <td>Slot ${run.slot}</td>
      <td>${run.battery_code ? `Batterie ${escapeHtml(run.battery_code)} · ` : ""}${escapeHtml(run.battery_type)} · ${escapeHtml(run.mode)}</td>
      <td>${run.ended_at ? formatDuration(duration) : "läuft"}</td>
      <td>${formatInteger(run.max_capacity_mah)} mAh</td>
      <td>${renderCapacityRatio(run)}</td>
      <td>${formatInteger(run.max_temperature_c)} °C</td>
      <td>${renderRunActions(run)}</td>
    </tr>
  `;
}

function renderCapacityRatio(run) {
  if (run.capacity_ratio_percent == null) return "--";
  return `
    <strong>${formatNumber(run.capacity_ratio_percent, 1)} %</strong>
    <small>Soll ${formatInteger(run.nominal_capacity_mah)} / Ist ${formatInteger(run.capacity_actual_mah)} mAh</small>
  `;
}

function renderRunActions(run) {
  return `
    <div class="row-actions">
      <button data-action="run-report" data-run-id="${run.id}">Bericht</button>
      ${run.ended_at ? `
        <button data-action="run-chart" data-run-id="${run.id}">Diagramm</button>
        <button data-action="run-pdf" data-run-id="${run.id}">PDF</button>
        <button class="danger-quiet" data-action="delete-run" data-run-id="${run.id}">Löschen</button>
      ` : ""}
    </div>
  `;
}

async function openRunReport(runId) {
  const report = await api(`/api/recordings/runs/${runId}/report`);
  elements.runReportTitle.textContent = `${report.battery_code ? `Batterie ${report.battery_code}` : "Batterie ohne Akte"} · ${report.mode}`;
  const statusLabel = {
    ok: "Unauffällig",
    warning: "Prüfen",
    danger: "Auffällig",
    active: "Läuft",
  }[report.rating] || report.rating;
  elements.runReportContent.innerHTML = `
    <div class="run-report-rating ${escapeHtml(report.rating)}">
      <strong>${escapeHtml(statusLabel)}</strong>
      <span>${report.ended_at ? `Beendet ${formatDateTime(report.ended_at)}` : "Programm läuft noch"}</span>
    </div>
    <div class="run-report-grid">
      <div><span>Kapazität Soll / Ist</span><strong>${report.capacity_actual_mah == null ? "--" : `${formatInteger(report.nominal_capacity_mah)} / ${formatInteger(report.capacity_actual_mah)} mAh`}</strong><small>${report.capacity_ratio_percent == null ? "Noch keine abgeschlossene Entladephase" : `${formatNumber(report.capacity_ratio_percent, 1)} %${report.soh_percent == null ? " Soll/Ist" : " SOH"}`}</small></div>
      <div><span>Energie</span><strong>${formatNumber(report.energy_wh, 3)} Wh</strong><small>${formatDuration(report.duration_s)}</small></div>
      <div><span>Spannung</span><strong>${formatNumber(report.start_voltage_v, 3)} → ${formatNumber(report.end_voltage_v, 3)} V</strong><small>${formatNumber(report.minimum_voltage_v, 3)} bis ${formatNumber(report.maximum_voltage_v, 3)} V</small></div>
      <div><span>Temperatur</span><strong>${formatInteger(report.maximum_temperature_c)} °C</strong><small>Grenze ${formatInteger(report.temperature_limit_c)} °C</small></div>
      <div><span>Innenwiderstand</span><strong>${report.start_resistance_mohm == null ? "--" : `${formatInteger(report.start_resistance_mohm)} mΩ`}</strong><small>${report.end_resistance_mohm == null ? "Kein Endwert" : `Ende ${formatInteger(report.end_resistance_mohm)} mΩ`}</small></div>
      <div><span>Abschlussstatus</span><strong>${escapeHtml(report.last_status || "--")}</strong><small>${formatInteger(report.sample_count)} Messpunkte</small></div>
    </div>
    <div class="run-report-warnings">
      ${report.warnings.length
        ? report.warnings.map((warning) => `<p class="${escapeHtml(warning.level)}">${escapeHtml(warning.text)}</p>`).join("")
        : "<p class=\"ok\">Keine Auffälligkeiten nach den eingestellten Grenzwerten.</p>"}
    </div>
    ${report.ended_at ? `
      <div class="dialog-actions">
        <button data-action="run-chart" data-run-id="${report.id}">Diagramm anzeigen</button>
        <button class="primary" data-action="run-pdf" data-run-id="${report.id}">Bericht als PDF</button>
        <button class="danger-quiet" data-action="delete-run" data-run-id="${report.id}">Bericht löschen</button>
      </div>
    ` : ""}
  `;
  elements.runReportDialog.showModal();
}

async function openRunChart(runId) {
  if (elements.runReportDialog.open) elements.runReportDialog.close();
  appState.runChart = null;
  resetChartZoom("run", false);
  elements.runChartTitle.textContent = "Programmlauf";
  elements.runChartMeta.textContent = "Lade Daten...";
  elements.runChartDialog.showModal();
  try {
    const data = await api(`/api/recordings/runs/${runId}/chart`);
    appState.runChart = data;
    const device = findDevice(data.address);
    elements.runChartTitle.textContent =
      `${device?.alias || data.address} · Slot ${data.slot}`;
    const capacitySummary = data.capacity_ratio_percent == null
      ? ""
      : ` · Soll ${formatInteger(data.capacity_target_mah)} / Ist ${formatInteger(data.capacity_actual_mah)} mAh`
        + ` · ${formatNumber(data.capacity_ratio_percent, 1)} %`;
    const phases = runPhaseAnnotations(data).phaseBands
      .map((phase) => phase.label)
      .join(" → ");
    const phaseSummary = phases ? ` · ${phases}` : "";
    elements.runChartMeta.textContent =
      `${formatDateTime(data.since)} bis ${formatDateTime(data.until)} · `
      + `5 Minuten vor Programmstart bis 1 Stunde nach Programmende · `
      + `${formatInteger(data.total_points)} Messpunkte${phaseSummary}${capacitySummary}`;
    requestAnimationFrame(() => drawRunCharts(data));
  } catch (error) {
    elements.runChartDialog.close();
    throw error;
  }
}

async function deleteRun(runId) {
  const confirmed = window.confirm(
    "Bericht wirklich löschen? Die zugehörigen Messpunkte "
    + "und die Abschlussmeldung werden ebenfalls entfernt.",
  );
  if (!confirmed) return;
  await api(`/api/recordings/runs/${runId}`, { method: "DELETE" });
  if (elements.runReportDialog.open) elements.runReportDialog.close();
  if (elements.runChartDialog.open) elements.runChartDialog.close();
  appState.runChart = null;
  const selectedBatteryId = appState.selectedBattery?.id;
  await Promise.all([
    loadRecordingRuns({ quiet: true }),
    loadNotifications(),
    selectedBatteryId ? selectBattery(selectedBatteryId) : Promise.resolve(),
  ]);
  showToast("Bericht wurde gelöscht");
}

function openBatteryQrLabel() {
  const battery = appState.selectedBattery;
  if (!battery) return;
  const popup = window.open("", "_blank", "width=520,height=680");
  if (!popup) {
    showToast("Popup wurde vom Browser blockiert", true);
    return;
  }
  popup.document.write(`<!doctype html>
    <html lang="de"><head><meta charset="utf-8"><title>Batterie ${escapeHtml(battery.code)}</title>
    <style>body{font:16px system-ui;text-align:center;padding:30px;color:#18211f}img{width:320px;max-width:90%}h1{font-size:42px;margin:10px}p{margin:6px}@media print{button{display:none}}</style></head>
    <body><img src="/api/batteries/${battery.id}/qr.svg" alt="QR-Code">
    <h1>${escapeHtml(battery.code)}</h1>
    <p>${escapeHtml(battery.name || battery.battery_type)}</p>
    <p>${formatInteger(battery.nominal_capacity_mah)} mAh</p>
    <button onclick="window.print()">Etikett drucken</button></body></html>`);
  popup.document.close();
}

async function loadNotifications({ announce = false } = {}) {
  try {
    const data = await api("/api/notifications?limit=50");
    appState.notifications = data.notifications || [];
    const unread = appState.notifications.filter((item) => !item.read);
    elements.notificationCount.hidden = unread.length === 0;
    elements.notificationCount.textContent = String(unread.length);
    elements.notificationButton.classList.toggle("has-unread", unread.length > 0);
    renderNotifications();
    if (announce && Notification.permission === "granted") {
      const announced = new Set(
        JSON.parse(localStorage.getItem("mc3000-announced-notifications") || "[]"),
      );
      const fresh = unread.filter((item) => !announced.has(item.id));
      fresh.forEach((item) => {
        new Notification(item.title, { body: item.message, tag: `mc3000-${item.id}` });
        announced.add(item.id);
      });
      localStorage.setItem(
        "mc3000-announced-notifications",
        JSON.stringify([...announced].slice(-200)),
      );
    }
  } catch (error) {
    if (!announce) showToast(error.message, true);
  }
}

function renderNotifications() {
  elements.notificationList.innerHTML = appState.notifications.length
    ? appState.notifications.map((item) => `
      <article class="${item.read ? "" : "unread"}">
        <div><strong>${escapeHtml(item.title)}</strong><time>${formatDateTime(item.created_at)}</time></div>
        <p>${escapeHtml(item.message)}</p>
        ${item.run_id ? `<button data-action="run-report" data-run-id="${item.run_id}">Abschlussbericht</button>` : ""}
      </article>
    `).join("")
    : '<p class="form-note">Noch keine Meldungen vorhanden.</p>';
}

async function openNotifications() {
  await loadNotifications();
  elements.notificationDialog.showModal();
}

async function markNotificationsRead() {
  const unread = appState.notifications.filter((item) => !item.read);
  if (!unread.length) return;
  await api("/api/notifications/read", {
    method: "POST",
    body: JSON.stringify({ notification_ids: unread.map((item) => item.id) }),
  });
  await loadNotifications();
}

async function enableBrowserNotifications() {
  if (!("Notification" in window)) {
    showToast("Dieser Browser unterstützt keine Desktop-Meldungen", true);
    return;
  }
  const permission = await Notification.requestPermission();
  showToast(
    permission === "granted"
      ? "Browser-Meldungen sind aktiviert"
      : "Browser-Meldungen wurden nicht freigegeben",
    permission !== "granted",
  );
}

function renderHistorySummary(data) {
  const points = data.points || [];
  if (!points.length) {
    elements.historySummary.textContent = "In diesem Zeitraum liegen noch keine Messwerte vor";
    return;
  }
  const latest = points.at(-1);
  const device = findDevice(data.address);
  elements.historySummary.innerHTML = `
    <strong>${escapeHtml(device?.alias || data.address)} · Slot ${data.slot}</strong>
    <span>${formatInteger(data.total_points)} Messpunkte · letzter Wert ${formatDateTime(latest.recorded_at)}</span>
    <span>${formatNumber(latest.voltage_v, 3)} V · ${formatNumber(latest.current_a, 3)} A · ${formatInteger(latest.resistance_mohm)} mΩ</span>
  `;
}

function exportHistory() {
  const address = elements.historyDevice.value;
  if (!address) {
    showToast("Kein Ladegerät ausgewählt", true);
    return;
  }
  const parameters = new URLSearchParams({
    address,
    slot: elements.historySlot.value,
    hours: elements.historyHours.value,
  });
  window.location.assign(`/api/recordings/export.csv?${parameters}`);
}

function drawHistoryCharts(points) {
  const palette = chartPalette();
  const phaseAnnotations = {
    ...historyPhaseAnnotations(points),
    phaseOpacity: chartPhaseOpacity(),
  };
  drawTimeChart(
    elements.voltageCurrentChart,
    points,
    { key: "voltage_v", color: palette.green, unit: "V", digits: 3 },
    { key: "current_a", color: palette.red, unit: "A", digits: 3 },
    null,
    { zoomGroup: "history", ...phaseAnnotations },
  );
  drawTimeChart(
    elements.temperatureResistanceChart,
    points,
    { key: "temperature_c", color: palette.amber, unit: "°C", digits: 0 },
    { key: "resistance_mohm", color: palette.purple, unit: "mΩ", digits: 0 },
    null,
    { zoomGroup: "history", ...phaseAnnotations },
  );
  drawTimeChart(
    elements.capacityChart,
    points,
    { key: "capacity_mah", color: palette.blue, unit: "mAh", digits: 0 },
    null,
    null,
    { zoomGroup: "history", ...phaseAnnotations },
  );
}

function drawRunCharts(data) {
  const palette = chartPalette();
  const points = data?.points || [];
  const range = { start: data?.since, end: data?.until };
  const phaseAnnotations = {
    ...runPhaseAnnotations(data),
    phaseOpacity: chartPhaseOpacity(),
  };
  const capacityTarget = Number(data?.capacity_target_mah);
  const capacityActual = Number(data?.capacity_actual_mah);
  const capacityRatio = Number(data?.capacity_ratio_percent);
  const hasCapacityResult = Number.isFinite(capacityTarget)
    && capacityTarget > 0
    && Number.isFinite(capacityActual)
    && capacityActual > 0
    && Number.isFinite(capacityRatio);
  elements.runCapacityLegend.innerHTML = hasCapacityResult
    ? `
      <span><i class="legend-capacity"></i>Ist ${formatInteger(capacityActual)} mAh</span>
      <span><i class="legend-capacity-target"></i>Soll ${formatInteger(capacityTarget)} mAh</span>
      <strong class="capacity-factor-chip">${formatNumber(capacityRatio, 1)} %</strong>
    `
    : '<span><i class="legend-capacity"></i>Ist-Verlauf mAh</span>';
  drawTimeChart(
    elements.runVoltageCurrentChart,
    points,
    { key: "voltage_v", color: palette.green, unit: "V", digits: 3 },
    { key: "current_a", color: palette.red, unit: "A", digits: 3 },
    range,
    { zoomGroup: "run", ...phaseAnnotations },
  );
  drawTimeChart(
    elements.runTemperatureResistanceChart,
    points,
    { key: "temperature_c", color: palette.amber, unit: "°C", digits: 0 },
    { key: "resistance_mohm", color: palette.purple, unit: "mΩ", digits: 0 },
    range,
    { zoomGroup: "run", ...phaseAnnotations },
  );
  drawTimeChart(
    elements.runCapacityChart,
    points,
    { key: "capacity_mah", color: palette.blue, unit: "mAh", digits: 0 },
    null,
    range,
    hasCapacityResult
      ? {
        zoomGroup: "run",
        ...phaseAnnotations,
        scaleValues: [capacityTarget, capacityActual],
        referenceLines: [
          {
            value: capacityTarget,
            color: palette.green,
            dash: [8, 5],
            label: `Soll ${formatInteger(capacityTarget)} mAh`,
            labelPosition: "below",
          },
          {
            value: capacityActual,
            color: palette.blue,
            dash: [2, 5],
            label: `Ist ${formatInteger(capacityActual)} mAh · ${formatNumber(capacityRatio, 1)} %`,
            labelPosition: "above",
          },
        ],
      }
      : { zoomGroup: "run", ...phaseAnnotations },
  );
}

function runPhaseAnnotations(data) {
  return measurementPhaseAnnotations(data?.points || [], {
    runId: Number(data?.run_id),
    numberRepeatedPhases: true,
  });
}

function historyPhaseAnnotations(points) {
  return measurementPhaseAnnotations(points);
}

function measurementPhaseAnnotations(
  points,
  { runId = null, numberRepeatedPhases = false } = {},
) {
  const expectedRunId = Number.isFinite(runId) ? runId : null;
  const segments = [];
  let current = null;
  (points || []).forEach((point) => {
    const statusCode = Number(point.status_code);
    const time = new Date(point.recorded_at).getTime();
    const pointRunId = Number(point.run_id);
    const belongsToRun = point.run_id != null
      && Number.isFinite(pointRunId)
      && (expectedRunId == null || pointRunId === expectedRunId);
    if (!belongsToRun || ![1, 2, 3, 4].includes(statusCode) || !Number.isFinite(time)) {
      current = null;
      return;
    }
    if (
      !current
      || current.statusCode !== statusCode
      || current.runId !== pointRunId
    ) {
      current = { runId: pointRunId, statusCode, start: time, end: time };
      segments.push(current);
    } else {
      current.end = time;
    }
  });

  const activeSegments = segments.filter((segment) => [1, 2].includes(segment.statusCode));
  const totals = activeSegments.reduce((counts, segment) => {
    const key = `${segment.runId}:${segment.statusCode}`;
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
  const seen = {};
  const palette = chartPalette();
  const bands = segments.filter((segment) => [1, 2, 3].includes(segment.statusCode)).map((segment) => {
    const key = `${segment.runId}:${segment.statusCode}`;
    seen[key] = (seen[key] || 0) + 1;
    const baseLabel = segment.statusCode === 1
      ? "Laden"
      : segment.statusCode === 2
        ? "Entladen"
        : "Pause";
    return {
      ...segment,
      label: numberRepeatedPhases
        && segment.statusCode !== 3
        && totals[key] > 1
        ? `${baseLabel} ${seen[key]}`
        : baseLabel,
      color: segment.statusCode === 1
        ? palette.green
        : segment.statusCode === 2
          ? palette.red
          : palette.amber,
    };
  });
  return { phaseBands: bands };
}

function chartPhaseOpacity() {
  const percent = Number(appState.settings?.phase_opacity_percent) || 15;
  return Math.max(15, Math.min(25, percent)) / 100;
}

function chartPalette() {
  const styles = getComputedStyle(document.documentElement);
  const color = (name, fallback) => styles.getPropertyValue(name).trim() || fallback;
  return {
    background: color("--chart-background", "#ffffff"),
    grid: color("--chart-grid", "#e0e5e7"),
    text: color("--chart-text", "#667078"),
    crosshair: color("--chart-crosshair", "#59656b"),
    baseline: color("--chart-baseline", "#d8dddf"),
    tooltip: color("--chart-tooltip", "rgba(28, 37, 42, 0.94)"),
    tooltipInk: color("--chart-tooltip-ink", "#ffffff"),
    labelBackground: color(
      "--chart-label-background",
      "rgba(255, 255, 255, 0.92)",
    ),
    hoverFill: color("--chart-hover-fill", "#ffffff"),
    selectionFill: color(
      "--chart-selection-fill",
      "rgba(40, 99, 167, 0.16)",
    ),
    selectionLabel: color(
      "--chart-selection-label",
      "rgba(40, 99, 167, 0.94)",
    ),
    green: color("--green", "#16825d"),
    red: color("--red", "#b52b34"),
    amber: color("--amber", "#a66300"),
    blue: color("--blue", "#2863a7"),
    purple: color("--purple", "#7a4d9b"),
  };
}

function drawTimeChart(
  canvas,
  points,
  leftSeries,
  rightSeries = null,
  requestedRange = null,
  options = {},
) {
  const { context, width, height } = prepareCanvas(canvas);
  const palette = chartPalette();
  context.clearRect(0, 0, width, height);
  context.fillStyle = palette.background;
  context.fillRect(0, 0, width, height);

  const margin = {
    top: 16,
    right: rightSeries ? 62 : 18,
    bottom: 30,
    left: leftSeries.unit === "mAh" ? 78 : 62,
  };
  const chartWidth = Math.max(1, width - margin.left - margin.right);
  const chartHeight = Math.max(1, height - margin.top - margin.bottom);

  if (!points.length) {
    chartGeometries.delete(canvas);
    updateChartZoomControls(options.zoomGroup);
    context.fillStyle = palette.text;
    context.font = "13px system-ui";
    context.textAlign = "center";
    context.fillText("Keine Messwerte im gewählten Zeitraum", width / 2, height / 2);
    return;
  }

  const times = points.map((point) => new Date(point.recorded_at).getTime());
  const requestedStart = new Date(requestedRange?.start).getTime();
  const requestedEnd = new Date(requestedRange?.end).getTime();
  const fullStart = Number.isFinite(requestedStart)
    ? requestedStart
    : Math.min(...times);
  const fullEndCandidate = Number.isFinite(requestedEnd) && requestedEnd > fullStart
    ? requestedEnd
    : Math.max(...times);
  const fullEnd = fullEndCandidate > fullStart ? fullEndCandidate : fullStart + 1;
  const { start, end } = chartViewRange(options.zoomGroup, fullStart, fullEnd);
  const timeRange = Math.max(end - start, 1);
  const xFor = (time) => margin.left + ((time - start) / timeRange) * chartWidth;
  const visible = chartPointsInRange(points, times, start, end);
  const leftScale = seriesScale(
    visible.points,
    leftSeries.key,
    options.scaleValues,
  );
  const rightScale = rightSeries
    ? seriesScale(visible.points, rightSeries.key)
    : null;

  chartGeometries.set(canvas, {
    group: options.zoomGroup,
    left: margin.left,
    top: margin.top,
    width: chartWidth,
    height: chartHeight,
    start,
    end,
    fullStart,
    fullEnd,
    formatter: (value) => formatChartTime(value),
  });
  updateChartZoomControls(options.zoomGroup);
  drawChartPhaseBands(
    context,
    options.phaseBands || [],
    start,
    end,
    margin.left,
    margin.top,
    chartWidth,
    chartHeight,
    options.phaseOpacity,
  );

  context.strokeStyle = palette.grid;
  context.lineWidth = 1;
  for (let row = 0; row <= 4; row += 1) {
    const y = margin.top + (chartHeight / 4) * row;
    context.beginPath();
    context.moveTo(margin.left, y);
    context.lineTo(margin.left + chartWidth, y);
    context.stroke();
  }

  drawAxisLabels(context, leftScale, margin.left - 8, margin.top, chartHeight, leftSeries, "right");
  if (rightSeries) {
    drawAxisLabels(
      context,
      rightScale,
      margin.left + chartWidth + 8,
      margin.top,
      chartHeight,
      rightSeries,
      "left",
    );
  }
  drawTimeLabels(context, start, end, margin.left, margin.top + chartHeight + 20, chartWidth);
  context.save();
  context.beginPath();
  context.rect(margin.left, margin.top, chartWidth, chartHeight);
  context.clip();
  drawTimeSeries(
    context,
    visible.points,
    visible.times,
    xFor,
    leftScale,
    leftSeries,
    margin.top,
    chartHeight,
  );
  if (rightSeries) {
    drawTimeSeries(
      context,
      visible.points,
      visible.times,
      xFor,
      rightScale,
      rightSeries,
      margin.top,
      chartHeight,
    );
  }
  context.restore();
  drawChartReferenceLines(
    context,
    options.referenceLines || [],
    leftScale,
    margin.left,
    margin.top,
    chartWidth,
    chartHeight,
  );
  drawTimeChartHover(
    canvas,
    context,
    visible.points,
    visible.times,
    xFor,
    leftScale,
    leftSeries,
    rightScale,
    rightSeries,
    margin,
    chartWidth,
    chartHeight,
    start,
    end,
  );
  drawChartSelectionOverlay(canvas, context);
}

function chartViewRange(group, fullStart, fullEnd) {
  const zoom = group ? chartZoomRanges.get(group) : null;
  if (!zoom) return { start: fullStart, end: fullEnd };
  const start = Math.max(fullStart, Number(zoom.start));
  const end = Math.min(fullEnd, Number(zoom.end));
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    chartZoomRanges.delete(group);
    return { start: fullStart, end: fullEnd };
  }
  return { start, end };
}

function chartPointsInRange(points, values, start, end) {
  let first = values.findIndex((value) => value >= start);
  if (first < 0) first = values.length - 1;
  let last = values.findIndex((value) => value > end);
  if (last < 0) last = values.length;
  first = Math.max(0, first - 1);
  last = Math.min(values.length, last + 1);
  return {
    points: points.slice(first, last),
    times: values.slice(first, last),
  };
}

function drawChartPhaseBands(
  context,
  bands,
  start,
  end,
  left,
  top,
  width,
  height,
  opacity = 0.15,
) {
  const range = Math.max(end - start, 1);
  bands.forEach((band) => {
    const bandStart = Math.max(start, Number(band.start));
    const bandEnd = Math.min(end, Number(band.end));
    if (!Number.isFinite(bandStart) || !Number.isFinite(bandEnd) || bandEnd < start || bandStart > end) {
      return;
    }
    const x1 = left + ((bandStart - start) / range) * width;
    const minimumEnd = bandStart + Math.max(range * 0.002, 1000);
    const x2 = left + ((Math.max(bandEnd, minimumEnd) - start) / range) * width;
    const bandWidth = Math.max(1, Math.min(left + width, x2) - Math.max(left, x1));
    const bandX = Math.max(left, x1);
    context.save();
    context.globalAlpha = Math.max(0.15, Math.min(0.25, Number(opacity) || 0.15));
    context.fillStyle = band.color;
    context.fillRect(bandX, top, bandWidth, height);
    context.globalAlpha = 1;
    if (bandWidth >= 52) {
      context.fillStyle = band.color;
      context.font = "700 10px system-ui";
      context.textAlign = "center";
      context.fillText(band.label, bandX + bandWidth / 2, top + 12);
    }
    context.restore();
  });
}

function seriesScale(points, key, scaleValues = []) {
  const values = [
    ...points.map((point) => Number(point[key]) || 0),
    ...scaleValues.filter((value) => Number.isFinite(Number(value))).map(Number),
  ];
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const minimumRanges = {
    voltage_v: 0.02,
    current_a: 0.05,
    temperature_c: 2,
    resistance_mohm: 5,
    capacity_mah: 10,
  };
  const range = Math.max(
    (rawMax - rawMin) * 1.16,
    minimumRanges[key] || 0.01,
  );
  const center = (rawMin + rawMax) / 2;
  let min = center - range / 2;
  let max = center + range / 2;
  if (rawMin >= 0 && min < 0) {
    max -= min;
    min = 0;
  }
  return { min, max, range: max - min };
}

function drawChartReferenceLines(
  context,
  referenceLines,
  scale,
  left,
  top,
  width,
  height,
) {
  const palette = chartPalette();
  referenceLines.forEach((line) => {
    const value = Number(line.value);
    if (!Number.isFinite(value) || value < scale.min || value > scale.max) return;
    const y = top + height - ((value - scale.min) / scale.range) * height;
    context.save();
    context.strokeStyle = line.color;
    context.lineWidth = 1.5;
    context.setLineDash(line.dash || [7, 5]);
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(left + width, y);
    context.stroke();
    context.setLineDash([]);

    if (line.label) {
      context.font = "600 11px system-ui";
      const labelWidth = context.measureText(line.label).width + 14;
      const labelHeight = 20;
      const labelX = left + width - labelWidth - 4;
      const wantsBelow = line.labelPosition === "below";
      const labelY = Math.max(
        top + 2,
        Math.min(
          wantsBelow ? y + 5 : y - labelHeight - 5,
          top + height - labelHeight - 2,
        ),
      );
      context.fillStyle = palette.labelBackground;
      context.fillRect(labelX, labelY, labelWidth, labelHeight);
      context.strokeStyle = line.color;
      context.strokeRect(labelX, labelY, labelWidth, labelHeight);
      context.fillStyle = line.color;
      context.textAlign = "left";
      context.fillText(line.label, labelX + 7, labelY + 14);
    }
    context.restore();
  });
}

function drawTimeChartHover(
  canvas,
  context,
  points,
  times,
  xFor,
  leftScale,
  leftSeries,
  rightScale,
  rightSeries,
  margin,
  chartWidth,
  chartHeight,
  chartStart,
  chartEnd,
) {
  const palette = chartPalette();
  const pointer = chartPointers.get(canvas);
  if (
    !pointer
    || pointer.dragging
    || pointer.anchorX != null
    || pointer.x < margin.left
    || pointer.x > margin.left + chartWidth
    || pointer.y < margin.top
    || pointer.y > margin.top + chartHeight
  ) return;

  const targetTime = chartStart
    + ((pointer.x - margin.left) / chartWidth) * (chartEnd - chartStart);
  const index = nearestValueIndex(times, targetTime);
  const point = points[index];
  const x = xFor(times[index]);
  const series = [
    { definition: leftSeries, scale: leftScale },
    ...(rightSeries ? [{ definition: rightSeries, scale: rightScale }] : []),
  ];

  context.save();
  context.strokeStyle = palette.crosshair;
  context.lineWidth = 1;
  context.setLineDash([4, 4]);
  context.beginPath();
  context.moveTo(x, margin.top);
  context.lineTo(x, margin.top + chartHeight);
  context.stroke();
  context.setLineDash([]);

  series.forEach(({ definition, scale }) => {
    const value = Number(point[definition.key]) || 0;
    const y = margin.top + chartHeight
      - ((value - scale.min) / scale.range) * chartHeight;
    drawHoverPoint(context, x, y, definition.color);
  });

  const lines = [
    `Uhrzeit: ${formatDateTime(point.recorded_at)}`,
    ...series.map(({ definition }) => (
      `${chartSeriesLabel(definition.key)}: ${formatNumber(point[definition.key], definition.digits)} ${definition.unit}`
    )),
  ];
  drawChartTooltip(
    context,
    lines,
    x,
    margin.top + 8,
    margin.left,
    margin.left + chartWidth,
  );
  context.restore();
}

function chartSeriesLabel(key) {
  return ({
    voltage_v: "Spannung",
    current_a: "Strom",
    temperature_c: "Temperatur",
    resistance_mohm: "Innenwiderstand",
    capacity_mah: "Kapazität",
  })[key] || "Wert";
}

function nearestValueIndex(values, target) {
  let low = 0;
  let high = values.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (values[middle] < target) low = middle + 1;
    else high = middle;
  }
  if (low === 0) return 0;
  return Math.abs(values[low] - target) < Math.abs(values[low - 1] - target)
    ? low
    : low - 1;
}

function drawHoverPoint(context, x, y, color) {
  context.fillStyle = chartPalette().hoverFill;
  context.strokeStyle = color;
  context.lineWidth = 3;
  context.beginPath();
  context.arc(x, y, 5, 0, Math.PI * 2);
  context.fill();
  context.stroke();
}

function drawChartTooltip(context, lines, pointX, y, minimumX, maximumX) {
  const palette = chartPalette();
  context.font = "12px system-ui";
  const lineHeight = 18;
  const width = Math.max(...lines.map((line) => context.measureText(line).width)) + 20;
  const height = lines.length * lineHeight + 12;
  let x = pointX + 12;
  if (x + width > maximumX) x = pointX - width - 12;
  x = Math.max(minimumX, Math.min(x, maximumX - width));

  context.fillStyle = palette.tooltip;
  context.fillRect(x, y, width, height);
  context.fillStyle = palette.tooltipInk;
  context.textAlign = "left";
  lines.forEach((line, index) => {
    context.fillText(line, x + 10, y + 19 + index * lineHeight);
  });
}

function drawTimeSeries(context, points, times, xFor, scale, series, top, height) {
  context.strokeStyle = series.color;
  context.lineWidth = 2;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.beginPath();
  points.forEach((point, index) => {
    const value = Number(point[series.key]) || 0;
    const x = xFor(times[index]);
    const y = top + height - ((value - scale.min) / scale.range) * height;
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.stroke();
}

function drawAxisLabels(context, scale, x, top, height, series, align) {
  context.fillStyle = series.color;
  context.font = "11px system-ui";
  context.textAlign = align;
  for (let index = 0; index <= 4; index += 1) {
    const value = scale.max - (scale.range / 4) * index;
    const y = top + (height / 4) * index + 4;
    context.fillText(`${formatNumber(value, series.digits)} ${series.unit}`, x, y);
  }
}

function drawTimeLabels(context, start, end, left, y, width) {
  context.fillStyle = chartPalette().text;
  context.font = "11px system-ui";
  const compact = width < 280;
  const values = compact
    ? [start, end]
    : [start, start + (end - start) / 2, end];
  const alignments = compact ? ["left", "right"] : ["left", "center", "right"];
  const positions = compact ? [0, width] : [0, width / 2, width];
  const sameDay = new Date(start).toDateString() === new Date(end).toDateString();
  values.forEach((value, index) => {
    context.textAlign = alignments[index];
    context.fillText(formatChartTime(value, sameDay), left + positions[index], y);
  });
}

function drawSparklines() {
  document.querySelectorAll(".sparkline").forEach((canvas) => {
    drawSparkline(canvas, histories.get(canvas.dataset.history) || []);
  });
}

function drawSparkline(canvas, points) {
  const { context, width, height } = prepareCanvas(canvas);
  const palette = chartPalette();
  context.clearRect(0, 0, width, height);
  context.fillStyle = palette.background;
  context.fillRect(0, 0, width, height);
  drawSparklinePhaseBands(context, points, width, height);
  context.strokeStyle = palette.baseline;
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(0, height - 1);
  context.lineTo(width, height - 1);
  context.stroke();
  if (!points.length) return;

  const voltages = points.map((point) => point.voltage);
  const currents = points.map((point) => point.current);
  drawSeries(context, voltages, width, height, palette.green, 2);
  const hasCurrent = currents.some((value) => value !== 0);
  if (hasCurrent) {
    drawSeries(context, currents, width, height, palette.red, 1.5);
  }

  const pointer = sparklinePointer(canvas, width, height);
  if (!pointer) return;
  const index = points.length === 1
    ? 0
    : Math.max(
      0,
      Math.min(
        points.length - 1,
        Math.round((pointer.x / width) * (points.length - 1)),
      ),
    );
  const x = points.length === 1
    ? width / 2
    : (index / (points.length - 1)) * width;

  context.save();
  context.strokeStyle = palette.crosshair;
  context.lineWidth = 1;
  context.setLineDash([4, 4]);
  context.beginPath();
  context.moveTo(x, 0);
  context.lineTo(x, height);
  context.stroke();
  context.setLineDash([]);
  drawHoverPoint(
    context,
    x,
    scaledSeriesY(voltages, index, height),
    palette.green,
  );
  if (hasCurrent) {
    drawHoverPoint(
      context,
      x,
      scaledSeriesY(currents, index, height),
      palette.red,
    );
  }
  drawChartTooltip(
    context,
    [
      `Uhrzeit: ${formatDateTime(points[index].stamp)}`,
      ...sparklinePhaseLabel(points[index].statusCode),
      `Spannung: ${formatNumber(points[index].voltage, 3)} V`,
      `Strom: ${formatNumber(points[index].current, 3)} A`,
    ],
    x,
    3,
    3,
    width - 3,
  );
  context.restore();
}

function drawSparklinePhaseBands(context, points, width, height) {
  if (!points.length) return;
  const palette = chartPalette();
  const colors = {
    1: palette.green,
    2: palette.red,
    3: palette.amber,
  };
  const denominator = Math.max(points.length - 1, 1);
  let start = 0;
  while (start < points.length) {
    const statusCode = Number(points[start].statusCode);
    let end = start;
    while (
      end + 1 < points.length
      && Number(points[end + 1].statusCode) === statusCode
    ) end += 1;
    if (colors[statusCode]) {
      const x1 = start === 0
        ? 0
        : ((start - 0.5) / denominator) * width;
      const x2 = end === points.length - 1
        ? width
        : ((end + 0.5) / denominator) * width;
      context.save();
      context.globalAlpha = chartPhaseOpacity();
      context.fillStyle = colors[statusCode];
      context.fillRect(x1, 0, Math.max(1, x2 - x1), height);
      context.restore();
    }
    start = end + 1;
  }
}

function sparklinePhaseLabel(statusCode) {
  const label = { 1: "Laden", 2: "Entladen", 3: "Pause" }[Number(statusCode)];
  return label ? [`Phase: ${label}`] : [];
}

function sparklinePointer(canvas, width, height) {
  if (
    !pointerPosition
    || hoveredSparklineKey !== canvas.dataset.history
  ) return null;
  const rect = canvas.getBoundingClientRect();
  const x = pointerPosition.clientX - rect.left;
  const y = pointerPosition.clientY - rect.top;
  if (x < 0 || x > width || y < 0 || y > height) return null;
  return { x, y };
}

function scaledSeriesY(values, index, height, padding = 2) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.02);
  const drawableHeight = Math.max(height - padding * 2, 1);
  return padding + drawableHeight
    - ((values[index] - min) / range) * drawableHeight;
}

function handleSparklinePointer(event) {
  pointerPosition = { clientX: event.clientX, clientY: event.clientY };
  const canvas = event.target instanceof HTMLCanvasElement
    && event.target.classList.contains("sparkline")
    ? event.target
    : null;
  const previousKey = hoveredSparklineKey;
  hoveredSparklineKey = canvas?.dataset.history || null;

  if (previousKey && previousKey !== hoveredSparklineKey) {
    redrawSparkline(previousKey);
  }
  if (canvas) {
    drawSparkline(canvas, histories.get(canvas.dataset.history) || []);
  }
}

function redrawSparkline(historyKeyValue) {
  const canvas = [...document.querySelectorAll(".sparkline")].find(
    (candidate) => candidate.dataset.history === historyKeyValue,
  );
  if (canvas) {
    drawSparkline(canvas, histories.get(historyKeyValue) || []);
  }
}

function clearSparklinePointer() {
  const previousKey = hoveredSparklineKey;
  pointerPosition = null;
  hoveredSparklineKey = null;
  if (previousKey) redrawSparkline(previousKey);
}

function drawCurve(canvas, points) {
  const { context, width, height } = prepareCanvas(canvas);
  const palette = chartPalette();
  context.clearRect(0, 0, width, height);
  context.fillStyle = palette.background;
  context.fillRect(0, 0, width, height);
  context.strokeStyle = palette.baseline;
  context.lineWidth = 1;
  for (let row = 1; row < 5; row += 1) {
    const y = (height / 5) * row;
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }
  if (!points.length) {
    chartGeometries.delete(canvas);
    updateChartZoomControls("curve");
    return;
  }
  const times = points.map((point) => Number(point.time_s) || 0);
  const fullStart = Math.min(...times);
  const fullEndCandidate = Math.max(...times);
  const fullEnd = fullEndCandidate > fullStart ? fullEndCandidate : fullStart + 1;
  const { start, end } = chartViewRange("curve", fullStart, fullEnd);
  const visible = chartPointsInRange(points, times, start, end);
  const values = visible.points.map((point) => Number(point.voltage_v) || 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.02);
  const drawableHeight = Math.max(height - 36, 1);
  const xFor = (time) => ((time - start) / Math.max(end - start, 1)) * width;
  const yFor = (value) => 18 + drawableHeight - ((value - min) / range) * drawableHeight;
  chartGeometries.set(canvas, {
    group: "curve",
    left: 0,
    top: 0,
    width,
    height,
    start,
    end,
    fullStart,
    fullEnd,
    formatter: formatDurationShort,
  });
  updateChartZoomControls("curve");

  context.save();
  context.beginPath();
  context.rect(0, 0, width, height);
  context.clip();
  context.strokeStyle = palette.green;
  context.lineWidth = 2.5;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.beginPath();
  visible.points.forEach((point, index) => {
    const x = xFor(visible.times[index]);
    const y = yFor(Number(point.voltage_v) || 0);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.stroke();
  context.restore();

  const pointer = chartPointers.get(canvas);
  if (
    !pointer
    || pointer.dragging
    || pointer.anchorX != null
    || pointer.x < 0
    || pointer.x > width
    || pointer.y < 0
    || pointer.y > height
  ) {
    drawChartSelectionOverlay(canvas, context);
    return;
  }
  const targetTime = start + (pointer.x / width) * (end - start);
  const index = nearestValueIndex(visible.times, targetTime);
  const point = visible.points[index];
  const x = xFor(visible.times[index]);
  const y = yFor(Number(point.voltage_v) || 0);
  context.save();
  context.strokeStyle = palette.crosshair;
  context.lineWidth = 1;
  context.setLineDash([4, 4]);
  context.beginPath();
  context.moveTo(x, 0);
  context.lineTo(x, height);
  context.stroke();
  context.setLineDash([]);
  drawHoverPoint(context, x, y, palette.green);
  drawChartTooltip(
    context,
    [
      `Dauer: ${formatDurationShort(point.time_s)}`,
      `Spannung: ${formatNumber(point.voltage_v, 3)} V`,
    ],
    x,
    10,
    4,
    width - 4,
  );
  context.restore();
  drawChartSelectionOverlay(canvas, context);
}

function drawSeries(context, values, width, height, color, lineWidth, padding = 2) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.02);
  const drawableHeight = Math.max(height - padding * 2, 1);
  context.strokeStyle = color;
  context.lineWidth = lineWidth;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.beginPath();
  values.forEach((value, index) => {
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
    const y = padding + drawableHeight - ((value - min) / range) * drawableHeight;
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.stroke();
}

function prepareCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(Math.round(rect.width), 1);
  const height = Math.max(Math.round(rect.height), 1);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function drawChartSelectionOverlay(canvas, context) {
  const palette = chartPalette();
  const geometry = chartGeometries.get(canvas);
  const pointer = chartPointers.get(canvas);
  if (!geometry || !pointer || (!pointer.dragging && pointer.anchorX == null)) return;

  const startX = pointer.dragging ? pointer.dragStartX : pointer.anchorX;
  const currentX = pointer.dragging ? pointer.dragCurrentX : pointer.x;
  const endX = Number.isFinite(currentX) ? currentX : startX;
  const x1 = Math.max(
    geometry.left,
    Math.min(geometry.left + geometry.width, Math.min(startX, endX)),
  );
  const x2 = Math.max(
    geometry.left,
    Math.min(geometry.left + geometry.width, Math.max(startX, endX)),
  );
  const valueForX = (x) => geometry.start
    + ((x - geometry.left) / geometry.width) * (geometry.end - geometry.start);
  const formatter = geometry.formatter || ((value) => String(value));
  const label = x2 - x1 < 8
    ? "Startpunkt gewählt"
    : `${formatter(valueForX(x1))} – ${formatter(valueForX(x2))}`;

  context.save();
  context.fillStyle = palette.selectionFill;
  context.fillRect(x1, geometry.top, Math.max(1, x2 - x1), geometry.height);
  context.strokeStyle = palette.blue;
  context.lineWidth = 1.5;
  context.setLineDash([5, 4]);
  [x1, x2].forEach((x) => {
    context.beginPath();
    context.moveTo(x, geometry.top);
    context.lineTo(x, geometry.top + geometry.height);
    context.stroke();
  });
  context.setLineDash([]);
  context.font = "700 11px system-ui";
  const labelWidth = Math.min(
    geometry.width - 8,
    context.measureText(label).width + 16,
  );
  const labelX = Math.max(
    geometry.left + 4,
    Math.min((x1 + x2 - labelWidth) / 2, geometry.left + geometry.width - labelWidth - 4),
  );
  context.fillStyle = palette.selectionLabel;
  context.fillRect(labelX, geometry.top + 7, labelWidth, 22);
  context.fillStyle = palette.tooltipInk;
  context.textAlign = "center";
  context.fillText(label, labelX + labelWidth / 2, geometry.top + 22);
  context.restore();
}

function setChartZoomRange(group, start, end, redraw = true) {
  if (!group || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) return;
  chartZoomRanges.set(group, { start, end });
  updateChartZoomControls(group);
  if (redraw) redrawChartGroup(group);
}

function resetChartZoom(group, redraw = true) {
  if (!group) return;
  chartZoomRanges.delete(group);
  updateChartZoomControls(group);
  if (redraw) redrawChartGroup(group);
}

function updateChartZoomControls(group) {
  if (!group) return;
  const zoomed = chartZoomRanges.has(group);
  document.querySelectorAll(
    `[data-action="reset-chart-zoom"][data-chart-group="${group}"]`,
  ).forEach((button) => {
    button.hidden = !zoomed;
  });
}

function redrawChartGroup(group) {
  if (group === "history") {
    drawHistoryCharts(appState.history?.points || []);
  } else if (group === "run") {
    drawRunCharts(appState.runChart);
  } else if (group === "battery-comparison") {
    drawBatteryComparison(appState.batteryComparison);
  } else if (group === "curve") {
    drawCurve(elements.curveCanvas, appState.curve?.points || []);
  }
}

function applyChartPointerSelection(canvas, firstX, secondX) {
  const geometry = chartGeometries.get(canvas);
  if (!geometry || !geometry.group || Math.abs(secondX - firstX) < 8) return false;
  const clampX = (x) => Math.max(
    geometry.left,
    Math.min(geometry.left + geometry.width, x),
  );
  const x1 = clampX(Math.min(firstX, secondX));
  const x2 = clampX(Math.max(firstX, secondX));
  const valueForX = (x) => geometry.start
    + ((x - geometry.left) / geometry.width) * (geometry.end - geometry.start);
  setChartZoomRange(geometry.group, valueForX(x1), valueForX(x2), false);
  return true;
}

function bindChartPointer(canvas, redraw, zoomGroup = null) {
  if (!canvas) return;
  let framePending = false;
  const scheduleRedraw = () => {
    if (framePending) return;
    framePending = true;
    requestAnimationFrame(() => {
      framePending = false;
      redraw();
    });
  };
  const pointerPositionFor = (event) => {
    const rect = canvas.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  };
  canvas.addEventListener("pointermove", (event) => {
    const position = pointerPositionFor(event);
    const previous = chartPointers.get(canvas) || {};
    chartPointers.set(canvas, {
      ...previous,
      ...position,
      dragCurrentX: previous.dragging ? position.x : previous.dragCurrentX,
    });
    if (previous.dragging) event.preventDefault();
    scheduleRedraw();
  });
  canvas.addEventListener("pointerdown", (event) => {
    if (!zoomGroup || event.button !== 0) return;
    const geometry = chartGeometries.get(canvas);
    const position = pointerPositionFor(event);
    if (
      !geometry
      || position.x < geometry.left
      || position.x > geometry.left + geometry.width
      || position.y < geometry.top
      || position.y > geometry.top + geometry.height
    ) return;
    const previous = chartPointers.get(canvas) || {};
    chartPointers.set(canvas, {
      ...previous,
      ...position,
      dragging: true,
      dragStartX: position.x,
      dragCurrentX: position.x,
      pointerId: event.pointerId,
    });
    canvas.setPointerCapture?.(event.pointerId);
    event.preventDefault();
    scheduleRedraw();
  });
  canvas.addEventListener("pointerup", (event) => {
    const pointer = chartPointers.get(canvas);
    if (!pointer?.dragging || pointer.pointerId !== event.pointerId) return;
    const position = pointerPositionFor(event);
    const distance = Math.abs(position.x - pointer.dragStartX);
    let anchorX = pointer.anchorX;
    let zoomed = false;
    if (distance >= 8) {
      zoomed = applyChartPointerSelection(
        canvas,
        pointer.dragStartX,
        position.x,
      );
      anchorX = null;
    } else if (anchorX == null) {
      anchorX = position.x;
    } else {
      zoomed = applyChartPointerSelection(canvas, anchorX, position.x);
      anchorX = zoomed ? null : position.x;
    }
    chartPointers.set(canvas, {
      ...pointer,
      ...position,
      dragging: false,
      dragStartX: null,
      dragCurrentX: null,
      pointerId: null,
      anchorX,
    });
    canvas.releasePointerCapture?.(event.pointerId);
    event.preventDefault();
    if (zoomed) redraw();
    else scheduleRedraw();
  });
  canvas.addEventListener("pointercancel", () => {
    const pointer = chartPointers.get(canvas);
    if (!pointer) return;
    chartPointers.set(canvas, {
      ...pointer,
      dragging: false,
      dragStartX: null,
      dragCurrentX: null,
      pointerId: null,
    });
    scheduleRedraw();
  });
  canvas.addEventListener("pointerleave", () => {
    const pointer = chartPointers.get(canvas);
    if (pointer?.dragging) return;
    if (pointer?.anchorX != null) {
      chartPointers.set(canvas, { ...pointer, x: pointer.anchorX, y: null });
    } else {
      chartPointers.delete(canvas);
    }
    scheduleRedraw();
  });
  canvas.addEventListener("dblclick", (event) => {
    if (!zoomGroup) return;
    chartPointers.delete(canvas);
    resetChartZoom(zoomGroup, false);
    redraw();
    event.preventDefault();
  });
}

function findDevice(address) {
  return appState.devices.find((device) => device.address === address);
}

function findProfile(profileId) {
  return appState.profiles.find((profile) => profile.id === profileId);
}

function findAutomaticProfile(programKey) {
  return (appState.batteryOptions?.automatic_programs || []).find(
    (program) => program.key === programKey,
  );
}

function findBattery(batteryId) {
  return appState.batteries.find((battery) => battery.id === batteryId);
}

function selectedBatteryOption() {
  const code = Number(elements.profileBatteryType.value);
  return appState.profileOptions?.battery_types?.find((battery) => battery.code === code);
}

function setVoltageInputLimits(input, minimumMv, maximumMv) {
  input.min = String(minimumMv / 1000);
  input.max = String(maximumMv / 1000);
}

function toMilli(value) {
  return Math.round(Number(value) * 1000);
}

function historyKey(address, slot) {
  return `${address}-${slot}`;
}

function deviceStateLabel(state) {
  return {
    connected: "Verbunden",
    connecting: "Verbindet",
    waiting: "Wartet",
    released: "Freigegeben",
    disabled: "Deaktiviert",
    error: "Fehler",
  }[state] || state || "Unbekannt";
}

function fanModeLabel(mode) {
  return {
    0: "Automatik",
    1: "Aus",
    2: "Ein",
    3: "ab 20 °C",
    4: "ab 25 °C",
    5: "ab 30 °C",
    6: "ab 35 °C",
    7: "ab 40 °C",
    8: "ab 45 °C",
    9: "ab 50 °C",
  }[Number(mode)] || `Unbekannt (${formatInteger(mode)})`;
}

function signalText(rssi) {
  if (rssi == null) return "Signal unbekannt";
  if (rssi >= -60) return "Signal sehr gut";
  if (rssi >= -75) return "Signal gut";
  return "Signal schwach";
}

function formatNumber(value, digits) {
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : "--";
}

function formatInteger(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number).toLocaleString("de-DE") : "--";
}

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remaining = Math.floor(value % 60);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

function formatDurationShort(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remaining = value % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")} h`
    : `${minutes}:${String(remaining).padStart(2, "0")} min`;
}

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "--"
    : date.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDateTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "--"
    : date.toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "--"
    : date.toLocaleDateString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
}

function formatChartTime(value, timeOnly = false) {
  const date = new Date(value);
  const options = {
    hour: "2-digit",
    minute: "2-digit",
  };
  if (!timeOnly) {
    options.day = "2-digit";
    options.month = "2-digit";
  }
  return date.toLocaleString("de-DE", options);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message, error = false) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", error);
  elements.toast.classList.add("visible");
  toastTimer = setTimeout(() => elements.toast.classList.remove("visible"), 3200);
}

[
  elements.voltageCurrentChart,
  elements.temperatureResistanceChart,
  elements.capacityChart,
].forEach((canvas) => {
  bindChartPointer(
    canvas,
    () => drawHistoryCharts(appState.history?.points || []),
    "history",
  );
});
[
  elements.runVoltageCurrentChart,
  elements.runTemperatureResistanceChart,
  elements.runCapacityChart,
].forEach((canvas) => {
  bindChartPointer(
    canvas,
    () => drawRunCharts(appState.runChart),
    "run",
  );
});
bindChartPointer(
  elements.batteryCompareChart,
  () => drawBatteryComparison(appState.batteryComparison),
  "battery-comparison",
);
bindChartPointer(
  elements.curveCanvas,
  () => drawCurve(elements.curveCanvas, appState.curve?.points || []),
  "curve",
);
document.addEventListener("mousemove", handleSparklinePointer);
document.documentElement.addEventListener("mouseleave", clearSparklinePointer);
window.addEventListener("blur", clearSparklinePointer);

connectWebsocket();
loadReferenceData();
loadNotifications();
setInterval(() => loadNotifications({ announce: true }), 20000);
