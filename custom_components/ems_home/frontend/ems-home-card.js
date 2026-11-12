/**
 * eMS Home Card – an animated energy-flow card for the ABL eMS Home integration.
 *
 * Bundled with the integration and loaded automatically, so it can be used as
 * `type: custom:ems-home-card` without adding a dashboard resource manually.
 *
 * No external dependencies (no lit, no mushroom): everything is plain web
 * component + inline SVG, which keeps it fast and theme-aware.
 */

const VERSION = "1.3.10";

const DEFAULTS = {
  title: "eMS Home",
  layout: "full",
  show_controls: true,
  show_flows: true,
  price: null,      // null = use the integration option, then DEFAULT_PRICE
  pv_price: null,
};

//: Falls back to this when neither the card nor the integration sets a tariff.
const DEFAULT_PRICE = 0.35;

const STRINGS = {
  de: {
    grid: "Netz",
    pv_grid: "PV + Netz",
    cost_grid: "Kosten",
    instead_of: "statt",
    pv: "PV",
    saved: "gespart",
    finished: "Ladevorgang beendet",
    last_charge: "Letzter Ladevorgang",
    plugged: "Fahrzeug angeschlossen",
    ended_today: "heute um {t}",
    ended_yesterday: "gestern um {t}",
    ended_date: "{d} um {t}",
    hub: "eMS",
    car: "Auto",
    grid_import: "Netzbezug",
    export: "Einspeisung",
    idle: "Bereit",
    charging: "Lädt",
    locked: "Gesperrt",
    session: "Ladevorgang",
    energy: "Geladen",
    duration: "Dauer",
    power: "Ladeleistung",
    mode: "Modus",
    pv_quota: "PV-Quote",
    modes: { lock: "Gesperrt", grid: "Netz", pv: "PV", hybrid: "Hybrid" },
    unavailable: "nicht verfügbar",
    cost: "Kosten",
    house: "Hausverbrauch",
    no_stream: "Keine Live-Daten",
    editor: {
      hint: "Benachrichtigungen werden in der Integration eingestellt – eine Stelle für Backend und Karte.",
      settings: "Zu den Einstellungen",
      title: "Titel",
      layout: "Layout",
      full: "Vollständig",
      compact: "Kompakt",
      show_flows: "Energiefluss anzeigen",
      show_controls: "Steuerung anzeigen",
      price: "Strompreis (€/kWh)",
      pv_price: "Wert PV-Strom (€/kWh)",
      entities: "Entitäten (optional)",
      grid_power: "Netzleistung",
      ev_power: "Ladeleistung",
      charge_mode: "Lademodus",
      pv_quota: "PV-Quote",
      wallbox_status: "Wallbox-Status",
      session_duration: "Ladedauer",
      session_energy: "Geladene Energie",
      pv_power: "PV-Leistung (extern)",
      description:
        "Animierter Energiefluss für die ABL eMS Home Wallbox-Steuerung (Netz, Ladung, Modus, PV-Quote).",
    },
  },
  en: {
    grid: "Grid",
    pv_grid: "PV + Grid",
    cost_grid: "Cost",
    instead_of: "instead of",
    pv: "PV",
    saved: "saved",
    finished: "Charging finished",
    last_charge: "Last charge",
    plugged: "Car still connected",
    ended_today: "today at {t}",
    ended_yesterday: "yesterday at {t}",
    ended_date: "{d} at {t}",
    hub: "eMS",
    car: "Car",
    grid_import: "Grid import",
    export: "Export",
    idle: "Idle",
    charging: "Charging",
    locked: "Locked",
    session: "Session",
    energy: "Charged",
    duration: "Duration",
    power: "Charging power",
    mode: "Mode",
    pv_quota: "PV quota",
    modes: { lock: "Locked", grid: "Grid", pv: "PV", hybrid: "Hybrid" },
    unavailable: "unavailable",
    cost: "Cost",
    house: "House load",
    no_stream: "No live data",
    editor: {
      hint: "Notifications are configured in the integration – one place for backend and card.",
      settings: "Open the settings",
      title: "Title",
      layout: "Layout",
      full: "Full",
      compact: "Compact",
      show_flows: "Show the energy flow",
      show_controls: "Show the controls",
      price: "Electricity price (€/kWh)",
      pv_price: "Value of PV energy (€/kWh)",
      entities: "Entities (optional)",
      grid_power: "Grid power",
      ev_power: "Charging power",
      charge_mode: "Charge mode",
      pv_quota: "PV quota",
      wallbox_status: "Wallbox status",
      session_duration: "Session duration",
      session_energy: "Session energy",
      pv_power: "PV power (external)",
      description:
        "Animated energy flow for ABL eMS Home wallbox control (grid, charging, mode, PV quota).",
    },
  },
};

const ICONS = {
  flash: "M11,15H6L13,1V9H18L11,23V15Z",
  home: "M10,20V14H14V20H19V12H22L12,3L2,12H5V20H10Z",
  car:
    "M18.92,6.01C18.72,5.42 18.16,5 17.5,5H6.5C5.84,5 5.28,5.42 5.08,6.01L3,12V20C3,20.55 3.45,21 4,21H5C5.55,21 6,20.55 6,20V19H18V20C18,20.55 18.45,21 19,21H20C20.55,21 21,20.55 21,20V12L18.92,6.01M6.85,7H17.14L18.43,11H5.57L6.85,7M6.5,16C5.67,16 5,15.33 5,14.5C5,13.67 5.67,13 6.5,13C7.33,13 8,13.67 8,14.5C8,15.33 7.33,16 6.5,16M17.5,16C16.67,16 16,15.33 16,14.5C16,13.67 16.67,13 17.5,13C18.33,13 19,13.67 19,14.5C19,15.33 18.33,16 17.5,16Z",
  lock:
    "M12,17A2,2 0 0,0 14,15C14,13.89 13.1,13 12,13A2,2 0 0,0 10,15A2,2 0 0,0 12,17M18,8A2,2 0 0,1 20,10V20A2,2 0 0,1 18,22H6A2,2 0 0,1 4,20V10C4,8.89 4.9,8 6,8H7V6A5,5 0 0,1 12,1A5,5 0 0,1 17,6V8H18M12,3A3,3 0 0,0 9,6V8H15V6A3,3 0 0,0 12,3Z",
  plug:
    "M16,7V3H14V7H10V3H8V7H8C7.45,7 7,7.45 7,8V14.5L11,18.5V22H13V18.5L17,14.5V8C17,7.45 16.55,7 16,7Z",
  sun:
    "M12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,2L14.39,5.42C13.65,5.15 12.84,5 12,5C11.16,5 10.35,5.15 9.61,5.42L12,2M3.34,7L7.5,6.65C6.9,7.16 6.36,7.78 5.94,8.5C5.5,9.24 5.25,10 5.11,10.79L3.34,7M3.36,17L5.12,13.23C5.26,14 5.53,14.78 5.95,15.5C6.37,16.24 6.91,16.86 7.5,17.37L3.36,17M20.65,7L18.88,10.79C18.74,10 18.47,9.23 18.05,8.5C17.63,7.78 17.1,7.15 16.5,6.64L20.65,7M20.64,17L16.5,17.36C17.09,16.85 17.62,16.22 18.04,15.5C18.46,14.77 18.73,14 18.87,13.21L20.64,17M12,22L9.59,18.56C10.33,18.83 11.14,19 12,19C12.82,19 13.63,18.83 14.37,18.56L12,22Z",
  meter:
    "M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2M12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4M12,6A6,6 0 0,1 18,12A6,6 0 0,1 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6M12,8A4,4 0 0,0 8,12A4,4 0 0,0 12,16A4,4 0 0,0 16,12A4,4 0 0,0 12,8Z",
  timer:
    "M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12.5,7H11V13L15.25,15.5L16,14.25L12.5,12.25V7Z",
  euro:
    "M15,18.5C12.5,18.5 10.5,16.5 10.5,14H15V12H10.5C10.5,9.5 12.5,7.5 15,7.5C15.9,7.5 16.7,7.7 17.5,8.1L18.5,6.4C17.4,5.8 16.2,5.5 15,5.5C11.4,5.5 8.5,8.4 8.5,12H6V14H8.5C8.5,17.6 11.4,20.5 15,20.5C16.2,20.5 17.4,20.2 18.5,19.6L17.5,17.9C16.7,18.3 15.9,18.5 15,18.5Z",
};

// stroke-based glyphs (used where a filled MDI path would be too busy at small size)
const GLYPHS = {
  pylon: '<path d="M12 3.2 6.3 20.8M12 3.2 17.7 20.8M8.6 13.4h6.8M9.6 9.4h4.8" stroke="currentColor" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
};

const MODE_COLORS = {
  lock: "#94a3b8",
  grid: "#f59e0b",
  pv: "#22c55e",
  hybrid: "#38bdf8",
};

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const num = (stateObj, fallback = 0) => {
  if (!stateObj) return fallback;
  const value = Number.parseFloat(stateObj.state);
  return Number.isFinite(value) ? value : fallback;
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

/** Strings for a Home Assistant language, with German as the fallback. */
const strings = (hass) => {
  const locale = (hass?.locale?.language || hass?.language || "en").slice(0, 2);
  return STRINGS[locale] || STRINGS.en;
};

//: Below this the wallbox is not charging – it reports 0,11–0,27 kW samples while
//: plugged in. The integration uses the same gate for its counters.
const NOISE_FLOOR_KW = 0.35;

//: Wallbox states in which a car is physically connected.
// The names the integration reports (they follow the ABL e-mobility app).
const PLUGGED_STATES = [
  "finished", "probing", "charging", "paused", "paused_manual", "paused_external",
];

//: Grid power is refreshed at most every 5 s – faster feels restless on a wall.
const GRID_REFRESH_MS = 5000;
const IMPORT_COLOUR = "#f59e0b";
const EXPORT_COLOUR = "#22c55e";
const CAR_COLOUR = "#38bdf8";

/* ------------------------------------------------------------------ */
/* Card                                                                */
/* ------------------------------------------------------------------ */

class EmsHomeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { ...DEFAULTS };
    this._hass = null;
    this._signature = "";
    this._entities = {};
    this._quotaTimer = null;
    this._built = false;
  }

  /* -- Lovelace API -------------------------------------------------- */

  static async getConfigElement() {
    return document.createElement("ems-home-card-editor");
  }

  static getStubConfig(hass) {
    return {
      type: "custom:ems-home-card",
      title: "eMS Home",
      layout: "full",
      show_controls: true,
    };
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = { ...DEFAULTS, ...config };
    this._entities = {};
    this._built = false;
    this._signature = "";
    if (this._hass) this._render();
  }

  getCardSize() {
    return this._config.layout === "compact" ? 3 : 6;
  }

  getGridOptions() {
    return {
      columns: this._config.layout === "compact" ? 6 : 12,
      min_columns: 4,
      rows: "auto",
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._render();
      return;
    }
    // A full re-render restarts every CSS animation and replaces the buttons
    // under the cursor – that is what made the flow flicker and swallowed clicks
    // between mousedown and mouseup. So: rebuild only when the structure really
    // changes, otherwise patch the values in place.
    // The card is often built before the state machine has delivered its states.
    // The cached entity map then stays empty and the card shows zeros forever,
    // because the structure signature never changes on its own.
    if (this._entitiesIncomplete()) {
      const fresh = this._resolveEntities();
      if (Object.keys(fresh).some((key) => fresh[key] && fresh[key] !== this._entities[key])) {
        this._entities = fresh;
        this._render();
        return;
      }
    }

    const structure = this._structureSignature();
    if (structure !== this._signature) {
      this._signature = structure;
      this._render();
      return;
    }
    this._updateValues();
  }

  /* -- entity discovery ---------------------------------------------- */

  _resolveEntities() {
    const configured = this._config.entities || {};
    const states = this._hass?.states || {};
    const registry = this._hass?.entities || {};

    // `domain` matters: there is both a sensor and a select called charge_mode,
    // and picking the sensor made the mode buttons call the wrong service.
    const roles = {
      grid_power: { domain: "sensor", unique: "_grid_power_total", key: "grid_power", names: ["grid_power", "netzleistung"] },
      grid_export: { domain: "sensor", unique: "_grid_power_export", key: "grid_power_export", names: ["grid_power_export", "einspeiseleistung"] },
      ev_power: { domain: "sensor", unique: "_ev_charging_power_total", key: "ev_charging_power", names: ["ev_charging_power", "ladeleistung"] },
      ev_state: { domain: "sensor", unique: "_ev_charging_state", key: "ev_charging_state", names: ["ev_charging_state", "ladezustand"] },
      charge_mode: { domain: "select", unique: "_charge_mode_select", key: "charge_mode", names: ["charge_mode", "lademodus"] },
      pv_quota: { domain: "number", unique: "_pv_quota_number", key: "pv_quota", names: ["pv_power_quota", "pv_quote"] },
      wallbox_status: { domain: "sensor", unique: "_evse_status", key: "evse_status", names: ["wallbox_status"] },
      session_duration: { domain: "sensor", unique: "_evse_session_duration", key: "evse_session_duration", names: ["charging_session_duration", "ladedauer"] },
      session_energy: { domain: "sensor", unique: "_evse_session_energy", key: "evse_session_energy", names: ["session_energy", "ladeenergie"] },
      energy_import: { domain: "sensor", unique: "_grid_energy_import", names: ["grid_energy_import", "energiebezug"] },
      energy_export: { domain: "sensor", unique: "_grid_energy_export", names: ["grid_energy_export", "energieeinspeisung"] },
    };

    // Explicit role mappings are authoritative (including intentional mixing).
    // Auto-discovery must stay on their device, or on the first discovered one.
    let deviceId = Object.entries(configured)
      .filter(([role, id]) => roles[role] && registry[id]?.platform === "ems_home")
      .map(([, id]) => registry[id]?.device_id).find(Boolean) || null;
    const onDevice = entry => !deviceId || entry?.device_id === deviceId;
    const resolved = {};
    for (const [role, spec] of Object.entries(roles)) {
      if (configured[role]) {
        resolved[role] = configured[role];
        continue;
      }
      resolved[role] = null;

      // 1. entity registry of our integration – independent of the device name
      //    and of the UI language, which makes this the reliable path.
      const fromRegistry = Object.values(registry).filter(
        (entry) =>
          entry &&
          entry.platform === "ems_home" &&
          onDevice(entry) &&
          entry.entity_id?.startsWith(`${spec.domain}.`) &&
          String(entry.unique_id || "").endsWith(spec.unique) &&
          states[entry.entity_id]
      );
      if (fromRegistry.length) {
        resolved[role] = fromRegistry[0].entity_id;
        deviceId ||= fromRegistry[0].device_id || null;
        continue;
      }

      // 1b. same thing via the translation key: recent Home Assistant versions
      //     hand the frontend a display entry without unique_id.
      if (spec.key) {
        const byKey = Object.values(registry).filter(
          (entry) =>
            entry &&
            entry.platform === "ems_home" &&
            onDevice(entry) &&
            entry.entity_id?.startsWith(`${spec.domain}.`) &&
            entry.translation_key === spec.key &&
            states[entry.entity_id]
        );
        if (byKey.length) {
          resolved[role] = byKey[0].entity_id;
          deviceId ||= byKey[0].device_id || null;
          continue;
        }
      }

      // 2. fall back to names, but never across domains
      const candidates = Object.keys(states).filter((id) => {
        const [domain, objectId] = id.split(".");
        if (domain !== spec.domain) return false;
        if (deviceId && !onDevice(registry[id])) return false;
        if (!objectId.includes("ems_home")) return false;
        return spec.names.some((needle) => objectId.endsWith(needle) || objectId.includes(`_${needle}`));
      });
      candidates.sort((a, b) => {
        const score = (id) => (spec.names.some((n) => id.endsWith(n)) ? 0 : 1) + id.length / 1000;
        return score(a) - score(b);
      });
      resolved[role] = candidates[0] || null;
    }

    // never let the EV or grid power point at a single phase
    if (resolved.ev_power && /_l[123]$/.test(resolved.ev_power)) resolved.ev_power = null;
    if (resolved.grid_power && /_l[123]$/.test(resolved.grid_power)) resolved.grid_power = null;

    resolved.pv_power = configured.pv_power || null;
    return resolved;
  }

  /** True while a role the card needs has no entity yet. */
  _entitiesIncomplete() {
    const e = this._entities || {};
    // pv_power/pv_price are optional (not every install has PV), so they must not
    // count – otherwise the card would re-resolve on every single update.
    const required = [
      "grid_power", "ev_power", "ev_state", "session_energy",
      "session_duration", "charge_mode", "wallbox_status",
    ];
    if (required.some((key) => !e[key])) return true;
    // Hybrid needs the quota slider; the entity can register later than the rest.
    const mode = this._currentMode(this._hass?.states || {});
    return (mode === "hybrid" || mode === "pv") && !e.pv_quota;
  }

  _structureSignature() {
    const e = this._entities;
    const st = this._hass?.states || {};
    const mode = this._currentMode(st);
    return [
      Object.keys(e).sort().map((k) => `${k}=${e[k] || ""}`).join(","),
      mode,
      this._phase(mode),
      mode === "hybrid" && Number.isFinite(num(st[e.pv_quota], NaN)) ? "quota" : "noquota",
      this._config.layout,
      this._config.title,
      this._config.show_flows === false ? "0" : "1",
      this._config.show_controls === false ? "0" : "1",
      Number.isFinite(Number.parseFloat(this._config.price)) ? "price" : "noprice",
      String(this._hass?.locale?.language || this._config.language || ""),
      String(
        this._hass?.states?.[e.session_energy]?.attributes?.price_per_kwh ?? "-"
      ),
    ].join("|");
  }

  /* -- rendering ----------------------------------------------------- */

  _t(key) {
    const table = strings(this._hass);
    return table[key] ?? STRINGS.en[key] ?? key;
  }

  _fmt(value, digits = 2) {
    if (!Number.isFinite(value)) return "–";
    const locale = this._hass?.locale?.language || "de-DE";
    try {
      return new Intl.NumberFormat(locale, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(value);
    } catch {
      return value.toFixed(digits);
    }
  }

  _render() {
    if (!this._hass) return;
    this._dragging = false;
    this._entities = this._resolveEntities();
    this._signature = this._structureSignature();
    this._built = true;
    this._gridTs = undefined; // repaint the throttled grid value immediately

    const e = this._entities;
    const st = this._hass.states;

    const mode = this._currentMode(st);
    const locked = mode === "lock" || mode === "locked";
    const phase = this._phase(mode);
    this._lastPhase = phase;
    const finished = this._isSummary(phase);
    const modeColour = MODE_COLORS[mode] || "#94a3b8";
    const compact = this._config.layout === "compact";

    // Locked or finished: nothing flows, so no animation. A finished session is
    // worth a summary instead – the figures below carry the information.
    const flow = this._config.show_flows !== false && !locked && !finished;
    const controls = this._config.show_controls !== false;
    const price = this._price();
    const showCost = price > 0 && !locked;

    if (compact) {
      this.shadowRoot.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card class="compact${locked ? " locked" : ""}">
          <div class="wrap">${this._compactTemplate({ mode, modeColour, phase, price, showCost: showCost && !locked, controls })}</div>
        </ha-card>`;
      this._attachHandlers();
      this._updateValues();
      return;
    }

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card class="${compact ? "compact" : ""}${locked ? " locked" : ""}">
        <div class="wrap">
          <header>
            <div class="brand">
              <span class="logo" style="--accent:${modeColour}">${this._icon(ICONS.flash)}</span>
              <div class="titles">
                <h1>${this._config.title}</h1>
                <span class="sub" data-bind="sub"></span>
              </div>
            </div>
            <div class="badges">
              <span class="pill" style="--accent:${modeColour}">${this._modeLabel(mode)}</span>
              <span class="status" data-bind="status"></span>
            </div>
          </header>

          ${flow ? this._flowTemplate({ mode, modeColour }) : ""}
          ${finished ? this._finishedTemplate(mode) : ""}

          ${
            locked
              ? ""
              : finished
              ? `<div class="stats">
            ${this._statTile({
              icon: ICONS.home,
              label: this._t("energy"),
              unit: "kWh",
              valueBind: "tile-energy",
            })}
            ${this._statTile({
              icon: ICONS.timer,
              label: this._t("duration"),
              unit: "min",
              valueBind: "tile-duration",
            })}
          </div>
          ${showCost ? this._resultTemplate(price) : ""}`
              : `<div class="stats">
            ${this._statTile({
              icon: ICONS.meter,
              label: this._t("grid_import"),
              unit: "kW",
              colour: IMPORT_COLOUR,
              labelBind: "tile-grid-label",
              valueBind: "tile-grid",
              iconBind: "tile-grid-icon",
            })}
            ${this._statTile({
              icon: ICONS.car,
              label: this._t("power"),
              unit: "kW",
              colour: CAR_COLOUR,
              valueBind: "tile-power",
              iconBind: "tile-power-icon",
            })}
            ${this._statTile({
              icon: ICONS.home,
              label: this._t("energy"),
              unit: "kWh",
              valueBind: "tile-energy",
            })}
            ${this._statTile({
              icon: ICONS.timer,
              label: this._t("duration"),
              unit: "min",
              valueBind: "tile-duration",
            })}
          </div>
          ${
            showCost
              ? `<div class="caption"><span data-bind="cost-label">${this._t("cost")}</span><b data-bind="cost">–</b><span class="muted">· <span data-bind="unit-price">${this._fmt(price, 2)}</span> €/kWh</span></div>
                 <div class="split"><span data-bind="split"></span><span class="saved" data-bind="saved"></span></div>`
              : ""
          }`
          }

          ${controls ? this._controlsTemplate(mode, e, st) : ""}
        </div>
      </ha-card>
    `;

    this._attachHandlers();
    this._updateValues();
  }

  _modeLabel(mode) {
    const locale = (this._hass?.locale?.language || "de").slice(0, 2);
    const table = STRINGS[locale] || STRINGS.de;
    return table.modes?.[mode] || mode;
  }

  _icon(path, cls = "") {
    return `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
  }

  /**
   * Compact layout for narrow columns.
   *
   * No flow (there is no room for it) and no 2x2 tile grid – a hero figure, one
   * row of three small values and icon-only mode buttons. The hero and the row
   * are filled by phase in _updateValues, so the same markup serves every state.
   */
  _compactTemplate({ mode, modeColour, price, showCost, controls }) {
    return `
      <header class="cmp-head">
        <div class="cmp-titles">
          <span class="cmp-title">${this._config.title}</span>
          <span class="sub" data-bind="sub"></span>
        </div>
        <div class="cmp-badges">
          <span class="pill" style="--accent:${modeColour}">${this._modeLabel(mode)}</span>
          <span class="status" data-bind="status"></span>
        </div>
      </header>

      <div class="cmp-hero">
        <span class="cmp-hero-value"><span data-bind="hero-value">–</span><small data-bind="hero-unit">kW</small></span>
        <span class="cmp-hero-label" data-bind="hero-label"></span>
      </div>

      <div class="cmp-grid">
        ${[1, 2, 3]
          .map(
            (i) => `<div class="cmp-cell" data-cell="${i}">
          <span class="cmp-label" data-bind="g${i}-label"></span>
          <b class="cmp-value" data-bind="g${i}-value"></b>
        </div>`
          )
          .join("")}
      </div>

      ${
        showCost
          ? `<div class="cmp-cost"><span data-bind="cost-label">${this._t("cost")}</span> <b data-bind="cost">–</b><span class="muted">· <span data-bind="unit-price">${this._fmt(price, 2)}</span> €/kWh</span></div>
             <div class="cmp-saved" data-bind="saved-line"></div>`
          : ""
      }

      ${controls ? this._controlsTemplate(mode, this._entities, this._hass.states, true) : ""}`;
  }

  /**
   * "heute um 14:32", "gestern um 18:05", "12.11. um 09:14" – a timestamp people
   * can place. "vor 1165 min" is arithmetic, not information.
   */
  _whenLabel(iso) {
    if (!iso) return "";
    const when = new Date(iso);
    if (Number.isNaN(when.getTime())) return "";
    const pad = (value) => String(value).padStart(2, "0");
    const time = `${pad(when.getHours())}:${pad(when.getMinutes())}`;
    // Compare calendar days, not elapsed hours: a DST switch would otherwise turn
    // "yesterday" into "today" (or the other way round).
    const midnight = new Date();
    midnight.setHours(0, 0, 0, 0);
    const thatDay = new Date(when.getFullYear(), when.getMonth(), when.getDate());
    const days = Math.round((midnight.getTime() - thatDay.getTime()) / 86400000);
    if (days === 0) return this._t("ended_today").replace("{t}", time);
    if (days === 1) return this._t("ended_yesterday").replace("{t}", time);
    const sameYear = when.getFullYear() === new Date().getFullYear();
    const date = sameYear
      ? `${pad(when.getDate())}.${pad(when.getMonth() + 1)}.`
      : `${pad(when.getDate())}.${pad(when.getMonth() + 1)}.${when.getFullYear()}`;
    return this._t("ended_date").replace("{d}", date).replace("{t}", time);
  }

  _finishedTemplate(mode) {
    const plugged = this._phase(mode) === "summary_plugged";
    return `
      <div class="ended">
        <span class="ended-icon">${this._icon(ICONS.car)}</span>
        <div class="ended-body">
          <b data-bind="ended-title">${plugged ? this._t("finished") : this._t("last_charge")}</b>
          <span>${plugged ? this._t("plugged") : ""}<em data-bind="ended">&nbsp;</em></span>
        </div>
      </div>`;
  }

  _resultTemplate(price) {
    return `
      <div class="result">
        <div class="result-row">
          <div class="result-main">
            <span class="result-label" data-bind="res-label">${this._t("cost")}</span>
            <b data-bind="res-cost">–</b>
            <span class="result-ref" data-bind="res-ref"></span>
          </div>
          <span class="result-saved" data-bind="res-saved"></span>
        </div>
        <div class="result-split" data-bind="res-split"></div>
      </div>`;
  }

  _statTile({ icon, label, value = "–", unit, colour = "var(--primary-text-color)", labelBind, valueBind, iconBind }) {
    return `
      <div class="tile">
        <span class="tile-icon"${iconBind ? ` data-bind="${iconBind}"` : ""} style="color:${colour}">${this._icon(icon)}</span>
        <div class="tile-body">
          <span class="tile-label"${labelBind ? ` data-bind="${labelBind}"` : ""}>${label}</span>
          <span class="tile-value" style="color:${colour}"><span${valueBind ? ` data-bind="${valueBind}"` : ""}>${value}</span><small>${unit}</small></span>
        </div>
      </div>`;
  }

  _flowTemplate({ mode, modeColour }) {
    // Grid: the meter is the source. PV: only surplus, so the roof alone.
    // Hybrid: both – that is the only mode where the grid joins in.
    const hybrid = mode === "hybrid";
    const solar = hybrid || mode === "pv";
    const sourceColour = solar ? "#22c55e" : IMPORT_COLOUR;
    const sourceLabel = hybrid ? this._t("pv_grid") : mode === "pv" ? this._t("pv") : this._t("grid");
    const sourceIcon = solar ? ICONS.sun : ICONS.plug;

    return `
      <div class="flow">
        <svg viewBox="0 0 420 148" class="flow-svg" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="glow-${this._uid()}" gradientUnits="userSpaceOnUse" x1="92" y1="58" x2="172" y2="58">
              <stop data-bind="stop-grid" offset="0%" stop-color="${sourceColour}" stop-opacity="0.9"/>
              <stop offset="100%" stop-color="${modeColour}" stop-opacity="0.55"/>
            </linearGradient>
            <linearGradient id="glow2-${this._uid()}" gradientUnits="userSpaceOnUse" x1="248" y1="58" x2="328" y2="58">
              <stop offset="0%" stop-color="${modeColour}" stop-opacity="0.55"/>
              <stop offset="100%" stop-color="${CAR_COLOUR}" stop-opacity="0.95"/>
            </linearGradient>
          </defs>

          <path class="rail" d="M92 58 H172"/>
          <path class="rail" d="M248 58 H328"/>

          <path data-bind="stream-grid" class="stream" d="M92 58 H172"
                style="--stroke:url(#glow-${this._uid()});--dur:3.2s"/>

          <path data-bind="stream-car" class="stream" d="M248 58 H328"
                style="--stroke:url(#glow2-${this._uid()});--dur:3.2s"/>

          <g class="node">
            <circle data-bind="source-ring" cx="62" cy="58" r="30" class="ring" style="stroke:${sourceColour}"/>
            <g data-bind="source-icon" transform="translate(48,45) scale(1.17)" fill="${sourceColour}"><path d="${sourceIcon}"/></g>
            <text x="62" y="110" class="label${solar ? " narrow" : ""}">${sourceLabel}</text>
            <text x="62" y="132" class="value"><tspan data-bind="grid-value">–</tspan><tspan class="unit"> kW</tspan></text>
          </g>

          <g class="node hub" data-bind="hub">
            <circle cx="210" cy="58" r="38" class="ring hub-ring" style="stroke:${modeColour}"/>
            <g transform="translate(194,42) scale(1.33)" fill="${modeColour}"><path d="${ICONS.flash}"/></g>
            <text x="210" y="110" class="label">${this._t("hub")}</text>
            <text x="210" y="132" class="value small" data-bind="hub-status">–</text>
          </g>

          <g class="node">
            <circle data-bind="car-ring" cx="358" cy="58" r="30" class="ring" style="stroke:var(--divider-color)"/>
            <g data-bind="car-icon" transform="translate(344,45) scale(1.17)" fill="var(--secondary-text-color)"><path d="${ICONS.car}"/></g>
            <foreignObject x="300" y="94" width="116" height="26">
              <div xmlns="http://www.w3.org/1999/xhtml" class="label car-label" data-bind="car-label">${this._t("car")}</div>
            </foreignObject>
            <text x="358" y="132" class="value"><tspan data-bind="car-value">–</tspan><tspan class="unit"> kW</tspan></text>
          </g>
        </svg>
      </div>`;
  }

  /* -- live values (no re-render) ------------------------------------- */

  _updateValues() {
    const root = this.shadowRoot;
    if (!root || !this._hass) return;
    const st = this._hass.states || {};
    const e = this._entities;
    const q = (bind) => root.querySelector(`[data-bind="${bind}"]`);
    const setText = (bind, text) => {
      const node = q(bind);
      if (node && node.textContent !== text) node.textContent = text;
    };
    const setFill = (bind, colour) => {
      const node = q(bind);
      if (node && node.style.fill !== colour) node.style.fill = colour;
    };
    const setColour = (bind, colour) => {
      const node = q(bind);
      if (node && node.style.color !== colour) node.style.color = colour;
    };

    const mode = this._currentMode(st);
    const evPower = num(st[e.ev_power]);
    const powerKnown = Number.isFinite(num(st[e.ev_power], NaN));
    // While the value is missing, keep what we know instead of claiming 0,00 kW
    // and "Bereit" – that reads like the charge ended.
    const charging = powerKnown ? evPower >= this._noiseFloor() : this._lastPhase === "charging";
    const powerText = powerKnown ? this._fmt(evPower, 2) : "–";

    // --- car side: every update, this is the number people watch
    setText("car-value", powerText);
    setFill("car-value", charging ? CAR_COLOUR : "var(--secondary-text-color)");
    setText("tile-power", powerText);
    setColour("tile-power", charging ? CAR_COLOUR : "var(--secondary-text-color)");
    setColour("tile-power-icon", charging ? CAR_COLOUR : "var(--secondary-text-color)");
    setText("tile-energy", this._fmt(num(st[e.session_energy], NaN), 1));
    setText("tile-duration", this._fmt(num(st[e.session_duration], NaN), 0));
    setText("hub-status", this._statusLabel(mode, charging));
    // the attributes are needed by the summary banner and by the compact status line
    const sessionAttrs = st[e.session_energy]?.attributes || {};
    const vehicle = [sessionAttrs.vehicle, sessionAttrs.last_vehicle]
      .find(name => typeof name === "string" && name.trim());
    const carLabel = vehicle ? vehicle.trim() : this._t("car");
    setText("car-label", carLabel);
    if (q("car-label")) q("car-label").title = carLabel;
    if (this._isSummary(this._phase(mode))) {
      const attrs = sessionAttrs;
      const since =
        attrs.last_ended_at ||
        st[e.ev_state]?.last_changed;
      const label = this._whenLabel(since);
      const prefix = this._phase(mode) === "summary_plugged" ? " · " : "";
      setText("ended", label ? prefix + label : "");

      // Which car was that? The vehicle sensor is optional – no name, no change.
      // A finished session keeps the car it was charged with: preferring the live
      // sensor would rename old data when the sensor switches cars.
      const vehicle = attrs.last_vehicle || attrs.vehicle || "";
      const title = this._phase(mode) === "summary_plugged"
        ? this._t("finished")
        : this._t("last_charge");
      setText("ended-title", vehicle ? `${vehicle} · ${title}` : title);
    }
    const compactVehicle = sessionAttrs.last_vehicle || sessionAttrs.vehicle || "";
    const subParts = [this._statusLabel(mode, charging)];
    if (compactVehicle && this._phase(mode) === "summary") subParts.push(compactVehicle);
    if (!this._isLive()) subParts.push(this._t("no_stream"));
    setText("sub", subParts.join(" · "));

    // quota slider: follow external changes, but not while the user drags it
    const range = root.getElementById?.("quota") || root.querySelector("#quota");
    if (range && root.activeElement !== range && !this._dragging) {
      const quota = num(st[e.pv_quota]);
      if (Math.abs(Number.parseFloat(range.value) - quota) > 0.001) {
        range.value = quota;
        range.style.setProperty("--fill", `${quota}%`);
        setText("quota-val", `${this._fmt(quota, 0)} %`);
      }
    }

    const carStream = q("stream-car");
    if (carStream) {
      carStream.classList.toggle("active", charging);
      carStream.style.setProperty("--dur", `${this._streamDuration(evPower)}s`);
    }
    const carRing = q("car-ring");
    if (carRing) carRing.style.stroke = charging ? CAR_COLOUR : "var(--divider-color)";
    const carIcon = q("car-icon");
    if (carIcon) carIcon.setAttribute("fill", charging ? CAR_COLOUR : "var(--secondary-text-color)");
    const hub = q("hub");
    if (hub) hub.classList.toggle("pulsing", charging);
    const status = q("status");
    if (status) status.classList.toggle("on", charging);

    // Cost: grid energy at the tariff, PV energy at pv_price (default 0 = own roof).
    // Tariff order: card config → integration option → DEFAULT_PRICE.
    const attrs = st[e.session_energy]?.attributes || {};
    const price = this._price();
    if (price > 0) {
      const gridKwh = Number.parseFloat(attrs.energy_from_grid_kwh);
      const pvKwh = Number.parseFloat(attrs.energy_from_pv_kwh);
      const splitKnown = Number.isFinite(gridKwh) && Number.isFinite(pvKwh);
      const pvPrice = Number.parseFloat(this._config.pv_price);
      const pvRate = Number.isFinite(pvPrice)
        ? pvPrice
        : Number(attrs.pv_price_per_kwh) || 0;
      setText("unit-price", this._fmt(price, 2));

      const total = splitKnown ? gridKwh + pvKwh : num(st[e.session_energy], NaN);
      const cost = splitKnown ? gridKwh * price + pvKwh * pvRate : total * price;
      // Derive the saving from the two amounts on screen, so subtracting them
      // really gives the green number (rounding used to be off by a cent).
      const r2 = (value) => Math.round(value * 100) / 100;
      const saved = splitKnown
        ? Math.max(r2(total * price) - r2(gridKwh * price + pvKwh * pvRate), 0)
        : 0;
      const label = this._t("cost_grid");
      const split = splitKnown
        ? `${this._fmt(gridKwh, 1)} kWh ${this._t("grid")} · ${this._fmt(pvKwh, 1)} kWh ${this._t("pv")}`
        : "";

      // The integration already knows what a cycle cost – use its figure unless
      // this card sets its own price, otherwise a stored session (or a changed
      // tariff) is silently recalculated.
      const storedCost = Number(attrs.cost);
      const storedSaved = Number(attrs.saved);
      const useStored =
        !Number.isFinite(Number.parseFloat(this._config.price)) &&
        !Number.isFinite(pvPrice) &&
        Number.isFinite(storedCost) &&
        storedCost >= 0 &&
        attrs.cost !== null;
      const shownCost = useStored ? storedCost : cost;
      const shownSaved = useStored
        ? Number.isFinite(storedSaved)
          ? storedSaved
          : 0
        : saved;

      if (q("res-cost")) {
        // finished session – costs are the headline
        const withoutPv = shownCost + shownSaved;
        setText("res-label", label);
        setText("res-cost", Number.isFinite(shownCost) ? this._fmt(shownCost, 2) + " €" : "–");
        setText(
          "res-ref",
          shownSaved >= 0.01 ? `${this._t("instead_of")} ${this._fmt(withoutPv, 2)} €` : ""
        );
        setText(
          "res-saved",
          shownSaved >= 0.01 ? `${this._fmt(shownSaved, 2)} € ${this._t("saved")}` : ""
        );
        setText("res-split", [split, `${this._fmt(price, 2)} €/kWh`].filter(Boolean).join(" · "));
      } else {
        setText("cost-label", label);
        setText("cost", Number.isFinite(shownCost) ? this._fmt(shownCost, 2) + " €" : "–");
        setText(
          "split",
          [split, shownSaved >= 0.01 ? `${this._t("instead_of")} ${this._fmt(shownCost + shownSaved, 2)} €` : ""]
            .filter(Boolean)
            .join(" · ")
        );
        setText(
          "saved",
          shownSaved >= 0.01 ? ` · ${this._fmt(shownSaved, 2)} € ${this._t("saved")}` : ""
        );
      }
    }

    // --- compact layout: hero + three values, chosen by phase
    if (q("hero-value")) {
      const phase = this._phase(mode);
    this._lastPhase = phase;
      const gridPower = num(st[e.grid_power], NaN);
      const energy = num(st[e.session_energy], NaN);
      const duration = num(st[e.session_duration], NaN);
      const attrs = st[e.session_energy]?.attributes || {};
      const gridKwh = Number.parseFloat(attrs.energy_from_grid_kwh);
      const pvKwh = Number.parseFloat(attrs.energy_from_pv_kwh);

      let hero;
      let cells;
      if (this._isSummary(phase)) {
        hero = { value: this._fmt(energy, 1), unit: "kWh", label: this._t("energy") };
        cells = [
          { label: this._t("duration"), value: `${this._fmt(duration, 0)} min` },
          Number.isFinite(gridKwh)
            ? { label: this._t("grid"), value: `${this._fmt(gridKwh, 1)} kWh` }
            : null,
          Number.isFinite(pvKwh) ? { label: this._t("pv"), value: `${this._fmt(pvKwh, 1)} kWh` } : null,
        ];
      } else if (phase === "idle") {
        hero = { value: this._fmt(Math.abs(gridPower), 2), unit: "kW", label: this._t("grid_import") };
        cells = [
          { label: this._t("energy"), value: `${this._fmt(energy, 1)} kWh` },
          { label: this._t("duration"), value: `${this._fmt(duration, 0)} min` },
          null,
        ];
      } else {
        hero = { value: powerText, unit: "kW", label: this._t("power") };
        cells = [
          {
            label: gridPower < -0.05 ? this._t("export") : this._t("grid_import"),
            value: `${this._fmt(Math.abs(gridPower), 2)} kW`,
          },
          { label: this._t("energy"), value: `${this._fmt(energy, 1)} kWh` },
          { label: this._t("duration"), value: `${this._fmt(duration, 0)} min` },
        ];
      }

      setText("hero-value", hero.value);
      setText("hero-unit", hero.unit);
      setText("hero-label", hero.label);
      cells.forEach((cell, index) => {
        const node = root.querySelector(`[data-cell="${index + 1}"]`);
        setText(`g${index + 1}-label`, cell ? cell.label : "");
        setText(`g${index + 1}-value`, cell ? cell.value : "");
        if (node) node.classList.toggle("off", !cell);
      });
      const priceCfg = this._price();
      if (priceCfg > 0 && Number.isFinite(pvKwh)) {
        const pvRateCfg = Number.parseFloat(this._config.pv_price);
        const pvRate = Number.isFinite(pvRateCfg)
          ? pvRateCfg
          : Number(attrs.pv_price_per_kwh) || 0;
        const saved = pvKwh * Math.max(priceCfg - pvRate, 0);
        setText("saved-line", saved >= 0.01 ? `${this._fmt(saved, 2)} € ${this._t("saved")}` : "");
      }
    }

    // --- grid side: throttled, otherwise the card feels restless
    const now = Date.now();
    if (this._gridTs === undefined || now - this._gridTs >= GRID_REFRESH_MS) {
      this._gridTs = now;
      const gridPower = num(st[e.grid_power], NaN);
      const exporting = gridPower < -0.05;
      const colour = exporting ? EXPORT_COLOUR : IMPORT_COLOUR;

      setText("grid-value", this._fmt(Math.abs(gridPower), 2));
      setFill("grid-value", colour);
      setText("tile-grid-label", exporting ? this._t("export") : this._t("grid_import"));
      setText("tile-grid", this._fmt(Math.abs(gridPower), 2));
      setColour("tile-grid", colour);
      setColour("tile-grid-icon", colour);
      const stop = q("stop-grid");
      if (stop) stop.setAttribute("stop-color", colour);
      const ring = q("source-ring");
      if (ring && mode !== "pv" && mode !== "hybrid") ring.style.stroke = colour;
      const icon = q("source-icon");
      if (icon && mode !== "pv" && mode !== "hybrid") icon.setAttribute("fill", colour);

      const gridStream = q("stream-grid");
      if (gridStream) {
        gridStream.classList.toggle("active", Math.abs(gridPower) > 0.05);
        gridStream.style.setProperty("--dur", `${this._streamDuration(Math.abs(gridPower))}s`);
        gridStream.style.animationDirection = exporting ? "reverse" : "normal";
      }
    }
  }

  /**
   * Which face the card shows.
   *
   * locked  – mode is lock
   * charging – the car is drawing power
   * summary  – not charging, but there is a session to report: the figures of the
   *            last charge, whether the car is still plugged in or already gone
   * live     – nothing to report, show what the house is doing
   */
  _phase(mode) {
    const st = this._hass?.states || {};
    const e = this._entities;
    if (mode === "lock" || mode === "locked") return "locked";
    // No fresh reading is not the same as "nothing is charging": keep the face we
    // had instead of announcing the end of a charge that may still be running.
    const powerKnown = Number.isFinite(num(st[e.ev_power], NaN));
    if (!powerKnown) {
      return this._lastPhase || "live";
    }
    let phase = "live";
    if (num(st[e.ev_power]) >= this._noiseFloor()) {
      phase = "charging";
    } else if (this._hasSession()) {
      const status = st[e.wallbox_status]?.state || "";
      phase = PLUGGED_STATES.includes(status) ? "summary_plugged" : "summary";
    }
    if (powerKnown) this._lastPhase = phase;
    return phase;
  }

  /** Power above which the car counts as charging (from the integration if known). */
  _noiseFloor() {
    const attrs = this._hass?.states?.[this._entities.session_energy]?.attributes || {};
    const value = Number(attrs.noise_floor_kw);
    return Number.isFinite(value) && value > 0 ? value : NOISE_FLOOR_KW;
  }

  /** Is there a (finished) charge worth reporting? */
  _hasSession() {
    const st = this._hass?.states || {};
    const e = this._entities;
    const attrs = st[e.session_energy]?.attributes || {};
    const lastEnergy = Number.parseFloat(attrs.last_energy_kwh);
    return (
      num(st[e.session_energy]) > 0.05 ||
      num(st[e.session_duration]) > 0.5 ||
      (Number.isFinite(lastEnergy) && lastEnergy > 0)
    );
  }

  _isSummary(phase) {
    return phase === "summary" || phase === "summary_plugged";
  }

  _isLive() {
    const st = this._hass?.states || {};
    const grid = st[this._entities.grid_power];
    return Boolean(grid) && grid.state !== "unavailable" && grid.state !== "unknown";
  }

  /** Tariff for the cost line: card config, then integration option, then default. */
  _price() {
    const configured = this._config.price;
    const numeric = Number.parseFloat(configured);
    if (Number.isFinite(numeric)) return numeric;         // explicit, 0 disables it
    const attrs = this._hass?.states?.[this._entities.session_energy]?.attributes;
    if (attrs && "price_per_kwh" in attrs) {
      // The integration reports the tariff it uses – null means "off".
      return Number(attrs.price_per_kwh) || 0;
    }
    return DEFAULT_PRICE;
  }

  /** Slower, calmer flow: ~3.2 s idle down to 1.6 s at full power. */
  _streamDuration(power) {
    return clamp(3.2 - Math.min(Math.abs(power) || 0, 11) * 0.14, 1.6, 3.2).toFixed(2);
  }

  _iconPath(path, scale = 1.17) {
    return `<path d="${path}" transform="scale(${scale})"/>`;
  }

  _statusLabel(mode, charging) {
    if (mode === "lock" || mode === "locked") return this._t("locked");
    if (charging) return this._t("charging");
    const phase = this._phase(mode);
    this._lastPhase = phase;
    if (phase === "summary_plugged") return this._t("finished");
    if (phase === "summary") return this._t("last_charge");
    return this._t("idle");
  }

  _controlsTemplate(mode, e, st, compact = false) {
    const quotaEntity = st[e.pv_quota];
    const quota = quotaEntity ? num(quotaEntity) : 0;
    const step = Number(quotaEntity?.attributes?.step) || 10;
    this._quotaStep = step;
    const quotaAvailable = Number.isFinite(num(quotaEntity, NaN));
    const modes = ["lock", "grid", "pv", "hybrid"];

    return `
      <div class="controls">
        <div class="segmented" role="group" aria-label="${this._t("mode")}">
          ${modes
            .map(
              (m) => `
            <button data-mode="${m}" class="${mode === m ? "sel" : ""}" style="--accent:${MODE_COLORS[m]}"
                    title="${this._modeLabel(m)}" aria-label="${this._modeLabel(m)}"
                    ${st[e.charge_mode] ? "" : "disabled"}>
              ${this._icon(MODE_ICONS[m] || ICONS.flash)}
              ${compact ? "" : `<span>${this._modeLabel(m)}</span>`}
            </button>`
            )
            .join("")}
        </div>

        ${
          // The quota only applies to hybrid charging – showing it in the other
          // modes was noise.
          quotaAvailable && mode === "hybrid"
            ? `<div class="quota">
                 <div class="quota-head">
                   <span>${this._t("pv_quota")}</span>
                   <b id="quota-val">${this._fmt(quota, 0)} %</b>
                 </div>
                 <input id="quota" type="range" min="0" max="100" step="${step}" value="${quota}" style="--fill:${quota}%" />
               </div>`
            : ""
        }
      </div>`;
  }

  /**
   * The mode to show. A click is reflected immediately: the device takes a
   * moment (and sometimes several seconds) to confirm, and waiting for the next
   * poll made the buttons feel broken.
   */
  _currentMode(st) {
    const observed =
      st[this._entities.charge_mode]?.state || st[this._entities.ev_state]?.state || "unknown";
    if (this._pendingMode) {
      if (observed === this._pendingMode) {
        this._pendingMode = null;
        // The structure depends on the mode (PV slider, tiles), so rebuild on
        // the next update instead of only patching values.
        this._signature = null;
      } else {
        return this._pendingMode;
      }
    }
    return observed;
  }

  _attachHandlers() {
    this.shadowRoot.querySelectorAll("button[data-mode]").forEach((button) => {
      button.addEventListener("click", () => this._setMode(button.dataset.mode, button));
    });

    const range = this.shadowRoot.getElementById("quota");
    if (range) {
      const label = this.shadowRoot.getElementById("quota-val");
      range.addEventListener("pointerdown", () => { this._dragging = true; });
      range.addEventListener("pointerup", () => { this._dragging = false; });
      // A cancelled drag (touch scroll, lost pointer) used to leave _dragging set,
      // and the slider then ignored every external value for good.
      range.addEventListener("pointercancel", () => { this._dragging = false; });
      range.addEventListener("pointerleave", () => {
        if (!range.matches(":active")) this._dragging = false;
      });
      range.addEventListener("input", () => {
        const value = Number.parseFloat(range.value);
        if (label) label.textContent = `${this._fmt(value, 0)} %`;
        range.style.setProperty("--fill", `${value}%`);
      });
      range.addEventListener("change", () => {
        const value = Number.parseFloat(range.value);
        clearTimeout(this._quotaTimer);
        this._quotaTimer = setTimeout(() => this._setQuota(value), 250);
      });
    }
  }

  _paintMode(mode) {
    const colour = MODE_COLORS[mode] || "#94a3b8";
    this.shadowRoot.querySelectorAll("button[data-mode]").forEach((btn) => {
      btn.classList.toggle("sel", btn.dataset.mode === mode);
    });
    const pill = this.shadowRoot.querySelector(".pill");
    if (pill) {
      pill.style.setProperty("--accent", colour);
      pill.textContent = this._modeLabel(mode);
    }
    this.shadowRoot.querySelectorAll(".logo").forEach((logo) => {
      logo.style.setProperty("--accent", colour);
    });
  }

  _setMode(mode, button) {
    const entity = this._entities.charge_mode;
    if (!entity || !this._hass) return;
    if (this._hass.states?.[entity]?.state === mode) return;

    // The device needs a moment; show the choice right away.
    this._pendingMode = mode;
    if (button) {
      button.classList.add("pending");
      setTimeout(() => button.classList.remove("pending"), 4000);
    }
    // Show the choice before the device answers – it can take seconds. The
    // signature is refreshed too, so the next update patches values instead of
    // rebuilding the card and swapping the buttons under the pointer.
    this._paintMode(mode);
    this._signature = this._structureSignature();

    clearTimeout(this._modeTimer);
    this._modeTimer = setTimeout(() => {
      if (!this._pendingMode) return;
      this._pendingMode = null;
      if (this._hass) this._render();
    }, 20000);

    this._hass.callService("select", "select_option", {
      entity_id: entity,
      option: mode,
    });
  }

  disconnectedCallback() {
    clearTimeout(this._quotaTimer);
    clearTimeout(this._modeTimer);
    this._pendingMode = null;
    this._dragging = false;
    this._signature = null;
  }

  _setQuota(value) {
    const entity = this._entities.pv_quota;
    if (!entity || !this._hass) return;
    // keep to the step the entity offers – the firmware drops anything between
    const step = this._quotaStep || 10;
    const rounded = Math.round(value / step) * step;
    this._hass.callService("number", "set_value", {
      entity_id: entity,
      value: rounded,
    });
  }

  _uid() {
    if (!this.__uid) this.__uid = Math.random().toString(36).slice(2, 8);
    return this.__uid;
  }

  _styles() {
    return `
      :host { display: block; }
      ha-card {
        background: var(--ha-card-background, var(--card-background-color, #1c1c1e));
        border-radius: var(--ha-card-border-radius, 20px);
        border: 1px solid var(--ha-card-border-color, var(--divider-color, rgba(255,255,255,.08)));
        overflow: hidden;
      }
      .wrap {
        padding: 18px 18px 16px;
        background:
          radial-gradient(120% 120% at 0% 0%, rgba(56,189,248,.10), transparent 55%),
          radial-gradient(100% 100% at 100% 0%, rgba(34,197,94,.08), transparent 60%);
      }
      header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
      .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
      .logo {
        width: 38px; height: 38px; flex: 0 0 38px;
        display: grid; place-items: center; border-radius: 12px;
        background: color-mix(in srgb, var(--accent) 18%, transparent);
        border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
      }
      .logo svg { width: 20px; height: 20px; fill: var(--accent); }
      .titles { min-width: 0; }
      h1 {
        margin: 0; font-size: 1.05rem; font-weight: 600; letter-spacing: .2px;
        color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .sub { font-size: .78rem; color: var(--secondary-text-color); }
      .sub em { font-style: normal; color: var(--warning-color, #f59e0b); }
      .badges { display: flex; align-items: center; gap: 10px; }
      .pill {
        font-size: .72rem; font-weight: 600; letter-spacing: .4px; text-transform: uppercase;
        padding: 5px 11px; border-radius: 999px;
        color: var(--accent);
        background: color-mix(in srgb, var(--accent) 14%, transparent);
        border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
      }
      .status {
        width: 9px; height: 9px; border-radius: 50%;
        background: var(--disabled-text-color, #6b7280); box-shadow: 0 0 0 0 rgba(56,189,248,.6);
      }
      .status.on { background: #38bdf8; animation: halo 1.8s ease-out infinite; }
      @keyframes halo {
        0% { box-shadow: 0 0 0 0 rgba(56,189,248,.55); }
        70% { box-shadow: 0 0 0 10px rgba(56,189,248,0); }
        100% { box-shadow: 0 0 0 0 rgba(56,189,248,0); }
      }

      .flow { margin: 8px -4px 2px; }
      .flow-svg { width: 100%; height: auto; display: block; overflow: visible; }
      .rail { fill: none; stroke: var(--divider-color, rgba(255,255,255,.12)); stroke-width: 3; stroke-linecap: round; opacity: .8; }
      .stream {
        fill: none; stroke: var(--stroke); stroke-width: 6; stroke-linecap: round;
        stroke-dasharray: 2 16; opacity: 0;
      }
      .stream.active {
        opacity: 1;
        animation: flow var(--dur, 3.2s) linear infinite;
        filter: drop-shadow(0 0 4px currentColor);
      }
      /* dash period is 18px – the offset must be a multiple of it to loop seamlessly */
      @keyframes flow { to { stroke-dashoffset: -72; } }

      .node .ring {
        fill: none;
        stroke-width: 2;
        opacity: .85;
      }
      .node .label {
        font-size: 12px; font-weight: 600; text-anchor: middle;
        fill: color-mix(in srgb, var(--primary-text-color) 68%, transparent);
      }
      .node .car-label {
        color: color-mix(in srgb, var(--primary-text-color) 68%, transparent);
        text-align: center; line-height: 13px; overflow-wrap: anywhere;
        display: -webkit-box; -webkit-box-orient: vertical;
        -webkit-line-clamp: 2; overflow: hidden;
      }
      .node .label.narrow { font-size: 10.5px; letter-spacing: -.2px; }
      .node .value { font-size: 15px; font-weight: 700; text-anchor: middle; fill: var(--primary-text-color); }
      .node .value.small { font-size: 12px; font-weight: 600; fill: var(--secondary-text-color); }
      .node .unit { font-size: 10px; font-weight: 500; opacity: .75; }
      .hub-ring { stroke-width: 3; }
      .hub.pulsing .hub-ring { animation: pulse 2.2s ease-in-out infinite; transform-origin: 210px 58px; }
      @keyframes pulse {
        0%, 100% { opacity: .55; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.06); }
      }

      .stats {
        display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px; margin-top: 6px;
      }
      .caption {
        display: flex; align-items: baseline; gap: 6px; justify-content: flex-end;
        margin-top: 8px; font-size: .74rem; color: var(--secondary-text-color);
      }
      .caption b { color: var(--primary-text-color); font-size: .86rem; }
      .caption .muted { opacity: .6; }
      .split {
        margin-top: 2px; text-align: right; font-size: .68rem;
        color: var(--secondary-text-color); opacity: .9;
      }
      .split .saved { color: #22c55e; font-weight: 600; }

      .result {
        margin-top: 10px; padding: 13px 15px; border-radius: 16px;
        background: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
        border: 1px solid color-mix(in srgb, var(--primary-text-color) 8%, transparent);
      }
      .result-row { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
      .result-label {
        display: block; font-size: .64rem; text-transform: uppercase; letter-spacing: .5px;
        color: var(--secondary-text-color);
      }
      .ended-body b { display: block; }
      .result-ref { font-size: .78rem; font-weight: 550; color: var(--secondary-text-color); margin-left: .45rem; }
      .result-main b { font-size: 1.45rem; font-weight: 700; letter-spacing: -.4px; color: var(--primary-text-color); }
      .result-saved { font-size: .84rem; font-weight: 650; color: #22c55e; white-space: nowrap; }
      .result-split { margin-top: 5px; font-size: .7rem; color: var(--secondary-text-color); }
      .glyph { transform-box: fill-box; }
      .tile {
        display: flex; align-items: center; gap: 8px; min-width: 0;
        padding: 9px 9px; border-radius: 14px;
        background: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
        border: 1px solid color-mix(in srgb, var(--primary-text-color) 7%, transparent);
      }
      .tile-icon svg { width: 17px; height: 17px; fill: currentColor; }
      .tile-body { display: flex; flex-direction: column; min-width: 0; }
      .tile-label {
        font-size: .62rem; text-transform: uppercase; letter-spacing: .4px;
        color: color-mix(in srgb, var(--primary-text-color) 62%, transparent);
        white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis;
      }
      .tile-value { font-size: 1.02rem; font-weight: 650; line-height: 1.15; }
      .tile-value small { font-size: .62rem; font-weight: 500; margin-left: 3px; opacity: .65; }

      .controls { margin-top: 14px; display: flex; flex-direction: column; gap: 12px; }
      .segmented {
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px;
        background: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
        padding: 5px; border-radius: 14px;
      }
      .segmented button {
        display: flex; align-items: center; justify-content: center; gap: 6px;
        padding: 9px 6px; border: 0; border-radius: 10px; cursor: pointer;
        background: transparent; color: var(--secondary-text-color);
        font: inherit; font-size: .78rem; font-weight: 600;
        transition: background .18s ease, color .18s ease, transform .12s ease;
      }
      .segmented button svg { width: 16px; height: 16px; fill: currentColor; }
      .segmented button:hover:not(:disabled) { color: var(--primary-text-color); }
      .segmented button:active:not(:disabled) { transform: scale(.97); }
      .segmented button.sel {
        color: var(--accent);
        background: color-mix(in srgb, var(--accent) 16%, var(--ha-card-background, #1c1c1e));
        box-shadow: 0 2px 10px color-mix(in srgb, var(--accent) 22%, transparent);
      }
      .segmented button:disabled { opacity: .4; cursor: default; }
      .segmented button.pending { opacity: .65; }

      .quota { transition: opacity .2s ease; }
      .quota.dim { opacity: .55; }
      .quota-head {
        display: flex; justify-content: space-between; align-items: baseline;
        font-size: .74rem; color: var(--secondary-text-color); margin-bottom: 2px;
      }
      .quota-head b { color: var(--primary-text-color); font-size: .85rem; }
      input[type="range"] {
        -webkit-appearance: none; appearance: none; width: 100%; height: 6px; border-radius: 999px;
        background: linear-gradient(90deg, #22c55e 0%, #22c55e var(--fill, 0%), var(--divider-color, #3f3f46) var(--fill, 0%));
        outline: none; cursor: pointer;
      }
      input[type="range"]::-webkit-slider-thumb {
        -webkit-appearance: none; width: 17px; height: 17px; border-radius: 50%;
        background: #22c55e; border: 3px solid var(--ha-card-background, #1c1c1e);
        box-shadow: 0 0 0 3px color-mix(in srgb, #22c55e 25%, transparent);
      }
      input[type="range"]::-moz-range-thumb {
        width: 14px; height: 14px; border-radius: 50%; background: #22c55e; border: 3px solid var(--ha-card-background, #1c1c1e);
      }

      .ended {
        display: flex; align-items: center; gap: 11px;
        margin: 12px 0 10px; padding: 12px 13px; border-radius: 14px;
        background: color-mix(in srgb, #22c55e 9%, transparent);
        border: 1px solid color-mix(in srgb, #22c55e 26%, transparent);
      }
      .ended-icon svg { width: 22px; height: 22px; fill: #22c55e; }
      .ended-body { display: flex; flex-direction: column; min-width: 0; }
      .ended-body b { font-size: .84rem; font-weight: 650; color: var(--primary-text-color); }
      .ended-body span { font-size: .73rem; color: var(--secondary-text-color); }
      .ended-body em { font-style: normal; }

      .locked .stats, .locked .flow { display: none; }
      .locked .wrap { padding-bottom: 18px; }
      /* ---- compact layout: vertical, no flow, no 2x2 grid ---- */
      .compact .wrap { padding: 14px; }
      .compact .flow { display: none; }
      .cmp-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
      .cmp-titles { min-width: 0; display: flex; flex-direction: column; }
      .cmp-title {
        font-size: .95rem; font-weight: 600; color: var(--primary-text-color);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .cmp-head .sub { font-size: .72rem; }
      .cmp-badges { display: flex; align-items: center; gap: 7px; flex: 0 0 auto; }
      .cmp-badges .pill { font-size: .64rem; padding: 4px 8px; }

      .cmp-hero { display: flex; flex-direction: column; margin: 12px 0 10px; }
      .cmp-hero-value {
        font-size: 1.85rem; font-weight: 700; line-height: 1.05; letter-spacing: -.6px;
        color: var(--primary-text-color);
      }
      .cmp-hero-value small { font-size: .78rem; font-weight: 500; margin-left: 4px; opacity: .6; }
      .cmp-hero-label {
        font-size: .64rem; text-transform: uppercase; letter-spacing: .5px;
        color: var(--secondary-text-color); margin-top: 2px;
      }

      .cmp-grid {
        display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px; padding-top: 10px;
        border-top: 1px solid color-mix(in srgb, var(--primary-text-color) 8%, transparent);
      }
      .cmp-cell { display: flex; flex-direction: column; min-width: 0; }
      .cmp-cell.off { display: none; }
      .cmp-label {
        font-size: .58rem; text-transform: uppercase; letter-spacing: .4px;
        color: var(--secondary-text-color); white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis;
      }
      .cmp-value { font-size: .88rem; font-weight: 650; color: var(--primary-text-color); white-space: nowrap; }

      .cmp-cost {
        margin-top: 10px; font-size: .72rem; color: var(--secondary-text-color);
        display: flex; align-items: baseline; gap: 5px; flex-wrap: wrap;
      }
      .cmp-cost b { color: var(--primary-text-color); font-size: .82rem; }
      .cmp-cost .muted { opacity: .6; }
      .cmp-saved { font-size: .7rem; font-weight: 600; color: #22c55e; }
      .cmp-saved:empty { display: none; }

      .compact .segmented { grid-template-columns: repeat(4, 1fr); gap: 5px; padding: 4px; margin-top: 12px; }
      .compact .segmented button { padding: 9px 4px; }
      .compact .segmented button span { display: none; }
      .compact .segmented button svg { width: 17px; height: 17px; }
      .compact .quota { margin-top: 10px; }
      .compact .quota-head { font-size: .68rem; }

      @media (max-width: 420px) {
        .segmented button span { display: none; }
      }
    `;
  }
}

const MODE_ICONS = {
  lock: ICONS.lock,
  grid: ICONS.plug,
  pv: ICONS.sun,
  hybrid: ICONS.flash,
};

/* ------------------------------------------------------------------ */
/* Visual editor                                                       */
/* ------------------------------------------------------------------ */

class EmsHomeCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  _t(key) {
    return strings(this._hass).editor?.[key] ?? key;
  }

  _schema() {
    return [
      { name: "title", selector: { text: {} } },
      {
        name: "layout",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "full", label: this._t("full") },
              { value: "compact", label: this._t("compact") },
            ],
          },
        },
      },
      { name: "show_flows", selector: { boolean: {} } },
      { name: "show_controls", selector: { boolean: {} } },
      {
        name: "price",
        default: DEFAULT_PRICE,
        selector: { number: { min: 0, max: 5, step: 0.01, mode: "box" } },
      },
      { name: "pv_price", selector: { number: { min: 0, max: 5, step: 0.01, mode: "box" } } },
      {
        name: "entities",
        type: "expandable",
        schema: [
          { name: "grid_power", selector: { entity: { domain: "sensor" } } },
          { name: "ev_power", selector: { entity: { domain: "sensor" } } },
          { name: "charge_mode", selector: { entity: { domain: "select" } } },
          { name: "pv_quota", selector: { entity: { domain: "number" } } },
          { name: "wallbox_status", selector: { entity: { domain: "sensor" } } },
          { name: "session_duration", selector: { entity: { domain: "sensor" } } },
          { name: "session_energy", selector: { entity: { domain: "sensor" } } },
        ],
      },
    ];
  }

  _render() {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = `
      <style>
        ha-form { display: block; padding: 4px 0; }
        .hint {
          display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
          margin-top: 10px; padding-top: 10px;
          border-top: 1px solid var(--divider-color);
          font-size: .8rem; line-height: 1.35; color: var(--secondary-text-color);
        }
        .hint a { color: var(--primary-color); font-weight: 600; text-decoration: none; }
        .hint a:hover { text-decoration: underline; }
      </style>
      <ha-form></ha-form>
      <div class="hint">
        <span>${this._t("hint")}</span>
        <a href="/config/integrations/integration/ems_home" target="_top">${this._t("settings")}</a>
      </div>
    `;
    const form = this.shadowRoot.querySelector("ha-form");
    form.hass = this._hass;
    form.data = this._config;
    form.schema = this._schema();
    form.computeLabel = (schema) => this._t(schema.name);
    form.addEventListener("value-changed", (ev) => {
      ev.stopPropagation();
      this._config = { ...this._config, ...ev.detail.value };
      this.dispatchEvent(
        new CustomEvent("config-changed", {
          detail: { config: this._config },
          bubbles: true,
          composed: true,
        })
      );
    });
    this._form = form;
  }
}

/* ------------------------------------------------------------------ */
/* Registration                                                        */
/* ------------------------------------------------------------------ */

if (!customElements.get("ems-home-card")) {
  customElements.define("ems-home-card", EmsHomeCard);
}
if (!customElements.get("ems-home-card-editor")) {
  customElements.define("ems-home-card-editor", EmsHomeCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "ems-home-card")) {
  window.customCards.push({
    type: "ems-home-card",
    name: "eMS Home Card",
    description: strings({ language: navigator.language }).editor.description,
    preview: true,
    documentationURL: "https://github.com/TorbenStriegel/eMS-Home-HomeAssistant",
  });
}

console.info(`%c EMS-HOME-CARD %c ${VERSION} `, "background:#0f766e;color:#fff;border-radius:3px 0 0 3px", "background:#134e4a;color:#a7f3d0;border-radius:0 3px 3px 0");
